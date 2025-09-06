"""
Step4統合処理モジュール
ページ数等判定・ページ分割の全工程を統合管理
"""

import os
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class Step4Processor:
    """Step4統合処理専用クラス"""
    
    def __init__(self, page_count_evaluator, page_splitter, prompts: Dict = None):
        """
        Args:
            page_count_evaluator: PageCountEvaluatorインスタンス
            page_splitter: PageSplitterインスタンス
            prompts (Dict): プロンプト設定
        """
        self.page_count_evaluator = page_count_evaluator
        self.page_splitter = page_splitter
        self.prompts = prompts or {}
        
        logger.debug("Step4Processor初期化完了")
    
    def is_ready(self) -> bool:
        """
        Step4コンポーネントが初期化済みかチェック
        
        Returns:
            bool: 全コンポーネントが初期化済みの場合True
        """
        return all([
            self.page_count_evaluator,
            self.page_splitter
        ])
    
    def _to_bool(self, value) -> bool:
        """文字列をboolに変換"""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes', 'on')
        return bool(value)
    
    def _to_int(self, value) -> Optional[int]:
        """値をintに変換"""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    
    def _to_float(self, value) -> Optional[float]:
        """値をfloatに変換"""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    async def _evaluate_single_page(self, page_data: Dict, session_dirs: Dict,
                                   page_idx: int, total_pages: int) -> Dict:
        """
        単一ページのページ数等判定
        
        Args:
            page_data (Dict): ページデータ
            session_dirs (Dict): セッションディレクトリ辞書
            page_idx (int): ページインデックス（1ベース）
            total_pages (int): 総ページ数
            
        Returns:
            Dict: ページ判定結果
        """
        page_number = page_data.get("page_number", page_idx)
        logger.info(f"Step4-01: ページ数等判定 (ページ{page_number})")
        
        try:
            # 処理対象画像を取得
            proc_images = page_data.get("processed_images") or [page_data.get("processed_image")]
            proc_images = [img for img in proc_images if img]  # None を除外
            
            if not proc_images:
                logger.warning(f"ページ{page_number}: 処理対象画像がありません")
                return {
                    "success": False,
                    "page_number": page_number,
                    "error": "処理対象画像がありません"
                }
            
            # 各画像に対してLLM判定を実行
            individual_results = []
            prompts = self.prompts.get("page_count_etc_judgment", {})
            
            for idx, img_path in enumerate(proc_images):
                # LLM評価を実行
                result = await self.page_count_evaluator.evaluate_page_count(img_path, prompts)
                individual_results.append(result)
                
                # 結果を保存
                if result.get("success"):
                    if len(proc_images) > 1:
                        output_file = os.path.join(
                            session_dirs["llm_judgments"],
                            f"page_{page_number:03d}_page_count_img{idx+1}.json"
                        )
                    else:
                        output_file = os.path.join(
                            session_dirs["llm_judgments"],
                            f"page_{page_number:03d}_page_count.json"
                        )
                    self.page_count_evaluator.save_result(result, output_file)
            
            # 複数画像の結果をマージ
            merged_result = self._merge_individual_results(individual_results, page_number)
            
            # ページデータに結果を記録
            if merged_result.get("success"):
                page_count = merged_result["merged_judgment"].get("page_count", 1)
                page_data["page_count"] = int(page_count)
                page_data["step4_page_count_result"] = merged_result
                
                logger.info(f"Step4-01: 完了!! (ページ{page_number}: page_count={page_count})")
            else:
                logger.warning(f"Step4-01: ページ{page_number}判定失敗")
                page_data["page_count"] = 1  # デフォルト値
            
            return merged_result
            
        except Exception as e:
            logger.error(f"ページ{page_number}判定エラー: {e}")
            return {
                "success": False,
                "page_number": page_number,
                "error": str(e)
            }
    
    def _merge_individual_results(self, individual_results: List[Dict], page_number: int) -> Dict:
        """
        個別画像の判定結果をマージ
        
        Args:
            individual_results (List[Dict]): 個別画像の判定結果リスト
            page_number (int): ページ番号
            
        Returns:
            Dict: マージされた判定結果
        """
        try:
            if not individual_results:
                return {"success": False, "error": "判定結果がありません"}
            
            # bool値のOR演算でマージ
            bool_or_fields = ["has_table_elements", "has_handwritten_notes_or_marks"]
            merged_bools = {}
            
            for key in bool_or_fields:
                acc = False
                for res in individual_results:
                    judgment = res.get("judgment", {}) if res.get("success") else {}
                    if key in judgment:
                        acc = acc or self._to_bool(judgment.get(key))
                merged_bools[key] = "True" if acc else "False"
            
            # page_countは加算し、最大3にクランプ
            merged_page_count = 0
            page_count_conf_list = []
            conf_list = []
            readability_comments = []
            overall_comments = []
            
            # readability_issuesの最悪値を取得
            order = {"none": 0, "minor": 1, "major": 2}
            rev_order = {v: k for k, v in order.items()}
            worst_val = -1
            
            for i, res in enumerate(individual_results, 1):
                if not res.get("success"):
                    continue
                    
                judgment = res.get("judgment", {})
                
                # page_count
                pc = self._to_int(judgment.get("page_count"))
                if pc is not None:
                    merged_page_count += pc
                
                # confidences
                pc_conf = self._to_float(judgment.get("page_count_confidence"))
                if pc_conf is not None:
                    page_count_conf_list.append(pc_conf)
                
                conf_v = self._to_float(judgment.get("confidence_score"))
                if conf_v is not None:
                    conf_list.append(conf_v)
                
                # comments
                rc = judgment.get("readability_comment")
                if rc:
                    readability_comments.append(f"img{i}: {rc}")
                
                oc = judgment.get("overall_comment")
                if oc:
                    overall_comments.append(f"img{i}: {oc}")
                
                # readability_issues
                ri = str(judgment.get("readability_issues", "")).lower()
                if ri in order:
                    worst_val = max(worst_val, order[ri])
            
            # page_countのクランプ
            if merged_page_count <= 0:
                merged_page_count = 1
            if merged_page_count > 3:
                merged_page_count = 3
            
            # 平均値の計算
            avg_pc_conf = sum(page_count_conf_list) / len(page_count_conf_list) if page_count_conf_list else None
            avg_conf = sum(conf_list) / len(conf_list) if conf_list else None
            
            # マージされた判定結果
            merged_judgment = {
                **merged_bools,
                "page_count": merged_page_count,
                "page_count_confidence": round(avg_pc_conf, 3) if avg_pc_conf is not None else None,
                "confidence_score": round(avg_conf, 3) if avg_conf is not None else None,
                "readability_issues": rev_order.get(worst_val, "none") if worst_val >= 0 else "none",
                "readability_comment": "\n".join(readability_comments) if readability_comments else None,
                "overall_comment": "\n".join(overall_comments) if overall_comments else None,
            }
            
            return {
                "success": True,
                "page_number": page_number,
                "merged_judgment": merged_judgment,
                "individual_results": individual_results
            }
            
        except Exception as e:
            logger.error(f"結果マージエラー (ページ{page_number}): {e}")
            return {
                "success": False,
                "page_number": page_number,
                "error": f"結果マージ失敗: {str(e)}"
            }
    
    async def process_pages(self, page_results: List[Dict], session_dirs: Dict) -> Dict:
        """
        Step4の全工程を実行（ページ数等判定・ページ分割）
        
        Args:
            page_results (List[Dict]): ページ結果リスト（Step3から）
            session_dirs (Dict): セッションディレクトリ辞書
            
        Returns:
            Dict: Step4処理結果
        """
        if not self.is_ready():
            logger.warning("Step4コンポーネントが初期化されていません。Step4処理をスキップします。")
            return {
                "success": False,
                "error": "Step4コンポーネント初期化失敗",
                "page_results": []
            }
        
        if not page_results:
            return {
                "success": True,
                "page_results": [],
                "message": "処理対象ページがありません"
            }
        
        try:
            logger.info("--- Step4: ページ数等判定・ページ分割 開始 ---")
            logger.info(f"Step4処理開始: {len(page_results)}ページ対象 (非同期並列処理)")
            
            # Step4-1: ページ数等判定（並列処理）
            import asyncio
            
            # ページ数等判定タスクを作成
            tasks = []
            valid_pages = []
            for i, page_data in enumerate(page_results, 1):
                if page_data.get("skip_processing"):
                    logger.debug(f"ページ{page_data.get('page_number')}: スキップ")
                    continue
                
                task = self._evaluate_single_page(page_data, session_dirs, i, len(page_results))
                tasks.append(task)
                valid_pages.append(page_data)
            
            # 全ページを並列処理
            if tasks:
                evaluation_results = await asyncio.gather(*tasks, return_exceptions=True)
            else:
                evaluation_results = []
            
            # エラーハンドリング
            processed_evaluation_results = []
            for i, result in enumerate(evaluation_results):
                if isinstance(result, Exception):
                    logger.error(f"ページ{i+1}評価でエラー: {result}")
                    processed_evaluation_results.append({
                        "success": False,
                        "error": str(result),
                        "page_number": valid_pages[i].get("page_number", i+1)
                    })
                else:
                    processed_evaluation_results.append(result)
            
            # Step4-2: ページ分割処理
            split_result = self.page_splitter.process_pages(page_results, session_dirs["dewarped"])
            
            # 処理結果の要約
            summary = self._generate_summary(processed_evaluation_results, split_result)
            
            total_successful = len([r for r in processed_evaluation_results if r.get("success")])
            split_count = split_result.get("split_count", 0)
            
            logger.info(f"--- Step4: 完了!! 判定={total_successful}ページ, 分割={split_count}ページ ---")
            
            return {
                "success": True,
                "total_pages": len(page_results),
                "evaluation_results": processed_evaluation_results,
                "split_result": split_result,
                "page_results": page_results,
                "summary": summary
            }
            
        except Exception as e:
            logger.error(f"Step4処理エラー: {e}")
            return {
                "success": False,
                "error": str(e),
                "page_results": []
            }
    
    def _generate_summary(self, evaluation_results: List[Dict], split_result: Dict) -> Dict:
        """
        Step4処理の要約情報を生成
        
        Args:
            evaluation_results (List[Dict]): ページ数等判定結果リスト
            split_result (Dict): ページ分割結果
            
        Returns:
            Dict: 要約情報
        """
        if not evaluation_results:
            return {}
        
        successful_evaluations = [r for r in evaluation_results if r.get("success")]
        
        # ページ数分布を集計
        page_count_distribution = {}
        for result in successful_evaluations:
            merged_judgment = result.get("merged_judgment", {})
            page_count = merged_judgment.get("page_count", 1)
            page_count_distribution[page_count] = page_count_distribution.get(page_count, 0) + 1
        
        # 表・手書き要素の統計
        has_table_count = sum(1 for result in successful_evaluations 
                             if result.get("merged_judgment", {}).get("has_table_elements") == "True")
        has_handwritten_count = sum(1 for result in successful_evaluations 
                                   if result.get("merged_judgment", {}).get("has_handwritten_notes_or_marks") == "True")
        
        return {
            "total_evaluations": len(evaluation_results),
            "successful_evaluations": len(successful_evaluations),
            "evaluation_success_rate": len(successful_evaluations) / len(evaluation_results) if evaluation_results else 0.0,
            "page_count_distribution": page_count_distribution,
            "has_table_elements": has_table_count,
            "has_handwritten_notes": has_handwritten_count,
            "split_summary": {
                "total_pages": split_result.get("total_pages", 0),
                "split_count": split_result.get("split_count", 0),
                "split_rate": split_result.get("split_count", 0) / split_result.get("total_pages", 1) if split_result.get("total_pages") else 0.0
            }
        }
    
    def get_processing_stats(self) -> Dict:
        """
        処理統計情報を取得
        
        Returns:
            Dict: 統計情報
        """
        return {
            "components": {
                "page_count_evaluator": type(self.page_count_evaluator).__name__ if self.page_count_evaluator else None,
                "page_splitter": type(self.page_splitter).__name__ if self.page_splitter else None
            },
            "ready": self.is_ready()
        }
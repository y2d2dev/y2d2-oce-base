"""
Step2統合処理モジュール
LLM判定・再画像化・歪み補正の全工程を統合管理
"""

import os
import logging
import asyncio
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class Step2Processor:
    """Step2統合処理専用クラス"""
    
    def __init__(self, llm_judgment, image_reprocessor, dewarping_engine, prompts: Dict):
        """
        Args:
            llm_judgment: LLMJudgmentインスタンス
            image_reprocessor: ImageReprocessorインスタンス
            dewarping_engine: DewarpingEngineインスタンス
            prompts (Dict): プロンプト設定
        """
        self.llm_judgment = llm_judgment
        self.image_reprocessor = image_reprocessor
        self.dewarping_engine = dewarping_engine
        self.prompts = prompts
        
        logger.debug("Step2Processor初期化完了")
    
    def is_ready(self) -> bool:
        """
        Step2コンポーネントが初期化済みかチェック
        
        Returns:
            bool: 全コンポーネントが初期化済みの場合True
        """
        return all([
            self.llm_judgment,
            self.image_reprocessor,
            self.dewarping_engine
        ])
    
    async def process_pages(self, pdf_result: Dict, pdf_path: str, session_dirs: Dict) -> Dict:
        """
        Step2の全工程を実行（非同期並列処理）
        
        Args:
            pdf_result (Dict): Step1のPDF変換結果
            pdf_path (str): 元PDFファイルパス
            session_dirs (Dict): セッションディレクトリ辞書
            
        Returns:
            Dict: Step2処理結果
        """
        # 初期化チェック
        if not self.is_ready():
            logger.warning("Step2コンポーネントが初期化されていません。Step2処理をスキップします。")
            return {
                "success": False,
                "error": "Step2コンポーネント初期化失敗",
                "page_results": []
            }
        
        try:
            # PDF変換されたページ情報を取得
            pages = [p for p in pdf_result.get("pages", []) if p.get("success")]
            if not pages:
                return {"success": False, "error": "変換成功ページがありません"}
            
            logger.info(f"Step2処理開始: {len(pages)}ページ対象 (非同期並列処理)")
            
            # 並列処理用のタスクリストを作成
            tasks = []
            valid_pages = []
            
            for page_info in pages:
                page_number = page_info.get("page_number")
                image_path = page_info.get("image_file")
                
                if not image_path or not os.path.exists(image_path):
                    logger.warning(f"ページ{page_number}: 画像ファイルが見つかりません")
                    continue
                
                # 非同期タスクを作成
                task = self._process_single_page(
                    image_path, page_number, pdf_path, pdf_result, session_dirs
                )
                tasks.append(task)
                valid_pages.append(page_info)
            
            # 全ページを並列処理
            page_results = []
            successful_count = 0
            
            if tasks:
                raw_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # 例外処理とカウント
                for i, result in enumerate(raw_results):
                    if isinstance(result, Exception):
                        page_number = valid_pages[i].get("page_number")
                        logger.error(f"ページ{page_number}処理エラー: {result}")
                        error_result = {
                            "page_number": page_number,
                            "success": False,
                            "error": str(result)
                        }
                        page_results.append(error_result)
                    else:
                        page_results.append(result)
                        if result.get("success"):
                            successful_count += 1
                
                # ページ番号順にソート
                page_results.sort(key=lambda x: x.get("page_number", 0))
                
                # 完了したページのログを順序通りに出力
                for result in page_results:
                    if result.get("success"):
                        page_num = result.get("page_number")
                        logger.info(f"ページ{page_num}: Step2処理完了")
            
            # 処理結果の要約
            summary = self._generate_summary(page_results)
            
            return {
                "success": True,
                "total_pages": len(pages),
                "processed_pages": len(page_results),
                "successful_pages": successful_count,
                "page_results": page_results,
                "summary": summary
            }
            
        except Exception as e:
            logger.error(f"Step2処理エラー: {e}")
            return {
                "success": False,
                "error": str(e),
                "page_results": []
            }
    
    async def _process_single_page(self, image_path: str, page_number: int, pdf_path: str, 
                                  pdf_result: Dict, session_dirs: Dict) -> Dict:
        """
        単一ページのStep2処理
        
        Args:
            image_path (str): 処理対象画像パス
            page_number (int): ページ番号
            pdf_path (str): 元PDFファイルパス
            pdf_result (Dict): PDF変換結果
            session_dirs (Dict): セッションディレクトリ辞書
            
        Returns:
            Dict: ページ処理結果
        """
        logger.info(f"Step2-01: LLM歪み判定 (ページ{page_number})")
        
        try:
            result = {
                "page_number": page_number,
                "success": True,
                "original_image": image_path,
                "processed_image": image_path,
                "processed_images": [image_path]
            }
            
            # Step2-01: LLM歪み判定
            judgment_prompts = self.prompts.get('dewarping_judgment', {})
            llm_result = await self.llm_judgment.evaluate_dewarping_need(image_path, judgment_prompts)
            result["llm_result"] = llm_result
            
            if not llm_result.get("success"):
                logger.warning(f"ページ{page_number}: LLM判定失敗 - {llm_result.get('error')}")
                result["success"] = False
                result["error"] = f"LLM判定失敗: {llm_result.get('error')}"
                return result
            
            judgment = llm_result.get("judgment", {})
            result["needs_dewarping"] = judgment.get("needs_dewarping", False)
            result["readability_issues"] = judgment.get("readability_issues", "none")
            result["has_out_of_document"] = judgment.get("has_something_out_of_document", False)
            
            logger.info(f"Step2-01: 完了!!")
            
            # Step2-02: 再画像化処理（readability_issues="major"の場合）
            if self.image_reprocessor.should_reprocess(llm_result):
                logger.info(f"Step2-02: 再画像化処理 (ページ{page_number})")
                
                # 元ページ情報を取得
                pages_info = {p.get("page_number"): p for p in pdf_result.get("pages", [])}
                original_page_info = pages_info.get(page_number, {})
                
                # 再画像化実行
                reprocess_result = self.image_reprocessor.reprocess_page(
                    pdf_path, page_number, original_page_info, session_dirs.get("converted_images", "")
                )
                
                result["reprocess_result"] = reprocess_result
                
                if reprocess_result.get("success"):
                    result["reprocessed_at_scale"] = True
                    result["processed_image"] = reprocess_result["reprocessed_image_path"]
                    result["processed_images"] = [reprocess_result["reprocessed_image_path"]]
                    logger.info(f"Step2-02: 完了!!")
                else:
                    result["reprocessed_at_scale"] = False
                    logger.warning(f"ページ{page_number}: 再画像化失敗")
            else:
                result["reprocessed_at_scale"] = False
                logger.debug(f"ページ{page_number}: 再画像化不要")
            
            # Step2-03: 歪み補正処理（needs_dewarping=trueの場合）
            if result["needs_dewarping"]:
                logger.info(f"Step2-03: 歪み補正処理 (ページ{page_number})")
                
                # 現在の処理済み画像を取得
                current_image = result["processed_image"]
                
                # 出力パス生成
                base_name = os.path.splitext(os.path.basename(current_image))[0]
                output_filename = f"{base_name}_dewarped.jpg"
                output_path = os.path.join(session_dirs.get("dewarped", ""), output_filename)
                
                # 歪み補正実行
                dewarp_result = self.dewarping_engine.process_image(current_image, output_path)
                result["dewarping_result"] = dewarp_result
                
                if dewarp_result.get("success"):
                    result["dewarping_applied"] = True
                    if not dewarp_result.get("skipped"):
                        result["processed_image"] = output_path
                        result["processed_images"] = dewarp_result["output_paths"]
                    logger.info(f"Step2-03: 完了!!")
                else:
                    result["dewarping_applied"] = False
                    logger.warning(f"ページ{page_number}: 歪み補正失敗")
            else:
                result["dewarping_applied"] = False
                logger.debug(f"ページ{page_number}: 歪み補正不要")
            
            return result
            
        except Exception as e:
            logger.error(f"Step2処理エラー (ページ{page_number}): {e}")
            return {
                "page_number": page_number,
                "success": False,
                "error": str(e)
            }
    
    def _generate_summary(self, page_results: List) -> Dict:
        """
        Step2処理の要約情報を生成
        
        Args:
            page_results (List): ページ処理結果リスト
            
        Returns:
            Dict: 要約情報
        """
        if not page_results:
            return {}
        
        # 統計情報の集計
        total_pages = len(page_results)
        successful_pages = len([r for r in page_results if r.get("success")])
        
        needs_dewarping_count = len([r for r in page_results if r.get("needs_dewarping")])
        reprocessed_count = len([r for r in page_results if r.get("reprocessed_at_scale")])
        dewarped_count = len([r for r in page_results if r.get("dewarping_applied")])
        
        readability_issues = {}
        for result in page_results:
            level = result.get("readability_issues", "unknown")
            readability_issues[level] = readability_issues.get(level, 0) + 1
        
        return {
            "total_pages": total_pages,
            "successful_pages": successful_pages,
            "success_rate": successful_pages / total_pages if total_pages > 0 else 0.0,
            "needs_dewarping_count": needs_dewarping_count,
            "reprocessed_count": reprocessed_count,
            "dewarped_count": dewarped_count,
            "readability_distribution": readability_issues
        }
    
    def get_processing_stats(self) -> Dict:
        """
        処理統計情報を取得
        
        Returns:
            Dict: 統計情報
        """
        return {
            "components": {
                "llm_judgment": type(self.llm_judgment).__name__ if self.llm_judgment else None,
                "image_reprocessor": type(self.image_reprocessor).__name__ if self.image_reprocessor else None,
                "dewarping_engine": type(self.dewarping_engine).__name__ if self.dewarping_engine else None
            },
            "ready": self.is_ready(),
            "prompts_loaded": bool(self.prompts.get('dewarping_judgment'))
        }
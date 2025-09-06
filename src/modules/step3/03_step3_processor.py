"""
Step3統合処理モジュール
回転判定・補正の全工程を統合管理
"""

import os
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class Step3Processor:
    """Step3統合処理専用クラス"""
    
    def __init__(self, orientation_detector, image_rotator):
        """
        Args:
            orientation_detector: OrientationDetectorインスタンス
            image_rotator: ImageRotatorインスタンス
        """
        self.orientation_detector = orientation_detector
        self.image_rotator = image_rotator
        
        logger.debug("Step3Processor初期化完了")
    
    def is_ready(self) -> bool:
        """
        Step3コンポーネントが初期化済みかチェック
        
        Returns:
            bool: 全コンポーネントが初期化済みの場合True
        """
        return all([
            self.orientation_detector,
            self.image_rotator
        ])
    
    async def process_pages(self, page_judgments: List[Dict], session_dirs: Dict[str, str]) -> Dict:
        """
        Step3の全工程を実行（回転判定・補正）
        
        Args:
            page_judgments (List[Dict]): ページ判定結果リスト（Step2から）
            session_dirs (Dict[str, str]): セッションディレクトリ辞書
            
        Returns:
            Dict: Step3処理結果
        """
        if not self.is_ready():
            logger.warning("Step3コンポーネントが初期化されていません。Step3処理をスキップします。")
            return {
                "success": False,
                "error": "Step3コンポーネント初期化失敗",
                "page_results": []
            }
        
        if not page_judgments:
            return {
                "success": True,
                "page_results": [],
                "message": "処理対象ページがありません"
            }
        
        try:
            # デバッグ保存先の設定
            self._setup_debug_dir(session_dirs)
            
            logger.info("--- Step3: 回転判定・補正 開始 ---")
            logger.info(f"Step3処理開始: {len(page_judgments)}ページ対象 (非同期並列処理)")
            
            # 非同期並列処理でページを処理
            import asyncio
            
            # 処理対象ページのタスクを作成
            tasks = []
            valid_pages = []
            for i, page_data in enumerate(page_judgments, 1):
                if page_data.get("skip_processing"):
                    logger.debug(f"ページ{page_data.get('page_number')}: スキップ")
                    continue
                
                task = self._process_single_page(page_data, i, len(page_judgments))
                tasks.append(task)
                valid_pages.append(page_data)
            
            # 全ページを並列処理
            if tasks:
                page_results = await asyncio.gather(*tasks, return_exceptions=True)
            else:
                page_results = []
            
            # エラーハンドリングと統計計算
            total_processed = 0
            total_rotated = 0
            processed_results = []
            
            for i, result in enumerate(page_results):
                if isinstance(result, Exception):
                    logger.error(f"ページ{i+1}処理でエラー: {result}")
                    processed_results.append({
                        "success": False,
                        "error": str(result),
                        "page_number": valid_pages[i].get("page_number", i+1)
                    })
                else:
                    processed_results.append(result)
                    if result.get("success"):
                        total_processed += 1
                        if result.get("rotated_count", 0) > 0:
                            total_rotated += result["rotated_count"]
            
            page_results = processed_results
            
            # 処理結果の要約
            summary = self._generate_summary(page_results)
            
            logger.info(f"--- Step3: 完了!! 処理={total_processed}ページ, 回転={total_rotated}画像 ---")
            
            return {
                "success": True,
                "total_pages": len(page_judgments),
                "processed_pages": total_processed,
                "rotated_images": total_rotated,
                "page_results": page_results,
                "summary": summary
            }
            
        except Exception as e:
            logger.error(f"Step3処理エラー: {e}")
            return {
                "success": False,
                "error": str(e),
                "page_results": []
            }
    
    def _setup_debug_dir(self, session_dirs: Dict[str, str]):
        """
        デバッグ保存先を設定
        
        Args:
            session_dirs (Dict[str, str]): セッションディレクトリ辞書
        """
        try:
            root_debug_dir = session_dirs.get("llm_judgments", session_dirs.get("converted_images", ""))
            if root_debug_dir:
                os.makedirs(root_debug_dir, exist_ok=True)
                self.orientation_detector.debug_save_dir = root_debug_dir
                logger.debug(f"デバッグ保存先設定: {root_debug_dir}")
        except Exception as e:
            logger.warning(f"デバッグディレクトリ設定エラー: {e}")
    
    async def _process_single_page(self, page_data: Dict, page_idx: int, total_pages: int) -> Dict:
        """
        単一ページのStep3処理
        
        Args:
            page_data (Dict): ページデータ
            page_idx (int): ページインデックス（1ベース）
            total_pages (int): 総ページ数
            
        Returns:
            Dict: ページ処理結果
        """
        page_number = page_data.get("page_number", page_idx)
        logger.info(f"Step3-01: 回転判定 (ページ{page_number})")
        
        result = {
            "page_number": page_number,
            "success": True,
            "rotated_count": 0,
            "image_results": []
        }
        
        try:
            # 処理対象画像を取得
            proc_images = page_data.get("processed_images") or [page_data.get("processed_image")]
            proc_images = [img for img in proc_images if img]  # None を除外
            
            if not proc_images:
                logger.warning(f"ページ{page_number}: 処理対象画像がありません")
                result["success"] = False
                result["error"] = "処理対象画像がありません"
                return result
            
            # 各画像に対して回転判定・補正を実行（非同期）
            new_paths = []
            
            for img_idx, img_path in enumerate(proc_images):
                img_result = await self._process_single_image(
                    img_path, page_number, img_idx + 1, len(proc_images)
                )
                
                result["image_results"].append(img_result)
                
                if img_result.get("success"):
                    new_paths.append(img_result.get("output_path", img_path))
                    if img_result.get("rotated"):
                        result["rotated_count"] += 1
                else:
                    new_paths.append(img_path)  # エラー時は元画像を保持
            
            # ページデータを更新
            page_data["processed_images"] = new_paths
            page_data["processed_image"] = new_paths[0]
            
            # Step3の処理結果を記録
            page_data["step3_result"] = {
                "processed": True,
                "rotated_count": result["rotated_count"],
                "image_results": result["image_results"]
            }
            
            if result["rotated_count"] > 0:
                logger.info(f"Step3-01: 完了!! (ページ{page_number}: {result['rotated_count']}画像を回転)")
            else:
                logger.info(f"Step3-01: 完了!! (ページ{page_number}: 回転不要)")
            
            return result
            
        except Exception as e:
            logger.error(f"ページ{page_number}処理エラー: {e}")
            result["success"] = False
            result["error"] = str(e)
            return result
    
    async def _process_single_image(self, img_path: str, page_number: int, 
                             img_idx: int, total_images: int) -> Dict:
        """
        単一画像の回転判定・補正処理
        
        Args:
            img_path (str): 画像パス
            page_number (int): ページ番号
            img_idx (int): 画像インデックス（1ベース）
            total_images (int): 総画像数
            
        Returns:
            Dict: 画像処理結果
        """
        try:
            # ログ出力（複数画像の場合のみインデックスを表示）
            if total_images > 1:
                logger.debug(f"  ページ{page_number} 画像{img_idx}/{total_images}: 回転判定中")
            
            # 回転角度を検出（非同期）
            detection_result = await self.orientation_detector.detect(
                img_path, 
                add_star=True,
                temp_dir=None,
                use_llm=True
            )
            
            if not detection_result.success:
                logger.warning(f"  ページ{page_number} 画像{img_idx}: 回転検出失敗 - {detection_result.error}")
                return {
                    "success": False,
                    "error": detection_result.error,
                    "input_path": img_path,
                    "output_path": img_path
                }
            
            angle = detection_result.angle
            
            # 回転が必要ない場合
            if angle == 0:
                logger.info(f"  ↪️ ページ{page_number} 画像{img_idx}: 回転不要")
                return {
                    "success": True,
                    "rotated": False,
                    "angle": 0,
                    "input_path": img_path,
                    "output_path": img_path,
                    "detection_confidence": detection_result.confidence
                }
            
            # 画像を回転
            rotation_result = self.image_rotator.rotate_image(img_path, angle)
            
            if rotation_result.get("success"):
                output_path = rotation_result.get("output_path")
                logger.info(f"  ↪️ ページ{page_number} 画像{img_idx}: {angle}度回転 → {os.path.basename(output_path)}")
                
                return {
                    "success": True,
                    "rotated": True,
                    "angle": angle,
                    "input_path": img_path,
                    "output_path": output_path,
                    "detection_confidence": detection_result.confidence
                }
            else:
                logger.warning(f"  ↪️ ページ{page_number} 画像{img_idx}: 回転処理失敗")
                return {
                    "success": False,
                    "error": rotation_result.get("error"),
                    "input_path": img_path,
                    "output_path": img_path
                }
                
        except Exception as e:
            logger.error(f"  ↪️ ページ{page_number} 画像{img_idx}: 回転処理エラー {e}")
            return {
                "success": False,
                "error": str(e),
                "input_path": img_path,
                "output_path": img_path
            }
    
    def _generate_summary(self, page_results: List[Dict]) -> Dict:
        """
        Step3処理の要約情報を生成
        
        Args:
            page_results (List[Dict]): ページ処理結果リスト
            
        Returns:
            Dict: 要約情報
        """
        if not page_results:
            return {}
        
        total_pages = len(page_results)
        successful_pages = len([r for r in page_results if r.get("success")])
        total_images = sum(len(r.get("image_results", [])) for r in page_results)
        rotated_images = sum(r.get("rotated_count", 0) for r in page_results)
        
        # 角度分布を集計
        angle_distribution = {}
        for page_result in page_results:
            for img_result in page_result.get("image_results", []):
                if img_result.get("success"):
                    angle = img_result.get("angle", 0)
                    angle_distribution[angle] = angle_distribution.get(angle, 0) + 1
        
        return {
            "total_pages": total_pages,
            "successful_pages": successful_pages,
            "success_rate": successful_pages / total_pages if total_pages > 0 else 0.0,
            "total_images": total_images,
            "rotated_images": rotated_images,
            "rotation_rate": rotated_images / total_images if total_images > 0 else 0.0,
            "angle_distribution": angle_distribution
        }
    
    def get_processing_stats(self) -> Dict:
        """
        処理統計情報を取得
        
        Returns:
            Dict: 統計情報
        """
        return {
            "components": {
                "orientation_detector": type(self.orientation_detector).__name__ if self.orientation_detector else None,
                "image_rotator": type(self.image_rotator).__name__ if self.image_rotator else None
            },
            "ready": self.is_ready()
        }
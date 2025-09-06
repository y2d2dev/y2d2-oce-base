"""
Step5-03: Step5統合プロセッサー
OCR用画像分割の統合処理
"""

import os
import asyncio
from typing import Dict, List, Optional
import logging

import importlib

# importlibを使って数字プレフィックス付きモジュールを読み込み
_image_splitter_module = importlib.import_module('src.modules.step5.01_image_splitter')
_image_processor_module = importlib.import_module('src.modules.step5.02_image_processor')

ImageSplitter = _image_splitter_module.ImageSplitter
ImageProcessor = _image_processor_module.ImageProcessor

logger = logging.getLogger(__name__)

class Step5Processor:
    """Step5統合プロセッサー"""
    
    def __init__(self, config: Dict):
        """
        Args:
            config: Step5設定
        """
        self.config = config
        split_config = config.get('split_image_for_ocr', {})
        
        # コンポーネント初期化
        self.image_splitter = ImageSplitter(split_config)
        self.image_processor = ImageProcessor()
        
        logger.debug("Step5プロセッサー初期化完了")
    
    def split_single_page_images(self, page_data: Dict, session_dirs: Dict, 
                                page_index: int, total_pages: int) -> Dict:
        """
        単一ページの全画像を分割
        
        Args:
            page_data: ページデータ
            session_dirs: セッションディレクトリ情報
            page_index: ページインデックス（1から開始）
            total_pages: 総ページ数
            
        Returns:
            Dict: 分割結果
        """
        page_number = page_data["page_number"]
        logger.info(f"Step5-01: 画像分割 ({page_index}/{total_pages}) ページ{page_number}")
        
        processed_images = page_data.get("processed_images", [])
        if not processed_images:
            logger.warning(f"ページ{page_number}: 処理対象画像がありません")
            return {
                "page_number": page_number,
                "split_results": [],
                "success": False
            }
        
        split_results = []
        
        # 各処理済み画像を分割
        for img_idx, proc_image_path in enumerate(processed_images):
            if len(processed_images) > 1:
                logger.debug(f"  📄 歪み補正画像 {img_idx + 1}/{len(processed_images)} を分割処理")
            
            # 出力ディレクトリとファイル名を設定
            base_name = f"page_{page_number:03d}_mask{img_idx + 1}"
            split_output_dir = os.path.join(session_dirs["split_images"], base_name)
            
            # 画像分割実行
            split_result = self.image_splitter.split_and_save(
                proc_image_path, split_output_dir, base_name
            )
            
            # メタデータ追加
            split_result["source_dewarped_image"] = proc_image_path
            split_result["source_mask_index"] = img_idx
            split_results.append(split_result)
        
        # 結果を整理
        page_result = self.image_processor.process_page_splits(page_data, split_results)
        
        logger.info(f"Step5-01: 完了!! (ページ{page_number}: {page_result['total_split_count']}個分割)")
        
        return {
            "page_number": page_number,
            "split_results": split_results,
            "processed_result": page_result,
            "success": True
        }
    
    async def process_pages(self, page_results: List[Dict], session_dirs: Dict) -> Dict:
        """
        全ページの画像分割処理（並列実行）
        
        Args:
            page_results: Step4からのページ結果
            session_dirs: セッションディレクトリ情報
            
        Returns:
            Dict: Step5処理結果
        """
        logger.info("--- Step5: OCR用画像分割 開始 ---")
        logger.info(f"Step5処理開始: {len(page_results)}ページ対象 (並列処理)")
        
        # 並列処理で各ページを分割
        tasks = [
            asyncio.to_thread(
                self.split_single_page_images,
                page_data, session_dirs, i, len(page_results)
            )
            for i, page_data in enumerate(page_results, 1)
        ]
        
        split_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 結果の整理
        successful_results = []
        failed_results = []
        
        for i, result in enumerate(split_results):
            if isinstance(result, Exception):
                logger.error(f"ページ{i+1}: 分割処理でエラー - {result}")
                failed_results.append({
                    "page_number": page_results[i]["page_number"],
                    "error": str(result)
                })
            elif result.get("success"):
                successful_results.append(result["processed_result"])
            else:
                failed_results.append(result)
        
        # OCRグループ作成
        ocr_groups = self.image_processor.create_ocr_groups(successful_results)
        processing_summary = self.image_processor.get_processing_summary(successful_results)
        
        logger.info(f"Step5-02: 分割結果整理完了")
        
        # 統計情報
        total_split_images = processing_summary["total_split_images"]
        successful_pages = len(successful_results)
        
        logger.info(f"--- Step5: 完了!! 処理={successful_pages}ページ, 分割={total_split_images}画像 ---")
        
        return {
            "success": successful_pages > 0,  # 1つでも成功したページがあれば成功
            "step5_results": {
                "split_results": successful_results,
                "failed_results": failed_results,
                "ocr_groups": ocr_groups,
                "processing_summary": processing_summary
            },
            "statistics": {
                "total_pages_processed": successful_pages,
                "total_pages_failed": len(failed_results),
                "total_split_images": total_split_images,
                "total_ocr_groups": ocr_groups["total_groups"]
            },
            # 次のステップ用データ
            "split_image_data": successful_results,
            "ocr_processing_groups": ocr_groups
        }
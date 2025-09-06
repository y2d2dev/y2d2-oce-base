"""
Step5-02: 画像処理・管理
分割結果の整理と画像情報管理
"""

import os
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class ImageProcessor:
    """画像処理・管理クラス"""
    
    def __init__(self):
        pass
    
    def process_page_splits(self, page_data: Dict, split_results: List[Dict]) -> Dict:
        """
        ページの分割結果を処理・整理
        
        Args:
            page_data: ページデータ
            split_results: 分割結果のリスト
            
        Returns:
            Dict: 整理された分割結果
        """
        page_number = page_data["page_number"]
        processed_images = page_data.get("processed_images", [])
        
        # 分割結果を整理
        organized_splits = []
        total_split_count = 0
        
        for source_idx, split_result in enumerate(split_results):
            if not split_result.get("success"):
                logger.warning(f"ページ{page_number} mask{source_idx+1}: 分割失敗")
                continue
            
            split_paths = split_result.get("split_paths", [])
            split_count = len(split_paths)
            total_split_count += split_count
            
            # 分割画像情報を作成
            for img_idx, split_path in enumerate(split_paths, 1):
                organized_splits.append({
                    "page_number": page_number,
                    "image_path": split_path,
                    "image_type": "split",
                    "source_mask_index": source_idx,
                    "source_dewarped_image": split_result.get("source_dewarped_image"),
                    "split_index": img_idx,
                    "split_total": split_count
                })
            
            # 元画像情報を追加（保存されている場合）
            original_path = split_result.get("original_path")
            if original_path:
                organized_splits.append({
                    "page_number": page_number,
                    "image_path": original_path,
                    "image_type": "original",
                    "source_mask_index": source_idx,
                    "source_dewarped_image": split_result.get("source_dewarped_image"),
                    "split_index": 0,  # 元画像は0番
                    "split_total": split_count
                })
        
        return {
            "page_number": page_number,
            "split_images": organized_splits,
            "total_split_count": total_split_count,
            "source_count": len([r for r in split_results if r.get("success")])
        }
    
    def create_ocr_groups(self, all_split_results: List[Dict]) -> Dict:
        """
        OCR処理用のグループ作成
        
        Args:
            all_split_results: 全ページの分割結果
            
        Returns:
            Dict: OCRグループ情報
        """
        # ページごと、ソース画像ごとにグループ化
        ocr_groups = {}
        total_images = 0
        
        for page_result in all_split_results:
            page_number = page_result["page_number"]
            split_images = page_result["split_images"]
            
            # ソース画像ごとにグループ化
            source_groups = {}
            for img_info in split_images:
                source_idx = img_info["source_mask_index"]
                group_key = f"page_{page_number:03d}_mask{source_idx+1}"
                
                if group_key not in source_groups:
                    source_groups[group_key] = {
                        "page_number": page_number,
                        "source_mask_index": source_idx,
                        "source_dewarped_image": img_info["source_dewarped_image"],
                        "images": []
                    }
                
                source_groups[group_key]["images"].append(img_info)
                total_images += 1
            
            ocr_groups.update(source_groups)
        
        return {
            "groups": ocr_groups,
            "total_groups": len(ocr_groups),
            "total_images": total_images
        }
    
    def get_image_paths_for_processing(self, ocr_groups: Dict, image_type: str = "all") -> List[str]:
        """
        処理対象画像パスを取得
        
        Args:
            ocr_groups: OCRグループ情報
            image_type: 取得する画像タイプ ("split", "original", "all")
            
        Returns:
            List[str]: 画像パスのリスト
        """
        image_paths = []
        
        for group_key, group_data in ocr_groups["groups"].items():
            for img_info in group_data["images"]:
                if image_type == "all" or img_info["image_type"] == image_type:
                    image_paths.append(img_info["image_path"])
        
        return sorted(image_paths)
    
    def get_processing_summary(self, all_split_results: List[Dict]) -> Dict:
        """
        処理サマリーを作成
        
        Args:
            all_split_results: 全ページの分割結果
            
        Returns:
            Dict: 処理サマリー
        """
        total_pages = len(all_split_results)
        total_splits = sum(r["total_split_count"] for r in all_split_results)
        total_sources = sum(r["source_count"] for r in all_split_results)
        
        # ページごとの詳細
        page_details = []
        for result in all_split_results:
            page_details.append({
                "page_number": result["page_number"],
                "split_count": result["total_split_count"],
                "source_count": result["source_count"]
            })
        
        return {
            "total_pages": total_pages,
            "total_split_images": total_splits,
            "total_source_images": total_sources,
            "page_details": page_details,
            "average_splits_per_page": total_splits / total_pages if total_pages > 0 else 0
        }
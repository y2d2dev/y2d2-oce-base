"""
Step5-01: 画像分割エンジン
OCR用に画像を5等分に分割（オーバーラップあり）
"""

import os
import cv2
import numpy as np
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class ImageSplitter:
    """画像分割処理クラス"""
    
    def __init__(self, config: Dict):
        """
        Args:
            config: 分割設定
                - num_splits: 分割数（デフォルト5）
                - overlap_ratio: オーバーラップ比率（デフォルト0.1）
                - min_height_per_split: 分割あたりの最小高さ（デフォルト100）
                - save_original: 元画像も保存するか（デフォルトTrue）
        """
        self.num_splits = config.get('num_splits', 5)
        self.overlap_ratio = config.get('overlap_ratio', 0.1)
        self.min_height_per_split = config.get('min_height_per_split', 100)
        self.save_original = config.get('save_original', True)
        
    def calculate_split_regions(self, image_height: int) -> List[Tuple[int, int]]:
        """
        分割領域を計算
        
        Args:
            image_height: 画像の高さ
            
        Returns:
            List[Tuple[int, int]]: [(start_y, end_y), ...] の形式
        """
        # 基本分割高さを計算
        base_height = image_height // self.num_splits
        
        # 最小高さチェック
        if base_height < self.min_height_per_split:
            logger.warning(f"分割高さ{base_height}が最小高さ{self.min_height_per_split}未満")
            # 最小高さに基づいて分割数を調整
            adjusted_splits = max(1, image_height // self.min_height_per_split)
            base_height = image_height // adjusted_splits
            actual_splits = adjusted_splits
            logger.info(f"分割数を{self.num_splits}から{actual_splits}に調整")
        else:
            actual_splits = self.num_splits
        
        # オーバーラップピクセル数を計算
        overlap_pixels = int(base_height * self.overlap_ratio)
        
        regions = []
        for i in range(actual_splits):
            start_y = max(0, i * base_height - overlap_pixels)
            
            if i == actual_splits - 1:  # 最後の分割
                end_y = image_height
            else:
                end_y = min(image_height, (i + 1) * base_height + overlap_pixels)
            
            regions.append((start_y, end_y))
            
        return regions
    
    def split_image(self, image: np.ndarray) -> List[np.ndarray]:
        """
        画像を分割
        
        Args:
            image: OpenCV画像（np.ndarray）
            
        Returns:
            List[np.ndarray]: 分割された画像のリスト
        """
        height, width = image.shape[:2]
        regions = self.calculate_split_regions(height)
        
        split_images = []
        for start_y, end_y in regions:
            split_img = image[start_y:end_y, :]
            split_images.append(split_img)
            
        return split_images
    
    def split_and_save(self, image_path: str, output_dir: str, base_name: str) -> Dict:
        """
        画像を分割して保存
        
        Args:
            image_path: 入力画像パス
            output_dir: 出力ディレクトリ
            base_name: ベース名（page_001など）
            
        Returns:
            Dict: 処理結果
                - success: bool
                - split_paths: List[str] (分割画像パス)
                - original_path: str (元画像パス、save_original=Trueの場合)
                - split_count: int
        """
        try:
            # 出力ディレクトリ作成
            os.makedirs(output_dir, exist_ok=True)
            
            # 画像読み込み
            image = cv2.imread(image_path)
            if image is None:
                raise ValueError(f"画像読み込み失敗: {image_path}")
            
            # 画像分割
            split_images = self.split_image(image)
            
            # 分割画像を保存
            split_paths = []
            for i, split_img in enumerate(split_images, 1):
                split_filename = f"{base_name}_split_{i:02d}.jpg"
                split_path = os.path.join(output_dir, split_filename)
                
                # JPEG品質95で保存
                cv2.imwrite(split_path, split_img, [cv2.IMWRITE_JPEG_QUALITY, 95])
                split_paths.append(split_path)
            
            result = {
                "success": True,
                "split_paths": split_paths,
                "split_count": len(split_paths)
            }
            
            # 元画像も保存する場合
            if self.save_original:
                original_filename = f"{base_name}_original.jpg"
                original_path = os.path.join(output_dir, original_filename)
                cv2.imwrite(original_path, image, [cv2.IMWRITE_JPEG_QUALITY, 95])
                result["original_path"] = original_path
            
            logger.debug(f"画像分割完了: {len(split_paths)}個の分割画像生成")
            return result
            
        except Exception as e:
            logger.error(f"画像分割エラー ({image_path}): {e}")
            return {
                "success": False,
                "error": str(e),
                "split_paths": [],
                "split_count": 0
            }
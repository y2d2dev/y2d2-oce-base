"""
ページ分割処理モジュール
page_count=2の場合の強制左右分割を行う
"""

import os
import logging
from typing import Dict, List, Tuple, Optional
import cv2

logger = logging.getLogger(__name__)


class PageSplitter:
    """ページ分割処理専用クラス"""
    
    def __init__(self, config: Dict):
        """
        Args:
            config (Dict): ページ分割設定
        """
        # split_image_for_ocrの設定を使用
        split_config = config.get('split_image_for_ocr', {})
        self.overlap_ratio = split_config.get('overlap_ratio', 0.1)
        self.min_height_per_split = split_config.get('min_height_per_split', 100)
        self.save_original = split_config.get('save_original', True)
        
        logger.debug(f"PageSplitter初期化: overlap_ratio={self.overlap_ratio}")
    
    def split_image_left_right_with_overlap(self, image, overlap_ratio: float, 
                                          output_dir: str, base_filename: str) -> Tuple[str, str]:
        """
        画像を左右に分割（オーバーラップ付き）
        
        Args:
            image: OpenCV画像オブジェクト
            overlap_ratio (float): オーバーラップ比率
            output_dir (str): 出力ディレクトリ
            base_filename (str): ベースファイル名
            
        Returns:
            Tuple[str, str]: (左画像パス, 右画像パス)
        """
        try:
            height, width = image.shape[:2]
            
            # オーバーラップ幅を計算
            overlap_width = int(width * overlap_ratio)
            
            # 左右の分割点を計算
            center_x = width // 2
            left_end = center_x + overlap_width // 2
            right_start = center_x - overlap_width // 2
            
            # 左画像: 0 から left_end まで
            left_image = image[:, :left_end]
            
            # 右画像: right_start から最後まで
            right_image = image[:, right_start:]
            
            # 出力パスを生成
            left_path = os.path.join(output_dir, f"{base_filename}_left.jpg")
            right_path = os.path.join(output_dir, f"{base_filename}_right.jpg")
            
            # 画像を保存
            cv2.imwrite(left_path, left_image)
            cv2.imwrite(right_path, right_image)
            
            logger.debug(f"左右分割完了: {base_filename} -> left:{left_image.shape}, right:{right_image.shape}")
            
            return left_path, right_path
            
        except Exception as e:
            logger.error(f"左右分割エラー: {e}")
            raise
    
    def should_split_page(self, page_data: Dict) -> bool:
        """
        ページが分割対象かどうかを判定
        
        Args:
            page_data (Dict): ページデータ
            
        Returns:
            bool: 分割対象の場合True
        """
        # page_count=2で、スキップ対象でなく、処理済み画像が1つの場合のみ分割
        return (
            page_data.get("page_count") == 2 and
            not page_data.get("skip_processing") and
            len(page_data.get("processed_images", [])) == 1
        )
    
    def split_page(self, page_data: Dict, output_dir: str) -> Dict:
        """
        単一ページの分割処理
        
        Args:
            page_data (Dict): ページデータ
            output_dir (str): 出力ディレクトリ
            
        Returns:
            Dict: 分割処理結果
        """
        page_number = page_data.get("page_number", 1)
        
        try:
            if not self.should_split_page(page_data):
                return {
                    "success": True,
                    "split": False,
                    "message": "分割対象外",
                    "page_number": page_number
                }
            
            # 分割対象画像を取得
            image_to_split = page_data["processed_images"][0]
            
            # 画像を読み込み
            image = cv2.imread(image_to_split)
            if image is None:
                raise IOError(f"画像読み込み失敗: {image_to_split}")
            
            # 分割用出力ディレクトリを作成
            forced_split_output_dir = os.path.join(output_dir, "forced_split")
            os.makedirs(forced_split_output_dir, exist_ok=True)
            
            # ベースファイル名を生成
            base_filename = f"page_{page_number:03d}_forced"
            
            # 左右分割を実行
            left_path, right_path = self.split_image_left_right_with_overlap(
                image=image,
                overlap_ratio=self.overlap_ratio,
                output_dir=forced_split_output_dir,
                base_filename=base_filename
            )
            
            # ページデータを更新
            page_data["processed_images"] = [left_path, right_path]
            page_data["processed_image"] = left_path
            
            logger.info(f"🔄 ページ{page_number}: 強制分割完了 ({os.path.basename(left_path)}, {os.path.basename(right_path)})")
            
            return {
                "success": True,
                "split": True,
                "page_number": page_number,
                "original_image": image_to_split,
                "split_images": [left_path, right_path],
                "output_dir": forced_split_output_dir
            }
            
        except Exception as e:
            logger.error(f"ページ{page_number}分割エラー: {e}")
            return {
                "success": False,
                "split": False,
                "page_number": page_number,
                "error": str(e)
            }
    
    def process_pages(self, page_judgments: List[Dict], output_dir: str) -> Dict:
        """
        全ページの分割処理
        
        Args:
            page_judgments (List[Dict]): ページ判定結果リスト
            output_dir (str): 出力ディレクトリ
            
        Returns:
            Dict: 分割処理結果
        """
        logger.info("Step4-02: ページ分割処理開始")
        
        try:
            results = []
            total_pages = len(page_judgments)
            split_count = 0
            
            for i, page_data in enumerate(page_judgments, 1):
                page_number = page_data.get("page_number", i)
                
                result = self.split_page(page_data, output_dir)
                results.append(result)
                
                if result.get("split"):
                    split_count += 1
                
                # 進捗ログ
                if result.get("success"):
                    if result.get("split"):
                        logger.debug(f"  ページ{page_number}: 分割完了")
                    else:
                        logger.debug(f"  ページ{page_number}: {result.get('message', '処理完了')}")
            
            logger.info(f"Step4-02: 完了!! (分割対象={split_count}ページ/{total_pages}ページ)")
            
            return {
                "success": True,
                "total_pages": total_pages,
                "split_count": split_count,
                "results": results
            }
            
        except Exception as e:
            logger.error(f"ページ分割処理エラー: {e}")
            return {
                "success": False,
                "error": str(e),
                "results": []
            }
    
    def get_processing_stats(self) -> Dict:
        """
        処理統計情報を取得
        
        Returns:
            Dict: 統計情報
        """
        return {
            "component": "PageSplitter",
            "overlap_ratio": self.overlap_ratio,
            "min_height_per_split": self.min_height_per_split,
            "save_original": self.save_original
        }
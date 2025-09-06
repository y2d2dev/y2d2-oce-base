"""
画像変換処理モジュール
PDFページから画像への変換処理を担当
"""

import os
import logging
from typing import Dict, Optional
import fitz  # PyMuPDF
from PIL import Image
import io

logger = logging.getLogger(__name__)


class ImageConverter:
    """画像変換専用クラス"""
    
    def __init__(self, config: Dict):
        """
        Args:
            config (Dict): PDF処理設定
        """
        self.image_format = config.get('image_format', 'JPEG')
        self.image_quality = config.get('image_quality', 95)
        
        logger.debug(f"ImageConverter初期化: format={self.image_format}, quality={self.image_quality}")
    
    def convert_page_to_image(self, page: fitz.Page, dpi: int, output_path: str) -> Dict:
        """
        PDFページを画像に変換
        
        Args:
            page (fitz.Page): PDFページオブジェクト
            dpi (int): DPI値
            output_path (str): 出力パス
            
        Returns:
            Dict: 変換結果
        """
        try:
            # DPIに基づいてズーム倍率を計算（72 DPIがベース）
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            
            # ページを画像として描画
            pix = page.get_pixmap(matrix=mat)
            
            # PILイメージに変換
            img_data = pix.tobytes("ppm")
            img = Image.open(io.BytesIO(img_data))
            
            # 出力ディレクトリを作成
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # 画像を保存
            img.save(output_path, self.image_format, quality=self.image_quality)
            
            # ページサイズ情報を取得
            page_rect = page.rect
            
            result = {
                "success": True,
                "output_path": output_path,
                "used_dpi": dpi,
                "zoom_factor": zoom,
                "original_size_pt": [page_rect.width, page_rect.height],
                "image_size_px": [img.width, img.height],
                "file_size_bytes": os.path.getsize(output_path) if os.path.exists(output_path) else 0
            }
            
            logger.debug(f"画像変換完了: {dpi}DPI, サイズ{img.width}x{img.height}px")
            
            return result
            
        except Exception as e:
            logger.error(f"画像変換エラー: {e}")
            return {
                "success": False,
                "error": str(e),
                "output_path": output_path
            }
    
    def convert_page_from_doc(self, doc: fitz.Document, page_num: int, dpi: int, output_path: str) -> Dict:
        """
        PDFドキュメントから指定されたページを画像に変換
        
        Args:
            doc (fitz.Document): PDFドキュメント
            page_num (int): ページ番号（0ベース）
            dpi (int): DPI値
            output_path (str): 出力パス
            
        Returns:
            Dict: 変換結果
        """
        try:
            if page_num < 0 or page_num >= doc.page_count:
                return {
                    "success": False,
                    "error": f"無効なページ番号: {page_num}",
                    "page_number": page_num + 1
                }
            
            page = doc.load_page(page_num)
            result = self.convert_page_to_image(page, dpi, output_path)
            result["page_number"] = page_num + 1  # 1ベースに変換
            
            return result
            
        except Exception as e:
            logger.error(f"ページ {page_num + 1} 変換エラー: {e}")
            return {
                "success": False,
                "page_number": page_num + 1,
                "error": str(e),
                "output_path": output_path
            }
    
    def batch_convert_pages(self, doc: fitz.Document, page_dpi_list: list, base_output_path: str) -> Dict:
        """
        複数ページの一括変換
        
        Args:
            doc (fitz.Document): PDFドキュメント
            page_dpi_list (list): [(page_num, dpi), ...] のリスト
            base_output_path (str): ベース出力パス
            
        Returns:
            Dict: 一括変換結果
        """
        results = []
        successful_count = 0
        
        for page_num, dpi in page_dpi_list:
            # 出力ファイルパスを生成
            base_name = os.path.splitext(base_output_path)[0]
            output_path = f"{base_name}_page_{page_num + 1:03d}.jpg"
            
            # ページを変換
            result = self.convert_page_from_doc(doc, page_num, dpi, output_path)
            results.append(result)
            
            if result.get("success"):
                successful_count += 1
        
        return {
            "success": successful_count > 0,
            "total_pages": len(page_dpi_list),
            "successful_pages": successful_count,
            "failed_pages": len(page_dpi_list) - successful_count,
            "results": results
        }
    
    def get_image_info(self, image_path: str) -> Dict:
        """
        画像ファイルの情報を取得
        
        Args:
            image_path (str): 画像ファイルパス
            
        Returns:
            Dict: 画像情報
        """
        try:
            if not os.path.exists(image_path):
                return {
                    "success": False,
                    "error": "画像ファイルが見つかりません",
                    "file_path": image_path
                }
            
            with Image.open(image_path) as img:
                return {
                    "success": True,
                    "file_path": image_path,
                    "format": img.format,
                    "mode": img.mode,
                    "size": img.size,
                    "file_size_bytes": os.path.getsize(image_path)
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "file_path": image_path
            }
    
    def validate_image_output(self, output_path: str, expected_min_size: tuple = (100, 100)) -> Dict:
        """
        出力画像の有効性を検証
        
        Args:
            output_path (str): 出力画像パス
            expected_min_size (tuple): 期待する最小サイズ (width, height)
            
        Returns:
            Dict: 検証結果
        """
        if not os.path.exists(output_path):
            return {
                "valid": False,
                "error": "出力ファイルが作成されていません",
                "file_path": output_path
            }
        
        try:
            info = self.get_image_info(output_path)
            if not info.get("success"):
                return {
                    "valid": False,
                    "error": f"画像情報取得失敗: {info.get('error')}",
                    "file_path": output_path
                }
            
            size = info["size"]
            min_width, min_height = expected_min_size
            
            if size[0] < min_width or size[1] < min_height:
                return {
                    "valid": False,
                    "error": f"画像サイズが小さすぎます: {size} < {expected_min_size}",
                    "file_path": output_path,
                    "actual_size": size
                }
            
            file_size = info["file_size_bytes"]
            if file_size < 1000:  # 1KB未満は異常
                return {
                    "valid": False,
                    "error": f"ファイルサイズが小さすぎます: {file_size} bytes",
                    "file_path": output_path
                }
            
            return {
                "valid": True,
                "file_path": output_path,
                "image_info": info
            }
            
        except Exception as e:
            return {
                "valid": False,
                "error": str(e),
                "file_path": output_path
            }
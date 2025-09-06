"""
再画像化処理モジュール
読みにくさが"major"の場合にPDFから高解像度で再変換
"""

import os
import logging
from typing import Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class ImageReprocessor:
    """再画像化処理専用クラス"""
    
    def __init__(self, pdf_processor, config: Dict):
        """
        Args:
            pdf_processor: PDFProcessorインスタンス（Step1から）
            config (Dict): 設定
        """
        self.pdf_processor = pdf_processor
        self.config = config.get('pdf_processing', {})
        self.default_scale_factor = 2.0  # デフォルト2倍DPI
        
        logger.debug("ImageReprocessor初期化完了")
    
    def _calculate_scaled_dpi(self, original_dpi: int, scale_factor: float) -> int:
        """
        スケールファクターに基づいて新しいDPIを計算
        
        Args:
            original_dpi (int): 元のDPI
            scale_factor (float): スケールファクター
            
        Returns:
            int: 新しいDPI値
        """
        new_dpi = int(original_dpi * scale_factor)
        
        # DPI範囲制限
        max_dpi = self.config.get('max_dpi', 600)
        min_dpi = self.config.get('min_dpi', 50)
        
        new_dpi = max(min_dpi, min(new_dpi, max_dpi))
        
        return new_dpi
    
    def should_reprocess(self, judgment_result: Dict) -> bool:
        """
        再画像化が必要かどうかを判定
        
        Args:
            judgment_result (Dict): LLM判定結果
            
        Returns:
            bool: 再画像化が必要な場合True
        """
        if not judgment_result.get("success"):
            return False
        
        judgment = judgment_result.get("judgment", {})
        readability_issues = str(judgment.get("readability_issues", "")).lower()
        
        return readability_issues == "major"
    
    def reprocess_page(self, pdf_path: str, page_number: int, original_page_info: Dict, 
                      output_dir: str, scale_factor: Optional[float] = None) -> Dict:
        """
        指定されたページを高解像度で再画像化
        
        Args:
            pdf_path (str): PDFファイルパス
            page_number (int): ページ番号（1ベース）
            original_page_info (Dict): 元ページ情報（DPI等）
            output_dir (str): 出力ディレクトリ
            scale_factor (float, optional): スケールファクター
            
        Returns:
            Dict: 再画像化結果
        """
        if scale_factor is None:
            scale_factor = self.default_scale_factor
        
        logger.debug(f"再画像化開始: ページ{page_number}, {scale_factor}x スケール")
        
        try:
            # 元のDPI情報を取得
            original_dpi = original_page_info.get("used_dpi", self.config.get('default_dpi', 300))
            new_dpi = self._calculate_scaled_dpi(original_dpi, scale_factor)
            
            # 出力ディレクトリを作成
            os.makedirs(output_dir, exist_ok=True)
            
            # 出力ファイル名を生成
            base_name = Path(pdf_path).stem
            output_filename = f"{base_name}_page_{page_number:03d}_reprocessed_{int(scale_factor)}x.jpg"
            output_path = os.path.join(output_dir, output_filename)
            
            # PDFProcessorを使用して再変換（0ベースに変換）
            page_idx = page_number - 1
            converted_path = self.pdf_processor.convert_page_to_image(
                pdf_path, page_idx, new_dpi, output_path
            )
            
            if converted_path and os.path.exists(converted_path):
                logger.debug(f"再画像化成功: {new_dpi}DPI → {os.path.basename(converted_path)}")
                
                return {
                    "success": True,
                    "page_number": page_number,
                    "original_image_path": original_page_info.get("image_file"),
                    "reprocessed_image_path": converted_path,
                    "original_dpi": original_dpi,
                    "new_dpi": new_dpi,
                    "scale_factor": scale_factor,
                    "file_size_bytes": os.path.getsize(converted_path)
                }
            else:
                return {
                    "success": False,
                    "page_number": page_number,
                    "error": "PDFProcessor変換失敗"
                }
                
        except Exception as e:
            logger.error(f"ページ {page_number} 再画像化エラー: {e}")
            return {
                "success": False,
                "page_number": page_number,
                "error": str(e)
            }
    
    def batch_reprocess_pages(self, pdf_path: str, page_judgments: list, 
                             output_dir: str, pdf_info: Dict) -> Dict:
        """
        複数ページの一括再画像化処理
        
        Args:
            pdf_path (str): PDFファイルパス
            page_judgments (list): ページ判定結果リスト
            output_dir (str): 出力ディレクトリ
            pdf_info (Dict): PDF情報（各ページのDPI情報含む）
            
        Returns:
            Dict: 一括処理結果
        """
        logger.debug("一括再画像化処理開始")
        
        try:
            reprocessed_count = 0
            results = []
            
            # ページ情報をマッピング
            pages_info = {p.get("page_number"): p for p in pdf_info.get("pages", [])}
            
            for page_judgment in page_judgments:
                page_number = page_judgment.get("page_number")
                
                # 再画像化が必要かチェック
                if self.should_reprocess(page_judgment.get("llm_result", {})):
                    logger.debug(f"ページ {page_number}: 再画像化対象（読みにくさ=major）")
                    
                    # 元ページ情報を取得
                    original_page_info = pages_info.get(page_number, {})
                    
                    # 再画像化実行
                    reprocess_result = self.reprocess_page(
                        pdf_path, page_number, original_page_info, output_dir
                    )
                    
                    results.append(reprocess_result)
                    
                    if reprocess_result.get("success"):
                        reprocessed_count += 1
                        # ページ判定データに結果を追加
                        page_judgment["reprocessed_at_scale"] = True
                        page_judgment["processed_image"] = reprocess_result["reprocessed_image_path"]
                        page_judgment["processed_images"] = [reprocess_result["reprocessed_image_path"]]
                        page_judgment["reprocess_result"] = reprocess_result
                    else:
                        page_judgment["reprocessed_at_scale"] = False
                        page_judgment["reprocess_result"] = reprocess_result
                        logger.warning(f"ページ {page_number} 再画像化失敗: {reprocess_result.get('error')}")
                else:
                    # 再画像化不要
                    page_judgment["reprocessed_at_scale"] = False
                    logger.debug(f"ページ {page_number}: 再画像化不要")
            
            return {
                "success": True,
                "total_processed": len(results),
                "successful_reprocessing": reprocessed_count,
                "results": results
            }
            
        except Exception as e:
            logger.error(f"一括再画像化エラー: {e}")
            return {
                "success": False,
                "error": str(e),
                "results": []
            }
    
    def get_reprocessing_stats(self, results: list) -> Dict:
        """
        再画像化処理の統計情報を生成
        
        Args:
            results (list): 処理結果リスト
            
        Returns:
            Dict: 統計情報
        """
        if not results:
            return {"total": 0, "successful": 0, "failed": 0}
        
        successful = len([r for r in results if r.get("success")])
        failed = len(results) - successful
        
        # サイズ情報
        total_size = sum(r.get("file_size_bytes", 0) for r in results if r.get("success"))
        avg_scale_factor = sum(r.get("scale_factor", 0) for r in results if r.get("success")) / max(successful, 1)
        
        return {
            "total": len(results),
            "successful": successful,
            "failed": failed,
            "success_rate": successful / len(results) if results else 0.0,
            "total_file_size_bytes": total_size,
            "average_scale_factor": avg_scale_factor
        }
    
    def validate_reprocessed_image(self, image_path: str, expected_min_size: tuple = (500, 500)) -> Dict:
        """
        再画像化された画像の有効性を検証
        
        Args:
            image_path (str): 検証対象画像パス
            expected_min_size (tuple): 期待する最小サイズ
            
        Returns:
            Dict: 検証結果
        """
        try:
            if not os.path.exists(image_path):
                return {
                    "valid": False,
                    "error": "画像ファイルが存在しません"
                }
            
            # ファイルサイズチェック
            file_size = os.path.getsize(image_path)
            if file_size < 1000:  # 1KB未満は異常
                return {
                    "valid": False,
                    "error": f"ファイルサイズが小さすぎます: {file_size} bytes"
                }
            
            # PIL で画像サイズを確認
            try:
                from PIL import Image
                with Image.open(image_path) as img:
                    width, height = img.size
                    
                    if width < expected_min_size[0] or height < expected_min_size[1]:
                        return {
                            "valid": False,
                            "error": f"画像サイズが小さすぎます: {width}x{height} < {expected_min_size}"
                        }
                    
                    return {
                        "valid": True,
                        "image_size": [width, height],
                        "file_size_bytes": file_size,
                        "format": img.format
                    }
                    
            except Exception as e:
                return {
                    "valid": False,
                    "error": f"画像読み込みエラー: {str(e)}"
                }
                
        except Exception as e:
            return {
                "valid": False,
                "error": str(e)
            }
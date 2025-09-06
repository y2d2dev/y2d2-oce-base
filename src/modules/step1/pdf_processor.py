"""
PDF処理メインオーケストレーターモジュール
各コンポーネントを統合してPDF→JPG変換処理を実行
"""

import os
import logging
from pathlib import Path
from typing import Dict, List, Optional

from .pdf_reader import PDFReader
from .dpi_calculator import DPICalculator
from .image_converter import ImageConverter

logger = logging.getLogger(__name__)


class PDFProcessor:
    """PDF処理メインオーケストレータークラス"""
    
    def __init__(self, config: Dict):
        """
        Args:
            config (Dict): 全体設定
        """
        self.config = config
        self.pdf_config = config.get('pdf_processing', {})
        
        # 各コンポーネントを初期化
        self.pdf_reader = PDFReader()
        self.dpi_calculator = DPICalculator(self.pdf_config)
        self.image_converter = ImageConverter(self.pdf_config)
        
        logger.debug("PDFProcessor初期化完了: 全コンポーネント準備完了")
    
    def process_pdf(self, pdf_path: str, output_dir: str) -> Dict:
        """
        PDFファイルをJPG画像に変換するメインメソッド
        
        Args:
            pdf_path (str): PDFファイルパス
            output_dir (str): 出力ディレクトリ
            
        Returns:
            Dict: 変換結果
        """
        logger.debug(f"PDF変換開始: {os.path.basename(pdf_path)}")
        
        try:
            # Step 1: PDFファイルを開く
            if not self.pdf_reader.open_pdf(pdf_path):
                raise RuntimeError("PDFファイルの読み込みに失敗しました")
            logger.info("Step1-01: 完了!!")
            
            # Step 2: PDFの有効性を検証とDPI計算準備
            validation = self.pdf_reader.validate_pdf()
            if not validation.get("valid"):
                raise RuntimeError(f"PDF検証失敗: {validation.get('error')}")
            
            total_pages = validation["page_count"]
            logger.info("Step1-02: 完了!!")
            
            # Step 3: 出力ディレクトリを作成
            os.makedirs(output_dir, exist_ok=True)
            
            # Step 4: ベースファイル名を生成
            base_name = Path(pdf_path).stem
            
            # Step 5: 各ページを処理
            pages = []
            successful_pages = 0
            
            for page_num in range(total_pages):
                logger.debug(f"ページ {page_num + 1}/{total_pages} 処理中...")
                
                # ページサイズを取得
                page_size = self.pdf_reader.get_page_size(page_num)
                if not page_size:
                    result = {
                        "success": False,
                        "page_number": page_num + 1,
                        "error": "ページサイズ取得失敗"
                    }
                    pages.append(result)
                    continue
                
                page_width, page_height = page_size
                
                # 最適DPIを計算
                optimal_dpi = self.dpi_calculator.calculate_optimal_dpi(page_width, page_height)
                
                # 出力ファイル名を生成
                output_filename = f"{base_name}_page_{page_num + 1:03d}.jpg"
                output_path = os.path.join(output_dir, output_filename)
                
                # ページを画像に変換
                doc = self.pdf_reader.get_document()
                result = self.image_converter.convert_page_from_doc(
                    doc, page_num, optimal_dpi, output_path
                )
                
                # 追加情報を設定
                if result.get("success"):
                    result["image_file"] = output_path  # main_pipeline.pyとの互換性
                    successful_pages += 1
                    logger.debug(f"ページ {page_num + 1} 変換完了: {optimal_dpi}DPI")
                else:
                    logger.error(f"ページ {page_num + 1} 変換失敗: {result.get('error')}")
                
                pages.append(result)
            
            # Step 6: PDFを閉じる
            self.pdf_reader.close_pdf()
            logger.info("Step1-03: 完了!!")
            
            # Step 7: 結果をまとめる
            pipeline_result = {
                "success": successful_pages > 0,
                "input_pdf": pdf_path,
                "output_directory": output_dir,
                "page_count": total_pages,
                "successful_pages": successful_pages,
                "failed_pages": total_pages - successful_pages,
                "pages": pages
            }
            
            if successful_pages == 0:
                pipeline_result["error"] = "すべてのページの変換に失敗しました"
                logger.error("PDF変換失敗: すべてのページで変換エラー")
            else:
                logger.debug(f"PDF変換完了: {successful_pages}/{total_pages}ページ成功")
            
            return pipeline_result
            
        except Exception as e:
            # エラー時にPDFを確実に閉じる
            self.pdf_reader.close_pdf()
            
            error_msg = f"PDF変換エラー: {e}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": str(e),
                "input_pdf": pdf_path,
                "page_count": 0,
                "pages": []
            }
    
    def convert_page_to_image(self, pdf_path: str, page_idx: int, dpi: int, output_path: str) -> Optional[str]:
        """
        指定されたページを指定されたDPIで画像に変換（main_pipeline.pyで使用）
        
        Args:
            pdf_path (str): PDFファイルパス
            page_idx (int): ページインデックス（0ベース）
            dpi (int): DPI値
            output_path (str): 出力パス
            
        Returns:
            Optional[str]: 成功時は出力パス、失敗時はNone
        """
        temp_reader = PDFReader()
        
        try:
            # PDFを開く
            if not temp_reader.open_pdf(pdf_path):
                logger.error(f"PDF読み込み失敗: {pdf_path}")
                return None
            
            # ドキュメントを取得して変換
            doc = temp_reader.get_document()
            result = self.image_converter.convert_page_from_doc(doc, page_idx, dpi, output_path)
            
            temp_reader.close_pdf()
            
            if result.get("success"):
                logger.info(f"単一ページ変換成功: ページ{page_idx + 1} → {output_path}")
                return output_path
            else:
                logger.error(f"単一ページ変換失敗: {result.get('error')}")
                return None
                
        except Exception as e:
            temp_reader.close_pdf()
            logger.error(f"単一ページ変換エラー: {e}")
            return None
    
    def get_pdf_info(self, pdf_path: str) -> Dict:
        """
        PDFファイルの基本情報を取得
        
        Args:
            pdf_path (str): PDFファイルパス
            
        Returns:
            Dict: PDF情報
        """
        temp_reader = PDFReader()
        
        try:
            if not temp_reader.open_pdf(pdf_path):
                return {
                    "success": False,
                    "error": "PDFファイルの読み込みに失敗しました",
                    "file_path": pdf_path
                }
            
            # 基本情報を取得
            metadata_info = temp_reader.get_pdf_metadata()
            
            if metadata_info.get("success"):
                # 最初のページのサイズから推奨DPIを計算
                first_page_size = metadata_info.get("first_page_size")
                if first_page_size:
                    suggested_dpi = self.dpi_calculator.calculate_optimal_dpi(
                        first_page_size[0], first_page_size[1]
                    )
                    metadata_info["suggested_dpi"] = suggested_dpi
                
                # DPI詳細情報を追加
                if first_page_size:
                    dpi_info = self.dpi_calculator.get_dpi_info(
                        first_page_size[0], first_page_size[1]
                    )
                    metadata_info["dpi_analysis"] = dpi_info
            
            temp_reader.close_pdf()
            return metadata_info
            
        except Exception as e:
            temp_reader.close_pdf()
            logger.error(f"PDF情報取得エラー: {e}")
            return {
                "success": False,
                "error": str(e),
                "file_path": pdf_path
            }
    
    def batch_convert_with_custom_dpi(self, pdf_path: str, output_dir: str, page_dpi_map: Dict[int, int]) -> Dict:
        """
        カスタムDPIでページごとに変換
        
        Args:
            pdf_path (str): PDFファイルパス
            output_dir (str): 出力ディレクトリ
            page_dpi_map (Dict[int, int]): {page_number: dpi} のマッピング
            
        Returns:
            Dict: 変換結果
        """
        logger.info(f"カスタムDPI変換開始: {os.path.basename(pdf_path)}")
        
        try:
            if not self.pdf_reader.open_pdf(pdf_path):
                raise RuntimeError("PDFファイルの読み込みに失敗しました")
            
            os.makedirs(output_dir, exist_ok=True)
            base_name = Path(pdf_path).stem
            doc = self.pdf_reader.get_document()
            
            results = []
            successful_count = 0
            
            for page_num, dpi in page_dpi_map.items():
                output_filename = f"{base_name}_page_{page_num:03d}_custom.jpg"
                output_path = os.path.join(output_dir, output_filename)
                
                result = self.image_converter.convert_page_from_doc(
                    doc, page_num - 1, dpi, output_path  # page_numは1ベースと仮定
                )
                
                if result.get("success"):
                    result["image_file"] = output_path
                    successful_count += 1
                
                results.append(result)
            
            self.pdf_reader.close_pdf()
            
            return {
                "success": successful_count > 0,
                "total_pages": len(page_dpi_map),
                "successful_pages": successful_count,
                "results": results
            }
            
        except Exception as e:
            self.pdf_reader.close_pdf()
            logger.error(f"カスタムDPI変換エラー: {e}")
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
            "components": {
                "pdf_reader": type(self.pdf_reader).__name__,
                "dpi_calculator": type(self.dpi_calculator).__name__,
                "image_converter": type(self.image_converter).__name__
            },
            "config": {
                "target_size": self.dpi_calculator.target_size,
                "dpi_range": [self.dpi_calculator.min_dpi, self.dpi_calculator.max_dpi],
                "default_dpi": self.dpi_calculator.default_dpi,
                "image_format": self.image_converter.image_format,
                "image_quality": self.image_converter.image_quality
            }
        }
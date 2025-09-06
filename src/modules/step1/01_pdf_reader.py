"""
PDF読み取り機能ラッパーモジュール
PDFファイルの基本操作（開く・閉じる・情報取得）を担当
"""

import os
import logging
from pathlib import Path
from typing import Dict, Optional
import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


class PDFReader:
    """PDF読み取り専用クラス"""
    
    def __init__(self):
        self.current_doc: Optional[fitz.Document] = None
        self.current_path: Optional[str] = None
    
    def open_pdf(self, pdf_path: str) -> bool:
        """
        PDFファイルを開く
        
        Args:
            pdf_path (str): PDFファイルパス
            
        Returns:
            bool: 成功時True、失敗時False
        """
        try:
            if not os.path.exists(pdf_path):
                logger.error(f"PDFファイルが見つかりません: {pdf_path}")
                return False
            
            # 既存のドキュメントがある場合は閉じる
            if self.current_doc:
                self.close_pdf()
            
            self.current_doc = fitz.open(pdf_path)
            self.current_path = pdf_path
            
            logger.debug(f"PDF読み込み完了: {os.path.basename(pdf_path)} ({self.current_doc.page_count}ページ)")
            return True
            
        except Exception as e:
            logger.error(f"PDF読み込みエラー: {e}")
            return False
    
    def close_pdf(self) -> None:
        """PDFファイルを閉じる"""
        if self.current_doc:
            self.current_doc.close()
            self.current_doc = None
            self.current_path = None
    
    def get_document(self) -> Optional[fitz.Document]:
        """現在のPDFドキュメントを取得"""
        return self.current_doc
    
    def get_page_count(self) -> int:
        """総ページ数を取得"""
        if not self.current_doc:
            return 0
        return self.current_doc.page_count
    
    def get_page(self, page_num: int) -> Optional[fitz.Page]:
        """
        指定されたページを取得
        
        Args:
            page_num (int): ページ番号（0ベース）
            
        Returns:
            Optional[fitz.Page]: ページオブジェクト、失敗時はNone
        """
        if not self.current_doc:
            logger.error("PDFドキュメントが開かれていません")
            return None
        
        try:
            if page_num < 0 or page_num >= self.current_doc.page_count:
                logger.error(f"無効なページ番号: {page_num}")
                return None
            
            return self.current_doc.load_page(page_num)
            
        except Exception as e:
            logger.error(f"ページ {page_num} の読み込みエラー: {e}")
            return None
    
    def get_page_size(self, page_num: int) -> Optional[tuple]:
        """
        指定されたページのサイズを取得
        
        Args:
            page_num (int): ページ番号（0ベース）
            
        Returns:
            Optional[tuple]: (width, height) タプル、失敗時はNone
        """
        page = self.get_page(page_num)
        if not page:
            return None
        
        rect = page.rect
        return (rect.width, rect.height)
    
    def get_pdf_metadata(self) -> Dict:
        """
        PDFのメタデータを取得
        
        Returns:
            Dict: PDFメタデータ情報
        """
        if not self.current_doc:
            return {"error": "PDFドキュメントが開かれていません"}
        
        try:
            metadata = self.current_doc.metadata
            page_count = self.current_doc.page_count
            
            # 最初のページのサイズを取得
            first_page_size = None
            if page_count > 0:
                first_page_size = self.get_page_size(0)
            
            return {
                "success": True,
                "file_path": self.current_path,
                "page_count": page_count,
                "metadata": metadata,
                "first_page_size": first_page_size
            }
            
        except Exception as e:
            logger.error(f"メタデータ取得エラー: {e}")
            return {
                "success": False,
                "error": str(e),
                "file_path": self.current_path
            }
    
    def validate_pdf(self) -> Dict:
        """
        PDFの有効性を検証
        
        Returns:
            Dict: 検証結果
        """
        if not self.current_doc:
            return {
                "valid": False,
                "error": "PDFドキュメントが開かれていません"
            }
        
        try:
            page_count = self.current_doc.page_count
            
            if page_count == 0:
                return {
                    "valid": False,
                    "error": "PDFにページが含まれていません"
                }
            
            # 最初のページが正常に読み込めるかチェック
            first_page = self.get_page(0)
            if not first_page:
                return {
                    "valid": False,
                    "error": "最初のページの読み込みに失敗しました"
                }
            
            return {
                "valid": True,
                "page_count": page_count,
                "file_path": self.current_path
            }
            
        except Exception as e:
            return {
                "valid": False,
                "error": str(e),
                "file_path": self.current_path
            }
    
    def __enter__(self):
        """コンテキストマネージャーのエントリ"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """コンテキストマネージャーの終了処理"""
        self.close_pdf()
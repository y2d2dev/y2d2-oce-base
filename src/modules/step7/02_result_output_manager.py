"""
Step7-02: 結果出力管理
統合されたテキストをresultディレクトリに保存
"""

import os
import json
import logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ResultOutputManager:
    """結果出力管理"""
    
    def __init__(self, config: Dict):
        """
        Args:
            config: Step7設定
        """
        self.config = config
        self.step7_config = config.get('step7', {})
        
        # デフォルト設定
        self.encoding = self.step7_config.get('encoding', 'utf-8')
        self.result_base_dir = self.step7_config.get('result_base_dir', 'result')
        self.include_metadata = self.step7_config.get('include_metadata', True)
        
        logger.debug("結果出力管理初期化完了")
    
    def save_integrated_results(self, integration_result: Dict, session_dirs: Dict, 
                              session_id: str) -> Dict:
        """
        統合結果を保存
        
        Args:
            integration_result: テキスト統合結果
            session_dirs: セッションディレクトリ情報
            session_id: セッションID
            
        Returns:
            Dict: 保存結果
        """
        logger.debug(f"統合結果保存開始: セッション={session_id}")
        
        try:
            # resultディレクトリを作成
            os.makedirs(self.result_base_dir, exist_ok=True)
            
            saved_files = []
            errors = []
            
            # Gemini統合テキストを保存
            gemini_result = self._save_gemini_text(
                integration_result, session_id
            )
            if gemini_result["success"]:
                saved_files.extend(gemini_result["saved_files"])
            else:
                errors.extend(gemini_result["errors"])
            
            # Document AI統合テキストを保存
            document_ai_result = self._save_document_ai_text(
                integration_result, session_id
            )
            if document_ai_result["success"]:
                saved_files.extend(document_ai_result["saved_files"])
            else:
                errors.extend(document_ai_result["errors"])
            
            # メタデータ保存
            if self.include_metadata:
                metadata_result = self._save_metadata(
                    integration_result, session_dirs, session_id
                )
                if metadata_result["success"]:
                    saved_files.extend(metadata_result["saved_files"])
                else:
                    errors.extend(metadata_result["errors"])
            
            logger.info(f"統合結果保存完了: {len(saved_files)}ファイル保存, {len(errors)}エラー")
            
            return {
                "success": len(saved_files) > 0,
                "saved_files": saved_files,
                "errors": errors,
                "total_files": len(saved_files)
            }
            
        except Exception as e:
            error_msg = f"統合結果保存エラー: {e}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "saved_files": [],
                "errors": [error_msg],
                "total_files": 0
            }
    
    def _save_gemini_text(self, integration_result: Dict, session_id: str) -> Dict:
        """
        Gemini統合テキストを保存
        
        Args:
            integration_result: 統合結果
            session_id: セッションID
            
        Returns:
            Dict: 保存結果
        """
        try:
            gemini_text = integration_result.get("gemini_integrated_text", "")
            if not gemini_text:
                return {
                    "success": False,
                    "errors": ["Geminiテキストが空です"],
                    "saved_files": []
                }
            
            # ファイル名生成
            filename = f"gemini_integrated_{session_id}.txt"
            filepath = os.path.join(self.result_base_dir, filename)
            
            # テキストファイル保存
            with open(filepath, 'w', encoding=self.encoding) as f:
                f.write(gemini_text)
            
            logger.debug(f"Gemini統合テキスト保存: {filepath} ({len(gemini_text)}文字)")
            
            return {
                "success": True,
                "saved_files": [filepath],
                "errors": []
            }
            
        except Exception as e:
            error_msg = f"Geminiテキスト保存エラー: {e}"
            logger.error(error_msg)
            return {
                "success": False,
                "errors": [error_msg],
                "saved_files": []
            }
    
    def _save_document_ai_text(self, integration_result: Dict, session_id: str) -> Dict:
        """
        Document AI統合テキストを保存
        
        Args:
            integration_result: 統合結果
            session_id: セッションID
            
        Returns:
            Dict: 保存結果
        """
        try:
            document_ai_text = integration_result.get("document_ai_integrated_text", "")
            if not document_ai_text:
                return {
                    "success": False,
                    "errors": ["Document AIテキストが空です"],
                    "saved_files": []
                }
            
            # ファイル名生成
            filename = f"document_ai_integrated_{session_id}.txt"
            filepath = os.path.join(self.result_base_dir, filename)
            
            # テキストファイル保存
            with open(filepath, 'w', encoding=self.encoding) as f:
                f.write(document_ai_text)
            
            logger.debug(f"Document AI統合テキスト保存: {filepath} ({len(document_ai_text)}文字)")
            
            return {
                "success": True,
                "saved_files": [filepath],
                "errors": []
            }
            
        except Exception as e:
            error_msg = f"Document AIテキスト保存エラー: {e}"
            logger.error(error_msg)
            return {
                "success": False,
                "errors": [error_msg],
                "saved_files": []
            }
    
    def _save_metadata(self, integration_result: Dict, session_dirs: Dict, 
                      session_id: str) -> Dict:
        """
        メタデータを保存
        
        Args:
            integration_result: 統合結果
            session_dirs: セッションディレクトリ情報
            session_id: セッションID
            
        Returns:
            Dict: 保存結果
        """
        try:
            # メタデータ構築
            metadata = {
                "session_id": session_id,
                "processing_timestamp": datetime.now().isoformat(),
                "integration_summary": {
                    "gemini": {
                        "files_count": integration_result.get("gemini_files_count", 0),
                        "total_characters": integration_result.get("gemini_total_characters", 0)
                    },
                    "document_ai": {
                        "files_count": integration_result.get("document_ai_files_count", 0),
                        "total_characters": integration_result.get("document_ai_total_characters", 0)
                    }
                },
                "session_directories": session_dirs,
                "output_files": {
                    "gemini_integrated": f"gemini_integrated_{session_id}.txt",
                    "document_ai_integrated": f"document_ai_integrated_{session_id}.txt"
                }
            }
            
            # メタデータファイル名生成
            filename = f"integration_metadata_{session_id}.json"
            filepath = os.path.join(self.result_base_dir, filename)
            
            # JSONファイル保存
            with open(filepath, 'w', encoding=self.encoding) as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"メタデータ保存: {filepath}")
            
            return {
                "success": True,
                "saved_files": [filepath],
                "errors": []
            }
            
        except Exception as e:
            error_msg = f"メタデータ保存エラー: {e}"
            logger.error(error_msg)
            return {
                "success": False,
                "errors": [error_msg],
                "saved_files": []
            }
    
    def create_integration_summary(self, integration_result: Dict, 
                                 save_result: Dict) -> Dict:
        """
        統合サマリーを作成
        
        Args:
            integration_result: 統合結果
            save_result: 保存結果
            
        Returns:
            Dict: サマリー情報
        """
        return {
            "integration_success": integration_result.get("success", False),
            "save_success": save_result.get("success", False),
            "gemini_files_processed": integration_result.get("gemini_files_count", 0),
            "document_ai_files_processed": integration_result.get("document_ai_files_count", 0),
            "gemini_total_characters": integration_result.get("gemini_total_characters", 0),
            "document_ai_total_characters": integration_result.get("document_ai_total_characters", 0),
            "output_files_created": save_result.get("total_files", 0),
            "total_errors": len(save_result.get("errors", []))
        }
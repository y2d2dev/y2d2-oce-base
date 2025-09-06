"""
Step6-05: Document AI結果管理
Document AI OCR結果の保存・管理・統計処理
"""

import os
import json
import logging
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class DocumentAIResultManager:
    """Document AI結果管理クラス"""
    
    def __init__(self, config: Dict = None):
        """
        Args:
            config: Document AI結果管理設定
                - output_format: 出力形式（txt/json/both、デフォルト: both）
                - encoding: テキストエンコーディング（デフォルト: utf-8）
                - include_metadata: メタデータ含める（デフォルト: True）
                - include_individual_results: 個別画像結果を含める（デフォルト: True）
        """
        self.config = config.get('document_ai_result_manager', {}) if config else {}
        self.output_format = self.config.get('output_format', 'both')
        self.encoding = self.config.get('encoding', 'utf-8')
        self.include_metadata = self.config.get('include_metadata', True)
        self.include_individual_results = self.config.get('include_individual_results', True)
        
        logger.debug("DocumentAIResultManager初期化完了")
    
    def _create_output_filename(self, base_name: str, file_type: str) -> str:
        """
        出力ファイル名を作成
        
        Args:
            base_name: ベース名（page_001_mask1など）
            file_type: ファイルタイプ（txt/json）
            
        Returns:
            str: ファイル名
        """
        return f"{base_name}_documentai_result.{file_type}"
    
    def _prepare_text_content(self, doc_ai_result: Dict) -> str:
        """
        テキストファイル用のコンテンツを準備（純粋なOCRテキストのみ）
        
        Args:
            doc_ai_result: Document AI処理結果
            
        Returns:
            str: テキストコンテンツ（抽出テキストのみ）
        """
        # 統合されたテキストのみを返す
        combined_text = doc_ai_result.get("combined_text", "")
        return combined_text.strip() if combined_text else ""
    
    def _prepare_json_content(self, doc_ai_result: Dict, additional_metadata: Dict = None) -> Dict:
        """
        JSONファイル用のコンテンツを準備
        
        Args:
            doc_ai_result: Document AI処理結果
            additional_metadata: 追加メタデータ
            
        Returns:
            Dict: JSONコンテンツ
        """
        # ベースのDocument AI結果をコピー
        json_content = {
            "success": doc_ai_result.get("success", False),
            "document_ai_result": {
                "combined_text": doc_ai_result.get("combined_text", ""),
                "processed_images": doc_ai_result.get("processed_images", 0),
                "successful_images": doc_ai_result.get("successful_images", 0),
                "failed_images": doc_ai_result.get("failed_images", 0),
                "average_confidence": doc_ai_result.get("average_confidence", 0.0)
            },
            "extraction_timestamp": datetime.now().isoformat()
        }
        
        # メタデータを含める場合
        if self.include_metadata:
            json_content["group_info"] = doc_ai_result.get("group_info", {})
            
            # 個別結果を含める場合
            if self.include_individual_results:
                json_content["individual_results"] = doc_ai_result.get("individual_results", [])
        
        # 追加メタデータをマージ
        if additional_metadata:
            json_content.update(additional_metadata)
        
        return json_content
    
    def save_document_ai_result(self, doc_ai_result: Dict, output_dir: str, 
                               base_name: str, additional_metadata: Dict = None) -> Dict:
        """
        Document AI結果をファイルに保存
        
        Args:
            doc_ai_result: Document AI処理結果
            output_dir: 出力ディレクトリ
            base_name: ベース名（page_001_mask1など）
            additional_metadata: 追加メタデータ
            
        Returns:
            Dict: 保存結果
                - success: bool
                - saved_files: List[str] (保存されたファイルパス)
                - errors: List[str] (エラーリスト)
        """
        try:
            # 出力ディレクトリ作成
            os.makedirs(output_dir, exist_ok=True)
            
            saved_files = []
            errors = []
            
            # テキストファイル保存
            if self.output_format in ['txt', 'both']:
                try:
                    txt_filename = self._create_output_filename(base_name, 'txt')
                    txt_path = os.path.join(output_dir, txt_filename)
                    
                    text_content = self._prepare_text_content(doc_ai_result)
                    
                    with open(txt_path, 'w', encoding=self.encoding) as f:
                        f.write(text_content)
                    
                    saved_files.append(txt_path)
                    logger.debug(f"Document AIテキストファイル保存: {txt_path}")
                    
                except Exception as e:
                    error_msg = f"Document AIテキストファイル保存エラー: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
            
            # JSONファイル保存
            if self.output_format in ['json', 'both']:
                try:
                    json_filename = self._create_output_filename(base_name, 'json')
                    json_path = os.path.join(output_dir, json_filename)
                    
                    json_content = self._prepare_json_content(doc_ai_result, additional_metadata)
                    
                    with open(json_path, 'w', encoding=self.encoding) as f:
                        json.dump(json_content, f, ensure_ascii=False, indent=2)
                    
                    saved_files.append(json_path)
                    logger.debug(f"Document AI JSONファイル保存: {json_path}")
                    
                except Exception as e:
                    error_msg = f"Document AI JSONファイル保存エラー: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
            
            return {
                "success": len(saved_files) > 0,
                "saved_files": saved_files,
                "errors": errors
            }
            
        except Exception as e:
            logger.error(f"Document AI結果保存エラー ({base_name}): {e}")
            return {
                "success": False,
                "saved_files": [],
                "errors": [str(e)]
            }
    
    def create_processing_summary(self, all_results: List[Dict]) -> Dict:
        """
        処理サマリーを作成
        
        Args:
            all_results: 全グループのDocument AI結果
            
        Returns:
            Dict: サマリー情報
        """
        successful_results = [r for r in all_results if r.get("success")]
        failed_results = [r for r in all_results if not r.get("success")]
        
        total_images_processed = sum(r.get("processed_images", 0) for r in successful_results)
        total_successful_images = sum(r.get("successful_images", 0) for r in successful_results)
        total_failed_images = sum(r.get("failed_images", 0) for r in successful_results)
        
        # 全体の平均信頼度を計算
        confidences = [r.get("average_confidence", 0.0) for r in successful_results 
                      if r.get("average_confidence", 0.0) > 0]
        overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        # 統合テキスト長の統計
        text_lengths = [len(r.get("combined_text", "")) for r in successful_results]
        total_text_length = sum(text_lengths)
        
        return {
            "total_groups": len(all_results),
            "successful_groups": len(successful_results),
            "failed_groups": len(failed_results),
            "total_images_processed": total_images_processed,
            "total_successful_images": total_successful_images,
            "total_failed_images": total_failed_images,
            "overall_confidence": overall_confidence,
            "total_text_length": total_text_length,
            "average_text_length_per_group": total_text_length / len(successful_results) if successful_results else 0,
            "success_rate": len(successful_results) / len(all_results) * 100 if all_results else 0
        }
    
    def save_processing_summary(self, summary_data: Dict, output_dir: str, 
                              session_id: str) -> Dict:
        """
        Document AI処理サマリーを保存
        
        Args:
            summary_data: サマリーデータ
            output_dir: 出力ディレクトリ
            session_id: セッションID
            
        Returns:
            Dict: 保存結果
        """
        try:
            os.makedirs(output_dir, exist_ok=True)
            
            summary_filename = f"document_ai_processing_summary_{session_id}.json"
            summary_path = os.path.join(output_dir, summary_filename)
            
            # タイムスタンプを追加
            summary_data["generation_timestamp"] = datetime.now().isoformat()
            summary_data["session_id"] = session_id
            summary_data["processor_type"] = "google_document_ai"
            
            with open(summary_path, 'w', encoding=self.encoding) as f:
                json.dump(summary_data, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"Document AI処理サマリー保存: {summary_path}")
            
            return {
                "success": True,
                "summary_path": summary_path
            }
            
        except Exception as e:
            logger.error(f"Document AI処理サマリー保存エラー: {e}")
            return {
                "success": False,
                "error": str(e)
            }
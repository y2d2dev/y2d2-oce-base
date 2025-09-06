import os
import sys
import json
import logging
import shutil
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path

# プロジェクト内モジュールのインポート
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Step0: 初期化モジュール群
from src.modules.step0 import (
    load_env,
    load_config,
    apply_processing_options,
    setup_logging,
    ComponentInitializer,
    load_prompts,
    DirectoryManager,
    to_bool,
    to_int,
    to_float
)

# その他必要なモジュール（一旦コメントアウト）
# from src.utils.file_utils import cleanup_directory
# from src.utils.image_utils import split_image_left_right_with_overlap
# import cv2
# import torch

logger = logging.getLogger(__name__)


class DocumentOCRPipeline:
    # Step0: 初期化
    def __init__(self, config_path: str, processing_options: Optional[Dict] = None):
        # Step0-01: .envファイルの読み込み
        load_env()
        
        self.config_path = config_path
        self.processing_options = processing_options or {}
        logger.info("Step0-01: 完了!!")
        
        # Step0-02: 設定ファイルの読み込みとオプション適用
        self.config = load_config(config_path)
        apply_processing_options(self.config, self.processing_options)
        logger.info("Step0-02: 完了!!")
        
        # Step0-03: ログシステムのセットアップ
        setup_logging(self.config)
        logger.info("Step0-03: 完了!!")
        
        # 環境変数の確認
        import os
        env_vars = [key for key in os.environ.keys() if 'API' in key or 'KEY' in key]
        
        # Step0-04: プロンプト設定の読み込み
        self.prompts = load_prompts(config_path)
        logger.info("Step0-04: 完了!!")
        
        # Step0-05: コンポーネントの初期化
        component_initializer = ComponentInitializer(self.config)
        components = component_initializer.initialize_all()
        logger.info("Step0-05: コンポーネント初期化 完了‼️")
        
        # 初期化されたコンポーネントをインスタンス変数に設定
        # Step1: PDFProcessor
        self.pdf_processor = components.get('pdf_processor')
        
        # Step2: Step2統合プロセッサー（プロンプトを設定）
        self.step2_processor = components.get('step2_processor')
        if self.step2_processor:
            self.step2_processor.prompts = self.prompts
        
        # Step3: Step3統合プロセッサー（プロンプトを設定）
        self.step3_processor = components.get('step3_processor')
        self.orientation_detector = components.get('orientation_detector')
        if self.orientation_detector and hasattr(self.orientation_detector, 'llm_evaluator'):
            # Step3のLLM評価器にプロンプトを設定
            self.orientation_detector.prompts = self.prompts
        
        # Step4以降のコンポーネント（未実装）
        # self.llm_evaluator_judgment = components.get('llm_evaluator_judgment')
        # self.llm_evaluator_ocr = components.get('llm_evaluator_ocr')
        # self.llm_evaluator_orientation = components.get('llm_evaluator_orientation')
        # self.orientation_detector = components.get('orientation_detector')
        # self.dewarping_runner = components.get('dewarping_runner')
        # self.image_splitter = components.get('image_splitter')
        # self.sr_runner = components.get('sr_runner')
        
        # Step0-06: ディレクトリ管理の設定
        self.directory_manager = DirectoryManager(self.config)
        self.dirs = self.directory_manager.setup_directories()
        self._to_bool = to_bool
        self._to_int = to_int
        self._to_float = to_float
        logger.info("Step0-06: ディレクトリ管理 完了‼️")
  
   # Step1: PDF → JPG変換
    def _pdf_to_jpg(self, pdf_path: str, output_dir: str) -> Dict:
        """
        ステップ1: PDF → JPG変換
        
        Args:
            pdf_path (str): PDFファイルパス
            output_dir (str): 出力ディレクトリ
            
        Returns:
            Dict: 変換結果
        """
        try:
            if not self.pdf_processor:
                raise RuntimeError("PDFProcessorが初期化されていません")
            
            result = self.pdf_processor.process_pdf(pdf_path, output_dir)
            return result
            
        except Exception as e:
            logger.error(f"PDF変換エラー: {e}")
            return {"success": False, "error": str(e)}
    
    # Step2: LLM判定・再画像化・歪み補正処理
    async def _process_step2(self, pdf_result: Dict, pdf_path: str, session_dirs: Dict) -> Dict:
        """
        ステップ2: LLM判定・再画像化・歪み補正処理
        
        Args:
            pdf_result (Dict): Step1のPDF変換結果
            pdf_path (str): 元PDFファイルパス
            session_dirs (Dict): セッションディレクトリ辞書
            
        Returns:
            Dict: Step2処理結果
        """
        if not self.step2_processor:
            logger.warning("Step2プロセッサーが初期化されていません。Step2処理をスキップします。")
            return {
                "success": False,
                "error": "Step2プロセッサー初期化失敗",
                "page_results": []
            }
        
        return await self.step2_processor.process_pages(pdf_result, pdf_path, session_dirs)
    
    # Step3: 回転判定・補正処理
    async def _process_step3(self, step2_result: Dict, session_dirs: Dict) -> Dict:
        """
        ステップ3: 回転判定・補正処理
        
        Args:
            step2_result (Dict): Step2処理結果
            session_dirs (Dict): セッションディレクトリ辞書
            
        Returns:
            Dict: Step3処理結果
        """
        if not self.step3_processor:
            logger.warning("Step3プロセッサーが初期化されていません。Step3処理をスキップします。")
            return {
                "success": False,
                "error": "Step3プロセッサー初期化失敗",
                "page_results": []
            }
        
        # Step2の結果からページデータを取得
        page_results = step2_result.get("page_results", [])
        if not page_results:
            logger.warning("Step3: 処理対象ページがありません")
            return {
                "success": True,
                "page_results": [],
                "message": "処理対象ページがありません"
            }
        
        return await self.step3_processor.process_pages(page_results, session_dirs)

    async def process_pdf(self, pdf_path: str, output_session_id: Optional[str] = None) -> Dict:
        """
        PDFファイルを処理するメインメソッド（Step1のみ実装）
        
        Args:
            pdf_path (str): 処理対象のPDFファイルパス
            output_session_id (str, optional): 出力セッションID
            
        Returns:
            Dict: 処理結果の詳細情報
        """
        # セッションIDの生成
        if output_session_id is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = os.path.splitext(os.path.basename(pdf_path))[0]
            output_session_id = f"{base_name}_{timestamp}"
        
        # セッション用ディレクトリの作成
        session_dirs = self.directory_manager.create_session_directories(output_session_id)
        
        # 処理結果を記録
        pipeline_result = {
            "session_id": output_session_id,
            "input_pdf": pdf_path,
            "start_time": datetime.now().isoformat(),
            "session_dirs": session_dirs,
            "steps": {},
            "final_results": {},
            "success": False
        }
        
        try:
            # ステップ1: PDF → JPG変換
            pdf_result = self._pdf_to_jpg(pdf_path, session_dirs["converted_images"])
            pipeline_result["steps"]["pdf_conversion"] = pdf_result
            
            if not pdf_result.get("success"):
                raise RuntimeError("PDF変換に失敗しました")

            # ステップ2: LLM判定・再画像化・歪み補正
            step2_result = await self._process_step2(pdf_result, pdf_path, session_dirs)
            pipeline_result["steps"]["step2_processing"] = step2_result
            
            if not step2_result.get("success"):
                logger.warning("Step2処理で一部エラーが発生しましたが、処理を続行します")
            
            # ステップ3: 回転判定・補正
            step3_result = await self._process_step3(step2_result, session_dirs)
            pipeline_result["steps"]["step3_processing"] = step3_result
            
            if not step3_result.get("success"):
                logger.warning("Step3処理で一部エラーが発生しましたが、処理を続行します")
            
            # 最終結果を設定（最後に成功したStepの結果を使用）
            if step3_result.get("success"):
                pipeline_result["final_results"] = step3_result
            elif step2_result.get("success"):
                pipeline_result["final_results"] = step2_result
            else:
                pipeline_result["final_results"] = pdf_result
            
            # パイプライン完了
            pipeline_result["success"] = True
            pipeline_result["end_time"] = datetime.now().isoformat()
            
            return pipeline_result
            
        except Exception as e:
            logger.error(f"パイプライン処理エラー: {e}")
            pipeline_result["error"] = str(e)
            pipeline_result["end_time"] = datetime.now().isoformat()
            return pipeline_result
    
    
def main():
    """
    メイン実行関数 (Step1 PDF変換対応版)
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Document OCR Pipeline - Step1 PDF変換",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python main_pipeline.py                           # pdf/内のPDFを自動検出
  python main_pipeline.py --input document.pdf     # 指定したPDFを処理
  python main_pipeline.py --config config.yml      # 設定ファイルを指定
        """
    )
    
    parser.add_argument("--config", default="config.yml", help="設定ファイルパス")
    parser.add_argument("--input", help="入力PDFファイルパス")
    parser.add_argument("--session-id", help="セッションID（省略時は自動生成）")
    
    args = parser.parse_args()
    
    try:
        # パイプライン初期化
        pipeline = DocumentOCRPipeline(args.config)
        
        # 入力PDFファイルの決定
        pdf_input = args.input
        
        if not pdf_input:
            # --inputが指定されていない場合、pdf/ディレクトリを検索
            pdf_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pdf")
            if os.path.exists(pdf_dir):
                pdf_files = [f for f in os.listdir(pdf_dir) if f.lower().endswith('.pdf')]
                if pdf_files:
                    pdf_input = os.path.join(pdf_dir, pdf_files[0])
                else:
                    print(f"❌ pdf/ディレクトリにPDFファイルが見つかりません")
                    return 1
            else:
                print("❌ --input でPDFファイルを指定するか、pdf/ディレクトリにPDFファイルを配置してください")
                return 1
        
        if not os.path.exists(pdf_input):
            print(f"❌ PDFファイルが見つかりません: {pdf_input}")
            return 1
        
        # PDF処理実行（非同期）
        result = asyncio.run(pipeline.process_pdf(pdf_input, args.session_id))
        
        # 結果表示
        if result["success"]:
            final_results = result.get("final_results", {})
        else:
            print(f"❌ 処理失敗: {result.get('error', '不明なエラー')}")
            return 1
        
        return 0
        
    except KeyboardInterrupt:
        print("\n⚠️ ユーザーによって処理が中断されました")
        return 1
    except Exception as e:
        print(f"❌ エラー: {e}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
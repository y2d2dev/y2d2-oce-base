import os
import sys
import yaml
import json
import logging
import shutil
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from dotenv import load_dotenv

# プロジェクト内モジュールのインポート
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pipeline.pdf_processor import PDFProcessor
from src.pipeline.image_splitter import ImageSplitter
from src.pipeline.llm_evaluator import LLMEvaluator
from src.dewarping.dewarping_runner import DewarpingRunner
from src.super_resolution.sr_runner import SuperResolutionRunner
from src.utils.logger import setup_logger
from src.utils.file_utils import ensure_directory, cleanup_directory
from src.utils.image_utils import split_image_left_right_with_overlap, rotate_image_correction
from src.utils.orientation_detector import OrientationDetector
import cv2
import torch

logger = logging.getLogger(__name__)


class DocumentOCRPipeline:
    """
    書類OCR前処理の統合パイプラインシステム

    process_pdf メソッドにより，パイプラインを実行する

    処理フロー:
    1. PDF → JPG変換 (DPI自動調整)
    2-1. 画像の歪み(および識別困難性の判定) (LLM)
    2-2. 最高解像度化 (必要な場合)
    2-3. 歪み補正 (必要な場合)
    3-1. 回転判定 (LLM)
    3-2. 回転補正
    4-1. ページ数等判定 (LLM)
    4-2. ページ分割 (必要な場合)
    5-1. 画像5等分 (オーバーラップ付き)
    6-1. 超解像処理 (DRCT)
    7-1. OCR実行 (LLM)
    """
    
    def __init__(self, config_path: str, processing_options: Optional[Dict] = None):
        """
        パイプライン初期化
        
        Args:
            config_path (str): 設定ファイルのパス
            processing_options (Optional[Dict]): 処理オプション
                - skip_super_resolution (bool): 超解像処理をスキップ
                - skip_ocr (bool): OCR処理をスキップ
        """
        # .envファイルの読み込み
        self._load_env()
        
        self.config_path = config_path
        self.processing_options = processing_options or {}
        self.config = self._load_config()
        self._apply_processing_options()
        self._setup_logging()
        self._initialize_components()
        self._setup_directories()
        
        logger.info("🎉 DocumentOCRPipeline 初期化完了")

    @staticmethod
    def _to_bool(v) -> bool:
        if isinstance(v, bool):
            return v
        if v is None:
            return False
        if isinstance(v, (int, float)):
            return v != 0
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("true"):
                return True
            if s in ("false"):
                return False
        return False

    @staticmethod
    def _to_int(v, default: Optional[int] = None) -> Optional[int]:
        if v is None:
            return default
        if isinstance(v, bool):
            return 1 if v else 0
        if isinstance(v, int):
            return v
        try:
            if isinstance(v, float):
                return int(v)
            s = str(v).strip()
            if s == "":
                return default
            return int(float(s))
        except Exception:
            return default

    @staticmethod
    def _to_float(v, default: Optional[float] = None) -> Optional[float]:
        if v is None:
            return default
        if isinstance(v, bool):
            return 1.0 if v else 0.0
        if isinstance(v, (int, float)):
            return float(v)
        try:
            s = str(v).strip()
            if s == "":
                return default
            return float(s)
        except Exception:
            return default
 
    def _load_env(self):
        """
        .envファイルから環境変数を読み込み
        """
        # プロジェクトルートの.envファイルを探す
        current_dir = Path(__file__).parent.parent.parent  # src/pipeline/ から project root へ
        env_path = current_dir / '.env'
        
        if env_path.exists():
            load_dotenv(env_path)
            logger.info(f".envファイルを読み込みました: {env_path}")
        else:
            logger.warning(f".envファイルが見つかりません: {env_path}")
    
    def _load_config(self) -> Dict:
        """
        設定ファイルを読み込み
        
        Returns:
            Dict: 設定データ
        """
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # 環境変数による設定の上書き
            if 'GEMINI_API_KEY' in os.environ:
                config.setdefault('llm_evaluation', {})['api_key'] = os.environ['GEMINI_API_KEY']
            
            return config
            
        except Exception as e:
            raise RuntimeError(f"設定ファイル読み込みエラー: {e}")
    
    def _apply_processing_options(self):
        """
        処理オプションを設定に適用
        """
        if self.processing_options.get('skip_super_resolution'):
            # 超解像設定を無効化
            if 'super_resolution' not in self.config:
                self.config['super_resolution'] = {}
            self.config['super_resolution']['enabled'] = False
            logger.info("⚡ 超解像処理がスキップされます")
        
        if self.processing_options.get('skip_dewarping'):
            # 歪み補正設定を無効化
            if 'dewarping' not in self.config:
                self.config['dewarping'] = {}
            self.config['dewarping']['enabled'] = False
            logger.info("⚡ 歪み補正処理がスキップされます")
        
        if self.processing_options.get('skip_ocr'):
            # OCR設定を無効化
            if 'llm_evaluation' not in self.config:
                self.config['llm_evaluation'] = {}
            self.config['llm_evaluation']['ocr_enabled'] = False
            logger.info("⚡ OCR処理がスキップされます")
    
    def _setup_logging(self):
        """
        階層構造を持つスマートなログシステムの設定
        """
        log_level = self.config.get('system', {}).get('log_level', 'INFO')
        
        # ルートロガーの設定を強制的に行う
        import logging
        import sys
        
        # 既存のハンドラーをクリア
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        
        # カスタムフォーマッターを作成
        class HierarchicalFormatter(logging.Formatter):
            """階層構造を表現するカスタムフォーマッター"""
            
            def __init__(self):
                super().__init__()
                self.component_prefixes = {
                    'src.pipeline.main_pipeline_v2': '🚀',
                    'src.pipeline.pdf_processor': '📄',
                    'src.dewarping.dewarping_runner': '🔧',
                    'src.super_resolution.sr_runner': '🔍',
                    'src.pipeline.image_splitter': '✂️',
                    'src.pipeline.llm_evaluator': '🤖',
                }
            
            def format(self, record):
                # コンポーネント名を取得
                component_name = record.name
                message = record.getMessage()
                
                # プレフィックスを決定
                prefix = None
                is_main_component = component_name.startswith('src.pipeline.main_pipeline_v2')
                
                for module_name, module_prefix in self.component_prefixes.items():
                    if component_name.startswith(module_name):
                        if is_main_component:
                            # main_pipelineの場合はプレフィックスなしでシンプルに
                            prefix = None
                        else:
                            # サブコンポーネントはインデントで表示
                            prefix = f"  {module_prefix}"
                        break
                
                # ログレベルに応じた装飾
                if record.levelno >= logging.ERROR:
                    level_icon = '❌ '
                elif record.levelno >= logging.WARNING:
                    level_icon = '⚠️ '
                else:
                    level_icon = ''
                
                # 最終的なフォーマット
                if prefix:
                    return f"{prefix} {level_icon}{message}"
                else:
                    return f"{level_icon}{message}"
        
        # コンソールハンドラーを設定
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level.upper()))
        console_handler.setFormatter(HierarchicalFormatter())
        
        root_logger.addHandler(console_handler)
        root_logger.setLevel(getattr(logging, log_level.upper()))
        
        # 子ロガーの伝播を有効にして統一フォーマットを適用
        for logger_name in ['src.pipeline', 'src.dewarping', 'src.super_resolution']:
            child_logger = logging.getLogger(logger_name)
            child_logger.propagate = True
            
        # カスタムフィルターで重複メッセージをフィルタリング
        class SuppressFilter(logging.Filter):
            def filter(self, record):
                # main_pipelineからの特定メッセージをサプレス
                if record.name.startswith('src.pipeline.main_pipeline'):
                    message = record.getMessage()
                    suppressed_patterns = [
                        'LLM歪み判定',
                        '歪み補正処理',
                        '超解像処理開始',
                    ]
                    for pattern in suppressed_patterns:
                        if pattern in message:
                            return False
                return True
                
        console_handler.addFilter(SuppressFilter())
        
        # 個別ロガーも設定（後方互換性のため）
        setup_logger(level=log_level)
    
    def _initialize_components(self):
        """
        各コンポーネントの初期化（設定辞書渡し方式）
        """
        # プロンプト設定の読み込み
        self.prompts = self._load_prompts()

        # PDF処理コンポーネント
        pdf_config = self.config.get('pdf_processing', {})
        self.pdf_processor = PDFProcessor(config=pdf_config)

        # LLM評価コンポーネントconfig
        llm_config = self.config.get('llm_evaluation', {})
        
        # LLMEvaluatorの初期化
        ## 歪み判定用LLMEvaluator
        judgment_config = llm_config.get('judgment', llm_config)
        self.llm_evaluator_judgment = LLMEvaluator(config=judgment_config)

        # OCR用LLMEvaluator
        ocr_config = llm_config.get('ocr', llm_config)
        self.llm_evaluator_ocr = LLMEvaluator(config=ocr_config)

        # 回転検出および補正コンポーネント
        # 設定キーの後方互換性: rotation | orientation_detection
        orient_cfg = self.config.get('orientation_detection', self.config.get('rotation', {}))
        self.orientation_detector = OrientationDetector(config=orient_cfg)
        
        # Orientation 用の LLM (専用設定があれば使用)
        orientation_llm_cfg = llm_config.get('orientation_judgment', llm_config)
        self.llm_evaluator_orientation = LLMEvaluator(config=orientation_llm_cfg)
        # OrientationDetector に LLM とプロンプトを関連付け
        try:
            self.orientation_detector.attach_llm_evaluator(self.llm_evaluator_orientation, self.prompts)
        except Exception as e:
            logger.warning(f"OrientationDetector の LLM 添付に失敗: {e}")

        # 歪み補正コンポーネント
        dewarping_config = self.config.get('dewarping', {})
        self.dewarping_runner = DewarpingRunner(config=dewarping_config)

        # 画像分割コンポーネント
        split_config = self.config.get('split_image_for_ocr', {})
        self.image_splitter = ImageSplitter(config=split_config)

        # 超解像コンポーネント
        sr_config = self.config.get('super_resolution', {})
        self.sr_runner = SuperResolutionRunner(config=sr_config)

    def _load_prompts(self) -> Dict:
        """
        LLMプロンプト設定を読み込み
        
        Returns:
            Dict: プロンプト設定データ
        """
        try:
            # 設定ファイルと同じディレクトリのllm_prompts.yamlを探す
            config_dir = os.path.dirname(os.path.abspath(self.config_path))
            prompts_path = os.path.join(config_dir, 'llm_prompts.yaml')
            logger.debug(f"_load_prompts: config_dir={config_dir}")
            logger.debug(f"_load_prompts: initial prompts_path={prompts_path}")
            
            if not os.path.exists(prompts_path):
                # プロジェクトルートのconfigディレクトリも確認
                project_root = Path(__file__).parent.parent.parent
                fallback_path = project_root / "config" / "llm_prompts.yaml"
                logger.debug(f"_load_prompts: project_root={project_root}")
                logger.debug(f"_load_prompts: fallback_path={fallback_path}")
                if fallback_path.exists():
                    prompts_path = str(fallback_path)
                    logger.debug(f"_load_prompts: using fallback_path={prompts_path}")
                else:
                    raise FileNotFoundError(f"llm_prompts.yaml not found in {config_dir} or {fallback_path}")
            
            with open(prompts_path, 'r', encoding='utf-8') as f:
                prompts = yaml.safe_load(f)
                logger.info(f"プロンプト設定読み込み: {prompts_path}")
                return prompts
                
        except Exception as e:
            logger.error(f"プロンプト設定読み込み失敗: {e}", exc_info=True)
            logger.info("デフォルトプロンプトを使用します")
            raise RuntimeError(f"プロンプト設定読み込みエラー: {e}")
    
    def _setup_directories(self):
        """
        作業ディレクトリの設定
        """
        self.dirs = self.config.get('directories', {})
        
        # 必要なディレクトリを作成
        for dir_key, dir_path in self.dirs.items():
            ensure_directory(dir_path)
            logger.debug(f"ディレクトリ確認: {dir_key} -> {dir_path}")

    def _create_session_directories(self, session_id: str) -> Dict[str, str]:
        """
        セッション用ディレクトリを作成
        
        Args:
            session_id (str): セッションID
            
        Returns:
            Dict[str, str]: 作成されたディレクトリのパス
        """
        base_output = self.dirs.get("output", "data/output")
        session_dirs = {}
        
        dir_names = [
            "converted_images", "llm_judgments", "dewarped", 
            "split_images", "super_resolved", "final_results"
        ]
        
        for dir_name in dir_names:
            dir_path = os.path.join(base_output, dir_name, session_id)
            ensure_directory(dir_path)
            session_dirs[dir_name] = dir_path
        
        return session_dirs    
  
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
            result = self.pdf_processor.process_pdf(pdf_path, output_dir)
            logger.info(f"PDF変換完了: {result['page_count']} ページ")
            return result
            
        except Exception as e:
            logger.error(f"PDF変換エラー: {e}")
            return {"success": False, "error": str(e)}
    
    def _dewarping_llm_judgment(self, image_path: str, output_dir: str, page_number: int) -> Dict:
        """
        ステップ2-1: LLM歪み判定&再画像化判定
        
        Args:
            image_path (str): 判定対象画像
            output_dir (str): 出力ディレクトリ
            page_number (int): ページ番号
            
        Returns:
            Dict: 判定結果
        """
        
        try:
            prompts = self.prompts.get("dewarping_judgment", {})
            result = self.llm_evaluator_judgment.evaluate_dewarping_need(image_path, prompts)
            
            # 結果を保存
            if result["success"]:
                output_file = os.path.join(output_dir, f"page_{page_number:03d}_dewarping_judgment.json")
                self.llm_evaluator_judgment.save_result(result, output_file)
            
            return result
            
        except Exception as e:
            logger.error(f"LLM判定エラー: {e}")
            return {"success": False, "error": str(e)}

    def _reprocess_page_from_pdf_at_scale(self, 
                                        page_number: int, 
                                        scale_factor: float, 
                                        output_dir: str) -> Dict:
        """
        指定されたページをPDFから指定されたスケールファクターで再画像化する。
        
        Args:
            page_number (int): 再処理するページ番号（1ベース）。
            scale_factor (float): 元のDPIに対するスケールファクター。（例: 2.0で2倍、4.0で4倍）
            output_dir (str): 再画像化された画像ファイルの出力先ディレクトリ。
            
        Returns:
            Dict: 再画像化の結果（成功/失敗、出力パスなど）。
        """
        logger.info(f"🔄 ページ {page_number} をPDFから {scale_factor}x スケールで再画像化します。")
        
        if not hasattr(self, '_current_pdf_path') or not self._current_pdf_path:
            logger.error("現在のPDFパスが設定されていません。再画像化できません。")
            return {"success": False, "error": "PDFパス未設定"}
        
        if not hasattr(self, '_current_pdf_info') or not self._current_pdf_info:
            logger.error("PDF情報が設定されていません。再画像化できません。")
            return {"success": False, "error": "PDF情報未設定"}

        try:
            # 0ベースのページインデックス
            page_idx = page_number - 1
            
            # 元のPDF情報から該当ページのDPIとサイズを取得
            original_page_info = None
            for p_info in self._current_pdf_info["pages"]:
                if p_info["page_number"] == page_number:
                    original_page_info = p_info
                    break
            
            if not original_page_info:
                logger.error(f"ページ {page_number} の元のPDF情報が見つかりません。")
                return {"success": False, "error": "ページ情報が見つかりません"}

            original_dpi = original_page_info["used_dpi"]
            new_dpi = int(original_dpi * scale_factor)
            
            # 出力ディレクトリを作成
            os.makedirs(output_dir, exist_ok=True)
            
            # 新しい出力ファイルパスを生成
            base_name = os.path.splitext(os.path.basename(self._current_pdf_path))[0]
            image_filename = f"{base_name}_page_{page_number:03d}_scaled_{int(scale_factor)}x.jpg"
            output_image_path = os.path.join(output_dir, image_filename)
            
            # PDFProcessorを使用して再変換
            converted_path = self.pdf_processor.convert_page_to_image(
                self._current_pdf_path, 
                page_idx, 
                new_dpi, 
                output_image_path
            )
            
            if converted_path and os.path.exists(converted_path):
                logger.info(f"✅ ページ {page_number} を {new_dpi} DPIで再画像化成功: {converted_path}")
                return {
                    "success": True,
                    "original_image_path": original_page_info["image_file"],
                    "reprocessed_image_path": converted_path,
                    "new_dpi": new_dpi,
                    "scale_factor": scale_factor
                }
            else:
                logger.error(f"❌ ページ {page_number} の再画像化に失敗しました。")
                return {"success": False, "error": "再画像化失敗"}

        except Exception as e:
            logger.error(f"ページ {page_number} の再画像化中にエラーが発生しました: {e}")
            return {"success": False, "error": str(e)}

    def _apply_reprocess_page(self, page_judgments: List[Dict], session_dirs: Dict[str, str]):
        """ステップ2-2: 読みにくさが major のページをPDFから2xで再画像化し、processed_image群を更新"""
        if not page_judgments:
            return
        try:
            reproc_dir = os.path.join(session_dirs.get("converted_images", ""), "reprocessed_scaled")
            os.makedirs(reproc_dir, exist_ok=True)
        except Exception:
            reproc_dir = session_dirs.get("converted_images", "")
        for i, page_data in enumerate(page_judgments, 1):
            if page_data.get("skip_processing"):
                continue
            pn = page_data.get("page_number")
            readability_issues = str(page_data.get("readability_issues", "")).lower()
            # 初期値
            if "reprocessed_at_scale" not in page_data:
                page_data["reprocessed_at_scale"] = False
            if readability_issues == "major":
                logger.info(f"  → ページ {pn}: 読みにくさ『major』のため、2倍スケールで再画像化を試行")
                try:
                    rep = self._reprocess_page_from_pdf_at_scale(pn, 2.0, reproc_dir)
                    # 結果の反映
                    if rep.get("success"):
                        new_img = rep["reprocessed_image_path"]
                        page_data["processed_image"] = new_img
                        page_data["processed_images"] = [new_img]
                        page_data["reprocessed_at_scale"] = True
                        page_data["reprocess_result"] = rep
                        logger.info("  → 2倍スケールで再画像化成功。新しい画像を使用")
                    else:
                        page_data["reprocess_result"] = rep
                        logger.warning("  → 2倍スケールでの再画像化失敗。元画像を使用")
                except Exception as e:
                    logger.warning(f"  → 再画像化処理中にエラー: {e}")
                    page_data["reprocessed_at_scale"] = False
            else:
                # major 以外は何もしない
                continue
    
    def _step_dewarping(self, image_path: str, output_dir: str, page_number: int) -> Dict:
        """
        ステップ2-2: 歪み補正
        
        Args:
            image_path (str): 補正対象画像
            output_dir (str): 出力ディレクトリ
            page_number (int): ページ番号
            
        Returns:
            Dict: 補正結果
        """
        # 歪み補正処理（詳細はDewarpingRunnerで出力）
        
        try:
            output_file = os.path.join(output_dir, f"page_{page_number:03d}_dewarped.jpg")
            result = self.dewarping_runner.process_image(image_path, output_file)
            return result
            
        except Exception as e:
            logger.error(f"歪み補正エラー: {e}")
            return {"success": False, "error": str(e)}

    def _apply_dewarping(self, page_judgments: List[Dict], session_dirs: Dict[str, str]):
        """
        ステップ2-2: 歪み補正
        """
        # 歪み補正が無効化されている場合、処理をスキップ
        if not self.config.get('dewarping', {}).get('enabled', True):
            logger.info("⚡ 歪み補正処理が設定によりスキップされました")
            # スキップされたことを示す結果を各ページデータに設定
            for page_data in page_judgments:
                # processed_images が存在しない場合、original_image を使用
                if "processed_images" not in page_data or not page_data["processed_images"]:
                    page_data["processed_images"] = [page_data["processed_image"]]
                page_data["dewarping_result"] = {"success": True, "skipped": True, "reason": "dewarping_disabled_by_config"}
                logger.info(f"  → ページ {page_data['page_number']}: 歪み補正スキップ (設定による)")
            return

        dewarping_needed_pages = [p for p in page_judgments if p.get("needs_dewarping") and not p.get("skip_processing")]
        if not dewarping_needed_pages:
            return

        logger.info(f"🔧 歪み補正処理: {len(dewarping_needed_pages)}ページ対象")
        for i, page_data in enumerate(dewarping_needed_pages, 1):
            page_number = page_data["page_number"]
            image_path = page_data["processed_image"]
            page_count = page_data.get("page_count", 1)
            
            # 3ページの場合は強制歪み補正であることを明示
            if page_count >= 3:
                logger.info(f"🔧 歪み補正 ({i}/{len(dewarping_needed_pages)}) ページ{page_number} [3ページ判定による強制補正]")
            else:
                logger.info(f"🔧 歪み補正 ({i}/{len(dewarping_needed_pages)}) ページ{page_number}")
            dewarping_result = self._step_dewarping(image_path, session_dirs["dewarped"], page_number)
            page_data["dewarping_result"] = dewarping_result
            
            if dewarping_result["success"] and not dewarping_result.get("skipped", False) and dewarping_result.get("output_paths"):
                page_data["processed_images"] = dewarping_result["output_paths"]
                page_data["processed_image"] = dewarping_result["output_paths"][0]
                
                # 3ページ判定で歪み補正した場合の結果を明示
                if page_count >= 3:
                    num_images = len(dewarping_result['output_paths'])
                    if num_images == 1:
                        logger.info(f"  → ✅補正完了: 1ページに分割（3ページ判定→1ページに補正）")
                    elif num_images == 2:
                        logger.info(f"  → ✅補正完了: 2ページに分割（3ページ判定→2ページに補正）")
                    else:
                        logger.info(f"  → ✅補正完了: {num_images}個の画像生成")
                else:
                    logger.info(f"  → ✅補正完了: {len(dewarping_result['output_paths'])}個の画像生成")
            else:
                logger.info(f"  → ⚠️補正スキップ/失敗 (前処理画像使用)")

            if hasattr(self, 'dewarping_runner') and torch.cuda.is_available():
                torch.cuda.empty_cache()

    def _apply_orientation_detector(self, page_judgments: List[Dict], session_dirs: Dict[str, str]):
        """
        ステップ3-1: 回転判定および補正
        """
        if not page_judgments:
            return
        # 生成物の保存先（デバッグ対比用）: llm_judgments配下に集約
        try:
            root_debug_dir = session_dirs.get("llm_judgments", session_dirs["converted_images"])
            os.makedirs(root_debug_dir, exist_ok=True)
            # OrientationDetector 側の保存先ルート（orientation_pairs, orientation_debugを自動管理）
            self.orientation_detector.debug_save_dir = root_debug_dir
        except Exception:
            pass

        logger.info("🧭 回転判定および補正を適用")
        for i, page_data in enumerate(page_judgments, 1):
            if page_data.get("skip_processing"):
                continue
            page_number = page_data["page_number"]
            proc_images = page_data.get("processed_images") or [page_data.get("processed_image")]
            if not proc_images:
                continue
            new_paths: List[str] = []
            for img_idx, img_path in enumerate(proc_images):
                try:

                    det = self.orientation_detector.detect(img_path, add_star=True, temp_dir=None, use_llm=True) # ここで LLM を使用して回転方向を検出
                    angle = det.angle
                    if angle == 0:
                        logger.info(f"  ↪️ ページ{page_number} 画像{img_idx+1}: 回転不要")
                        new_paths.append(img_path)
                        continue
                    # 画像を回転して保存
                    img = cv2.imread(img_path)
                    if img is None:
                        logger.warning(f"  ↪️ ページ{page_number} 画像{img_idx+1}: 画像読み込み失敗 (回転スキップ)")
                        new_paths.append(img_path)
                        continue
                    if angle == 90:
                        rotated = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
                    elif angle == -90:
                        rotated = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
                    elif angle in (180, -180):
                        rotated = cv2.rotate(img, cv2.ROTATE_180)
                    else:
                        rotated = img
                    base, ext = os.path.splitext(img_path)
                    out_path = f"{base}_rot{ext or '.jpg'}"
                    cv2.imwrite(out_path, rotated)
                    logger.info(f"  ↪️ ページ{page_number} 画像{img_idx+1}: {angle}度回転 → {os.path.basename(out_path)}")
                    new_paths.append(out_path)
                except Exception as e:
                    logger.warning(f"  ↪️ ページ{page_number} 画像{img_idx+1}: 回転処理エラー {e}")
                    new_paths.append(img_path)
            # 更新
            page_data["processed_images"] = new_paths
            page_data["processed_image"] = new_paths[0]

    def _page_count_etc_llm_judgment(self, image_path: str, output_dir: str, page_number: int, image_index: Optional[int] = None) -> Dict:
        """
        ステップ4-1: ページ数等判定（LLM）
        
        Args:
            image_path (str): 判定対象画像
            output_dir (str): 出力ディレクトリ
            page_number (int): ページ番号
            image_index (Optional[int]): 画像インデックス（複数画像の場合）
            
        Returns:
            Dict: 判定結果
        """
        try:
            prompts = self.prompts.get("page_count_etc_judgment", {})
            # Fix: evaluate_page_count only expects (image_path, prompts)
            result = self.llm_evaluator_judgment.evaluate_page_count(image_path, prompts)
            
            # 結果を保存（複数画像の場合の上書き回避のため image_index を付与）
            if result["success"]:
                if image_index is not None:
                    output_file = os.path.join(output_dir, f"page_{page_number:03d}_page_count_img{image_index+1}.json")
                else:
                    output_file = os.path.join(output_dir, f"page_{page_number:03d}_page_count.json")
                self.llm_evaluator_judgment.save_result(result, output_file)
        
            return result
            
        except Exception as e:
            logger.error(f"ページ数等判定エラー: {e}")
            return {"success": False, "error": str(e)}

    def _apply_page_count_etc_judgment(self, page_judgments: List[Dict], session_dirs: Dict[str, str]) -> Dict[str, Dict]:
        """
        ステップ4-1: ページ数等判定（分割前、必要に応じて複数画像を集約）
        各ページの代表/派生画像に対して判定を実施し、マージした結果を返す。

        Returns:
            Dict[str, Dict]: {"page_XXX_page_count": {merged, individual, success}}
        """
        results_map: Dict[str, Dict] = {}
        for page_data in page_judgments:
            pn = page_data["page_number"]
            proc_images = page_data.get("processed_images") or [page_data.get("processed_image")]
            logger.info(f"🔍 ステップ4-1: LLMページ数判定 ページ{pn} ({len(proc_images)}画像)")
            individual_results: List[Dict] = []
            for idx, img_path in enumerate(proc_images):
                r = self._page_count_etc_llm_judgment(img_path, session_dirs["llm_judgments"], pn, image_index=(idx if len(proc_images) > 1 else None))
                individual_results.append(r)

            # マージロジック
            bool_or_fields = ["has_table_elements", "has_handwritten_notes_or_marks"]
            merged_bools: Dict[str, str] = {}
            for key in bool_or_fields:
                acc = False
                for res in individual_results:
                    j = (res or {}).get("judgment", {})
                    if key in j:
                        acc = acc or self._to_bool(j.get(key))
                merged_bools[key] = "True" if acc else "False"

            # page_count は加算し、最大3にクランプ
            merged_page_count = 0
            page_count_conf_list: List[float] = []
            conf_list: List[float] = []
            readability_comments: List[str] = []
            overall_comments: List[str] = []
            order = {"none": 0, "minor": 1, "major": 2}
            rev_order = {v: k for k, v in order.items()}
            worst_val = -1
            for i, res in enumerate(individual_results, 1):
                j = (res or {}).get("judgment", {})
                pc = self._to_int(j.get("page_count"))
                try:
                    merged_page_count += pc if pc is not None else 0
                except Exception:
                    pass
                pc_conf = self._to_float(j.get("page_count_confidence"))
                if pc_conf is not None:
                    page_count_conf_list.append(pc_conf)
                conf_v = self._to_float(j.get("confidence_score"))
                if conf_v is not None:
                    conf_list.append(conf_v)
                rc = j.get("readability_comment")
                if rc:
                    readability_comments.append(f"page{i}のコメント: {rc}")
                oc = j.get("overall_comment")
                if oc:
                    overall_comments.append(f"page{i}のコメント: {oc}")
                ri = str(j.get("readability_issues", "")).lower()
                if ri in order:
                    worst_val = max(worst_val, order[ri])

            # クランプ
            if merged_page_count <= 0:
                merged_page_count = 1
            if merged_page_count > 3:
                merged_page_count = 3
            avg_pc_conf = sum(page_count_conf_list) / len(page_count_conf_list) if page_count_conf_list else None
            avg_conf = sum(conf_list) / len(conf_list) if conf_list else None

            merged_judgment = {
                **merged_bools,
                "page_count": merged_page_count,
                "page_count_confidence": round(avg_pc_conf, 3) if avg_pc_conf is not None else None,
                "confidence_score": round(avg_conf, 3) if avg_conf is not None else None,
                "readability_issues": rev_order.get(worst_val, "none") if worst_val >= 0 else "none",
                "readability_comment": "\n".join(readability_comments) if readability_comments else None,
                "overall_comment": "\n".join(overall_comments) if overall_comments else None,
            }

            results_map[f"page_{pn:03d}_page_count"] = {
                "success": True,
                "merged": merged_judgment,
                "individual": individual_results,
            }

            # 後続処理のために page_count を保存
            try:
                page_data["page_count"] = int(merged_judgment.get("page_count", 1))
            except Exception:
                page_data["page_count"] = 1

        return results_map

    def _apply_page_splits(self, page_judgments: List[Dict], session_dirs: Dict[str, str]):
        """
        ステップ4-2: page_count=2 の場合の強制左右分割
        """
        logger.info("✂️ ステップ 4-2: page_count=2 強制分割チェック")
        for i, page_data in enumerate(page_judgments, 1):
            if page_data.get("page_count") == 2 and not page_data.get("skip_processing") and len(page_data.get("processed_images", [])) == 1:
                page_number = page_data["page_number"]
                logger.info(f"🔄 強制分割対象 ({i}/{len(page_judgments)}) ページ{page_number}")
                try:
                    image_to_split = page_data["processed_images"][0]
                    image = cv2.imread(image_to_split)
                    if image is None:
                        raise IOError(f"画像読み込み失敗: {image_to_split}")

                    forced_split_output_dir = os.path.join(session_dirs["dewarped"], "forced_split")
                    os.makedirs(forced_split_output_dir, exist_ok=True)
                    base_filename = f"page_{page_number:03d}_forced"

                    left_path, right_path = split_image_left_right_with_overlap(
                        image=image, overlap_ratio=0.1, output_dir=forced_split_output_dir, base_filename=base_filename
                    )

                    page_data["processed_images"] = [left_path, right_path]
                    page_data["processed_image"] = left_path
                    page_data["forced_split_applied"] = True
                    logger.info(f"  → ✅強制分割完了: 2個の画像生成")
                except Exception as e:
                    logger.error(f"  → ❌強制分割エラー: {e}")
                    page_data["forced_split_applied"] = False

    def _image_splitting_for_ocr(self, image_path: str, output_dir: str, page_number: int) -> Dict:
        """
        ステップ5: 画像5等分
        """
        logger.info(f"ページ {page_number}: 画像分割処理")
        try:
            base_name = f"page_{page_number:03d}"
            page_output_dir = os.path.join(output_dir, base_name)
            result = self.image_splitter.split_and_save(image_path, page_output_dir, base_name)
            return result
        except Exception as e:
            logger.error(f"画像分割エラー: {e}")
            return {"success": False, "error": str(e)}

    def _apply_image_split_for_ocr(self, page_judgments: List[Dict], session_dirs: Dict[str, str]) -> List[Dict]:
        """
        ステップ5: OCR用の画像分割（歪み補正後の各画像に対して）
        """
        logger.info("✂️ ステップ 5: 全ページ画像分割（ページ数対応）")
        all_split_images: List[Dict] = []
        for i, page_data in enumerate(page_judgments, 1):
            page_number = page_data["page_number"]
            logger.info(f"✂️ 画像分割 ({i}/{len(page_judgments)}) ページ{page_number}")
            processed_images = page_data.get("processed_images", [])
            split_results_by_source: List[Dict] = []
            for img_idx, proc_image_path in enumerate(processed_images):
                if len(processed_images) > 1:
                    logger.info(f"  📄 歪み補正画像 {img_idx + 1}/{len(processed_images)} を分割処理")
                base_name = f"page_{page_number:03d}_mask{img_idx + 1}"
                split_output_dir = os.path.join(session_dirs["split_images"], base_name)
                split_result = self._image_splitting_for_ocr(proc_image_path, split_output_dir, page_number)
                split_result["source_dewarped_image"] = proc_image_path
                split_result["source_mask_index"] = img_idx
                split_results_by_source.append(split_result)

            page_data["split_results_by_source"] = split_results_by_source

            total_split_images = 0
            for source_idx, split_result in enumerate(split_results_by_source):
                if split_result.get("success"):
                    split_images = split_result.get("split_paths", [])
                    total_split_images += len(split_images)
                    for img_path in split_images:
                        all_split_images.append({
                            "page_number": page_number, "image_path": img_path, "image_type": "split",
                            "source_mask_index": source_idx, "source_dewarped_image": split_result["source_dewarped_image"]
                        })
            logger.info(f"  → ✅合計{total_split_images}個の分割画像生成")

            # 元画像（歪み補正後の各画像）をOCRグループのメイン画像として追加
            for source_idx, split_result in enumerate(split_results_by_source):
                if split_result.get("success"):
                    original_path = split_result.get("original_path")
                    if original_path:
                        all_split_images.append({
                            "page_number": page_number, "image_path": original_path, "image_type": "original",
                            "source_mask_index": source_idx, "source_dewarped_image": split_result["source_dewarped_image"]
                        })
        return all_split_images

    def _group_images_for_ocr(self, all_processed_images: List[Dict]) -> List[Dict]:
        """超解像済みの画像をOCRジョブのグループにまとめる"""
        groups: Dict[Tuple[int,int], Dict] = {}
        for img_info in all_processed_images:
            page_number = img_info["page_number"]
            mask_index = img_info.get("source_mask_index", -1)
            group_key = (page_number, mask_index)
            if group_key not in groups:
                groups[group_key] = {
                    "page_number": page_number,
                    "mask_index": mask_index,
                    "original_image": None,
                    "split_images": []
                }
            image_type = img_info["image_type"]
            output_path = img_info.get("output_path", img_info["image_path"])
            if image_type == "original":
                groups[group_key]["original_image"] = output_path
            elif image_type == "split":
                groups[group_key]["split_images"].append(output_path)
        ocr_jobs: List[Dict] = []
        for group_key, group_data in sorted(groups.items()):
            image_paths: List[str] = []
            if group_data["original_image"]:
                image_paths.append(group_data["original_image"])
            image_paths.extend(sorted(group_data["split_images"]))
            ocr_jobs.append({
                "page_number": group_data["page_number"],
                "mask_index": group_data["mask_index"],
                "image_paths": image_paths
            })
        return ocr_jobs

    def _create_skip_super_resolution_result(self, phase1_result: Dict) -> Dict:
        """
        超解像スキップ時の結果を作成（元画像をそのまま使用）
        """
        all_images = phase1_result.get("all_images_for_sr", [])
        processed_images: List[Dict] = []
        for img_info in all_images:
            processed_images.append({
                **img_info,
                "success": True,
                "skipped": True,
                "skip_reason": "super_resolution_disabled",
                "output_path": img_info["image_path"]
            })
        logger.info(f"⚡ 超解像スキップ: {len(all_images)}個の画像を元画像のまま使用")
        return {
            "success": True,
            "total_images_processed": len(all_images),
            "successful_sr": 0,
            "skipped": True,
            "all_processed_images": processed_images
        }

    def _batch_super_resolution(self, phase1_result: Dict, session_dirs: Dict[str, str]) -> Dict:
        """
        フェーズ2: 全画像のバッチ超解像処理
        
        Args:
            phase1_result (Dict): フェーズ1の結果
            session_dirs (Dict[str, str]): セッションディレクトリ
            
        Returns:
            Dict: 超解像処理結果
        """
        logger.info("🔍 === フェーズ2: バッチ超解像処理 ===")
        
        # 超解像処理がスキップされる場合
        if not self.config.get('super_resolution', {}).get('enabled', True):
            logger.info("⚡ 超解像処理をスキップします")
            return self._create_skip_super_resolution_result(phase1_result)
        
        all_images = phase1_result.get("all_images_for_sr", [])
        split_images_to_process = [img for img in all_images if img["image_type"] == "split"]
        
        logger.info(f"🎯 超解像対象: {len(split_images_to_process)} 個の分割画像")
        
        sr_results = []
        success_count = 0
        
        for i, img_info in enumerate(split_images_to_process, 1):
            page_number = img_info["page_number"]
            image_path = img_info["image_path"]
            
            image_name = os.path.splitext(os.path.basename(image_path))[0]
            # マスク情報に基づいて出力ディレクトリを決定
            source_mask_index = img_info.get("source_mask_index", 0)
            base_name = f"page_{page_number:03d}_mask{source_mask_index + 1}"
            output_dir = os.path.join(session_dirs["super_resolved"], base_name)
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"{image_name}_sr.jpg")

            try:
                if hasattr(self.sr_runner, 'clear_cuda_cache'):
                    self.sr_runner.clear_cuda_cache()
                
                logger.info(f"🔄 超解像 ({i}/{len(split_images_to_process)}) ページ{page_number} - {os.path.basename(image_path)}")
                sr_result = self.sr_runner.process_image(image_path, output_path)
                
                # 元の画像情報を引き継ぐ
                sr_result.update(img_info)
                sr_results.append(sr_result)
                
                if sr_result["success"]:
                    success_count += 1
                    if not sr_result.get("skipped"):
                        logger.info(f"  → ✅超解像成功")
                else:
                    logger.warning(f"  → ❌超解像失敗: {sr_result.get('error', 'unknown')}")
                    shutil.copy2(image_path, output_path)

            except Exception as e:
                logger.error(f"  → 💥超解像エラー: {e}")
                shutil.copy2(image_path, output_path)
                sr_results.append({
                    **img_info,
                    "success": False, "error": str(e), "fallback_copy": True
                })

        # 超解像されなかった「オリジナル」画像の情報も結果に含める
        original_images = [img for img in all_images if img["image_type"] == "original"]
        for img_info in original_images:
            sr_results.append({
                **img_info,
                "success": True, "skipped": True, "skip_reason": "original_image_not_processed",
                "output_path": img_info["image_path"]
            })

        result = {
            "success": True,
            "total_images_processed": len(split_images_to_process),
            "successful_sr": success_count,
            "all_processed_images": sr_results
        }
        
        logger.info(f"✅ フェーズ2完了: 超解像{success_count}/{len(split_images_to_process)}成功")
        return result

    def _batch_ocr(self, phase2_result: Dict, session_dirs: Dict[str, str]) -> Dict:
        """
        フェーズ3: バッチOCR処理
        
        Args:
            phase2_result (Dict): フェーズ2の結果
            session_dirs (Dict[str, str]): セッションディレクトリ
            
        Returns:
            Dict: OCR処理結果
        """
        logger.info("📝 === フェーズ3: バッチOCR処理 ===")
        
        # OCR処理がスキップされる場合
        if not self.config.get('llm_evaluation', {}).get('ocr_enabled', True):
            logger.info("⚡ OCR処理をスキップします")
            return self._create_skip_ocr_result(phase2_result)
        
        all_processed_images = phase2_result.get("all_processed_images", [])
        
        # OCRジョブをグループ化
        ocr_jobs = self._group_images_for_ocr(all_processed_images)
        
        # 契約書モードかどうかをチェック（デフォルトTrue）
        is_contract_mode = self.config.get('ocr', {}).get('contract_mode', True)
        
        ocr_results = []
        
        if is_contract_mode:
            # 契約書モード：全ページを一度に処理
            logger.info(f"📝 契約書OCR: 全{len(ocr_jobs)}ジョブを統合処理")
            
            # 全ページの画像を収集
            all_images = []
            for job in ocr_jobs:
                all_images.extend(job["image_paths"])
            
            logger.info(f"    📊 全画像数: {len(all_images)}枚")
            
            try:
                if not all_images:
                    raise ValueError("OCR対象画像がありません")
                
                # 全ページを一度に契約書OCR処理
                ocr_prompts = self.prompts.get("multi_image_ocr", self.prompts.get("ocr_extraction", {}))
                contract_result = self.llm_evaluator_ocr.extract_contract_ocr_multi_images(all_images, ocr_prompts)
                
                contract_result.update({
                    "page_count": len(ocr_jobs),
                    "total_images": len(all_images),
                    "processing_mode": "contract_unified"
                })
                ocr_results.append(contract_result)
                
                if contract_result.get("success"):
                    logger.info(f"    → ✅契約書OCR統合処理成功")
                else:
                    logger.warning(f"    → ❌契約書OCR統合処理失敗: {contract_result.get('error', 'unknown')}")
                    
            except Exception as e:
                logger.error(f"    → 💥契約書OCRエラー: {e}")
                ocr_results.append({
                    "success": False, "error": str(e),
                    "processing_mode": "contract_unified"
                })
        
        else:
            # 通常モード：ページごとに処理
            for i, job in enumerate(ocr_jobs, 1):
                page_number = job["page_number"]
                mask_index = job["mask_index"]
                image_paths = job["image_paths"]
                
                logger.info(f"📝 OCRジョブ ({i}/{len(ocr_jobs)}) ページ{page_number}, マスク{mask_index + 1}")
                logger.info(f"    📊 OCR対象: {len(image_paths)}枚")

                try:
                    if not image_paths:
                        raise ValueError("OCR対象画像がありません")

                    # 通常のOCR
                    ocr_prompts = self.prompts.get("multi_image_ocr", self.prompts.get("ocr_extraction", {}))
                    ocr_result = self.llm_evaluator_ocr.extract_text_ocr_multi_images(image_paths, ocr_prompts)
                    
                    ocr_result.update({
                        "page_number": page_number,
                        "mask_index": mask_index,
                        "group_type": "dewarped_mask" if mask_index != -1 else "no_dewarping",
                        "num_images": len(image_paths)
                    })
                    ocr_results.append(ocr_result)

                    if ocr_result.get("success"):
                        logger.info(f"    → ✅OCR成功")
                    else:
                        logger.warning(f"    → ❌OCR失敗: {ocr_result.get('error', 'unknown')}")

                except Exception as e:
                    logger.error(f"    → 💥OCRエラー: {e}")
                    ocr_results.append({
                        "success": False, "error": str(e),
                        "page_number": page_number, "mask_index": mask_index
                    })

        successful_ocr = len([r for r in ocr_results if r.get("success")])
        result = {
            "success": successful_ocr > 0,
            "total_jobs": len(ocr_jobs),
            "successful_ocr": successful_ocr,
            "ocr_results": ocr_results
        }
        
        logger.info(f"✅ フェーズ3完了: {successful_ocr}/{len(ocr_jobs)}ジョブ成功")
        return result
    
    def _save_pipeline_result(self, result: Dict, output_dir: str):
        """パイプライン結果をJSON保存"""
        try:
            result_path = os.path.join(output_dir, "pipeline_result.json")
            with open(result_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            logger.info(f"💾 パイプライン結果保存: {os.path.basename(result_path)}")
        except Exception as e:
            logger.error(f"結果保存エラー: {e}")

    def _cleanup_temp_files(self, session_dirs: Dict[str, str]):
        """一時ファイルのクリーンアップ"""
        if not self.config.get('debug', {}).get('skip_cleanup', False):
            temp_dir = self.config.get('system', {}).get('temp_dir')
            if temp_dir and os.path.exists(temp_dir):
                cleanup_directory(temp_dir)
                logger.info("🧹 一時ファイルクリーンアップ完了")

        # === 追加: LLM出力の型解釈ユーティリティをクラス全体で利用可能に ===

    def process_pdf(self, pdf_path: str, output_session_id: Optional[str] = None) -> Dict:
        """
        PDFファイルを処理するメインメソッド
        
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
        
        logger.info(f"🚀 === PDF処理開始: {os.path.basename(pdf_path)} ===")
        logger.info(f"🏷️ セッションID: {output_session_id}")
        
        # セッション用ディレクトリの作成
        session_dirs = self._create_session_directories(output_session_id)
        
        # 処理結果を記録
        pipeline_result = {
            "session_id": output_session_id,
            "input_pdf": pdf_path,
            "start_time": datetime.now().isoformat(),
            "session_dirs": session_dirs,
            "steps": {
                "llm_judgments": {},
            },
            "final_results": {},
            "success": False
        }
        
        try:
            # 現在のPDFパスを保存
            self._current_pdf_path = pdf_path

            # ステップ1: PDF → JPG変換
            logger.info("📄 ステップ1: PDF → JPG変換")
            pdf_result = self._pdf_to_jpg(pdf_path, session_dirs["converted_images"])
            pipeline_result["steps"]["pdf_conversion"] = pdf_result
            # PDF変換結果を保存（各ページのDPI情報を含む）
            self._current_pdf_info = pdf_result
            
            if not pdf_result.get("success"):
                raise RuntimeError("PDF変換に失敗しました")

            # ページ配列
            pages = [p for p in pdf_result.get("pages", []) if p.get("success")]
            if not pages:
                raise RuntimeError("変換成功ページがありません")

            # 各ページの初期データ
            page_judgments: List[Dict] = []
            for p in pages:
                pn = p["page_number"]
                orig_img = p["image_file"]
                page_rec = {
                    "page_number": pn,
                    "original_image": orig_img,
                    "processed_image": orig_img,
                    "processed_images": [orig_img],
                    "skip_processing": False
                }
                # ステップ2-1: 歪み判定（記録のみ、判断は後続で使用）
                logger.info(f"🔍 ステップ2-1: LLM歪み判定 ページ{pn}")
                judge_res = self._dewarping_llm_judgment(orig_img, session_dirs["llm_judgments"], pn)
                pipeline_result["steps"]["llm_judgments"][f"page_{pn:03d}_dewarp"] = judge_res
                j = (judge_res or {}).get("judgment", {})
                needs_dewarping = self._to_bool(j.get("needs_dewarping")) or self._to_bool(j.get("has_something_out_of_document"))
                readability_issues = str(j.get("readability_issues", "")).lower()
                page_rec["readability_issues"] = readability_issues
                page_rec["reprocessed_at_scale"] = False
                page_rec["needs_dewarping"] = needs_dewarping
                page_judgments.append(page_rec)
        
            # ステップ2-2: 2x再画像化(読みにくさが majorの場合)
            self._apply_reprocess_page(page_judgments, session_dirs)

            # ステップ2-3: 歪み補正（必要に応じて）
            self._apply_dewarping(page_judgments, session_dirs)

            # ステップ3-1: 回転判定および補正
            self._apply_orientation_detector(page_judgments, session_dirs)

            # ステップ4-1: ページ数等判定
            pagecount_results = self._apply_page_count_etc_judgment(page_judgments, session_dirs)
            pipeline_result["steps"]["llm_judgments"].update(pagecount_results)

            # ステップ4-2: page_count=2 の場合の強制左右分割
            self._apply_page_splits(page_judgments, session_dirs)

            # ステップ5: OCR用の画像分割
            all_images_for_sr = self._apply_image_split_for_ocr(page_judgments, session_dirs)

            # ステップ6: 超解像（設定によるスキップ対応）
            phase1_like = {"all_images_for_sr": all_images_for_sr}
            if not self.config.get('super_resolution', {}).get('enabled', True):
                sr_result = self._create_skip_super_resolution_result(phase1_like)
            else:
                sr_result = self._batch_super_resolution(phase1_like, session_dirs)
            pipeline_result["steps"]["super_resolution"] = sr_result

            # ステップ7: OCR（設定によるスキップ対応）
            if not self.config.get('llm_evaluation', {}).get('ocr_enabled', True):
                ocr_result = self._create_skip_ocr_result(sr_result)
            else:
                ocr_result = self._batch_ocr(sr_result, session_dirs)
            pipeline_result["final_results"] = ocr_result

            pipeline_result["success"] = True
            pipeline_result["end_time"] = datetime.now().isoformat()

        except Exception as e:
            logger.error(f"パイプライン処理エラー: {e}")
            pipeline_result["error"] = str(e)
            pipeline_result["end_time"] = datetime.now().isoformat()
        
        # 結果を保存
        self._save_pipeline_result(pipeline_result, session_dirs["final_results"])
        
        # 一時ファイルのクリーンアップ
        if self.config.get('system', {}).get('cleanup_temp', True):
            self._cleanup_temp_files(session_dirs)
        
        return pipeline_result
    
def main():
    """
    メイン実行関数
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Document OCR Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
            使用例:
            python main_pipeline.py --input document.pdf
            python main_pipeline.py --input document.pdf --config config/config_test.yaml
            python main_pipeline.py --input document.pdf --session-id my_session
                    """
                )
    
    # プロジェクトルートからの絶対パス設定
    project_root = Path(__file__).parent.parent.parent
    default_config = project_root / "config" / "config.yaml"
    
    parser.add_argument(
        "--config", 
        default=str(default_config), 
        help=f"設定ファイルパス (デフォルト: {default_config})"
    )
    parser.add_argument(
        "--input",
        help="入力PDFファイルパス（省略時はサンプル実行）"
    )
    parser.add_argument(
        "--session-id", 
        help="セッションID（省略時は自動生成）"
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="サンプル画像でテスト実行"
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="設定ファイルと依存関係をチェックして終了"
    )
    
    args = parser.parse_args()
    
    try:
        # 設定ファイル存在チェック
        if not os.path.exists(args.config):
            # デフォルト設定ファイルが見つからない場合の対処
            config_test_path = project_root / "config" / "config_test.yaml"
            if config_test_path.exists():
                print(f"⚠️ デフォルト設定ファイルが見つかりません: {args.config}")
                print(f"📋 テスト用設定ファイルを使用します: {config_test_path}")
                args.config = str(config_test_path)
            else:
                print(f"❌ 設定ファイルが見つかりません: {args.config}")
                print(f"📋 利用可能な設定ファイル:")
                config_dir = project_root / "config"
                if config_dir.exists():
                    for config_file in config_dir.glob("*.yaml"):
                        print(f"   - {config_file}")
                else:
                    print(f"   設定ディレクトリが存在しません: {config_dir}")
                print(f"\n💡 サンプル実行を試す場合: python {Path(__file__).name} --sample")
                return 1
        
        # パイプライン初期化
        pipeline = DocumentOCRPipeline(args.config)
        
        # 設定チェックモード
        if args.check_config:
            print("✅ 設定ファイル読み込み成功")
            print("✅ パイプライン初期化成功")
            print("📋 設定内容:")
            for component, config in pipeline.config.items():
                if isinstance(config, dict):
                    print(f"   {component}: {len(config)} items")
                else:
                    print(f"   {component}: {config}")
            return 0
        
        # 入力ファイルの決定
        if args.sample:
            # サンプル実行モード
            print("🧪 サンプル画像でテスト実行を開始します")
            input_path = _create_sample_pdf(project_root)
            if not input_path:
                print("❌ サンプルPDF作成に失敗しました")
                return 1
            print(f"📄 サンプルPDF作成: {input_path}")
        elif args.input:
            # 指定ファイル使用
            input_path = args.input
            if not os.path.exists(input_path):
                print(f"❌ 入力PDFファイルが見つかりません: {input_path}")
                print(f"💡 サンプル実行を試す場合: python {Path(__file__).name} --sample")
                return 1
        else:
            # 入力ファイル自動検索
            input_dir = project_root / "data" / "input"
            if input_dir.exists():
                pdf_files = list(input_dir.glob("*.pdf"))
                if pdf_files:
                    input_path = str(pdf_files[0])
                    print(f"📄 自動検出PDFファイル: {os.path.basename(input_path)}")
                else:
                    print(f"❌ data/input/ にPDFファイルが見つかりません")
                    print(f"💡 以下のオプションを試してください:")
                    print(f"   - PDFファイルを data/input/ に配置")
                    print(f"   - --input でファイルパス指定")
                    print(f"   - --sample でサンプル実行")
                    return 1
            else:
                print(f"❌ 入力ディレクトリが存在しません: {input_dir}")
                print(f"💡 サンプル実行を試す場合: python {Path(__file__).name} --sample")
                return 1
        
        print(f"🚀 PDF処理開始: {os.path.basename(input_path)}")
        
        # PDF処理実行
        result = pipeline.process_pdf(input_path, args.session_id)
        
        # 結果表示
        if result["success"]:
            print(f"✅ 処理完了: セッションID {result['session_id']}")
            final_results = result.get("final_results", {})
            if final_results.get("success"):
                print(f"📝 最終テキスト: {final_results['final_text_path']}")
                print(f"📊 処理ページ数: {len(final_results['successful_pages'])}")
            else:
                print(f"⚠️ 一部処理で問題が発生しましたが、部分的に完了しました")
        else:
            print(f"❌ 処理失敗: {result.get('error', '不明なエラー')}")
            return 1
            
        return 0
            
    except KeyboardInterrupt:
        print("\n⚠️ ユーザーによって処理が中断されました")
        return 1
    except Exception as e:
        logger.error(f"メイン処理エラー: {e}")
        print(f"❌ エラー: {e}")
        print(f"💡 詳細はログを確認してください")
        return 1

def _create_sample_pdf(project_root: Path) -> Optional[str]:
    """
    サンプルPDFファイルを作成
    
    Args:
        project_root (Path): プロジェクトルート
        
    Returns:
        Optional[str]: 作成されたPDFファイルのパス
    """
    try:
        from PIL import Image, ImageDraw
        import tempfile
        
        # サンプル画像作成
        img = Image.new('RGB', (2100, 2970), color='white')  # A4サイズ相当
        draw = ImageDraw.Draw(img)
        
        # タイトル
        draw.text((100, 100), "Document OCR Pipeline Test PDF", fill='black')
        draw.text((100, 200), "Generated for main_pipeline.py testing", fill='gray')
        
        # コンテンツ
        y_pos = 400
        sample_content = [
            "Chapter 1: Introduction",
            "",
            "This is a sample PDF document created for testing",
            "the Document OCR Pipeline system. The system",
            "processes PDF files through the following steps:",
            "",
            "1. PDF to JPG conversion with DPI optimization",
            "2. LLM-based distortion judgment",
            "3. YOLO-based document dewarping",
            "4. Image split_image_5parts with overlap",
            "5. DRCT super-resolution processing",
            "6. Multi-image batch OCR",
            "7. Final text integration",
            "",
            "Chapter 2: Test Content",
            "",
            "Lorem ipsum dolor sit amet, consectetur",
            "adipiscing elit. Sed do eiusmod tempor",
            "incididunt ut labore et dolore magna aliqua.",
            "",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        ]
        
        for line in sample_content:
            draw.text((100, y_pos), line, fill='black')
            y_pos += 60
        
        # 枠線
        draw.rectangle([50, 50, 2050, 2920], outline='black', width=3)
        
        # 一時画像として保存
        input_dir = project_root / "data" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        
        sample_path = input_dir / "sample_test.jpg"
        img.save(sample_path, 'JPEG', quality=95)
        
        # JPGからPDFに変換（簡易版）
        pdf_path = input_dir / "sample_test.pdf"
        img_pdf = img.convert('RGB')
        img_pdf.save(pdf_path, 'PDF')
        
        return str(pdf_path)
        
    except Exception as e:
        print(f"❌ サンプルPDF作成エラー: {e}")
        return None

if __name__ == "__main__":
    import sys
    sys.exit(main())
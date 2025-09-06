"""
コンポーネント初期化モジュール
"""

import logging
from typing import Dict

logger = logging.getLogger(__name__)

# 実際のコンポーネントインポート
from src.modules.step1 import PDFProcessor
# from src.pipeline.llm_evaluator_judgment import LLMEvaluatorJudgment
# from src.pipeline.llm_evaluator_ocr import LLMEvaluatorOCR
# from src.pipeline.llm_evaluator_orientation import LLMEvaluatorOrientation
# from src.pipeline.orientation_detector import OrientationDetector
# from src.pipeline.dewarping_runner import DewarpingRunner
# from src.pipeline.image_splitter import ImageSplitter
# from src.pipeline.sr_runner import SuperResolutionRunner


class ComponentInitializer:
    """コンポーネント初期化クラス"""
    
    def __init__(self, config: Dict):
        """
        Args:
            config (Dict): 設定データ
        """
        self.config = config
        self.components = {}
    
    def initialize_all(self) -> Dict:
        """
        全コンポーネントを初期化
        
        Returns:
            Dict: 初期化されたコンポーネントの辞書
        """
        # コンポーネント初期化
        components = {}
        
        # Step1: PDFProcessor初期化
        try:
            components['pdf_processor'] = PDFProcessor(self.config)
        except Exception as e:
            logger.error(f"❌ PDFProcessor初期化エラー: {e}")
        
        # Step2: Step2統合プロセッサー初期化
        try:
            if self.config.get('enable_step2', False):
                from src.modules.step2 import LLMJudgment, ImageReprocessor, DewarpingEngine, Step2Processor
                
                # 個別コンポーネントを初期化
                llm_judgment = LLMJudgment(self.config)
                image_reprocessor = ImageReprocessor(components.get('pdf_processor'), self.config)
                dewarping_engine = DewarpingEngine(self.config)
                
                # 統合プロセッサーを初期化 (promptsは後でmain_pipelineで設定)
                if all([llm_judgment, image_reprocessor, dewarping_engine]):
                    # プロンプトは空の辞書で初期化、後でmain_pipelineで設定
                    components['step2_processor'] = Step2Processor(
                        llm_judgment, image_reprocessor, dewarping_engine, {}
                    )
                    logger.debug("Step2統合プロセッサー初期化完了")
                else:
                    logger.warning("Step2個別コンポーネント初期化失敗")
            else:
                logger.debug("Step2処理は無効に設定されています")
        except Exception as e:
            logger.error(f"❌ Step2プロセッサー初期化エラー: {e}")
        
        # TODO: 他のコンポーネント初期化（後で実装）
        # components.update({
        #     'llm_evaluator_judgment': LLMEvaluatorJudgment(self.config.get('llm_evaluation', {}), self.prompts),
        #     'llm_evaluator_ocr': LLMEvaluatorOCR(self.config.get('llm_evaluation', {}), self.prompts),
        #     'llm_evaluator_orientation': LLMEvaluatorOrientation(self.config.get('llm_evaluation', {}), self.prompts),
        #     'orientation_detector': OrientationDetector(self.config.get('orientation_detection', {})),
        #     'dewarping_runner': DewarpingRunner(self.config.get('dewarping', {})),
        #     'image_splitter': ImageSplitter(self.config.get('split_image_for_ocr', {})),
        #     'sr_runner': SuperResolutionRunner(self.config.get('super_resolution', {}))
        # })
        
        self.components = components
        
        return components
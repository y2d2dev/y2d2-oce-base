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
        llm_judgment = None  # 他のStepでも使用するため外側で宣言
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
                    components['llm_judgment'] = llm_judgment  # 他のStepでも使用できるように保存
                    logger.debug("Step2統合プロセッサー初期化完了")
                else:
                    logger.warning("Step2個別コンポーネント初期化失敗")
            else:
                logger.debug("Step2処理は無効に設定されています")
        except Exception as e:
            logger.error(f"❌ Step2プロセッサー初期化エラー: {e}")
        
        # Step3: 回転判定・補正プロセッサー初期化
        try:
            if self.config.get('enable_step3', False):
                from src.modules.step3 import OrientationDetector, ImageRotator, Step3Processor, LLMOrientationEvaluator
                
                # Step3専用のLLM評価器を初期化
                llm_orientation_evaluator = LLMOrientationEvaluator(self.config)
                
                # 個別コンポーネントを初期化
                orientation_detector = OrientationDetector(self.config)
                image_rotator = ImageRotator(self.config)
                
                # Step3専用のLLM評価器をアタッチ
                # プロンプトは後でmain_pipelineで設定するため、ここでは空の辞書を設定
                orientation_detector.attach_llm_evaluator(llm_orientation_evaluator, {})
                logger.debug("Step3にStep3専用LLM評価器をアタッチしました")
                
                # 統合プロセッサーを初期化
                if all([orientation_detector, image_rotator]):
                    components['step3_processor'] = Step3Processor(
                        orientation_detector, image_rotator
                    )
                    components['orientation_detector'] = orientation_detector
                    components['llm_orientation_evaluator'] = llm_orientation_evaluator
                    logger.debug("Step3統合プロセッサー初期化完了")
                else:
                    logger.warning("Step3個別コンポーネント初期化失敗")
            else:
                logger.debug("Step3処理は無効に設定されています")
        except Exception as e:
            logger.error(f"❌ Step3プロセッサー初期化エラー: {e}")
        
        # Step4: ページ数等判定・ページ分割プロセッサー初期化
        try:
            if self.config.get('enable_step4', True):  # デフォルトで有効
                from src.modules.step4 import PageCountEvaluator, PageSplitter, Step4Processor
                
                # 個別コンポーネントを初期化
                page_count_evaluator = PageCountEvaluator(self.config)
                page_splitter = PageSplitter(self.config)
                
                # 統合プロセッサーを初期化（プロンプトは後でmain_pipelineで設定）
                if all([page_count_evaluator, page_splitter]):
                    components['step4_processor'] = Step4Processor(
                        page_count_evaluator, page_splitter, {}
                    )
                    components['page_count_evaluator'] = page_count_evaluator
                    components['page_splitter'] = page_splitter
                    logger.debug("Step4統合プロセッサー初期化完了")
                else:
                    logger.warning("Step4個別コンポーネント初期化失敗")
            else:
                logger.debug("Step4処理は無効に設定されています")
        except Exception as e:
            logger.error(f"❌ Step4プロセッサー初期化エラー: {e}")
        
        # Step5プロセッサー初期化
        try:
            from src.modules.step5 import Step5Processor
            components['step5_processor'] = Step5Processor(self.config)
            logger.debug("Step5プロセッサー初期化完了")
        except Exception as e:
            logger.error(f"❌ ❌ Step5プロセッサー初期化エラー: {e}")
            components['step5_processor'] = None
        
        # Step6プロセッサー初期化
        try:
            if self.config.get('enable_step6', True):  # デフォルトで有効
                from src.modules.step6 import Step6Processor
                components['step6_processor'] = Step6Processor(self.config, {})  # プロンプトは後でmain_pipelineで設定
                logger.debug("Step6プロセッサー初期化完了")
            else:
                logger.debug("Step6処理は無効に設定されています")
                components['step6_processor'] = None
        except Exception as e:
            logger.error(f"❌ Step6プロセッサー初期化エラー: {e}")
            components['step6_processor'] = None
        
        # Step7: 結果統合・最終出力プロセッサー初期化
        try:
            if self.config.get('enable_step7', True):  # デフォルトで有効
                from src.modules.step7 import Step7Processor
                components['step7_processor'] = Step7Processor(self.config)
                logger.debug("Step7プロセッサー初期化完了")
            else:
                logger.debug("Step7処理は無効に設定されています")
                components['step7_processor'] = None
        except Exception as e:
            logger.error(f"❌ Step7プロセッサー初期化エラー: {e}")
            components['step7_processor'] = None
        
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
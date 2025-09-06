"""
Step6: Gemini OCR処理
"""

import importlib

# 数字プレフィックス付きモジュールをimportlibで読み込み
_gemini_ocr_engine_module = importlib.import_module('src.modules.step6.01_gemini_ocr_engine')
_text_result_manager_module = importlib.import_module('src.modules.step6.02_text_result_manager')
_step6_processor_module = importlib.import_module('src.modules.step6.03_step6_processor')
_document_ai_ocr_engine_module = importlib.import_module('src.modules.step6.04_document_ai_ocr_engine')
_document_ai_result_manager_module = importlib.import_module('src.modules.step6.05_document_ai_result_manager')

# クラスをエクスポート
GeminiOCREngine = _gemini_ocr_engine_module.GeminiOCREngine
TextResultManager = _text_result_manager_module.TextResultManager
Step6Processor = _step6_processor_module.Step6Processor
DocumentAIOCREngine = _document_ai_ocr_engine_module.DocumentAIOCREngine
DocumentAIResultManager = _document_ai_result_manager_module.DocumentAIResultManager

__all__ = ['GeminiOCREngine', 'TextResultManager', 'Step6Processor', 'DocumentAIOCREngine', 'DocumentAIResultManager']
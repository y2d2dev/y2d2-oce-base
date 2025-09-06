"""
Step7: 結果統合・最終出力
"""

import importlib

# 数字プレフィックス付きモジュールをimportlibで読み込み
_text_integration_engine_module = importlib.import_module('src.modules.step7.01_text_integration_engine')
_result_output_manager_module = importlib.import_module('src.modules.step7.02_result_output_manager')
_step7_processor_module = importlib.import_module('src.modules.step7.03_step7_processor')

# クラスをエクスポート
TextIntegrationEngine = _text_integration_engine_module.TextIntegrationEngine
ResultOutputManager = _result_output_manager_module.ResultOutputManager
Step7Processor = _step7_processor_module.Step7Processor

__all__ = ['TextIntegrationEngine', 'ResultOutputManager', 'Step7Processor']
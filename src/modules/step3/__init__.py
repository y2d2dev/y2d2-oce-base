"""
Step3: 回転判定・補正モジュール

このモジュールはStep3の処理を以下のコンポーネントに分割して提供します:
1. OrientationDetector: 画像の向き検出（LLMベース）
2. ImageRotator: 画像の回転処理
3. Step3Processor: 上記2つのコンポーネントを統合した処理オーケストレーター
"""

import importlib

# 数字プレフィックス付きモジュールをimportlibで読み込み
_orientation_detector_module = importlib.import_module('src.modules.step3.01_orientation_detector')
_image_rotator_module = importlib.import_module('src.modules.step3.02_image_rotator')
_step3_processor_module = importlib.import_module('src.modules.step3.03_step3_processor')
_llm_orientation_evaluator_module = importlib.import_module('src.modules.step3.04_llm_orientation_evaluator')

OrientationDetector = _orientation_detector_module.OrientationDetector
ImageRotator = _image_rotator_module.ImageRotator
Step3Processor = _step3_processor_module.Step3Processor
LLMOrientationEvaluator = _llm_orientation_evaluator_module.LLMOrientationEvaluator

__all__ = [
    'OrientationDetector',
    'ImageRotator',
    'Step3Processor',
    'LLMOrientationEvaluator'
]
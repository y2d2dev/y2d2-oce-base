"""
Step5: 画像分割（OCR用）
"""

import importlib

# 数字プレフィックス付きモジュールをimportlibで読み込み
_image_splitter_module = importlib.import_module('src.modules.step5.01_image_splitter')
_image_processor_module = importlib.import_module('src.modules.step5.02_image_processor')
_step5_processor_module = importlib.import_module('src.modules.step5.03_step5_processor')

# クラスをエクスポート
ImageSplitter = _image_splitter_module.ImageSplitter
ImageProcessor = _image_processor_module.ImageProcessor
Step5Processor = _step5_processor_module.Step5Processor

__all__ = ['ImageSplitter', 'ImageProcessor', 'Step5Processor']
# Step1モジュール - PDF→JPG変換処理
import importlib

# 数字プレフィックス付きモジュールをimportlibで読み込み
_pdf_reader_module = importlib.import_module('src.modules.step1.01_pdf_reader')
_dpi_calculator_module = importlib.import_module('src.modules.step1.02_dpi_calculator')
_image_converter_module = importlib.import_module('src.modules.step1.03_image_converter')
_pdf_processor_module = importlib.import_module('src.modules.step1.04_pdf_processor')

PDFReader = _pdf_reader_module.PDFReader
DPICalculator = _dpi_calculator_module.DPICalculator
ImageConverter = _image_converter_module.ImageConverter
PDFProcessor = _pdf_processor_module.PDFProcessor

# メインクラスをエクスポート（下位互換性のため）
__all__ = [
    'PDFProcessor',  # メインインターフェース
    'PDFReader',     # PDF読み取り
    'DPICalculator', # DPI計算
    'ImageConverter' # 画像変換
]
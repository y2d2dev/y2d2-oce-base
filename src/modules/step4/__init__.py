"""
Step4: ページ数等判定・ページ分割モジュール

このモジュールはStep4の処理を以下のコンポーネントに分割して提供します:
1. PageCountEvaluator: ページ数や文書要素のLLM判定
2. PageSplitter: page_count=2の場合の強制左右分割
3. Step4Processor: 上記2つのコンポーネントを統合した処理オーケストレーター
"""

import importlib

# 数字プレフィックス付きモジュールをimportlibで読み込み
_page_count_evaluator_module = importlib.import_module('src.modules.step4.01_page_count_evaluator')
_page_splitter_module = importlib.import_module('src.modules.step4.02_page_splitter')
_step4_processor_module = importlib.import_module('src.modules.step4.03_step4_processor')

PageCountEvaluator = _page_count_evaluator_module.PageCountEvaluator
PageSplitter = _page_splitter_module.PageSplitter
Step4Processor = _step4_processor_module.Step4Processor

__all__ = [
    'PageCountEvaluator',
    'PageSplitter',
    'Step4Processor'
]
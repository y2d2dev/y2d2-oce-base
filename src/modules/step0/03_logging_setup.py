"""
ログシステムセットアップモジュール
階層構造を持つスマートなログシステムの設定機能を提供
"""

import logging
import sys
from typing import Dict


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


class SuppressFilter(logging.Filter):
    """重複メッセージをフィルタリングするカスタムフィルター"""
    
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


def setup_logging(config: Dict):
    """
    階層構造を持つスマートなログシステムの設定
    
    Args:
        config (Dict): 設定データ（systemセクションからlog_levelを取得）
    """
    log_level = config.get('system', {}).get('log_level', 'INFO')
    
    # ルートロガーの設定を強制的に行う
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    
    # コンソールハンドラーを設定
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))
    console_handler.setFormatter(HierarchicalFormatter())
    
    # フィルターを追加
    console_handler.addFilter(SuppressFilter())
    
    root_logger.addHandler(console_handler)
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # 子ロガーの伝播を有効にして統一フォーマットを適用
    for logger_name in ['src.pipeline', 'src.dewarping', 'src.super_resolution']:
        child_logger = logging.getLogger(logger_name)
        child_logger.propagate = True
    
    # Step0専用のロガー設定完了（独立モジュールとして動作）
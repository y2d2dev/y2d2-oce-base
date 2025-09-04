"""
プロンプトローダーモジュール
LLMプロンプト設定を読み込む機能を提供
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)


def load_prompts(config_path: str) -> Dict:
    """
    LLMプロンプト設定を読み込み
    
    Args:
        config_path (str): 設定ファイルのパス（プロンプトファイルの基準位置）
        
    Returns:
        Dict: プロンプト設定データ
        
    Raises:
        RuntimeError: プロンプト設定読み込み失敗時
    """
    try:
        # 設定ファイルと同じディレクトリのllm_prompts.yamlを探す
        config_dir = os.path.dirname(os.path.abspath(config_path))
        prompts_path = os.path.join(config_dir, 'llm_prompts.yaml')
        logger.debug(f"load_prompts: config_dir={config_dir}")
        logger.debug(f"load_prompts: initial prompts_path={prompts_path}")
        
        if not os.path.exists(prompts_path):
            # プロジェクトルートのconfigディレクトリも確認
            current_file = Path(__file__)
            # src/modules/step0/ から project root へ (3階層上)
            project_root = current_file.parent.parent.parent.parent
            fallback_path = project_root / "config" / "llm_prompts.yaml"
            logger.debug(f"load_prompts: project_root={project_root}")
            logger.debug(f"load_prompts: fallback_path={fallback_path}")
            
            if fallback_path.exists():
                prompts_path = str(fallback_path)
                logger.debug(f"load_prompts: using fallback_path={prompts_path}")
            else:
                raise FileNotFoundError(
                    f"llm_prompts.yaml not found in {config_dir} or {fallback_path}"
                )
        
        with open(prompts_path, 'r', encoding='utf-8') as f:
            prompts = yaml.safe_load(f)
            return prompts
            
    except Exception as e:
        logger.error(f"プロンプト設定読み込み失敗: {e}", exc_info=True)
        logger.info("デフォルトプロンプトを使用します")
        raise RuntimeError(f"プロンプト設定読み込みエラー: {e}")
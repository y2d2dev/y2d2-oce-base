"""
環境変数ローダーモジュール
.envファイルから環境変数を読み込む機能を提供
"""

import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def load_env():
    """
    .envファイルから環境変数を読み込み
    
    プロジェクトルートの.envファイルを探して読み込む
    """
    # プロジェクトルートの.envファイルを探す
    current_file = Path(__file__)
    # src/modules/step0/ から project root へ (3階層上)
    project_root = current_file.parent.parent.parent.parent
    env_path = project_root / '.env'
    
    if env_path.exists():
        load_dotenv(env_path)
        logger.info(f".envファイルを読み込みました: {env_path}")
    else:
        logger.warning(f".envファイルが見つかりません: {env_path}")
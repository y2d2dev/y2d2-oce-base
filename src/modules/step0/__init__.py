"""
Step0: パイプライン初期化モジュール群
__init__ から _create_session_directories までの初期化処理を提供
"""

import importlib
import sys
from pathlib import Path

# 数字で始まるモジュール名を動的にインポート
_module_path = Path(__file__).parent

# 00_type_utils
_type_utils = importlib.import_module('src.modules.step0.00_type_utils')
to_bool = _type_utils.to_bool
to_int = _type_utils.to_int
to_float = _type_utils.to_float

# 01_env_loader
_env_loader = importlib.import_module('src.modules.step0.01_env_loader')
load_env = _env_loader.load_env

# 02_config_loader
_config_loader = importlib.import_module('src.modules.step0.02_config_loader')
load_config = _config_loader.load_config
apply_processing_options = _config_loader.apply_processing_options

# 03_logging_setup
_logging_setup = importlib.import_module('src.modules.step0.03_logging_setup')
setup_logging = _logging_setup.setup_logging

# 04_prompt_loader
_prompt_loader = importlib.import_module('src.modules.step0.04_prompt_loader')
load_prompts = _prompt_loader.load_prompts

# 05_component_initializer
_component_initializer = importlib.import_module('src.modules.step0.05_component_initializer')
ComponentInitializer = _component_initializer.ComponentInitializer

# 06_directory_manager
_directory_manager = importlib.import_module('src.modules.step0.06_directory_manager')
DirectoryManager = _directory_manager.DirectoryManager

__all__ = [
    'load_env',
    'load_config',
    'apply_processing_options',
    'setup_logging',
    'ComponentInitializer',
    'load_prompts',
    'DirectoryManager',
    'to_bool',
    'to_int',
    'to_float'
]
#!/usr/bin/env python3
"""
Step0完全独立テスト
すべての外部依存を排除してStep0モジュールのみをテスト
"""

import os
import sys
import importlib
import tempfile
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_00_type_utils():
    """型変換ユーティリティの完全独立テスト"""
    print("🧪 [00] 型変換ユーティリティテスト")
    try:
        # 完全に独立したモジュールとしてテスト
        spec = importlib.util.spec_from_file_location(
            "type_utils", 
            project_root / "src" / "modules" / "step0" / "00_type_utils.py"
        )
        type_utils = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(type_utils)
        
        # テストケース実行
        assert type_utils.to_bool("true") == True
        assert type_utils.to_bool("false") == False
        assert type_utils.to_bool(1) == True
        assert type_utils.to_bool(0) == False
        
        assert type_utils.to_int("123") == 123
        assert type_utils.to_int("123.45") == 123
        assert type_utils.to_int(None, 999) == 999
        
        assert type_utils.to_float("123.45") == 123.45
        assert type_utils.to_float(None, 999.0) == 999.0
        
        print("   ✅ 全テストケース合格")
        return True
    except Exception as e:
        print(f"   ❌ エラー: {e}")
        return False

def test_01_env_loader():
    """環境変数ローダーの完全独立テスト"""
    print("🧪 [01] 環境変数ローダーテスト")
    try:
        spec = importlib.util.spec_from_file_location(
            "env_loader", 
            project_root / "src" / "modules" / "step0" / "01_env_loader.py"
        )
        env_loader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(env_loader)
        
        # 環境変数ローダー実行（エラーが出なければOK）
        env_loader.load_env()
        
        print("   ✅ 環境変数ローダー実行成功")
        return True
    except Exception as e:
        print(f"   ❌ エラー: {e}")
        return False

def test_02_config_loader():
    """設定ローダーの完全独立テスト"""
    print("🧪 [02] 設定ローダーテスト")
    try:
        spec = importlib.util.spec_from_file_location(
            "config_loader", 
            project_root / "src" / "modules" / "step0" / "02_config_loader.py"
        )
        config_loader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config_loader)
        
        # テスト用の設定ファイル作成
        test_config_content = """
system:
  log_level: INFO
  temp_dir: /tmp
test_section:
  enabled: true
  value: 42
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write(test_config_content)
            temp_config_path = f.name
        
        try:
            # 設定読み込みテスト
            config = config_loader.load_config(temp_config_path)
            assert 'system' in config
            assert config['system']['log_level'] == 'INFO'
            print(f"   ✅ 設定読み込み成功: {len(config)}セクション")
            
            # 処理オプション適用テスト
            test_options = {"skip_super_resolution": True}
            config_loader.apply_processing_options(config, test_options)
            assert config['super_resolution']['enabled'] == False
            print("   ✅ 処理オプション適用成功")
            
            return True
        finally:
            os.unlink(temp_config_path)
            
    except Exception as e:
        print(f"   ❌ エラー: {e}")
        return False

def test_03_logging_setup():
    """ログ設定の完全独立テスト"""
    print("🧪 [03] ログ設定テスト")
    try:
        spec = importlib.util.spec_from_file_location(
            "logging_setup", 
            project_root / "src" / "modules" / "step0" / "03_logging_setup.py"
        )
        logging_setup = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(logging_setup)
        
        # テスト用設定
        test_config = {"system": {"log_level": "INFO"}}
        
        # ログ設定実行
        logging_setup.setup_logging(test_config)
        
        print("   ✅ ログ設定実行成功")
        return True
    except Exception as e:
        print(f"   ❌ エラー: {e}")
        return False

def test_04_prompt_loader():
    """プロンプトローダーの完全独立テスト"""
    print("🧪 [04] プロンプトローダーテスト")
    try:
        spec = importlib.util.spec_from_file_location(
            "prompt_loader", 
            project_root / "src" / "modules" / "step0" / "04_prompt_loader.py"
        )
        prompt_loader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(prompt_loader)
        
        # テスト用プロンプトファイル作成
        test_prompts = {
            "test_prompt": {
                "system": "You are a test assistant",
                "user": "Test prompt"
            }
        }
        
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = os.path.join(temp_dir, "config.yml")
            prompts_path = os.path.join(temp_dir, "llm_prompts.yaml")
            
            # 設定ファイル作成
            with open(config_path, 'w') as f:
                f.write("test: true")
            
            # プロンプトファイル作成
            import yaml
            with open(prompts_path, 'w') as f:
                yaml.dump(test_prompts, f)
            
            # プロンプト読み込みテスト
            prompts = prompt_loader.load_prompts(config_path)
            assert 'test_prompt' in prompts
            print(f"   ✅ プロンプト読み込み成功: {len(prompts)}個")
            return True
            
    except Exception as e:
        print(f"   ❌ エラー: {e}")
        return False

def main():
    """完全独立テストの実行"""
    print("=" * 60)
    print("Step0完全独立テスト - 外部依存ゼロ")
    print("=" * 60)
    
    tests = [
        ("00_type_utils", test_00_type_utils),
        ("01_env_loader", test_01_env_loader), 
        ("02_config_loader", test_02_config_loader),
        ("03_logging_setup", test_03_logging_setup),
        ("04_prompt_loader", test_04_prompt_loader),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n▶ テスト開始: {test_name}")
        result = test_func()
        results.append(result)
        print(f"▶ テスト終了: {test_name} {'✅' if result else '❌'}")
    
    passed = sum(results)
    total = len(results)
    
    print("\n" + "=" * 60)
    if passed == total:
        print(f"🎉 全テスト成功！({passed}/{total})")
        print("Step0モジュールは完全に独立して動作します！")
        return 0
    else:
        print(f"💥 テスト失敗: {passed}/{total}")
        print("修正が必要です")
        return 1

if __name__ == "__main__":
    import importlib.util
    sys.exit(main())
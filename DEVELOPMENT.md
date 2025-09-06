# 開発ドキュメント

## ログ出力ルール

### 基本原則
- **各Stepの細分化された工程が終わるごとに完了ログを出す**
- それ以外の詳細ログは不要（debugレベルに設定）
- 統一されたフォーマットを使用

### ログフォーマット
```
StepX-XX: 完了!!
```

### 例：Step0（初期化）
```
Step0-01: 完了!!  ← 環境変数読み込み
Step0-02: 完了!!  ← 設定ファイル読み込み
Step0-03: 完了!!  ← ログシステム設定
Step0-04: 完了!!  ← プロンプト読み込み
Step0-05: 完了!!  ← コンポーネント初期化
Step0-06: 完了!!  ← ディレクトリ管理
--- Step0:初期化 完了‼️ ---
```

### 例：Step1（PDF→JPG変換）
```
Step1-01: 完了!!  ← PDF読み込み
Step1-02: 完了!!  ← PDF検証・DPI計算準備
Step1-03: 完了!!  ← 画像変換・ファイル保存
```

### 実装場所
- メイン工程：各Stepのprocessorクラス内
- 詳細ログ：`logger.debug()` を使用
- 完了ログ：`logger.info("StepX-XX: 完了!!")` を使用

## Docker開発環境

### 初回セットアップ（1回のみ）
```bash
docker build -t y2d2-pipeline .
```

### 開発時の実行（コード変更してもビルド不要）
```bash
# pdf/ディレクトリのPDFを自動処理
docker run --rm -v $(pwd):/app y2d2-pipeline python src/main_pipeline.py

# 指定したPDFを処理
docker run --rm -v $(pwd):/app y2d2-pipeline python src/main_pipeline.py --input pdf/your_file.pdf

# 対話モード（デバッグ用）
docker run -it --rm -v $(pwd):/app y2d2-pipeline bash
```

### 重要なポイント
- `-v $(pwd):/app` でローカルコードをマウント
- **コード変更時にビルド不要**（ファイル変更 → Docker実行で即反映）
- 結果はローカルの `data/output/` に保存される

## プロジェクト構造

### Stepモジュール分離ルール
各Stepは以下のように細分化：

#### Step0（初期化）
- `01_env_loader.py` - 環境変数読み込み
- `02_config_loader.py` - 設定ファイル読み込み
- `03_logging_setup.py` - ログシステム設定
- `04_prompt_loader.py` - プロンプト読み込み
- `05_component_initializer.py` - コンポーネント初期化
- `06_directory_manager.py` - ディレクトリ管理

#### Step1（PDF→JPG変換）
- `pdf_reader.py` - PDF読み取り・基本操作
- `dpi_calculator.py` - DPI計算ロジック
- `image_converter.py` - ページ→画像変換
- `pdf_processor.py` - メインオーケストレーター

### ファイル命名規則
- **数字で始まるファイル名は避ける**（Pythonインポートエラーの原因）
- 機能を表す分かりやすい名前を使用
- `__init__.py`で適切にエクスポート

## PDF処理仕様

### 入力ファイルの検索順序
1. `--input` で指定されたファイル
2. `pdf/` ディレクトリ内の最初のPDFファイル（自動検出）

### 出力先
```
data/output/converted_images/{session_id}/
├── {filename}_page_001.jpg
├── {filename}_page_002.jpg
└── ...
```

### DPI自動調整
- 目標サイズ：[2048, 2560] ピクセル
- DPI範囲：50-600（デフォルト300）
- ページサイズに基づいて最適DPI自動計算

## 今後の拡張

### Step2以降の実装予定
- Step2: 歪み判定・補正
- Step3: 回転判定・補正
- Step4: ページ分割
- Step5: 画像分割
- Step6: 超解像処理
- Step7: OCR実行

### ログフォーマットの統一
各Stepで同様のフォーマットを維持：
```
Step2-01: 完了!!
Step2-02: 完了!!
Step3-01: 完了!!
...
```

## トラブルシューティング

### よくある問題
1. **Pythonインポートエラー** → ファイル名に数字が含まれていないか確認
2. **Docker実行時の権限エラー** → `-v $(pwd):/app` が正しく設定されているか確認
3. **PDF処理失敗** → `pdf/` ディレクトリにPDFファイルが存在するか確認

### デバッグ方法
```bash
# 詳細ログを確認
docker run --rm -v $(pwd):/app y2d2-pipeline python src/main_pipeline.py --config config.yml

# 対話モードでステップ実行
docker run -it --rm -v $(pwd):/app y2d2-pipeline bash
# python src/main_pipeline.py --input pdf/test.pdf
```
# y2d2-oce-base
OCRのベースリポジトリ

## Docker実行

### 1. 初回ビルド（1回のみ）
```bash
docker build -t y2d2-pipeline .
```

### 2. 開発モード（コード変更してもビルド不要）
```bash
# pdf/ディレクトリのPDFを自動処理
docker run --rm -v $(pwd):/app y2d2-pipeline python src/main_pipeline.py

# 指定したPDFを処理
docker run --rm -v $(pwd):/app y2d2-pipeline python src/main_pipeline.py --input pdf/your_file.pdf
```

### 3. 対話モード（開発・デバッグ用）
```bash
docker run -it --rm -v $(pwd):/app y2d2-pipeline bash
# コンテナ内で自由に実行:
# python src/main_pipeline.py
# python src/main_pipeline.py --input pdf/test.pdf
```

**📝 重要：** `-v $(pwd):/app` でローカルコードをマウントするため、**コード変更時にビルド不要**です。

## 開発者向け情報

詳細な開発ルール・ログフォーマット・トラブルシューティングについては [DEVELOPMENT.md](./DEVELOPMENT.md) を参照してください。








書類OCR前処理の統合パイプラインシステム

process_pdf メソッドにより，パイプラインを実行する

処理フロー:
1. PDF → JPG変換 (DPI自動調整)
2-1. 画像の歪み(および識別困難性の判定) (LLM)
2-2. 最高解像度化 (必要な場合)
2-3. 歪み補正 (必要な場合)
3-1. 回転判定 (LLM)
3-2. 回転補正
4-1. ページ数等判定 (LLM)
4-2. ページ分割 (必要な場合)
5-1. 画像5等分 (オーバーラップ付き)
6-1. 超解像処理 (DRCT)
7-1. OCR実行 (LLM)

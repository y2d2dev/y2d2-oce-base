# y2d2-oce-base
OCRのベースリポジトリ

Docker

docker build -t y2d2-pipeline . && docker run -it --rm y2d2-pipeline

docker run -it --rm y2d2-pipeline

python /app/src/main_pipeline.py








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

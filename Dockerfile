FROM python:3.11-slim

WORKDIR /app

# 必要なパッケージをインストール
RUN pip install --no-cache-dir \
    pyyaml \
    python-dotenv \
    PyMuPDF \
    Pillow

# プロジェクトファイルをコピー
COPY . /app/

# 環境変数設定
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

CMD ["bash"]
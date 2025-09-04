FROM python:3.11-slim

WORKDIR /app

# Step0に必要な最小限のパッケージのみ
RUN pip install --no-cache-dir pyyaml python-dotenv

# プロジェクトファイルをコピー
COPY . /app/

# 環境変数設定
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

CMD ["bash"]
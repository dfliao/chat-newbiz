FROM python:3.11-slim

# 安裝系統相依套件
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 建立非 root 使用者
RUN groupadd -r appuser && useradd -r -g appuser appuser

# 設定工作目錄
WORKDIR /app

# 複製 requirements 並安裝相依套件
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    rm -rf /root/.cache/pip

# 複製應用程式檔案
COPY app.py .

# 建立 logs 目錄並設定權限
RUN mkdir -p logs && \
    chown -R appuser:appuser /app

# 切換到非 root 使用者
USER appuser

# 設定預設環境變數
ENV PORT=8085

# 健康檢查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:${PORT}/health || exit 1

# 啟動應用程式
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
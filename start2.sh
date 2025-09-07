#!/bin/sh
# run.sh - 啟動 chat_newbiz_to_redmine 服務

# 1. 移除 Windows CRLF
sed -i 's/\r$//' .env

# 2. 載入環境變數
set -a
. ./.env
set +a

# 3. 啟動服務
echo "🚀 啟動服務在 PORT=${PORT:-8085} ..."
exec python app.py


~~

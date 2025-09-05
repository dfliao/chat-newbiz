#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

PORT=${PORT:-8085}

# 啟動虛擬環境
. .venv/bin/activate

# 若舊的在跑先停掉
if [ -f app.pid ]; then
  kill "$(cat app.pid)" 2>/dev/null || true
  rm -f app.pid
fi

# 乾脆以前景啟 2 秒測試一次，確認能起來就放背景
PYTHONWARNINGS=ignore PORT="$PORT" nohup python app.py > app.log 2>&1 &
echo $! > app.pid
sleep 1

echo "== 最近日志 =="
tail -n 20 app.log || true


#!/bin/sh
# run.sh - 管理 chat_newbiz_to_redmine 常駐服務
# 用法：./run.sh start|stop|restart|status|logs

set -e

BASEDIR="$(cd "$(dirname "$0")" && pwd)"
cd "$BASEDIR"

APP="chat_newbiz_to_redmine"
PIDFILE="$BASEDIR/$APP.pid"
LOGFILE="$BASEDIR/app.log"

# 1) 確保 .env 可用（移除 CRLF）
[ -f ".env" ] || { echo "❌ 找不到 .env"; exit 1; }
sed -i 's/\r$//' .env

# 2) 載入環境變數
set -a
. ./.env
set +a

# 3) 啟用 venv（若存在）
if [ -d ".venv" ] && [ -f ".venv/bin/activate" ]; then
  . ".venv/bin/activate"
fi

PYTHON_BIN="${PYTHON_BIN:-python}"
PORT="${PORT:-8085}"

cmd_start() {
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "ℹ️  已在執行中（PID=$(cat "$PIDFILE")），用 ./run.sh restart 重新啟動"
    exit 0
  fi

  # 建立/輪替 log（最多保留一份 .1）
  [ -f "$LOGFILE.1" ] && rm -f "$LOGFILE.1"
  [ -f "$LOGFILE" ] && mv "$LOGFILE" "$LOGFILE.1"
  touch "$LOGFILE"

  echo "🚀 啟動服務（port=$PORT）… log: $LOGFILE"
  # 建議用 uvicorn 啟動，較穩定；若你要用 python app.py 也可
  nohup $PYTHON_BIN -m uvicorn app:app --host 0.0.0.0 --port "$PORT" \
    >> "$LOGFILE" 2>&1 &
  echo $! > "$PIDFILE"
  sleep 0.6
  if kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "✅ 已啟動，PID=$(cat "$PIDFILE")"
  else
    echo "❌ 啟動失敗，詳見 $LOGFILE"
    exit 1
  fi
}

cmd_stop() {
  if [ -f "$PIDFILE" ]; then
    PID="$(cat "$PIDFILE")"
    if kill -0 "$PID" 2>/dev/null; then
      echo "🛑 停止 PID=$PID …"
      kill "$PID" 2>/dev/null || true
      # 給 5 秒優雅關閉，之後強殺
      for i in 1 2 3 4 5; do
        kill -0 "$PID" 2>/dev/null || break
        sleep 1
      done
      kill -0 "$PID" 2>/dev/null && kill -9 "$PID" 2>/dev/null || true
    fi
    rm -f "$PIDFILE"
    echo "✅ 已停止"
  else
    echo "ℹ️  沒有 PID 檔，可能已停止"
  fi
}

cmd_status() {
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "✅ 執行中（PID=$(cat "$PIDFILE")，port=$PORT）"
  else
    echo "🛌 未在執行"
    exit 1
  fi
}

cmd_logs() {
  echo "📜 追蹤日誌（Ctrl+C 離開） → $LOGFILE"
  tail -n 200 -f "$LOGFILE"
}

case "$1" in
  start)   cmd_start ;;
  stop)    cmd_stop ;;
  restart) cmd_stop; cmd_start ;;
  status)  cmd_status ;;
  logs)    cmd_logs ;;
  *)
    echo "用法：$0 {start|stop|restart|status|logs}"
    exit 1
    ;;
esac


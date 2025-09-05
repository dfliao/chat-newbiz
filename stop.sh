#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

if [ -f app.pid ]; then
  kill "$(cat app.pid)" 2>/dev/null || true
  rm -f app.pid
  echo "stopped"
else
  # 備援：找出殘留的 app.py
  ps -ef | grep '[p]ython .*app.py' | awk '{print $2}' | xargs -r kill 2>/dev/null || true
  echo "no pid file; tried to kill by name"
fi


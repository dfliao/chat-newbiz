#!/bin/bash
set -euo pipefail
cd /volume3/ai-stack/chat-newbiz

# 載入環境變數
set -a
[ -f .env ] && . ./.env
set +a

# 執行單次輪詢
/usr/bin/env python3 ./chat_newbiz_to_redmine.py run-once


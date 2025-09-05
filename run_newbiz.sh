#!/usr/bin/env bash
set -euo pipefail
cd /volume3/ai-stack/chat-newbiz

# 讀 .env
if [[ -f .env ]]; then set -a; . ./.env; set +a; fi

# 自簽憑證先放行（正式再上 CA）
if [[ "${CHAT_VERIFY_TLS:-false}" == "false" ]]; then
  export REQUESTS_CA_BUNDLE=""
fi

# 用 enable_syno_token=yes 一次拿 SID + SYNO_TOKEN
LOGIN_JSON=$(curl -sk -X POST "${CHAT_BASE_URL}/webapi/auth.cgi" \
  --data "api=SYNO.API.Auth&method=login&version=6&session=chat&format=sid&enable_syno_token=yes" \
  --data-urlencode "account=${CHAT_USER}" \
  --data-urlencode "passwd=${CHAT_PASS}")

export CHAT_SID=$(echo "$LOGIN_JSON"        | sed -n 's/.*"sid":"\([^"]*\)".*/\1/p')
export CHAT_SYNO_TOKEN=$(echo "$LOGIN_JSON" | sed -n 's/.*"synotoken":"\([^"]*\)".*/\1/p')

# 交給 Python 執行（Python 內請帶上 Cookie+X-SYNO-TOKEN）
python3 chat_newbiz_to_redmine.py run-once


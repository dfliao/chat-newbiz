#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-https://192.168.0.222:5001}"   # 視情況改
USER="${CHAT_USER:?need CHAT_USER}"
PASS="${CHAT_PASS:?need CHAT_PASS}"

# 1) login：一次拿 sid + synotoken
LOGIN_JSON=$(curl -sk -X POST "$BASE/webapi/auth.cgi" \
  --data "api=SYNO.API.Auth&method=login&version=6&session=chat&format=sid&enable_syno_token=yes" \
  --data-urlencode "account=$USER" --data-urlencode "passwd=$PASS")

SID=$(printf "%s" "$LOGIN_JSON" | sed -n 's/.*"sid":"\([^"]*\)".*/\1/p')
SYNO_TOKEN=$(printf "%s" "$LOGIN_JSON" | sed -n 's/.*"synotoken":"\([^"]*\)".*/\1/p')
[[ -n "$SID" && -n "$SYNO_TOKEN" ]] || { echo "Login failed: $LOGIN_JSON"; exit 1; }
echo "→ SID=${SID:0:6}…  TOKEN=${SYNO_TOKEN:0:6}…"

HDR=(-H "Cookie: id=$SID" -H "X-Requested-With: XMLHttpRequest")

# 2) list workspace（若未啟用也會回空，我們預設 wid=1）
WS_JSON=$(curl -sk -X POST \
  "$BASE/chat/webapi/entry.cgi?api=SYNO.Chat.Workspace&method=list&version=2&SynoToken=$SYNO_TOKEN" \
  "${HDR[@]}") || true
WID=$(printf "%s" "$WS_JSON" | sed -n 's/.*"id":[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -n1)
: "${WID:=1}"
echo "→ workspace_id=$WID"

# 3) list channels（最穩：/chat/webapi + SynoToken=URL + 帶 workspace_id）
CH_JSON=$(curl -sk -X POST \
  "$BASE/chat/webapi/entry.cgi?api=SYNO.Chat.Channel&method=list&version=2&SynoToken=$SYNO_TOKEN" \
  "${HDR[@]}" \
  -d "workspace_id=$WID") || true
if ! echo "$CH_JSON" | grep -q '"success":true'; then
  # 回退 version=1
  CH_JSON=$(curl -sk -X POST \
    "$BASE/chat/webapi/entry.cgi?api=SYNO.Chat.Channel&method=list&version=1&SynoToken=$SYNO_TOKEN" \
    "${HDR[@]}" \
    -d "workspace_id=$WID") || true
fi
echo "$CH_JSON" | grep -q '"success":true' || { echo "$CH_JSON"; exit 1; }

echo "→ 可見頻道(前20)："
printf "%s\n" "$CH_JSON" | sed 's/},{/},\n{/g' | sed -n 's/.*"id":[[:space:]]*\([0-9]\+\).*"name":"\([^"]\+\)".*/\1\t\2/p' | head -n20

# 4) 任取第一個 channel_id 讀訊息（可自行 export CHAT_CHANNEL_ID 覆蓋）
: "${CHAT_CHANNEL_ID:=$(printf "%s" "$CH_JSON" | sed -n 's/.*"id":[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -n1)}"
echo "→ 使用 channel_id=$CHAT_CHANNEL_ID"

MSG_JSON=$(curl -sk -X POST \
  "$BASE/chat/webapi/entry.cgi?api=SYNO.Chat.Message&method=list&version=2&SynoToken=$SYNO_TOKEN" \
  "${HDR[@]}" \
  -d "channel_id=$CHAT_CHANNEL_ID" -d "workspace_id=$WID" -d "limit=20") || true
if ! echo "$MSG_JSON" | grep -q '"success":true'; then
  MSG_JSON=$(curl -sk -X POST \
    "$BASE/chat/webapi/entry.cgi?api=SYNO.Chat.Message&method=list&version=1&SynoToken=$SYNO_TOKEN" \
    "${HDR[@]}" \
    -d "channel_id=$CHAT_CHANNEL_ID" -d "workspace_id=$WID" -d "limit=20") || true
fi
echo "$MSG_JSON" | grep -q '"success":true' || { echo "$MSG_JSON"; exit 1; }

echo "→ 取到訊息（節錄）"
printf "%s\n" "$MSG_JSON" | cut -c1-400

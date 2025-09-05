# app.py
# -*- coding: utf-8 -*-
import os
import json
import logging
from typing import Dict, Tuple, Optional

import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse


# ----------------------------
# 工具
# ----------------------------
def parse_bool(s: Optional[str], default: bool = False) -> bool:
    if s is None:
        return default
    return str(s).strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_map(raw: str) -> Dict[str, str]:
    """
    解析 'k1:v1,k2:v2' 成 dict，左右兩邊會 strip。
    例：
      '196:tokA, 94:tokB' -> {'196': 'tokA', '94': 'tokB'}
    也可用來解析 '196:urlA,94:urlB'
    """
    m: Dict[str, str] = {}
    for part in [p for p in (raw or "").split(",") if p.strip()]:
        if ":" in part:
            k, v = part.split(":", 1)
            m[k.strip()] = v.strip()
    return m


# ----------------------------
# 環境變數
# ----------------------------
PORT = int(os.getenv("PORT", "8085"))

# Outgoing 驗證
OUTGOING_TOKEN = os.getenv("OUTGOING_TOKEN", "").strip()  # 單一 token（僅支援一個頻道）
CHAT_TOKENS = parse_map(os.getenv("CHAT_TOKENS", ""))     # 多頻道：'196:tokA,94:tokB'
CHAT_CHANNEL_IDS = {s for s in os.getenv("CHAT_CHANNEL_IDS", "").replace(" ", "").split(",") if s}

# Incoming 回貼
CHAT_INCOMING_URLS = parse_map(os.getenv("CHAT_INCOMING_URLS", ""))  # '196:urlA,94:urlB,95:urlC'
DEFAULT_INCOMING_URL = os.getenv("CHAT_WEBHOOK_URL", "").strip()     # 找不到對應時的預設
CHAT_VERIFY_TLS = parse_bool(os.getenv("CHAT_VERIFY_TLS"), default=False)  # 自簽憑證先關

# Redmine
REDMINE_URL = os.getenv("REDMINE_URL", "").rstrip("/")
REDMINE_API_KEY = os.getenv("REDMINE_API_KEY", "").strip()
REDMINE_PROJECT = os.getenv("REDMINE_PROJECT", "").strip()
REDMINE_PROJECT_ID = os.getenv("REDMINE_PROJECT_ID", "").strip()
REDMINE_TRACKER_ID = os.getenv("REDMINE_TRACKER_ID", "").strip()
REDMINE_STATUS_ID = os.getenv("REDMINE_STATUS_ID", "").strip()
REDMINE_VERIFY = parse_bool(os.getenv("REDMINE_VERIFY"), default=False)

# 關鍵字
KEYWORD = os.getenv("KEYWORD", "新商機").strip()


# ----------------------------
# Logging
# ----------------------------
logger = logging.getLogger("chat-newbiz")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = logging.StreamHandler()
    _fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    _h.setFormatter(_fmt)
    logger.addHandler(_h)

# 啟動時印出對照摘要（避免洩漏，只印末8碼）
def _safe_tail(s: str, n: int = 8) -> str:
    return s[-n:] if s else ""

logger.info(f"Startup: channels={sorted(CHAT_CHANNEL_IDS) if CHAT_CHANNEL_IDS else 'ALL'}")
if CHAT_TOKENS:
    masked = {k: _safe_tail(v) for k, v in CHAT_TOKENS.items()}
    logger.info(f"Outgoing map(last8)={masked}")
if CHAT_INCOMING_URLS:
    masked = {k: _safe_tail(v) for k, v in CHAT_INCOMING_URLS.items()}
    logger.info(f"Incoming map(last8)={masked}")
if DEFAULT_INCOMING_URL:
    logger.info(f"Default incoming URL(last8)={_safe_tail(DEFAULT_INCOMING_URL)}")

app = FastAPI()


# ----------------------------
# 驗證 Outgoing token
# ----------------------------
def verify_outgoing_token(channel_id: str, token: str) -> bool:
    channel_id = (channel_id or "").strip()
    token = (token or "").strip()
    if not channel_id or not token:
        return False

    # 若設定了 per-channel 對照，優先使用
    if CHAT_TOKENS:
        expect = CHAT_TOKENS.get(channel_id)
        if not expect:
            return False
        return token == expect

    # 否則回退到單一 OUTGOING_TOKEN
    return token == OUTGOING_TOKEN


# ----------------------------
# Chat：依頻道回貼訊息（Incoming Webhook）
# ----------------------------
def send_chat_message(text: str, channel_id: str) -> Tuple[int, str]:
    """
    依 channel_id 選擇對應的 Incoming URL（CHAT_INCOMING_URLS），
    沒對到就用 DEFAULT_INCOMING_URL。必須用 x-www-form-urlencoded + payload=JSON。
    """
    text = (text or "").strip()
    if not text:
        return 0, "empty text"

    url = CHAT_INCOMING_URLS.get(str(channel_id), DEFAULT_INCOMING_URL)
    if not url:
        return 0, f"no incoming url for channel {channel_id}"

    try:
        r = requests.post(
            url,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"payload": json.dumps({"text": text}, ensure_ascii=False)},
            verify=CHAT_VERIFY_TLS,
            timeout=8,
        )
        return r.status_code, r.text
    except Exception as e:
        return -1, f"request failed: {e}"


# ----------------------------
# Redmine：建立議題
# ----------------------------
def _project_identifier() -> Optional[str]:
    if REDMINE_PROJECT_ID:
        return REDMINE_PROJECT_ID
    if REDMINE_PROJECT:
        return REDMINE_PROJECT
    return None


def create_redmine_issue(subject: str, description: str) -> Tuple[int, str]:
    if not REDMINE_URL or not REDMINE_API_KEY:
        return 0, "REDMINE_URL or REDMINE_API_KEY not set"

    issue: Dict[str, object] = {
        "subject": (subject or "(no subject)")[:255],
        "description": description or "",
    }
    pid = _project_identifier()
    if pid:
        issue["project_id"] = pid
    if REDMINE_TRACKER_ID:
        try:
            issue["tracker_id"] = int(REDMINE_TRACKER_ID)
        except ValueError:
            pass
    if REDMINE_STATUS_ID:
        try:
            issue["status_id"] = int(REDMINE_STATUS_ID)
        except ValueError:
            pass

    url = f"{REDMINE_URL}/issues.json"
    headers = {
        "X-Redmine-API-Key": REDMINE_API_KEY,
        "Content-Type": "application/json; charset=utf-8",
    }

    try:
        resp = requests.post(url, headers=headers, json={"issue": issue}, verify=REDMINE_VERIFY, timeout=12)
        return resp.status_code, resp.text
    except Exception as e:
        return -1, f"request failed: {e}"


# ----------------------------
# Routes
# ----------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat_webhook")
async def chat_webhook(request: Request):
    """
    Synology Chat 傳出 Webhook（Outgoing）以 x-www-form-urlencoded 送資料：
      常見 keys：channel_id, channel_name, token, text, user_id, username, post_id, ...
    流程：
      1) 驗證 token（per-channel 或單一）
      2) 限制頻道（若 CHAT_CHANNEL_IDS 有設定）
      3) 關鍵字判斷（KEYWORD）
      4) 建立 Redmine 議題
      5) 依 channel_id 回貼到對應頻道（Incoming Webhook）
    """
    form = dict(await request.form())

    channel_id = (form.get("channel_id") or "").strip()
    text_raw = (form.get("text") or "").strip()
    token_in = (form.get("token") or "").strip()

    # 記錄收到的欄位（不印 token 值）
    log_keys = ",".join(sorted(form.keys()))
    logger.info(f"Webhook keys={log_keys} | channel_id={channel_id} | has_text={bool(text_raw)}")

    # 限制允許的頻道
    if CHAT_CHANNEL_IDS and channel_id not in CHAT_CHANNEL_IDS:
        raise HTTPException(status_code=403, detail="Channel not allowed")

    # 驗證 Outgoing token
    if not verify_outgoing_token(channel_id, token_in):
        raise HTTPException(status_code=403, detail="Invalid token for channel")

    # 關鍵字過濾
    if not text_raw or KEYWORD not in text_raw:
        return JSONResponse({"ok": True, "skipped": True, "reason": "keyword not found"})

    # 建 Redmine 議題內容
    subject = text_raw[:120]
    description_lines = [
        f"**來源頻道**: {form.get('channel_name','')} (id={channel_id})",
        f"**使用者**: {form.get('username','')} (id={form.get('user_id','')})",
        f"**原始文字**:\n{text_raw}",
    ]
    description = "\n\n".join(description_lines)

    # 建立議題
    r_code, r_body = create_redmine_issue(subject, description)
    logger.info(f"Redmine create status={r_code} body={r_body[:500]}")

    # 回貼訊息（依頻道對應 URL）
    ack_msg = "✅ 已建立 Redmine 議題" if 200 <= r_code < 300 else f"❌ 建議題失敗（HTTP {r_code}）"
    c_status, c_body = send_chat_message(ack_msg, channel_id)
    logger.info(f"Chat ack status={c_status} body={c_body}")

    return JSONResponse({"ok": True, "redmine_status": r_code})


@app.get("/")
def root():
    return JSONResponse({"detail": "Not Found"}, status_code=404)


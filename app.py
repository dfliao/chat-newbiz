# app.py
# -*- coding: utf-8 -*-
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional, List

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


def calculate_business_days(start_date: datetime, days: int) -> str:
    """計算工作天（排除週末）"""
    current = start_date
    while days > 0:
        current += timedelta(days=1)
        # 0=Monday, 6=Sunday
        if current.weekday() < 5:  # 週一到週五
            days -= 1
    return current.strftime("%Y-%m-%d")


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

# 關鍵字（支援多個，用逗號分隔）
KEYWORD = os.getenv("KEYWORD", "新商機").strip()
KEYWORDS_RAW = os.getenv("KEYWORDS", "").strip()
KEYWORDS = [k.strip() for k in KEYWORDS_RAW.split(",") if k.strip()] if KEYWORDS_RAW else [KEYWORD]


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


def find_redmine_user(assignee_query: str) -> Optional[int]:
    """
    根據 ID 或姓名查詢 Redmine 使用者
    優先順序：1. 精確 ID 匹配 2. 姓名匹配 3. 返回 None
    """
    if not REDMINE_URL or not REDMINE_API_KEY or not assignee_query:
        logger.warning("缺少 Redmine 配置或查詢參數")
        return None
    
    headers = {"X-Redmine-API-Key": REDMINE_API_KEY}
    logger.info(f"開始查詢 Redmine 用戶: {assignee_query}")
    
    # 嘗試直接 ID 查詢
    try:
        user_id = int(assignee_query)
        url = f"{REDMINE_URL}/users/{user_id}.json"
        logger.info(f"嘗試用戶ID查詢: {url}")
        resp = requests.get(url, headers=headers, verify=REDMINE_VERIFY, timeout=8)
        logger.info(f"用戶ID查詢結果: 狀態={resp.status_code}")
        
        if resp.status_code == 200:
            user_data = resp.json().get("user", {})
            username = user_data.get("login", "")
            fullname = f"{user_data.get('firstname', '')} {user_data.get('lastname', '')}".strip()
            logger.info(f"找到用戶: ID={user_id}, 登入名={username}, 全名={fullname}")
            return user_id
        else:
            logger.warning(f"用戶ID查詢失敗: {resp.status_code} - {resp.text[:200]}")
    except ValueError:
        logger.info(f"'{assignee_query}' 不是數字，嘗試姓名查詢")
    except Exception as e:
        logger.error(f"用戶ID查詢異常: {e}")
    
    # 嘗試姓名查詢
    try:
        url = f"{REDMINE_URL}/users.json"
        params = {"name": assignee_query, "limit": 25}
        logger.info(f"嘗試姓名查詢: {url} with params={params}")
        resp = requests.get(url, headers=headers, params=params, verify=REDMINE_VERIFY, timeout=8)
        logger.info(f"姓名查詢結果: 狀態={resp.status_code}")
        
        if resp.status_code == 200:
            users = resp.json().get("users", [])
            logger.info(f"找到 {len(users)} 個可能的用戶")
            
            for user in users:
                user_id = user.get("id")
                login = user.get("login", "").lower()
                firstname = user.get("firstname", "").lower()
                lastname = user.get("lastname", "").lower()
                fullname = f"{user.get('firstname', '')} {user.get('lastname', '')}".strip().lower()
                
                logger.info(f"檢查用戶: ID={user_id}, login={login}, fullname={fullname}")
                
                query_lower = assignee_query.lower()
                if (login == query_lower or
                    firstname == query_lower or
                    lastname == query_lower or
                    fullname == query_lower or
                    query_lower in login or
                    query_lower in fullname):
                    logger.info(f"匹配成功: 用戶ID={user_id}")
                    return user_id
            
            logger.warning(f"在 {len(users)} 個用戶中未找到匹配的用戶")
        else:
            logger.warning(f"姓名查詢失敗: {resp.status_code} - {resp.text[:200]}")
    except Exception as e:
        logger.error(f"姓名查詢異常: {e}")
    
    logger.warning(f"未找到匹配的用戶: {assignee_query}")
    return None


def create_redmine_issue(subject: str, description: str, assignee_query: str = None, parent_issue_id: int = None, due_date: str = None) -> Tuple[int, str, Optional[int]]:
    if not REDMINE_URL or not REDMINE_API_KEY:
        return 0, "REDMINE_URL or REDMINE_API_KEY not set", None

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
    
    # 設定被指派者
    if assignee_query:
        assignee_id = find_redmine_user(assignee_query)
        if assignee_id:
            issue["assigned_to_id"] = assignee_id
    
    # 設定父議題
    if parent_issue_id:
        issue["parent_issue_id"] = parent_issue_id
    
    # 設定到期日
    if due_date:
        issue["due_date"] = due_date

    url = f"{REDMINE_URL}/issues.json"
    headers = {
        "X-Redmine-API-Key": REDMINE_API_KEY,
        "Content-Type": "application/json; charset=utf-8",
    }

    try:
        resp = requests.post(url, headers=headers, json={"issue": issue}, verify=REDMINE_VERIFY, timeout=12)
        
        # 詳細解析返回的議題 ID
        issue_id = None
        if resp.status_code in (200, 201):
            try:
                result = resp.json()
                issue_id = result.get("issue", {}).get("id")
                logger.info(f"Redmine API 回應解析: 狀態={resp.status_code}, 議題ID={issue_id}")
                if not issue_id:
                    logger.warning(f"無法從回應中解析議題ID，完整回應: {resp.text[:500]}")
            except Exception as parse_e:
                logger.error(f"解析 Redmine API 回應時發生錯誤: {parse_e}")
                logger.error(f"原始回應: {resp.text[:500]}")
        else:
            logger.error(f"Redmine API 回應錯誤: 狀態={resp.status_code}, 內容={resp.text[:500]}")
        
        return resp.status_code, resp.text, issue_id
    except Exception as e:
        logger.error(f"調用 Redmine API 時發生異常: {e}")
        return -1, f"request failed: {e}", None


def create_business_lead_subtasks(parent_issue_id: int, creation_date: datetime, assignee_query: str = None) -> List[Tuple[int, str]]:
    """建立新商機的三個子議題（依序進行）"""
    subtasks = [
        {
            "subject": "合法性與可行性評估",
            "description": "評估此商機的合法性與技術可行性",
            "due_days_from_start": 2  # 從建立日期算起
        },
        {
            "subject": "初步模組舖排圖說", 
            "description": "製作初步的模組架構與流程圖說",
            "due_days_from_start": 4  # 2+2天
        },
        {
            "subject": "預算報價",
            "description": "評估專案成本並提供初步報價",
            "due_days_from_start": 7  # 2+2+3天
        }
    ]
    
    results = []
    logger.info(f"開始建立 {len(subtasks)} 個子議題，父議題ID: {parent_issue_id}")
    
    for i, subtask in enumerate(subtasks, 1):
        try:
            due_date = calculate_business_days(creation_date, subtask["due_days_from_start"])
            logger.info(f"建立子議題 {i}: {subtask['subject']}，到期日: {due_date}")
            
            status_code, response, subtask_id = create_redmine_issue(
                subject=subtask["subject"],
                description=subtask["description"],
                assignee_query=assignee_query,
                parent_issue_id=parent_issue_id,
                due_date=due_date
            )
            
            if 200 <= status_code < 300:
                logger.info(f"子議題 {i} 建立成功，ID: {subtask_id}")
                results.append((status_code, f"{subtask['subject']}: 建立成功 (ID: {subtask_id})"))
            else:
                logger.error(f"子議題 {i} 建立失敗: {status_code} - {response[:200]}")
                results.append((status_code, f"{subtask['subject']}: 建立失敗 ({status_code})"))
                
        except Exception as e:
            logger.error(f"建立子議題 {i} 時發生異常: {e}")
            results.append((500, f"{subtask['subject']}: 異常錯誤 - {str(e)}"))
    
    return results


# ----------------------------
# Routes
# ----------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/test_webhook")
async def test_webhook(request: Request):
    """測試端點，用於除錯 webhook 功能"""
    form = dict(await request.form())
    
    # 解析測試參數
    test_text = form.get("text", "新商機測試 sandy.chung")
    test_channel_id = form.get("channel_id", "196")
    test_username = form.get("username", "test_user")
    test_channel_name = form.get("channel_name", "test_channel")
    
    logger.info(f"🧪 測試模式: text='{test_text}', channel_id={test_channel_id}")
    
    # 模擬完整的 webhook 處理流程（跳過 token 驗證）
    import re
    
    # 解析指派者
    assignee_query = None
    text_for_subject = test_text
    if "@" in test_text:
        match = re.search(r'@(\S+)', test_text)
        if match:
            assignee_raw = match.group(1)
            if assignee_raw.startswith('u:'):
                user_id_match = re.match(r'u:(\d+)', assignee_raw)
                if user_id_match:
                    assignee_query = user_id_match.group(1)
                    logger.info(f"🔍 解析 Synology Chat 格式: @{assignee_raw} -> 用戶ID {assignee_query}")
            else:
                assignee_query = assignee_raw
                logger.info(f"🔍 解析一般格式: @{assignee_raw}")
            
            text_for_subject = re.sub(r'@\S+', '', test_text).strip()
            text_for_subject = re.sub(r'\s+', ' ', text_for_subject)
    
    # 測試用戶查詢
    if assignee_query:
        found_user_id = find_redmine_user(assignee_query)
        logger.info(f"🔍 用戶查詢結果: '{assignee_query}' -> {found_user_id}")
    
    # 建立測試議題
    subject = text_for_subject[:120] if text_for_subject else test_text[:120]
    description = f"**測試模式**\n\n**來源頻道**: {test_channel_name} (id={test_channel_id})\n**使用者**: {test_username}\n**原始文字**: {test_text}"
    
    creation_time = datetime.now()
    r_code, r_body, parent_issue_id = create_redmine_issue(subject, description, assignee_query)
    
    # 嘗試建立子議題
    subtask_results = []
    if 200 <= r_code < 300 and parent_issue_id:
        logger.info(f"🏗️ 開始建立子議題，父議題ID: {parent_issue_id}")
        subtask_results = create_business_lead_subtasks(parent_issue_id, creation_time, assignee_query)
    
    return {
        "test_mode": True,
        "original_text": test_text,
        "parsed_assignee": assignee_query,
        "subject": subject,
        "main_issue": {
            "status_code": r_code,
            "issue_id": parent_issue_id,
            "response_preview": r_body[:200] if r_body else None
        },
        "subtasks": [
            {
                "status_code": status,
                "result": result
            } for status, result in subtask_results
        ],
        "total_created": 1 + len([r for r in subtask_results if 200 <= r[0] < 300]) if 200 <= r_code < 300 else 0
    }


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

    # 關鍵字過濾（檢查是否包含任何一個關鍵字）
    if not text_raw or not any(keyword in text_raw for keyword in KEYWORDS):
        return JSONResponse({"ok": True, "skipped": True, "reason": "keyword not found"})

    # 解析指派者（支援多種格式）
    assignee_query = None
    text_for_subject = text_raw
    import re
    
    # 1. 優先檢查 @ 符號格式
    if "@" in text_raw:
        # 匹配 @後面的內容
        match = re.search(r'@(\S+)', text_raw)
        if match:
            assignee_raw = match.group(1)
            
            # 檢查是否為 Synology Chat 內部格式 u:ID
            if assignee_raw.startswith('u:'):
                # 提取用戶ID
                user_id_match = re.match(r'u:(\d+)', assignee_raw)
                if user_id_match:
                    assignee_query = user_id_match.group(1)  # 只保留數字ID
                    logger.info(f"解析 Synology Chat 格式: @{assignee_raw} -> 用戶ID {assignee_query}")
            else:
                # 一般用戶名格式
                assignee_query = assignee_raw
                logger.info(f"解析一般格式: @{assignee_raw}")
            
            # 從標題中移除 @assignee 部分
            text_for_subject = re.sub(r'@\S+', '', text_raw).strip()
            text_for_subject = re.sub(r'\s+', ' ', text_for_subject)  # 清理多餘空白
    
    # 2. 如果沒有 @ 符號，嘗試從文字中識別常見的用戶名格式
    elif not assignee_query:
        # 搜尋常見的用戶名模式 (英文名.姓氏)
        name_patterns = [
            r'\b([a-zA-Z]+\.[a-zA-Z]+)\b',  # john.doe
            r'\b([a-zA-Z]+_[a-zA-Z]+)\b',   # john_doe  
        ]
        
        for pattern in name_patterns:
            matches = re.findall(pattern, text_raw)
            if matches:
                assignee_query = matches[0]
                logger.info(f"從文字中識別用戶名: {assignee_query}")
                # 不移除這部分文字，因為可能是描述的一部分
                break

    # 建 Redmine 主議題內容
    subject = text_for_subject[:120] if text_for_subject else text_raw[:120]
    description_lines = [
        f"**來源頻道**: {form.get('channel_name','')} (id={channel_id})",
        f"**使用者**: {form.get('username','')} (id={form.get('user_id','')})",
        f"**指派者**: {assignee_query}" if assignee_query else "",
        f"**原始文字**:\n{text_raw}",
    ]
    description = "\n\n".join([line for line in description_lines if line])

    # 建立主議題（設定7個工作天的到期日）
    creation_time = datetime.now()
    main_issue_due_date = calculate_business_days(creation_time, 7)
    logger.info(f"準備建立主議題: subject={subject[:50]}, assignee={assignee_query}, due_date={main_issue_due_date}")
    
    r_code, r_body, parent_issue_id = create_redmine_issue(subject, description, assignee_query, due_date=main_issue_due_date)
    logger.info(f"主議題建立結果: status={r_code}, id={parent_issue_id}")
    logger.info(f"主議題回應內容: {r_body[:500]}")

    # 如果主議題建立成功，建立子議題
    subtask_results = []
    if 200 <= r_code < 300:
        if parent_issue_id:
            logger.info(f"✅ 主議題建立成功！開始建立子議題，父議題ID: {parent_issue_id}")
            try:
                subtask_results = create_business_lead_subtasks(parent_issue_id, creation_time, assignee_query)
                success_count = sum(1 for code, _ in subtask_results if 200 <= code < 300)
                logger.info(f"📊 子議題建立完成，成功: {success_count}/{len(subtask_results)}")
                
                # 詳細記錄每個子議題的結果
                for i, (status_code, result) in enumerate(subtask_results, 1):
                    if 200 <= status_code < 300:
                        logger.info(f"✅ 子議題 {i}: {result}")
                    else:
                        logger.error(f"❌ 子議題 {i}: {result}")
            except Exception as e:
                logger.error(f"❌ 建立子議題時發生異常: {e}")
                subtask_results = [(500, f"異常錯誤: {str(e)}") for _ in range(3)]
        else:
            logger.warning("⚠️ 主議題建立成功但未取得議題ID，跳過子議題建立")
            logger.warning(f"主議題回應內容: {r_body}")
    else:
        logger.error(f"❌ 主議題建立失敗，狀態碼: {r_code}，跳過子議題建立")

    # 準備回貼訊息
    if 200 <= r_code < 300:
        success_subtasks = sum(1 for code, _ in subtask_results if 200 <= code < 300)
        total_subtasks = len(subtask_results)
        if success_subtasks == total_subtasks:
            ack_msg = f"✅ 已建立 Redmine 主議題及 {success_subtasks} 個子議題"
        else:
            ack_msg = f"✅ 已建立 Redmine 主議題，子議題 {success_subtasks}/{total_subtasks} 成功"
    else:
        ack_msg = f"❌ 建議題失敗（HTTP {r_code}）"

    # 回貼訊息（依頻道對應 URL）
    c_status, c_body = send_chat_message(ack_msg, channel_id)
    logger.info(f"Chat ack status={c_status} body={c_body}")

    return JSONResponse({
        "ok": True, 
        "redmine_status": r_code,
        "parent_issue_id": parent_issue_id,
        "subtasks_created": len([r for r in subtask_results if 200 <= r[0] < 300])
    })


@app.get("/")
def root():
    return JSONResponse({"detail": "Not Found"}, status_code=404)


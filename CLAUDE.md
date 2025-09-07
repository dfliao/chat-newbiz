# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based chat webhook service that integrates Synology Chat with Redmine issue tracking. The service receives messages from chat channels, filters for specific keywords (default: "新商機"), and automatically creates Redmine issues while posting confirmation messages back to the chat.

## Architecture

The system is a single FastAPI service:

### Core Service (`app.py`)
- **FastAPI application** running on port 8085 (configurable via `PORT` env var)
- **Multi-channel support**: Handles multiple chat channels with per-channel token validation and webhook URLs
- **Webhook endpoint**: `/chat_webhook` processes incoming Synology Chat outgoing webhooks
- **Token verification**: Supports both single token (`OUTGOING_TOKEN`) and per-channel tokens (`CHAT_TOKENS` format: `"196:tokA,94:tokB"`)
- **Channel filtering**: Optional restriction via `CHAT_CHANNEL_IDS` 
- **Bidirectional integration**: Receives outgoing webhooks and sends responses via incoming webhooks
- **Advanced Redmine integration**: 
  - Creates parent issues with structured descriptions and 7-day due dates
  - Auto-creates 3 sequential subtasks with calculated due dates:
    - 合法性與可行性評估 (建立日 +2 工作天)
    - 初步模組舖排圖說 (建立日 +4 工作天, 上個任務完成 +2 工作天)  
    - 預算報價 (建立日 +7 工作天, 上個任務完成 +3 工作天)
  - Flexible assignee detection:
    - Synology Chat @mentions (auto-converted to @u:ID)
    - Direct @username or @user_id syntax
    - Smart username detection without @ symbol (john.doe, john_doe patterns)
  - Intelligent user lookup by ID or name matching
  - Business day calculation for due dates
  - Enhanced logging with emoji indicators for debugging

## Configuration

The application is configured entirely through environment variables:

### Chat Integration
- `OUTGOING_TOKEN`: Single token for webhook verification (legacy single-channel mode)
- `CHAT_TOKENS`: Per-channel token mapping (`"196:tokA,94:tokB"`)
- `CHAT_CHANNEL_IDS`: Comma-separated allowed channel IDs
- `CHAT_INCOMING_URLS`: Per-channel incoming webhook URL mapping (`"196:urlA,94:urlB"`)
- `CHAT_WEBHOOK_URL`: Default incoming webhook URL when channel-specific URL not found
- `CHAT_VERIFY_TLS`: Boolean for TLS certificate verification (default: false)

### Redmine Integration
- `REDMINE_URL`: Base Redmine URL (without trailing slash)
- `REDMINE_API_KEY`: API key for authentication
- `REDMINE_PROJECT` / `REDMINE_PROJECT_ID`: Project identifier
- `REDMINE_TRACKER_ID`, `REDMINE_STATUS_ID`: Issue defaults (optional)
- `REDMINE_VERIFY`: Boolean for TLS verification (default: false)

### Other
- `KEYWORD`: Trigger keyword for processing (default: "新商機")
- `PORT`: Service port (default: 8085)

## Common Commands

### Development
```bash
# Install dependencies
pip install -r requirements.txt

# Start service (foreground)
python app.py

# Start service (background with logging)
./start.sh

# Stop service
./stop.sh
```

### Docker Deployment
```bash
# Run with docker-compose
docker-compose up -d

# View logs
docker-compose logs -f chat-newbiz

# Stop service
docker-compose down
```


### Health Check
```bash
curl http://localhost:8085/health
```

## Key Implementation Details

### Message Processing Flow
1. **Webhook receives** Synology Chat outgoing webhook (form-encoded)
2. **Token validation** using per-channel or global token
3. **Channel filtering** if `CHAT_CHANNEL_IDS` is configured  
4. **Keyword detection** in message text (supports multiple keywords)
5. **Assignee parsing** from @username or @user_id syntax
6. **Main Redmine issue creation** with structured description including channel/user info
7. **Subtask creation** with calculated due dates (business days only)
8. **User lookup** in Redmine database for assignee matching
9. **Response posting** with creation summary to appropriate channel

### Usage Examples
```
# Basic new business lead
新商機：客戶詢問企業版方案

# With assignee by username (with @)
新商機：大型企業客戶需求 @john.doe

# With assignee by ID (with @)  
新商機：政府單位專案機會 @123

# Synology Chat internal format (auto-converted)
新商機：重要客戶需求 @sandy.chung  → becomes @u:4 in webhook

# Smart detection without @ symbol
新商機測試 任務負責人 sandy.chung 鐘淑萍 特助
                       ↑ auto-detected as assignee
```

### Testing and Debugging
```bash
# Test webhook endpoint (bypasses token validation)
curl -X POST http://localhost:8085/test_webhook \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "text=新商機測試 @u:4&channel_id=196"

# View detailed logs
docker-compose logs -f chat-newbiz | grep -E "(🧪|🔍|🏗️)"
```

### Environment Variable Parsing
- `parse_bool()`: Converts various string formats to boolean
- `parse_map()`: Parses `"k1:v1,k2:v2"` format for channel mappings
- Per-channel configurations take precedence over global settings

### Security Considerations
- Tokens are masked in logs (only last 8 characters shown)
- TLS verification disabled by default for self-signed certificates
- Channel-based access control via `CHAT_CHANNEL_IDS`

## File Structure
- `app.py`: Main FastAPI service
- `requirements.txt`: Python dependencies
- `docker-compose.yaml`: Container deployment configuration
- `start.sh` / `stop.sh`: Service management scripts
- `run_newbiz.sh`: Alternative runner with Synology Chat API authentication
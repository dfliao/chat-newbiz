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
- **Direct Redmine integration**: Creates issues with structured descriptions including channel and user information

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
4. **Keyword detection** in message text
5. **Redmine issue creation** with structured description including channel/user info
6. **Response posting** to appropriate channel via incoming webhook

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
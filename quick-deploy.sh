#!/bin/bash
# 一鍵部署腳本（本地 + 遠端）
set -euo pipefail

# 讀取參數
COMMIT_MSG="$*"
REMOTE_HOST=${REMOTE_HOST:-""}
REMOTE_USER=${REMOTE_USER:-""}
REMOTE_PATH=${REMOTE_PATH:-""}
DEPLOY_MODE=${DEPLOY_MODE:-"python"}  # docker 或 python

echo "🚀 一鍵部署腳本啟動..."

# 檢查必要的遠端連線參數
if [[ -n "$REMOTE_HOST" && -n "$REMOTE_USER" && -n "$REMOTE_PATH" ]]; then
    REMOTE_DEPLOY=true
    echo "🌐 遠端部署模式: $REMOTE_USER@$REMOTE_HOST:$REMOTE_PATH"
else
    REMOTE_DEPLOY=false
    echo "📋 僅執行本地部署（需手動在伺服器執行 update.sh）"
fi

# 步驟 1: 本地部署
echo ""
echo "=== 步驟 1: 本地部署 ==="
if [[ -n "$COMMIT_MSG" ]]; then
    bash deploy.sh "$COMMIT_MSG"
else
    bash deploy.sh
fi

# 步驟 2: 遠端部署（如果有設定）
if [[ "$REMOTE_DEPLOY" == "true" ]]; then
    echo ""
    echo "=== 步驟 2: 遠端部署 ==="
    
    echo "🔐 連接遠端伺服器並更新..."
    ssh "$REMOTE_USER@$REMOTE_HOST" "cd $REMOTE_PATH && bash update.sh $DEPLOY_MODE"
    
    echo "✅ 遠端部署完成！"
else
    echo ""
    echo "=== 步驟 2: 手動遠端部署 ==="
    echo "請在伺服器上執行以下指令："
    echo "cd /path/to/chat-newbiz"
    echo "bash update.sh          # Python 方式"
    echo "bash update.sh docker   # Docker 方式"
fi

echo ""
echo "🎉 部署流程完成！"
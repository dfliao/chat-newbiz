#!/bin/bash
# 本地開發端部署腳本
set -euo pipefail

echo "🚀 開始本地部署流程..."

# 檢查是否有變更
if [[ -n $(git status --porcelain) ]]; then
    echo "📝 發現檔案變更，準備提交..."
    
    # 顯示變更的檔案
    echo "變更的檔案："
    git status --short
    
    # 讀取提交訊息
    if [[ $# -gt 0 ]]; then
        COMMIT_MSG="$*"
    else
        echo -n "請輸入提交訊息（預設: Update code）: "
        read -r COMMIT_MSG
        COMMIT_MSG=${COMMIT_MSG:-"Update code"}
    fi
    
    # 提交變更
    echo "📤 提交變更..."
    git add .
    git commit -m "$(cat <<EOF
$COMMIT_MSG

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
    
    # 推送到 GitHub
    echo "🌐 推送到 GitHub..."
    git push origin master
    
    echo "✅ 本地部署完成！"
else
    echo "ℹ️  沒有檔案變更，跳過提交步驟"
fi

echo ""
echo "📋 接下來在伺服器上執行："
echo "   bash update.sh"
echo "或"
echo "   bash update.sh docker  # 使用 Docker 方式"
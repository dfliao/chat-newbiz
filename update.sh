#!/bin/bash
# 伺服器端更新腳本
set -euo pipefail

DEPLOY_MODE=${1:-"python"}  # 預設使用 Python 模式，可傳入 "docker"

echo "🔄 開始伺服器更新流程..."
echo "📋 部署模式: $DEPLOY_MODE"

# 檢查 git 狀態
echo "📡 檢查 Git 狀態..."
git fetch origin

# 檢查是否有新的提交
LOCAL=$(git rev-parse @)
REMOTE=$(git rev-parse @{u} 2>/dev/null || echo "")
if [[ "$LOCAL" == "$REMOTE" ]]; then
    echo "ℹ️  代碼已是最新版本"
else
    echo "📥 發現新版本，開始更新..."
    git pull origin master
    echo "✅ 代碼更新完成"
fi

# 根據模式停止服務
echo "🛑 停止現有服務..."
case $DEPLOY_MODE in
    "docker")
        if docker-compose ps | grep -q "chat-newbiz"; then
            echo "🐳 停止 Docker 服務..."
            docker-compose down
        else
            echo "ℹ️  Docker 服務未運行"
        fi
        ;;
    "python"|*)
        if [[ -f "./stop.sh" ]]; then
            echo "🐍 停止 Python 服務..."
            ./stop.sh
        else
            echo "ℹ️  找不到 stop.sh，跳過停止步驟"
        fi
        ;;
esac

# 等待服務完全停止
sleep 2

# 根據模式重新啟動服務
echo "🚀 重新啟動服務..."
case $DEPLOY_MODE in
    "docker")
        echo "🐳 使用 Docker 啟動服務..."
        docker-compose up --build -d
        
        # 等待服務啟動
        echo "⏳ 等待服務啟動..."
        sleep 5
        
        # 檢查服務狀態
        if docker-compose ps | grep -q "Up"; then
            echo "✅ Docker 服務啟動成功"
            echo "📊 容器狀態："
            docker-compose ps
        else
            echo "❌ Docker 服務啟動失敗"
            echo "📋 查看日誌："
            docker-compose logs --tail=20 chat-newbiz
            exit 1
        fi
        ;;
    "python"|*)
        if [[ -f "./start.sh" ]]; then
            echo "🐍 使用 Python 啟動服務..."
            ./start.sh
        else
            echo "❌ 找不到 start.sh 腳本"
            exit 1
        fi
        ;;
esac

# 健康檢查
echo "🏥 執行健康檢查..."
sleep 3
if curl -fsS http://localhost:8085/health >/dev/null 2>&1; then
    echo "✅ 服務健康檢查通過"
else
    echo "⚠️  健康檢查失敗，請檢查服務狀態"
fi

echo ""
echo "🎉 伺服器更新完成！"
echo "🌐 服務地址: http://localhost:8085"
echo "🏥 健康檢查: curl http://localhost:8085/health"

# 顯示最新的 commit 資訊
echo ""
echo "📜 當前版本資訊："
git log --oneline -3
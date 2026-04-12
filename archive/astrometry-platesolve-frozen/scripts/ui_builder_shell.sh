#!/usr/bin/env bash
# OGScope UI Builder 交互式 Shell / Interactive Shell for UI Builder
# 启动 Docker Compose 容器并进入 / Start Docker Compose container and attach
#
# 环境变量 / Environment:
#   OGSCOPE_NPM_REGISTRY  — npm 镜像源（中国：https://registry.npmmirror.com）
#                          npm registry mirror (CN: https://registry.npmmirror.com)
#
# 用法 / Usage:
#   ./scripts/ui_builder_shell.sh                    # 进入容器 / Enter container
#   ./scripts/ui_builder_shell.sh build              # 直接构建并退出 / Build and exit
#   ./scripts/ui_builder_shell.sh install            # 安装依赖并退出 / Install deps and exit
#   ./scripts/ui_builder_shell.sh clean              # 清理构建产物 / Clean build artifacts
#   ./scripts/ui_builder_shell.sh stop               # 停止容器 / Stop container

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${PROJECT_DIR}/docker/compose.yml"
CONTAINER_NAME="ogscope-ui-builder"

cd "${PROJECT_DIR}"

# 检查 Docker 和 Docker Compose / Check Docker and Docker Compose
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装 / Docker not found"
    exit 1
fi

if ! docker compose version &> /dev/null 2>&1; then
    echo "❌ Docker Compose (v2) 未安装 / Docker Compose v2 not found"
    echo "   安装指南 / Install guide: https://docs.docker.com/compose/install/"
    exit 1
fi

# 设置用户 ID / Set user ID
export USER_ID=$(id -u)
export GROUP_ID=$(id -g)

# 函数：确保容器运行 / Function: Ensure container is running
ensure_container_running() {
    if ! docker ps --filter "name=${CONTAINER_NAME}" --filter "status=running" | grep -q "${CONTAINER_NAME}"; then
        echo "🚀 启动容器 / Starting container: ${CONTAINER_NAME}..."
        docker compose -f "${COMPOSE_FILE}" up -d
        echo "⏳ 等待容器就绪 / Waiting for container to be ready..."
        sleep 2
    else
        echo "✅ 容器已运行 / Container already running: ${CONTAINER_NAME}"
    fi
}

# 函数：执行容器命令 / Function: Execute command in container
exec_in_container() {
    docker compose -f "${COMPOSE_FILE}" exec ui-builder "$@"
}

# 函数：显示帮助信息 / Function: Show help message
show_help() {
    cat << 'EOF'
OGScope UI Builder Shell / OGScope UI 构建器 Shell

用法 / Usage:
  ./scripts/ui_builder_shell.sh [COMMAND]

命令 / Commands:
  (无参数)    进入交互式 shell / Enter interactive shell
  build       构建 UI（npm run build）/ Build UI
  install     安装依赖（npm install）/ Install dependencies  
  ci          干净安装依赖（npm ci）/ Clean install dependencies
  dev         启动开发服务器（npm run dev）/ Start dev server
  clean       清理构建产物和 node_modules / Clean build artifacts
  stop        停止容器 / Stop container
  restart     重启容器 / Restart container
  logs        查看容器日志 / View container logs
  help        显示此帮助 / Show this help

容器内可用命令 / Commands inside container:
  npm install              # 安装依赖 / Install dependencies
  npm run build            # 构建生产版本 / Build for production
  npm run dev              # 开发模式（热重载）/ Dev mode with hot reload
  npm run preview          # 预览构建产物 / Preview build
  
  cd /workspace/analysis-ui  # UI 源码目录 / UI source directory
  cd /workspace/static       # 静态文件目录 / Static files directory

环境变量 / Environment:
  OGSCOPE_NPM_REGISTRY     # npm 镜像源 / npm registry mirror
                           # 示例 / Example: https://registry.npmmirror.com

示例 / Examples:
  # 进入容器交互式构建
  ./scripts/ui_builder_shell.sh
  
  # 快速构建
  ./scripts/ui_builder_shell.sh build
  
  # 使用国内镜像
  OGSCOPE_NPM_REGISTRY=https://registry.npmmirror.com ./scripts/ui_builder_shell.sh install
  
  # 开发模式（热重载）
  ./scripts/ui_builder_shell.sh dev
EOF
}

# 解析命令 / Parse command
CMD="${1:-shell}"

case "${CMD}" in
    help|--help|-h)
        show_help
        exit 0
        ;;
    
    shell|bash|sh)
        ensure_container_running
        echo "🐳 进入容器 / Entering container: ${CONTAINER_NAME}"
        echo "   工作目录 / Working dir: /workspace/analysis-ui"
        echo "   退出 / Exit: 输入 'exit' 或按 Ctrl+D"
        echo ""
        exec_in_container bash
        ;;
    
    build)
        ensure_container_running
        echo "📦 构建 UI / Building UI..."
        
        # 检查并安装依赖 / Check and install dependencies
        echo "🔍 检查依赖 / Checking dependencies..."
        exec_in_container bash -c '
            if [ ! -d "node_modules" ] || [ ! -f "node_modules/.package-lock.json" ]; then
                echo "📦 安装依赖 / Installing dependencies..."
                npm ci --include=dev --prefer-offline 2>/dev/null || npm install --include=dev
            else
                echo "✅ 依赖已存在 / Dependencies already installed"
            fi
        '
        
        exec_in_container npm run build
        echo "✅ 构建完成 / Build completed"
        echo "📁 构建产物 / Build artifacts: web/static/analysis-lab/"
        ;;
    
    install)
        ensure_container_running
        echo "📦 安装依赖 / Installing dependencies..."
        if [ -n "${OGSCOPE_NPM_REGISTRY:-}" ]; then
            exec_in_container npm config set registry "${OGSCOPE_NPM_REGISTRY}"
        fi
        exec_in_container npm install --include=dev
        echo "✅ 依赖安装完成 / Dependencies installed"
        ;;
    
    ci)
        ensure_container_running
        echo "📦 干净安装依赖 / Clean installing dependencies..."
        if [ -n "${OGSCOPE_NPM_REGISTRY:-}" ]; then
            exec_in_container npm config set registry "${OGSCOPE_NPM_REGISTRY}"
        fi
        exec_in_container npm ci --include=dev
        echo "✅ 依赖安装完成 / Dependencies installed"
        ;;
    
    dev)
        ensure_container_running
        echo "🔥 启动开发服务器 / Starting dev server..."
        echo "   访问 / Access: http://localhost:5173"
        echo "   停止 / Stop: Ctrl+C"
        exec_in_container npm run dev -- --host 0.0.0.0
        ;;
    
    clean)
        ensure_container_running
        echo "🗑️  清理构建产物 / Cleaning build artifacts..."
        exec_in_container rm -rf node_modules dist
        if [ -d "${PROJECT_DIR}/web/static/analysis-lab" ]; then
            rm -rf "${PROJECT_DIR}/web/static/analysis-lab"
            echo "   已删除 / Removed: web/static/analysis-lab/"
        fi
        echo "✅ 清理完成 / Clean completed"
        ;;
    
    stop)
        echo "🛑 停止容器 / Stopping container..."
        docker compose -f "${COMPOSE_FILE}" down
        echo "✅ 容器已停止 / Container stopped"
        ;;
    
    restart)
        echo "🔄 重启容器 / Restarting container..."
        docker compose -f "${COMPOSE_FILE}" restart
        echo "✅ 容器已重启 / Container restarted"
        ;;
    
    logs)
        docker compose -f "${COMPOSE_FILE}" logs -f ui-builder
        ;;
    
    *)
        echo "❌ 未知命令 / Unknown command: ${CMD}"
        echo "   使用 --help 查看帮助 / Use --help for usage"
        exit 1
        ;;
esac

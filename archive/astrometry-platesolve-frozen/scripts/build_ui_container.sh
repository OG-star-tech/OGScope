#!/usr/bin/env bash
# OGScope UI 容器构建脚本 / OGScope UI Container Build Script
# 使用 Docker 构建前端，无需本地 Node.js / Build frontend using Docker without local Node.js
#
# 环境变量 / Environment:
#   OGSCOPE_UI_SKIP_BUILD_IMAGE=1  — 跳过 Docker 镜像构建（已存在时）/ Skip Docker image build if exists
#   OGSCOPE_UI_FORCE_REBUILD=1     — 强制重新构建 Docker 镜像 / Force rebuild Docker image
#   OGSCOPE_NPM_REGISTRY           — npm 镜像源（可选）/ npm registry mirror (optional)
#
# 用法 / Usage:
#   ./scripts/build_ui_container.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
UI_SOURCE_DIR="${PROJECT_DIR}/web/analysis-ui"
UI_OUTPUT_DIR="${PROJECT_DIR}/web/static/analysis-lab"
DOCKERFILE="${PROJECT_DIR}/docker/Dockerfile.ui-builder"
IMAGE_NAME="ogscope-ui-builder:latest"

echo "======================================"
echo "  OGScope UI 容器构建 / UI Container Build"
echo "======================================"

# 检查 Docker / Check Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装 / Docker not found"
    echo "   安装指南 / Install guide: https://docs.docker.com/engine/install/"
    exit 1
fi

# 检查源码目录 / Check source directory
if [ ! -f "${UI_SOURCE_DIR}/package.json" ]; then
    echo "❌ 未找到 ${UI_SOURCE_DIR}/package.json"
    exit 1
fi

cd "${PROJECT_DIR}"

# 构建 Docker 镜像 / Build Docker image
if [ "${OGSCOPE_UI_FORCE_REBUILD:-0}" = "1" ] || [ "${OGSCOPE_UI_SKIP_BUILD_IMAGE:-0}" != "1" ]; then
    echo "🐳 构建 Docker 镜像 / Building Docker image: ${IMAGE_NAME}..."
    
    BUILD_ARGS=()
    if [ "${OGSCOPE_UI_FORCE_REBUILD:-0}" = "1" ]; then
        BUILD_ARGS+=(--no-cache)
    fi
    
    docker build \
        "${BUILD_ARGS[@]}" \
        -t "${IMAGE_NAME}" \
        -f "${DOCKERFILE}" \
        "${PROJECT_DIR}/docker/"
    
    echo "✅ Docker 镜像构建完成 / Image built successfully"
else
    echo "⏭️  跳过镜像构建（OGSCOPE_UI_SKIP_BUILD_IMAGE=1）/ Skipping image build"
fi

# 检查镜像是否存在 / Check if image exists
if ! docker image inspect "${IMAGE_NAME}" &> /dev/null; then
    echo "❌ Docker 镜像不存在 / Image not found: ${IMAGE_NAME}"
    echo "   请运行：OGSCOPE_UI_SKIP_BUILD_IMAGE=0 $0 / Run: OGSCOPE_UI_SKIP_BUILD_IMAGE=0 $0"
    exit 1
fi

# 准备构建命令 / Prepare build command
BUILD_CMD="npm ci --prefer-offline && npm run build"

# 可选：设置 npm 镜像 / Optional: Set npm registry
if [ -n "${OGSCOPE_NPM_REGISTRY:-}" ]; then
    BUILD_CMD="npm config set registry ${OGSCOPE_NPM_REGISTRY} && ${BUILD_CMD}"
    echo "🌐 使用 npm 镜像 / Using npm registry: ${OGSCOPE_NPM_REGISTRY}"
fi

# 在容器中构建 UI / Build UI in container
echo "📦 在容器中构建前端 / Building UI in container..."
echo "   源码目录 / Source: ${UI_SOURCE_DIR}"
echo "   输出目录 / Output: ${UI_OUTPUT_DIR}"

# 清理旧的输出目录（可选）/ Clean old output (optional)
if [ -d "${UI_OUTPUT_DIR}" ]; then
    echo "🗑️  清理旧构建产物 / Cleaning old build artifacts..."
    rm -rf "${UI_OUTPUT_DIR}"
fi

# 运行容器构建 / Run container build
# 挂载整个 web/ 目录，因为 vite 输出到 ../static/analysis-lab
# Mount entire web/ dir since vite outputs to ../static/analysis-lab
docker run --rm \
    -v "${PROJECT_DIR}/web:/workspace:rw" \
    -w /workspace/analysis-ui \
    -u "$(id -u):$(id -g)" \
    "${IMAGE_NAME}" \
    "${BUILD_CMD}"

# 验证构建产物 / Verify build output
if [ ! -f "${UI_OUTPUT_DIR}/system.html" ]; then
    echo "❌ 构建失败：未找到 system.html / Build failed: system.html not found"
    exit 1
fi

echo "✅ UI 构建完成 / UI build completed successfully"
echo "📁 构建产物 / Build artifacts: ${UI_OUTPUT_DIR}"

# 列出构建产物 / List build artifacts
echo ""
echo "构建产物列表 / Build artifacts:"
ls -lh "${UI_OUTPUT_DIR}/" | grep -E '\.(html|js|css)$' || true

echo ""
echo "======================================"
echo "✅ 完成 / Done"
echo "======================================"
echo ""
echo "下一步 / Next steps:"
echo "1. 检查构建产物 / Check build artifacts: ${UI_OUTPUT_DIR}"
echo "2. 同步到开发板 / Sync to dev board:"
echo "   rsync -avz ${UI_OUTPUT_DIR}/ ogstartech@192.168.0.150:/home/ogstartech/OGScope/web/static/analysis-lab/"
echo "3. 重启服务 / Restart service:"
echo "   ssh ogstartech@192.168.0.150 'sudo systemctl restart ogscope'"

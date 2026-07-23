#!/usr/bin/env bash
# OGScope bootstrap script
# 作用：把任意源码目录部署到固定目录 /opt/ogscope，再执行安装脚本

set -euo pipefail

if [ "${EUID}" -eq 0 ]; then
    echo "❌ 请不要直接使用 root 运行 / Do not run as root"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_SOURCE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

SOURCE_DIR="${OGSCOPE_SOURCE_DIR:-${DEFAULT_SOURCE_DIR}}"
DEPLOY_DIR="${OGSCOPE_DEPLOY_DIR:-/opt/ogscope}"
INSTALL_MODE="${OGSCOPE_BOOTSTRAP_MODE:-full}" # full|min

if [ ! -f "${SOURCE_DIR}/pyproject.toml" ]; then
    echo "❌ 源码目录无效 / Invalid source dir: ${SOURCE_DIR}"
    echo "   请设置 OGSCOPE_SOURCE_DIR 指向 OGScope 仓库根目录"
    exit 2
fi

if ! command -v rsync >/dev/null 2>&1; then
    echo "❌ 缺少 rsync，请先安装 / rsync is required"
    exit 3
fi

echo "📦 OGScope Bootstrap"
echo "   Source: ${SOURCE_DIR}"
echo "   Deploy: ${DEPLOY_DIR}"
echo "   Mode:   ${INSTALL_MODE}"

sudo install -d -m 755 "$(dirname "${DEPLOY_DIR}")"
if [ ! -d "${DEPLOY_DIR}" ]; then
    sudo mkdir -p "${DEPLOY_DIR}"
fi
sudo chown "${USER}:${USER}" "${DEPLOY_DIR}"

rsync -a --delete \
    --exclude ".git/" \
    --exclude ".venv/" \
    --exclude "__pycache__/" \
    --exclude ".pytest_cache/" \
    --exclude "web/spa/node_modules/" \
    --exclude "uploads/" \
    --exclude "logs/" \
    --exclude "data/" \
    "${SOURCE_DIR}/" "${DEPLOY_DIR}/"

INSTALL_SCRIPT="${DEPLOY_DIR}/scripts/install.sh"
if [ "${INSTALL_MODE}" = "min" ]; then
    INSTALL_SCRIPT="${DEPLOY_DIR}/scripts/install-min.sh"
fi

if [ ! -x "${INSTALL_SCRIPT}" ]; then
    chmod +x "${INSTALL_SCRIPT}" || true
fi

echo "🚀 开始执行安装 / Running install script..."
OGSCOPE_DEPLOY_DIR="${DEPLOY_DIR}" "${INSTALL_SCRIPT}"

echo "✅ Bootstrap 完成 / Bootstrap completed"

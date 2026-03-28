#!/bin/bash
# OGScope 开发板增量更新 / Board incremental update (after first install)
#
# 环境变量 / Environment:
#   OGSCOPE_GIT_PULL=1     — 在更新前执行 git pull（需 git 仓库）/ Run git pull before update (requires .git)
#   OGSCOPE_INSTALL_DEV=1  — poetry install 时包含 dev 依赖 / Include dev dependency group
#   POETRY_INSTALLER_MAX_WORKERS — 默认 2，低配板可设为 1 / Default 2; set to 1 on low-RAM boards
#   OGSCOPE_MIRROR=auto|cn|international — 与 install.sh 相同 / Same as install.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SERVICE_NAME="ogscope"

cd "${PROJECT_DIR}"

# 加载镜像逻辑 / Load mirror helpers
# shellcheck source=mirror.sh
source "${SCRIPT_DIR}/mirror.sh"
OGSCOPE_MIRROR_RESOLVED="$(ogscope_resolve_mirror)"
echo "🌐 镜像模式 / Mirror: ${OGSCOPE_MIRROR_RESOLVED}（OGSCOPE_MIRROR=${OGSCOPE_MIRROR:-auto}）"

if [ ! -f "${PROJECT_DIR}/pyproject.toml" ]; then
    echo "❌ 未找到 pyproject.toml / pyproject.toml not found"
    exit 1
fi

export PATH="${HOME}/.local/bin:${PATH}"
if ! command -v poetry >/dev/null 2>&1; then
    echo "❌ 未找到 Poetry，请先运行 ./scripts/install.sh / Poetry not found; run ./scripts/install.sh first"
    exit 1
fi

if [ "${OGSCOPE_GIT_PULL:-}" = "1" ]; then
    if [ -d "${PROJECT_DIR}/.git" ]; then
        echo "📥 git pull..."
        git pull --ff-only
    else
        echo "⚠️ 非 git 仓库，跳过 git pull / Not a git repo; skipping git pull"
    fi
fi

# 与 install.sh 保持一致，避免 PEP 668 / Match install.sh; avoid PEP 668 issues
poetry config virtualenvs.create true
poetry config virtualenvs.in-project true
poetry config virtualenvs.options.system-site-packages true 2>/dev/null || true

INSTALL_ARGS=(install --no-interaction)
if [ "${OGSCOPE_INSTALL_DEV:-}" = "1" ]; then
    echo "📦 poetry install（含 dev / with dev）..."
else
    INSTALL_ARGS+=(--only main)
    echo "📦 poetry install --only main..."
fi

export POETRY_INSTALLER_MAX_WORKERS="${POETRY_INSTALLER_MAX_WORKERS:-2}"

if [ "${OGSCOPE_MIRROR_RESOLVED}" = "cn" ]; then
    ogscope_export_pypi_mirror_cn
else
    ogscope_export_pypi_mirror_international
fi

poetry "${INSTALL_ARGS[@]}"

echo "🔄 重启服务 / Restarting service..."
sudo systemctl daemon-reload
sudo systemctl restart "${SERVICE_NAME}"

sleep 2
sudo systemctl --no-pager status "${SERVICE_NAME}" || true

echo ""
echo "✅ 更新完成 / Update done. 日志 / Logs: sudo journalctl -u ${SERVICE_NAME} -f"
echo "健康检查 / Health: curl -s http://127.0.0.1:8000/health"

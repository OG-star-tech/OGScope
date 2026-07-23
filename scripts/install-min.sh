#!/bin/bash
# OGScope 最小安装脚本 / OGScope minimal installation script
# 目标：仅安装运行所需最小依赖并注册主服务 / Goal: install minimal runtime deps and register service
#
# 环境变量 / Environment:
#   OGSCOPE_INSTALL_DEV=1      — 安装 dev 依赖 / Install dev dependency group
#   OGSCOPE_MIRROR=auto|cn|international — 镜像策略 / Mirror strategy
#   OGSCOPE_NONINTERACTIVE=1   — 跳过镜像交互 / Skip mirror prompt
#   OGSCOPE_POETRY_INSTALLER_URL — 可选 Poetry 安装地址 / Optional Poetry installer URL
#   OGSCOPE_MIN_SKIP_APT=1     — 跳过 apt 安装（用于已满足环境）/ Skip apt install when prerequisites are ready

set -euo pipefail

if [ "${EUID}" -eq 0 ]; then
    echo "❌ 请不要使用 root 用户运行此脚本 / Do not run this script as root"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEPLOY_DIR="${OGSCOPE_DEPLOY_DIR:-/opt/ogscope}"
PROJECT_DIR="${DEPLOY_DIR}"
SERVICE_NAME="ogscope"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
OGSCOPE_ENV_DIR="/etc/ogscope"
OGSCOPE_ENV_FILE="${OGSCOPE_ENV_DIR}/ogscope.env"

if [ ! -f "${PROJECT_DIR}/pyproject.toml" ]; then
    echo "❌ 未找到部署目录中的 pyproject.toml: ${PROJECT_DIR}"
    echo "   请先运行 ./scripts/bootstrap.sh 将源码同步到固定部署目录"
    exit 1
fi

cd "${PROJECT_DIR}"

# shellcheck source=mirror.sh
source "${SCRIPT_DIR}/mirror.sh"
ogscope_prompt_mirror_if_needed
if ! ogscope_load_os_release; then
    exit 1
fi
ogscope_print_os_summary
if ! ogscope_require_debian_family_apt; then
    exit 1
fi

OGSCOPE_MIRROR_RESOLVED="$(ogscope_resolve_mirror)"
echo "🌐 镜像模式 / Mirror: ${OGSCOPE_MIRROR_RESOLVED}"
if [ "${OGSCOPE_MIRROR_RESOLVED}" = "cn" ]; then
    ogscope_apply_apt_mirror_cn
fi

if [ "${OGSCOPE_MIN_SKIP_APT:-0}" != "1" ]; then
    echo "📦 安装最小系统依赖 / Installing minimal system dependencies..."
    sudo apt update
    sudo apt install -y \
        python3 \
        python3-pip \
        python3-venv \
        python3-dev \
        git \
        curl \
        build-essential \
        libturbojpeg0
fi

if ! command -v poetry >/dev/null 2>&1; then
    echo "📦 安装 Poetry / Installing Poetry..."
    _poetry_installer="${OGSCOPE_POETRY_INSTALLER_URL:-https://install.python-poetry.org}"
    curl -sSL --retry 3 --connect-timeout 30 "${_poetry_installer}" | python3 -
fi

export PATH="${HOME}/.local/bin:${PATH}"
if ! grep -q 'export PATH="$HOME/.local/bin:$PATH"' "${HOME}/.bashrc" 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "${HOME}/.bashrc"
fi

poetry config virtualenvs.create true
poetry config virtualenvs.in-project true
poetry config virtualenvs.options.system-site-packages true 2>/dev/null || true

INSTALL_ARGS=(install --no-interaction)
if [ "${OGSCOPE_INSTALL_DEV:-}" != "1" ]; then
    INSTALL_ARGS+=(--only main)
fi

if [ "${OGSCOPE_MIRROR_RESOLVED}" = "cn" ]; then
    ogscope_export_pypi_mirror_cn
else
    ogscope_export_pypi_mirror_international
fi

poetry "${INSTALL_ARGS[@]}"

if ! ogscope_verify_turbojpeg; then
    echo "⚠️ TurboJPEG 不可用，尝试补装 libturbojpeg0 + PyTurboJPEG / TurboJPEG unavailable; installing fallback deps"
    sudo apt install -y libturbojpeg0
    poetry run pip install --no-cache-dir "PyTurboJPEG>=1.7,<2"
fi
if ogscope_verify_turbojpeg; then
    echo "✅ TurboJPEG 编码加速已就绪 / TurboJPEG encoder ready"
else
    echo "⚠️ TurboJPEG 仍不可用，将自动回退 OpenCV / TurboJPEG still unavailable; OpenCV fallback will be used"
fi

VENV_PATH="$(poetry env info --path)"
VENV_PYTHON="${VENV_PATH}/bin/python"
if [ ! -x "${VENV_PYTHON}" ]; then
    echo "❌ 虚拟环境解释器不存在 / Missing venv python: ${VENV_PYTHON}"
    exit 1
fi

echo "📁 创建最小运行目录 / Creating minimal runtime directories..."
mkdir -p logs data uploads data/analysis data/plate_solve

# 自动同步星图数据库（与 install.sh / board-update.sh 一致）
# Auto-sync plate-solve DB (aligned with install.sh / board-update.sh).
ogscope_sync_plate_solve_database_if_needed "${PROJECT_DIR}"

echo "📝 初始化 /etc/ogscope/ogscope.env / Initializing /etc/ogscope/ogscope.env..."
sudo install -d -m 755 "${OGSCOPE_ENV_DIR}"
if [ ! -f "${OGSCOPE_ENV_FILE}" ]; then
    sudo tee "${OGSCOPE_ENV_FILE}" >/dev/null <<'EOF'
# OGScope 主配置（部署态）/ OGScope primary deployment configuration
OGSCOPE_HOST=0.0.0.0
OGSCOPE_PORT=8000
OGSCOPE_RELOAD=false
OGSCOPE_LOG_LEVEL=INFO
EOF
    sudo chown "root:${USER}" "${OGSCOPE_ENV_FILE}" 2>/dev/null || true
    sudo chmod 640 "${OGSCOPE_ENV_FILE}"
fi
sudo chown "root:${USER}" "${OGSCOPE_ENV_FILE}" 2>/dev/null || true
sudo chmod 640 "${OGSCOPE_ENV_FILE}" 2>/dev/null || true

echo "⚙️ 写入 systemd 服务 / Writing systemd service..."
sudo tee "${SERVICE_PATH}" >/dev/null <<EOF
[Unit]
Description=OGScope Service (minimal)
After=network.target

[Service]
Type=simple
User=${USER}
WorkingDirectory=${PROJECT_DIR}
EnvironmentFile=-/etc/ogscope/ogscope.env
EnvironmentFile=-/etc/ogscope/network.env
ExecStart=${VENV_PYTHON} -m ogscope.main
Restart=on-failure
RestartSec=3
TimeoutStopSec=8
KillMode=mixed

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"

echo "✅ 最小安装完成 / Minimal installation completed"
echo "   服务状态 / Service: sudo systemctl status ${SERVICE_NAME}"
echo "   健康检查 / Health: curl -s http://127.0.0.1:8000/health"
ogscope_report_plate_solve_database_status "${PROJECT_DIR}"

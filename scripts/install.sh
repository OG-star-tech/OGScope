#!/bin/bash
# OGScope 安装脚本 / OGScope installation script
# 适用于 Raspberry Pi / For Raspberry Pi

set -euo pipefail

echo "======================================"
echo "  OGScope 安装脚本"
echo "======================================"

# 检查是否为 root / Check if it is root
if [ "${EUID}" -eq 0 ]; then
    echo "❌ 请不要使用 root 用户运行此脚本"
    exit 1
fi

# 基本路径 / base path
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SERVICE_NAME="ogscope"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

echo "📁 项目目录: ${PROJECT_DIR}"

# 检查项目结构 / Check project structure
if [ ! -f "${PROJECT_DIR}/pyproject.toml" ]; then
    echo "❌ 未找到 pyproject.toml，请在项目目录中执行此脚本"
    exit 1
fi

cd "${PROJECT_DIR}"

# 更新系统 / Update system
echo "📦 更新系统包..."
sudo apt update

# 安装系统依赖 / Install system dependencies
echo "📦 安装系统依赖..."
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    git \
    curl \
    build-essential \
    libopencv-dev \
    libjpeg-dev \
    libpng-dev \
    libfreetype6-dev \
    libatlas-base-dev \
    libspidev-dev \
    python3-picamera2 \
    python3-numpy

# Python 版本提示 / Python version tips
PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "🐍 当前 python3 版本: ${PY_VER}"
echo "ℹ️ 项目要求: Python ^3.10（详见 pyproject.toml）"

# 安装 Poetry / Install Poetry
if ! command -v poetry >/dev/null 2>&1; then
    echo "📦 安装 Poetry..."
    curl -sSL https://install.python-poetry.org | python3 -
fi

# 设置 Poetry 路径 / Set Poetry path
export PATH="${HOME}/.local/bin:${PATH}"
if ! grep -q 'export PATH="$HOME/.local/bin:$PATH"' "${HOME}/.bashrc" 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "${HOME}/.bashrc"
fi

# 验证 Poetry 安装 / Verify Poetry installation
poetry --version >/dev/null
echo "✅ Poetry 已安装: $(poetry --version)"

# 安装 Python 依赖 / Install Python dependencies
echo "📦 安装 Python 依赖..."
poetry install --no-interaction

# 解析虚拟环境解释器路径 / Resolve virtual environment interpreter path
VENV_PATH="$(poetry env info --path)"
VENV_PYTHON="${VENV_PATH}/bin/python"
if [ ! -x "${VENV_PYTHON}" ]; then
    echo "❌ 未找到虚拟环境解释器: ${VENV_PYTHON}"
    exit 1
fi

# 创建必要目录 / Create necessary directories
echo "📁 创建必要目录..."
mkdir -p logs data uploads

# 兼容不同发行版的系统 Python 包路径 / Compatible with system Python package paths of different distributions
PY_PATHS=()
[ -d "/usr/lib/python3/dist-packages" ] && PY_PATHS+=("/usr/lib/python3/dist-packages")
[ -d "/usr/local/lib/python3.13/dist-packages" ] && PY_PATHS+=("/usr/local/lib/python3.13/dist-packages")
[ -d "/usr/local/lib/python3.12/dist-packages" ] && PY_PATHS+=("/usr/local/lib/python3.12/dist-packages")
[ -d "/usr/local/lib/python3.11/dist-packages" ] && PY_PATHS+=("/usr/local/lib/python3.11/dist-packages")
[ -d "/usr/local/lib/python3.10/dist-packages" ] && PY_PATHS+=("/usr/local/lib/python3.10/dist-packages")

PYTHONPATH_VALUE="$(IFS=:; echo "${PY_PATHS[*]}")"
[ -z "${PYTHONPATH_VALUE}" ] && PYTHONPATH_VALUE="/usr/lib/python3/dist-packages"

LD_LIBRARY_PATH_VALUE="/usr/lib/aarch64-linux-gnu"

# 生成 systemd 服务 / Generate systemd service
echo "⚙️ 配置 systemd 服务: ${SERVICE_PATH}"
sudo tee "${SERVICE_PATH}" >/dev/null <<EOF
[Unit]
Description=OGScope Service
After=network.target

[Service]
Type=simple
User=${USER}
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONPATH=${PYTHONPATH_VALUE}
Environment=LD_LIBRARY_PATH=${LD_LIBRARY_PATH_VALUE}
Environment=OGSCOPE_RELOAD=false
Environment=OGSCOPE_LOG_LEVEL=INFO
ExecStart=${VENV_PYTHON} -m ogscope.main
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# 重新加载并启用服务 / Reload and enable the service
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"

echo ""
echo "======================================"
echo "  ✅ 安装完成"
echo "======================================"
echo "服务名称: ${SERVICE_NAME}"
echo "虚拟环境: ${VENV_PATH}"
echo "启动命令: ${VENV_PYTHON} -m ogscope.main"
echo "PYTHONPATH: ${PYTHONPATH_VALUE}"
echo "LD_LIBRARY_PATH: ${LD_LIBRARY_PATH_VALUE}"
echo ""
echo "下一步："
echo "1. 启动服务: sudo systemctl start ${SERVICE_NAME}"
echo "2. 查看状态: sudo systemctl status ${SERVICE_NAME}"
echo "3. 查看日志: sudo journalctl -u ${SERVICE_NAME} -f"
echo "4. 重启调试: sudo systemctl restart ${SERVICE_NAME}"
echo "5. 访问 Web: http://$(hostname -I | awk '{print $1}'):8000"
echo ""


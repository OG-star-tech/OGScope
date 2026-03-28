#!/bin/bash
# OGScope 安装脚本 / OGScope installation script
# 适用于 Raspberry Pi / Orange Pi 等嵌入式板 / For Raspberry Pi, Orange Pi, etc.
#
# 环境变量 / Environment:
#   OGSCOPE_INSTALL_DEV=1  — 安装含 dev 依赖（开发机）；默认仅 main / Install dev deps; default main only
#   OGSCOPE_APT_SLOW=1     — 分批安装 apt 包并在批次间暂停，减轻低配板内存压力 / Stagger apt for low-memory boards
#   OGSCOPE_MIRROR=auto|cn|international — 软件源：auto 按语言/时区启发；中国大陆建议 cn 或保持 auto / Mirrors for CN vs abroad
#   OGSCOPE_POETRY_INSTALLER_URL — 可选，覆盖 Poetry 引导脚本 URL（国内可自建镜像）/ Optional Poetry bootstrap URL mirror

set -euo pipefail

echo "======================================"
echo "  OGScope 安装脚本 / OGScope installation script"
echo "======================================"

if [ "${EUID}" -eq 0 ]; then
    echo "❌ 请不要使用 root 用户运行此脚本 / Do not run as root"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SERVICE_NAME="ogscope"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

echo "📁 项目目录 / Project: ${PROJECT_DIR}"

if [ ! -f "${PROJECT_DIR}/pyproject.toml" ]; then
    echo "❌ 未找到 pyproject.toml / pyproject.toml not found"
    exit 1
fi

cd "${PROJECT_DIR}"

# 加载镜像逻辑（apt / PyPI）/ Load mirror helpers for apt and PyPI
# shellcheck source=mirror.sh
source "${SCRIPT_DIR}/mirror.sh"

# 识别发行版并要求 Debian 系 + apt，避免误操作 / Detect OS; require Debian family + apt for safety
if ! ogscope_load_os_release; then
    exit 1
fi
ogscope_print_os_summary
if ! ogscope_require_debian_family_apt; then
    exit 1
fi

OGSCOPE_MIRROR_RESOLVED="$(ogscope_resolve_mirror)"
echo "🌐 镜像模式 / Mirror: ${OGSCOPE_MIRROR_RESOLVED}（OGSCOPE_MIRROR=${OGSCOPE_MIRROR:-auto}）"

if [ "${OGSCOPE_MIRROR_RESOLVED}" = "cn" ]; then
    ogscope_apply_apt_mirror_cn
fi

# 低配板可选在 apt 批次间暂停 / Optional pause between apt batches on low-RAM boards
_apt_pause() {
    if [ "${OGSCOPE_APT_SLOW:-}" = "1" ]; then
        echo "⏳ 等待 3s 释放内存... / Waiting to free memory..."
        sleep 3
    fi
}

echo "📦 apt update..."
sudo apt update
_apt_pause

echo "📦 安装基础系统包 / Installing base packages..."
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    git \
    curl \
    build-essential
_apt_pause

echo "📦 安装图像与开发库 / Installing image and dev libraries..."
sudo apt install -y \
    libopencv-dev \
    libjpeg-dev \
    libpng-dev \
    libfreetype6-dev
_apt_pause

# 树莓派常见；Orange Pi 若无此包可忽略 / Raspberry Pi; skip if unavailable on Orange Pi
if apt-cache show python3-picamera2 >/dev/null 2>&1; then
    echo "📦 安装 python3-picamera2..."
    sudo apt install -y python3-picamera2 || echo "⚠️ picamera2 安装跳过 / picamera2 install skipped"
else
    echo "ℹ️ 未找到 python3-picamera2 软件包，请按板卡文档安装相机栈 / No python3-picamera2 package"
fi
_apt_pause

PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "🐍 当前 python3 版本 / python3 version: ${PY_VER}"
echo "ℹ️ 项目要求 Python ^3.10（见 pyproject.toml）"

if ! command -v poetry >/dev/null 2>&1; then
    echo "📦 安装 Poetry（官方引导脚本；与 PEP 668 兼容）..."
    echo "📦 Installing Poetry via official installer (PEP 668–safe)..."
    # 国内外统一用官方脚本，避免在系统 Python 上 pip install poetry 触发 PEP 668
    # Same official bootstrap everywhere; avoids pip install poetry on managed system Python
    _poetry_installer="${OGSCOPE_POETRY_INSTALLER_URL:-https://install.python-poetry.org}"
    curl -sSL --retry 3 --connect-timeout 30 "${_poetry_installer}" | python3 -
fi

export PATH="${HOME}/.local/bin:${PATH}"
if ! grep -q 'export PATH="$HOME/.local/bin:$PATH"' "${HOME}/.bashrc" 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "${HOME}/.bashrc"
fi

poetry --version >/dev/null
echo "✅ Poetry: $(poetry --version)"

# 强制使用项目虚拟环境，避免 PEP 668 与系统混装 / Force project venv (avoids PEP 668)
echo "⚙️ 配置 Poetry 虚拟环境 / Configuring Poetry virtualenvs..."
poetry config virtualenvs.create true
poetry config virtualenvs.in-project true
if poetry config virtualenvs.options.system-site-packages true 2>/dev/null; then
    echo "✅ virtualenvs.options.system-site-packages = true（可与系统 picamera2 共存 / can see system picamera2）"
else
    echo "⚠️ 当前 Poetry 可能不支持 system-site-packages，将仅依赖 PYTHONPATH / Poetry may lack system-site-packages; using PYTHONPATH only"
fi

INSTALL_ARGS=(install --no-interaction)
if [ "${OGSCOPE_INSTALL_DEV:-}" = "1" ]; then
    echo "📦 poetry install（含 dev）..."
else
    INSTALL_ARGS+=(--only main)
    echo "📦 poetry install --only main（生产默认；设 OGSCOPE_INSTALL_DEV=1 可装 dev）..."
fi

# 低配板：限制并行 wheel 安装数，减轻峰值内存 / Limit parallel installs on low-RAM boards
export POETRY_INSTALLER_MAX_WORKERS="${POETRY_INSTALLER_MAX_WORKERS:-2}"

if [ "${OGSCOPE_MIRROR_RESOLVED}" = "cn" ]; then
    ogscope_export_pypi_mirror_cn
else
    ogscope_export_pypi_mirror_international
fi

poetry "${INSTALL_ARGS[@]}"

# numpy/scipy 与 lock 一致；Poetry 偶发「无更新」但 wheel 未落盘 / Align deps with lock; retry if missing
if ! ogscope_verify_numpy_scipy; then
    echo "⚠️ numpy/scipy 导入失败，使用 --no-cache 重试 poetry install / Import failed; retrying poetry with --no-cache"
    poetry "${INSTALL_ARGS[@]}" --no-cache
fi
if ! ogscope_verify_numpy_scipy; then
    echo "⚠️ 仍缺少 scipy，使用 pip 补装（与 pyproject 版本约束一致）/ scipy still missing; pip install (same constraints)"
    poetry run pip install --no-cache-dir "scipy>=1.10,<1.17"
fi
if ! ogscope_verify_numpy_scipy; then
    echo "❌ numpy/scipy 仍不可用。请删除 .venv 后重试: rm -rf .venv && ./scripts/install.sh"
    echo "❌ Still failing. Try: rm -rf .venv && ./scripts/install.sh"
    exit 1
fi
echo "✅ numpy/scipy 已就绪 / numpy & scipy OK"

VENV_PATH="$(poetry env info --path)"
VENV_PYTHON="${VENV_PATH}/bin/python"
if [ ! -x "${VENV_PYTHON}" ]; then
    echo "❌ 未找到虚拟环境解释器 / venv python missing: ${VENV_PYTHON}"
    exit 1
fi

echo "📁 创建数据目录 / Creating data directories..."
mkdir -p logs data uploads data/plate_solve data/analysis

# systemd 注入 PYTHONPATH，便于 venv 内 import apt 安装的包 / PYTHONPATH for apt-installed packages in venv
PY_PATHS=()
[ -d "/usr/lib/python3/dist-packages" ] && PY_PATHS+=("/usr/lib/python3/dist-packages")
# 动态加入 /usr/local/lib/pythonX.Y/dist-packages（若存在）/ Add /usr/local dist-packages if present
for _py in 13 12 11 10; do
    _d="/usr/local/lib/python3.${_py}/dist-packages"
    [ -d "${_d}" ] && PY_PATHS+=("${_d}")
done

PYTHONPATH_VALUE="$(IFS=:; echo "${PY_PATHS[*]}")"
[ -z "${PYTHONPATH_VALUE}" ] && PYTHONPATH_VALUE="/usr/lib/python3/dist-packages"

# libcamera 等动态库路径（按架构探测）/ Dynamic linker paths for libcamera etc. (arch-detected)
LD_PARTS=()
for _ld in /usr/lib/aarch64-linux-gnu /usr/lib/arm-linux-gnueabihf; do
    [ -d "${_ld}" ] && LD_PARTS+=("${_ld}")
done
LD_LIBRARY_PATH_VALUE="$(IFS=:; echo "${LD_PARTS[*]}")"
if [ -z "${LD_LIBRARY_PATH_VALUE}" ]; then
    LD_LIBRARY_PATH_VALUE="/usr/lib/aarch64-linux-gnu"
    echo "⚠️ 未检测到标准库目录，使用默认 ${LD_LIBRARY_PATH_VALUE} / No lib dir found; using default aarch64 path"
fi

# ExecStart 使用 poetry env info --path（与 virtualenvs.in-project=true 时即项目 .venv），勿手写 ~/.virtualenvs/
# ExecStart uses poetry env path (project .venv when in-project=true); do not hardcode ~/.virtualenvs/
echo "⚙️ 写入 systemd: ${SERVICE_PATH}"
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

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"

echo ""
echo "======================================"
echo "  ✅ 安装完成 / Installation done"
echo "======================================"
echo "服务 / Service: ${SERVICE_NAME}"
echo "虚拟环境 / venv: ${VENV_PATH}"
echo "PYTHONPATH: ${PYTHONPATH_VALUE}"
echo "LD_LIBRARY_PATH: ${LD_LIBRARY_PATH_VALUE}"
echo ""
echo "请将 default_database.npz 放到 data/plate_solve/（星图解算）"
echo "Place default_database.npz under data/plate_solve/ for plate solving"
echo ""
echo "下一步 / Next:"
echo "  sudo systemctl start ${SERVICE_NAME}"
echo "  sudo systemctl status ${SERVICE_NAME}"
echo "  sudo journalctl -u ${SERVICE_NAME} -f"
echo "  日常更新可运行: ./scripts/board-update.sh"
echo ""

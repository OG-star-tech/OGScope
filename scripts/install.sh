#!/bin/bash
# OGScope 安装脚本 / OGScope installation script
# 适用于 Raspberry Pi Zero 2W 等嵌入式板 / For Raspberry Pi Zero 2W, etc.
#
# 环境变量 / Environment:
#   OGSCOPE_INSTALL_DEV=1  — 安装含 dev 依赖（开发机）；默认仅 main / Install dev deps; default main only
#   OGSCOPE_APT_SLOW=0|1|未设置 — 未设置且内存≤1GB 时自动开；1 强制开；0 强制关 / Auto on if RAM≤1GB; 1=force; 0=disable
#   OGSCOPE_SKIP_OPENCV_APT=1 — 不 apt 安装 libopencv-dev（减轻 OOM；OpenCV 由 pip opencv-python-headless 提供）/ Skip libopencv-dev to avoid OOM
#   OGSCOPE_MIRROR=auto|cn|international — apt/PyPI 镜像；未显式指定时交互选择 / apt & PyPI mirrors; interactive prompt if unset
#   OGSCOPE_NONINTERACTIVE=1 — 跳过网络环境询问（CI/无人值守）/ Skip mirror region prompt
#   OGSCOPE_SKIP_NETWORK_BOOT=1 — 不安装开机 WiFi 引导单元 / Skip ogscope-network-boot.service
#   OGSCOPE_SKIP_PLATE_DB=1 — 不自动复制 default_database.npz 到 data/plate_solve/ / Skip Tetra3 pattern DB copy
#   OGSCOPE_FORCE_PLATE_DB=1 — 若目标已存在仍覆盖 / Overwrite data/plate_solve/default_database.npz if present
#   OGSCOPE_DEVELOPMENT_MODE=1 — 启用开发模式（默认 OGSCOPE_LOG_LEVEL=DEBUG；也可显式设置 OGSCOPE_LOG_LEVEL）/ Dev mode (default DEBUG log level)
#   OGSCOPE_POETRY_INSTALLER_URL — 可选，覆盖 Poetry 引导脚本 URL（国内可自建镜像）/ Optional Poetry bootstrap URL mirror
#   OGSCOPE_CAMERA=imx327|skip — 非交互指定摄像头 boot 配置（树莓派 config.txt）/ Boot camera preset (non-interactive)
#   OGSCOPE_SKIP_BOOT_CAMERA=1 — 不询问、不写入 /boot 摄像头配置 / Skip boot camera prompt and changes
#   OGSCOPE_SKIP_BOOT_I2C=1 — 不写入 /boot 中 dtparam=i2c_arm=on（仍会 apt 装 i2c-tools、仍将用户加入 i2c 组）/ Skip appending I2C dtparam; still installs i2c-tools and adds user to i2c group
#   OGSCOPE_SKIP_JOURNALD_PERSISTENT=1 — 不安装 journald 持久化 drop-in（默认安装）/ Skip persistent journald config
#   OGSCOPE_SYSTEMD_MEMORY_MAX=380M — 可选，写入 ogscope.service.d MemoryMax（cgroup 内存上限；过小会提前 SIGKILL）/ Optional cgroup MemoryMax
#   低内存解算保护另见环境变量 OGSCOPE_SOLVER_MAX_STARS_HARD_CAP、OGSCOPE_SOLVER_MAX_IMAGE_SIDE_HARD_CAP（见 config.py）/ Low-RAM solve caps
#   OGSCOPE_SKIP_LOW_RAM_DEFAULTS=1 — 内存≤512MiB 时不自动安装 ogscope-low-ram.conf（默认会自动装）/ Skip auto low-RAM solver drop-in
#   OGSCOPE_SKIP_HARDWARE_PLANE_DROPIN=1 — 不安装 ogscope.service.d/ogscope-hardware-plane.conf / Skip hardware-plane environment drop-in

set -euo pipefail

echo "======================================"
echo "  OGScope 安装脚本 / OGScope installation script"
echo "======================================"

if [ "${EUID}" -eq 0 ]; then
    echo "❌ 请不要使用 root 用户运行此脚本 / Do not run as root"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEPLOY_DIR="${OGSCOPE_DEPLOY_DIR:-/opt/ogscope}"
PROJECT_DIR="${DEPLOY_DIR}"
SERVICE_NAME="ogscope"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

echo "📁 源码目录 / Source: ${SOURCE_DIR}"
echo "📁 部署目录 / Deploy: ${PROJECT_DIR}"

if [ ! -f "${PROJECT_DIR}/pyproject.toml" ]; then
    echo "❌ 未找到部署目录中的 pyproject.toml: ${PROJECT_DIR}"
    echo "   请先运行 ./scripts/bootstrap.sh 将源码同步到固定部署目录"
    exit 1
fi

cd "${PROJECT_DIR}"

# 加载镜像逻辑（apt / PyPI）/ Load mirror helpers for apt and PyPI
# shellcheck source=mirror.sh
source "${SCRIPT_DIR}/mirror.sh"
# shellcheck source=boot-config-camera.sh
source "${SCRIPT_DIR}/boot-config-camera.sh"
# shellcheck source=boot-config-i2c.sh
source "${SCRIPT_DIR}/boot-config-i2c.sh"

# 交互式选择 apt/PyPI 镜像（未显式指定 cn|international 时）/ Interactive mirror selection when not preset
ogscope_prompt_mirror_if_needed

# 识别发行版并要求 Debian 系 + apt，避免误操作 / Detect OS; require Debian family + apt for safety
if ! ogscope_load_os_release; then
    exit 1
fi
ogscope_print_os_summary
if ! ogscope_require_debian_family_apt; then
    exit 1
fi

ogscope_prompt_camera_model_and_apply

OGSCOPE_MIRROR_RESOLVED="$(ogscope_resolve_mirror)"
echo "🌐 镜像模式 / Mirror: ${OGSCOPE_MIRROR_RESOLVED}（OGSCOPE_MIRROR=${OGSCOPE_MIRROR:-auto}）"

if [ "${OGSCOPE_MIRROR_RESOLVED}" = "cn" ]; then
    ogscope_apply_apt_mirror_cn
fi

# 低配板在 apt 批次间暂停，减轻 OOM（apt/dpkg 解压时）/ Pause between apt batches to reduce OOM risk
_mem_kb="$(grep '^MemTotal:' /proc/meminfo 2>/dev/null | awk '{print $2}' || echo 9999999)"
if [ "${OGSCOPE_APT_SLOW:-}" = "1" ]; then
    _apt_effective_slow="1"
elif [ "${OGSCOPE_APT_SLOW:-}" = "0" ]; then
    _apt_effective_slow="0"
else
    if [ "${_mem_kb}" -lt 1048576 ]; then
        _apt_effective_slow="1"
        echo "ℹ️  MemTotal≈$((_mem_kb / 1024)) MiB — 已自动启用 apt 分批间隔（关闭：OGSCOPE_APT_SLOW=0）/ Auto staggered apt (disable: OGSCOPE_APT_SLOW=0)"
    else
        _apt_effective_slow="0"
    fi
fi

_apt_pause() {
    if [ "${_apt_effective_slow}" = "1" ]; then
        echo "⏳ 等待 4s 释放内存... / Waiting to free memory..."
        sleep 4
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
    build-essential \
    network-manager \
    avahi-daemon \
    i2c-tools
_apt_pause

# I²C：用户组 + 固件 dtparam（i2c-tools 已随上表安装）/ I2C group + boot dtparam (i2c-tools installed above)
ogscope_i2c_host_setup_full 0

echo "📦 安装图像基础库（jpeg/png/freetype）/ Installing image base dev libraries..."
sudo apt install -y \
    libjpeg-dev \
    libpng-dev \
    libfreetype6-dev
_apt_pause

if [ "${OGSCOPE_SKIP_OPENCV_APT:-}" = "1" ]; then
    echo "ℹ️  已跳过 apt 安装 libopencv-dev（OGSCOPE_SKIP_OPENCV_APT=1）；OpenCV 由 pip opencv-python-headless 提供 / Skipped libopencv-dev; pip provides OpenCV"
else
    echo "📦 安装 libopencv-dev（依赖多；若进程被 Killed 多为 OOM，可重试并加 OGSCOPE_SKIP_OPENCV_APT=1 或 swap）"
    echo "📦 Installing libopencv-dev (--no-install-recommends); if Killed (OOM), retry with OGSCOPE_SKIP_OPENCV_APT=1 or add swap"
    sudo apt install -y --no-install-recommends libopencv-dev
fi
_apt_pause

# 树莓派常见；若无此包可忽略 / Common on Raspberry Pi OS; skip if unavailable
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

ogscope_sync_plate_solve_database_if_needed "${PROJECT_DIR}"

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

# 开发模式：更详细日志（与 ogscope.config.Settings.development_mode 对齐）/ Dev mode: richer logs
OGSCOPE_DEVELOPMENT_MODE_VALUE="${OGSCOPE_DEVELOPMENT_MODE:-0}"
if [ "${OGSCOPE_DEVELOPMENT_MODE_VALUE}" = "1" ]; then
    echo "🧪 启用开发模式（OGSCOPE_DEVELOPMENT_MODE=1）/ Development mode enabled"
    if [ -z "${OGSCOPE_LOG_LEVEL:-}" ]; then
        OGSCOPE_LOG_LEVEL_VALUE="DEBUG"
    else
        OGSCOPE_LOG_LEVEL_VALUE="${OGSCOPE_LOG_LEVEL}"
    fi
else
    OGSCOPE_LOG_LEVEL_VALUE="${OGSCOPE_LOG_LEVEL:-INFO}"
fi

OGSCOPE_ENV_DIR="/etc/ogscope"
OGSCOPE_ENV_FILE="${OGSCOPE_ENV_DIR}/ogscope.env"
echo "📝 写入主配置文件 / Writing primary config: ${OGSCOPE_ENV_FILE}"
sudo install -d -m 755 "${OGSCOPE_ENV_DIR}"
if [ ! -f "${OGSCOPE_ENV_FILE}" ]; then
    sudo tee "${OGSCOPE_ENV_FILE}" >/dev/null <<EOF
# OGScope 主配置（部署态）/ OGScope primary deployment configuration
OGSCOPE_HOST=0.0.0.0
OGSCOPE_PORT=8000
OGSCOPE_RELOAD=false
OGSCOPE_DEVELOPMENT_MODE=${OGSCOPE_DEVELOPMENT_MODE_VALUE}
OGSCOPE_LOG_LEVEL=${OGSCOPE_LOG_LEVEL_VALUE}
EOF
    sudo chown "root:${USER}" "${OGSCOPE_ENV_FILE}" 2>/dev/null || true
    sudo chmod 640 "${OGSCOPE_ENV_FILE}"
else
    echo "ℹ️  已存在 ${OGSCOPE_ENV_FILE}，保留现有配置 / Existing file preserved"
    sudo chown "root:${USER}" "${OGSCOPE_ENV_FILE}" 2>/dev/null || true
    sudo chmod 640 "${OGSCOPE_ENV_FILE}" 2>/dev/null || true
fi

ogscope_install_config_write_artifacts "${PROJECT_DIR}" "${USER}"

# ExecStart 使用 poetry env info --path（与 virtualenvs.in-project=true 时即项目 .venv），勿手写 ~/.virtualenvs/
# ExecStart uses poetry env path (project .venv when in-project=true); do not hardcode ~/.virtualenvs/
echo "⚙️ 写入 systemd: ${SERVICE_PATH}"
sudo tee "${SERVICE_PATH}" >/dev/null <<EOF
[Unit]
Description=OGScope Service
After=network.target NetworkManager.service

[Service]
Type=simple
User=${USER}
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONPATH=${PYTHONPATH_VALUE}
Environment=LD_LIBRARY_PATH=${LD_LIBRARY_PATH_VALUE}
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

if [ -n "${OGSCOPE_SYSTEMD_MEMORY_MAX:-}" ]; then
    echo "📝 写入 ogscope cgroup MemoryMax=${OGSCOPE_SYSTEMD_MEMORY_MAX} / Writing MemoryMax drop-in..."
    sudo install -d /etc/systemd/system/ogscope.service.d
    sudo tee /etc/systemd/system/ogscope.service.d/memory-limit.conf >/dev/null <<EOF
[Service]
MemoryMax=${OGSCOPE_SYSTEMD_MEMORY_MAX}
EOF
fi

LOW_RAM_DROPIN_SRC="${SCRIPT_DIR}/systemd/system/ogscope.service.d/ogscope-low-ram.conf"
_mem_total_kb_install="$(grep '^MemTotal:' /proc/meminfo 2>/dev/null | awk '{print $2}' || echo 9999999)"
if [ "${OGSCOPE_SKIP_LOW_RAM_DEFAULTS:-}" = "1" ]; then
    echo "⏭️  跳过低内存解算默认（OGSCOPE_SKIP_LOW_RAM_DEFAULTS=1）/ Skipping low-RAM solver drop-in"
elif [ ! -f "${LOW_RAM_DROPIN_SRC}" ]; then
    echo "⚠️  未找到 ${LOW_RAM_DROPIN_SRC}，跳过低内存解算默认 / Low-RAM drop-in missing; skipping"
elif [ "${_mem_total_kb_install}" -le 524288 ]; then
    echo "📝 安装低内存解算推荐值（MemTotal≤512MiB → 星数≤40、长边≤1280）/ Installing low-RAM solver caps..."
    sudo install -d /etc/systemd/system/ogscope.service.d
    sudo install -m 0644 "${LOW_RAM_DROPIN_SRC}" /etc/systemd/system/ogscope.service.d/ogscope-low-ram.conf
else
    echo "ℹ️  MemTotal≈$((_mem_total_kb_install / 1024)) MiB — 未安装 ogscope-low-ram.conf（仅≤512MiB 自动）/ Skipping low-RAM drop-in"
fi

HARDWARE_PLANE_DROPIN_SRC="${SCRIPT_DIR}/systemd/system/ogscope.service.d/ogscope-hardware-plane.conf"
if [ "${OGSCOPE_SKIP_HARDWARE_PLANE_DROPIN:-}" = "1" ]; then
    echo "⏭️  跳过硬件平面 drop-in（OGSCOPE_SKIP_HARDWARE_PLANE_DROPIN=1）/ Skipping hardware-plane drop-in"
elif [ ! -f "${HARDWARE_PLANE_DROPIN_SRC}" ]; then
    echo "⚠️  未找到 ${HARDWARE_PLANE_DROPIN_SRC}，跳过硬件平面 drop-in / Hardware-plane drop-in missing; skipping"
else
    echo "📝 安装硬件平面环境 drop-in / Installing hardware-plane environment drop-in..."
    sudo install -d /etc/systemd/system/ogscope.service.d
    sudo install -m 0644 "${HARDWARE_PLANE_DROPIN_SRC}" /etc/systemd/system/ogscope.service.d/ogscope-hardware-plane.conf
fi

if [ "${OGSCOPE_SKIP_NETWORK_INIT:-}" = "1" ]; then
    echo "⏭️  跳过网络初始化（OGSCOPE_SKIP_NETWORK_INIT=1）/ Skipping network init"
else
    chmod +x "${SCRIPT_DIR}/ogscope-network-init.sh" 2>/dev/null || true
    echo "🌐 运行网络初始化（需 sudo）/ Running network bootstrap..."
    sudo env OGSCOPE_SERVICE_USER="${USER}" "${SCRIPT_DIR}/ogscope-network-init.sh" init --yes \
        || echo "⚠️ 网络初始化失败，可稍后 sudo ${SCRIPT_DIR}/ogscope-network-init.sh diag / network init failed"
fi

BOOT_UNIT="ogscope-network-boot"
BOOT_UNIT_PATH="/etc/systemd/system/${BOOT_UNIT}.service"
if [ "${OGSCOPE_SKIP_NETWORK_BOOT:-}" = "1" ]; then
    echo "⏭️  跳过开机网络引导单元（OGSCOPE_SKIP_NETWORK_BOOT=1）/ Skipping ${BOOT_UNIT}.service"
else
    chmod +x "${SCRIPT_DIR}/ogscope-network-boot.sh" 2>/dev/null || true
    echo "⚙️ 写入开机 WiFi 引导（root oneshot）/ Writing ${BOOT_UNIT}.service..."
    sudo tee "${BOOT_UNIT_PATH}" >/dev/null <<EOF
[Unit]
Description=OGScope boot WiFi (STA wait, fallback AP)
After=NetworkManager.service
Before=${SERVICE_NAME}.service
ConditionPathExists=/etc/ogscope/network.env

[Service]
Type=oneshot
RemainAfterExit=yes
EnvironmentFile=-/etc/ogscope/network.env
ExecStart=${PROJECT_DIR}/scripts/ogscope-network-boot.sh

[Install]
WantedBy=multi-user.target
EOF
fi

JOURNALD_DROPIN_SRC="${SCRIPT_DIR}/systemd/journald.conf.d/ogscope-persistent.conf"
JOURNALD_DROPIN_DST="/etc/systemd/journald.conf.d/ogscope-persistent.conf"
if [ "${OGSCOPE_SKIP_JOURNALD_PERSISTENT:-}" = "1" ]; then
    echo "⏭️  跳过 journald 持久化（OGSCOPE_SKIP_JOURNALD_PERSISTENT=1）/ Skipping journald persistent config"
elif [ ! -f "${JOURNALD_DROPIN_SRC}" ]; then
    echo "⚠️  未找到 ${JOURNALD_DROPIN_SRC}，跳过 journald 配置 / journald drop-in missing; skipping"
else
    echo "📝 配置持久化 systemd journal（卡死后可用 journalctl -b -1）/ Enabling persistent journal..."
    sudo install -d /etc/systemd/journald.conf.d
    sudo install -m 0644 "${JOURNALD_DROPIN_SRC}" "${JOURNALD_DROPIN_DST}"
    sudo systemctl restart systemd-journald
fi

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
if [ "${OGSCOPE_SKIP_NETWORK_BOOT:-}" != "1" ]; then
    sudo systemctl enable "${BOOT_UNIT}.service" 2>/dev/null || true
fi

echo ""
echo "======================================"
echo "  ✅ 安装完成 / Installation done"
echo "======================================"
echo "服务 / Service: ${SERVICE_NAME}"
echo "虚拟环境 / venv: ${VENV_PATH}"
echo "PYTHONPATH: ${PYTHONPATH_VALUE}"
echo "LD_LIBRARY_PATH: ${LD_LIBRARY_PATH_VALUE}"
echo ""
if [ "${OGSCOPE_I2C_GROUP_ADDED:-0}" = "1" ]; then
    echo "ℹ️  I²C：已加入 i2c 组，请重新登录 SSH 后 \`groups\` 可见；当前会话内可能仍无 / Re-login SSH for i2c group in shell"
fi
if [ "${OGSCOPE_I2C_BOOT_CHANGED:-0}" = "1" ]; then
    echo "⚠️  已写入 dtparam=i2c_arm=on，请重启树莓派以使 /dev/i2c-1 等生效 / Reboot the Pi for I2C device nodes"
fi
echo ""
ogscope_report_plate_solve_database_status "${PROJECT_DIR}"
echo ""
echo "下一步 / Next:"
echo "  sudo systemctl start ${SERVICE_NAME}"
echo "  sudo systemctl status ${SERVICE_NAME}"
echo "  sudo journalctl -u ${SERVICE_NAME} -f"
if [ "${OGSCOPE_SKIP_JOURNALD_PERSISTENT:-}" != "1" ] && [ -f "${JOURNALD_DROPIN_DST:-}" ]; then
    echo "  上次启动内核/系统日志 / Previous boot: sudo journalctl -b -1 -e"
    echo "  上次启动错误级 / Previous boot errors: sudo journalctl -b -1 -p err..alert --no-pager"
fi
if [ "${OGSCOPE_SKIP_NETWORK_BOOT:-}" != "1" ]; then
    echo "  开机 WiFi 引导日志 / Boot WiFi: sudo journalctl -u ${BOOT_UNIT} -b"
fi
echo "  日常更新可运行: ./scripts/board-update.sh"
echo ""

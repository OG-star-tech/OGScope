#!/bin/bash
# OGScope 开发板增量更新 / Board incremental update (after first install)
#
# 环境变量 / Environment:
#   OGSCOPE_GIT_PULL=1     — 在更新前执行 git pull（需 git 仓库）/ Run git pull before update (requires .git)
#   OGSCOPE_INSTALL_DEV=1  — poetry install 时包含 dev 依赖 / Include dev dependency group
#   POETRY_INSTALLER_MAX_WORKERS — 默认 2，低配板可设为 1 / Default 2; set to 1 on low-RAM boards
#   OGSCOPE_MIRROR=auto|cn|international — 与 install.sh 相同 / Same as install.sh
#   OGSCOPE_NONINTERACTIVE=1 — 跳过网络环境询问 / Skip mirror region prompt
#   OGSCOPE_SKIP_PLATE_DB=1 — 不复制 default_database.npz / Skip Tetra3 pattern DB copy
#   OGSCOPE_FORCE_PLATE_DB=1 — 覆盖已存在的 data/plate_solve/default_database.npz / Overwrite pattern DB
#   OGSCOPE_SKIP_NETWORK_SYNC=1 — 不同步 WiFi 切换脚本与 ensure-systemd（免密 sudo 不可用时可设）/ Skip WiFi script + ensure-systemd
#   OGSCOPE_CAMERA=imx327|skip — 非交互指定摄像头 boot 配置 / Boot camera preset (non-interactive)
#   OGSCOPE_SKIP_BOOT_CAMERA=1 — 不询问、不写入 /boot 摄像头配置 / Skip boot camera prompt and changes
#   OGSCOPE_SKIP_BOOT_I2C=1 — 不写入 /boot 中 dtparam=i2c_arm=on（仍会安装 i2c-tools、仍将用户加入 i2c 组）/ Skip I2C boot dtparam; still installs i2c-tools and adds user to i2c group
#   OGSCOPE_SKIP_JOURNALD_PERSISTENT=1 — 不同步 journald 持久化配置 / Skip journald persistent drop-in
#   OGSCOPE_SYSTEMD_MEMORY_MAX=380M — 可选，同步 ogscope.service.d MemoryMax / Optional MemoryMax drop-in
#   OGSCOPE_SKIP_LOW_RAM_DEFAULTS=1 — 内存≤512MiB 时不同步 ogscope-low-ram.conf / Skip low-RAM solver drop-in sync
#   OGSCOPE_SKIP_HARDWARE_PLANE_DROPIN=1 — 不同步 ogscope.service.d/ogscope-hardware-plane.conf / Skip hardware-plane drop-in sync
#   OGSCOPE_DEVELOPMENT_MODE=1 — 同步开发模式 drop-in（更详细日志；可选 OGSCOPE_LOG_LEVEL 覆盖）/ Dev-mode drop-in for richer logs

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEPLOY_DIR="${OGSCOPE_DEPLOY_DIR:-/opt/ogscope}"
PROJECT_DIR="${DEPLOY_DIR}"
SERVICE_NAME="ogscope"

echo "📁 源码目录 / Source: ${SOURCE_DIR}"
echo "📁 部署目录 / Deploy: ${PROJECT_DIR}"

if [ ! -f "${PROJECT_DIR}/pyproject.toml" ]; then
    echo "❌ 未找到部署目录中的 pyproject.toml: ${PROJECT_DIR}"
    echo "   请先运行 ./scripts/bootstrap.sh"
    exit 1
fi

cd "${PROJECT_DIR}"

# 加载镜像逻辑 / Load mirror helpers
# shellcheck source=mirror.sh
source "${SCRIPT_DIR}/mirror.sh"
# shellcheck source=boot-config-camera.sh
source "${SCRIPT_DIR}/boot-config-camera.sh"
# shellcheck source=boot-config-i2c.sh
source "${SCRIPT_DIR}/boot-config-i2c.sh"
ogscope_prompt_mirror_if_needed
OGSCOPE_MIRROR_RESOLVED="$(ogscope_resolve_mirror)"
echo "🌐 镜像模式 / Mirror: ${OGSCOPE_MIRROR_RESOLVED}（OGSCOPE_MIRROR=${OGSCOPE_MIRROR:-auto}）"

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
    echo "❌ numpy/scipy 仍不可用。请删除 .venv 后重试: rm -rf .venv && OGSCOPE_MIRROR=cn ./scripts/board-update.sh"
    echo "❌ Still failing. Try: rm -rf .venv && ./scripts/board-update.sh"
    exit 1
fi
echo "✅ numpy/scipy 已就绪 / numpy & scipy OK"

echo "📦 I²C 主机依赖（与 install.sh 对齐）/ I2C host setup (aligned with install.sh)..."
sudo apt update -qq
ogscope_i2c_host_setup_full 1

VENV_PYTHON="$(poetry env info --path)/bin/python"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
ogscope_sync_systemd_execstart_if_needed "${SERVICE_PATH}" "${VENV_PYTHON}"
ogscope_ensure_systemd_primary_envfile "${SERVICE_PATH}"

OGSCOPE_ENV_DIR="/etc/ogscope"
OGSCOPE_ENV_FILE="${OGSCOPE_ENV_DIR}/ogscope.env"
if [ ! -f "${OGSCOPE_ENV_FILE}" ]; then
    echo "📝 初始化主配置 / Initializing primary config: ${OGSCOPE_ENV_FILE}"
    sudo install -d -m 755 "${OGSCOPE_ENV_DIR}"
    if [ "${OGSCOPE_DEVELOPMENT_MODE:-0}" = "1" ] && [ -z "${OGSCOPE_LOG_LEVEL:-}" ]; then
        _update_log_level="DEBUG"
    else
        _update_log_level="${OGSCOPE_LOG_LEVEL:-INFO}"
    fi
    sudo tee "${OGSCOPE_ENV_FILE}" >/dev/null <<EOF
# OGScope 主配置（部署态）/ OGScope primary deployment configuration
OGSCOPE_HOST=0.0.0.0
OGSCOPE_PORT=8000
OGSCOPE_RELOAD=false
OGSCOPE_DEVELOPMENT_MODE=${OGSCOPE_DEVELOPMENT_MODE:-0}
OGSCOPE_LOG_LEVEL=${_update_log_level}
EOF
    sudo chmod 640 "${OGSCOPE_ENV_FILE}"
fi

chmod +x "${PROJECT_DIR}/scripts/ogscope-network-boot.sh" 2>/dev/null || true
ogscope_sync_network_boot_unit_if_needed "${PROJECT_DIR}"

ogscope_sync_network_board_artifacts_if_needed "${PROJECT_DIR}"

ogscope_sync_plate_solve_database_if_needed "${PROJECT_DIR}"
ogscope_report_plate_solve_database_status "${PROJECT_DIR}"

ogscope_prompt_camera_model_and_apply

JOURNALD_DROPIN_SRC="${SCRIPT_DIR}/systemd/journald.conf.d/ogscope-persistent.conf"
JOURNALD_DROPIN_DST="/etc/systemd/journald.conf.d/ogscope-persistent.conf"
if [ "${OGSCOPE_SKIP_JOURNALD_PERSISTENT:-}" = "1" ]; then
    echo "⏭️  跳过 journald 持久化（OGSCOPE_SKIP_JOURNALD_PERSISTENT=1）/ Skipping journald persistent config"
elif [ ! -f "${JOURNALD_DROPIN_SRC}" ]; then
    echo "⚠️  未找到 ${JOURNALD_DROPIN_SRC}，跳过 journald 配置 / journald drop-in missing; skipping"
else
    echo "📝 同步持久化 systemd journal 配置 / Syncing persistent journald drop-in..."
    sudo install -d /etc/systemd/journald.conf.d
    sudo install -m 0644 "${JOURNALD_DROPIN_SRC}" "${JOURNALD_DROPIN_DST}"
    sudo systemctl restart systemd-journald
fi

if [ -n "${OGSCOPE_SYSTEMD_MEMORY_MAX:-}" ]; then
    echo "📝 同步 ogscope MemoryMax=${OGSCOPE_SYSTEMD_MEMORY_MAX} / Syncing MemoryMax drop-in..."
    sudo install -d /etc/systemd/system/ogscope.service.d
    sudo tee /etc/systemd/system/ogscope.service.d/memory-limit.conf >/dev/null <<EOF
[Service]
MemoryMax=${OGSCOPE_SYSTEMD_MEMORY_MAX}
EOF
fi

LOW_RAM_DROPIN_SRC="${SCRIPT_DIR}/systemd/system/ogscope.service.d/ogscope-low-ram.conf"
_mem_total_kb_board="$(grep '^MemTotal:' /proc/meminfo 2>/dev/null | awk '{print $2}' || echo 9999999)"
if [ "${OGSCOPE_SKIP_LOW_RAM_DEFAULTS:-}" = "1" ]; then
    echo "⏭️  跳过低内存解算默认（OGSCOPE_SKIP_LOW_RAM_DEFAULTS=1）/ Skipping low-RAM solver drop-in sync"
elif [ ! -f "${LOW_RAM_DROPIN_SRC}" ]; then
    echo "⚠️  未找到 ${LOW_RAM_DROPIN_SRC}，跳过 / Low-RAM drop-in missing; skipping"
elif [ "${_mem_total_kb_board}" -le 524288 ]; then
    echo "📝 同步低内存解算推荐值（星数≤40、长边≤1280）/ Syncing low-RAM solver caps..."
    sudo install -d /etc/systemd/system/ogscope.service.d
    sudo install -m 0644 "${LOW_RAM_DROPIN_SRC}" /etc/systemd/system/ogscope.service.d/ogscope-low-ram.conf
else
    echo "ℹ️  MemTotal≈$((_mem_total_kb_board / 1024)) MiB — 未同步 ogscope-low-ram.conf / Skipping low-RAM drop-in on this host"
fi

HARDWARE_PLANE_DROPIN_SRC="${SCRIPT_DIR}/systemd/system/ogscope.service.d/ogscope-hardware-plane.conf"
if [ "${OGSCOPE_SKIP_HARDWARE_PLANE_DROPIN:-}" = "1" ]; then
    echo "⏭️  跳过硬件平面 drop-in（OGSCOPE_SKIP_HARDWARE_PLANE_DROPIN=1）/ Skipping hardware-plane drop-in sync"
elif [ ! -f "${HARDWARE_PLANE_DROPIN_SRC}" ]; then
    echo "⚠️  未找到 ${HARDWARE_PLANE_DROPIN_SRC}，跳过 / Hardware-plane drop-in missing; skipping"
else
    echo "📝 同步硬件平面环境 drop-in / Syncing hardware-plane environment drop-in..."
    sudo install -d /etc/systemd/system/ogscope.service.d
    sudo install -m 0644 "${HARDWARE_PLANE_DROPIN_SRC}" /etc/systemd/system/ogscope.service.d/ogscope-hardware-plane.conf
fi

DEV_DROPIN_DST="/etc/systemd/system/ogscope.service.d/ogscope-development.conf"
if [ "${OGSCOPE_DEVELOPMENT_MODE:-0}" = "1" ]; then
    echo "🧪 同步开发模式 drop-in（OGSCOPE_DEVELOPMENT_MODE=1）/ Syncing development-mode drop-in..."
    sudo install -d /etc/systemd/system/ogscope.service.d
    if [ -z "${OGSCOPE_LOG_LEVEL:-}" ]; then
        _dev_log_level="DEBUG"
    else
        _dev_log_level="${OGSCOPE_LOG_LEVEL}"
    fi
    sudo tee "${DEV_DROPIN_DST}" >/dev/null <<EOF
[Service]
Environment=OGSCOPE_DEVELOPMENT_MODE=1
Environment=OGSCOPE_LOG_LEVEL=${_dev_log_level}
EOF
else
    if [ -f "${DEV_DROPIN_DST}" ]; then
        echo "🧹 移除开发模式 drop-in（OGSCOPE_DEVELOPMENT_MODE!=1）/ Removing development-mode drop-in..."
        sudo rm -f "${DEV_DROPIN_DST}"
    fi
fi

echo "🔄 重启服务 / Restarting service..."
sudo systemctl daemon-reload
sudo systemctl restart "${SERVICE_NAME}"

sleep 2
sudo systemctl --no-pager status "${SERVICE_NAME}" || true

echo ""
if [ "${OGSCOPE_I2C_GROUP_ADDED:-0}" = "1" ]; then
    echo "ℹ️  I²C：已加入 i2c 组，请重新登录 SSH 后 \`groups\` 可见 / Re-login SSH for i2c group"
fi
if [ "${OGSCOPE_I2C_BOOT_CHANGED:-0}" = "1" ]; then
    echo "⚠️  已写入 dtparam=i2c_arm=on，请重启树莓派以使 I²C 生效 / Reboot Pi for I2C device nodes"
fi
echo "✅ 更新完成 / Update done. 日志 / Logs: sudo journalctl -u ${SERVICE_NAME} -f"
if [ "${OGSCOPE_SKIP_JOURNALD_PERSISTENT:-}" != "1" ] && [ -f "${JOURNALD_DROPIN_DST:-}" ]; then
    echo "上次启动排查 / Previous boot: sudo journalctl -b -1 -e  |  errors: sudo journalctl -b -1 -p err..alert --no-pager"
fi
echo "健康检查 / Health: curl -s http://127.0.0.1:8000/health"

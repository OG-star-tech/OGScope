#!/bin/bash
# OGScope 卸载脚本 / OGScope uninstall script
# 从本机移除 systemd 主服务、开机网络单元（若存在）与 drop-in，以及（可选）项目虚拟环境；不卸载 apt 包与全局 Poetry / Removes main service, ogscope-network-boot unit (if any), drop-in, and optional venv; does not remove apt packages or global Poetry
#
# 环境变量 / Environment:
#   OGSCOPE_UNINSTALL_CONFIRM=1 — 必须设置，否则脚本退出（防误删）/ Must be set to proceed (safety)
#   OGSCOPE_UNINSTALL_KEEP_VENV=1 — 保留项目 .venv / Keep project virtualenv
#   OGSCOPE_UNINSTALL_REMOVE_DATA=1 — 同时删除 logs/、uploads/、data/ 下内容（危险）/ Also remove logs, uploads, data (destructive)
#   OGSCOPE_UNINSTALL_REMOVE_LEGACY_POETRY_VENV=1 — 删除旧版 Poetry 全局名 venv：~/.virtualenvs/OGScope（若存在）/ Remove legacy Poetry venv at ~/.virtualenvs/OGScope if present

set -euo pipefail

if [ "${EUID}" -eq 0 ]; then
    echo "❌ 请不要使用 root 用户运行此脚本 / Do not run as root"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SERVICE_NAME="ogscope"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
BOOT_SERVICE_NAME="ogscope-network-boot"
BOOT_SERVICE_PATH="/etc/systemd/system/${BOOT_SERVICE_NAME}.service"
NETWORK_DROPIN="/etc/systemd/system/ogscope.service.d/ogscope-network-env.conf"

echo "======================================"
echo "  OGScope 卸载 / OGScope uninstall"
echo "======================================"
echo "📁 项目目录 / Project: ${PROJECT_DIR}"

if [ ! -f "${PROJECT_DIR}/pyproject.toml" ]; then
    echo "❌ 未找到 pyproject.toml / pyproject.toml not found"
    exit 1
fi

# 确认 / Confirmation
if [ "${OGSCOPE_UNINSTALL_CONFIRM:-}" != "1" ]; then
    if [ -t 0 ] && [ -t 1 ]; then
        echo ""
        echo "⚠️ 将停止并移除 systemd 服务 ${SERVICE_NAME}、ogscope-network-boot（若存在）与相关 drop-in，并可选删除 .venv。"
        echo "⚠️ Will stop and remove ${SERVICE_NAME}, ogscope-network-boot (if present), related drop-ins, and optionally remove .venv."
        echo "   数据目录默认保留；设 OGSCOPE_UNINSTALL_REMOVE_DATA=1 可删除 logs/uploads/data。"
        echo "   Data dirs are kept by default; set OGSCOPE_UNINSTALL_REMOVE_DATA=1 to remove them."
        echo ""
        read -r -p "输入 YES 继续 / Type YES to continue: " _ans
        if [ "${_ans}" != "YES" ]; then
            echo "已取消 / Aborted."
            exit 0
        fi
    else
        echo "❌ 非交互环境请设置: OGSCOPE_UNINSTALL_CONFIRM=1 / For non-interactive runs, set OGSCOPE_UNINSTALL_CONFIRM=1"
        exit 1
    fi
fi

cd "${PROJECT_DIR}"

# 停止并禁用主服务 / Stop and disable main service
echo "🛑 停止服务 / Stopping service..."
sudo systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
sudo systemctl disable "${SERVICE_NAME}" 2>/dev/null || true

if [ -f "${SERVICE_PATH}" ]; then
    echo "🗑️  移除 unit 文件 / Removing unit file: ${SERVICE_PATH}"
    sudo rm -f "${SERVICE_PATH}"
else
    echo "ℹ️  未找到 ${SERVICE_PATH}，跳过删除主 unit / Main unit file not found, skipping"
fi

# 开机网络单元与 drop-in（与 install.sh 对应）/ Boot unit and drop-in (matches install.sh)
if [ -f "${BOOT_SERVICE_PATH}" ]; then
    echo "🛑 禁用并移除 ${BOOT_SERVICE_NAME}.service ..."
    sudo systemctl stop "${BOOT_SERVICE_NAME}.service" 2>/dev/null || true
    sudo systemctl disable "${BOOT_SERVICE_NAME}.service" 2>/dev/null || true
    sudo rm -f "${BOOT_SERVICE_PATH}"
fi
if [ -f "${NETWORK_DROPIN}" ]; then
    echo "🗑️  移除 systemd drop-in ${NETWORK_DROPIN} ..."
    sudo rm -f "${NETWORK_DROPIN}"
    sudo rmdir /etc/systemd/system/ogscope.service.d 2>/dev/null || true
fi

sudo systemctl daemon-reload
echo "✅ systemd 已更新 / systemd reloaded"

# 虚拟环境 / Virtualenv
if [ "${OGSCOPE_UNINSTALL_KEEP_VENV:-}" = "1" ]; then
    echo "ℹ️  保留 .venv（OGSCOPE_UNINSTALL_KEEP_VENV=1）/ Keeping .venv"
elif [ -d "${PROJECT_DIR}/.venv" ]; then
    echo "🗑️  删除虚拟环境 / Removing .venv..."
    rm -rf "${PROJECT_DIR}/.venv"
    echo "✅ .venv 已删除 / .venv removed"
else
    echo "ℹ️  无 .venv 目录 / No .venv directory"
fi

# 旧版安装曾将 venv 放在 ~/.virtualenvs/OGScope，与当前「项目内 .venv」并存易混淆；可选删除 / Legacy global venv name; optional cleanup
if [ "${OGSCOPE_UNINSTALL_REMOVE_LEGACY_POETRY_VENV:-}" = "1" ]; then
    _legacy_venv="${HOME}/.virtualenvs/OGScope"
    if [ -d "${_legacy_venv}" ]; then
        echo "🗑️  删除遗留 Poetry 虚拟环境 / Removing legacy Poetry venv: ${_legacy_venv}"
        rm -rf "${_legacy_venv}"
        echo "✅ 已删除 / Removed"
    else
        echo "ℹ️  无 ${_legacy_venv} / No legacy venv at that path"
    fi
else
    echo "ℹ️  若存在旧路径 ~/.virtualenvs/OGScope，可设 OGSCOPE_UNINSTALL_REMOVE_LEGACY_POETRY_VENV=1 一并删除 / Optional: remove legacy ~/.virtualenvs/OGScope"
fi

# 用户数据（可选）/ Optional user data
if [ "${OGSCOPE_UNINSTALL_REMOVE_DATA:-}" = "1" ]; then
    echo "🗑️  删除 logs、uploads、data（OGSCOPE_UNINSTALL_REMOVE_DATA=1）..."
    echo "🗑️  Removing logs, uploads, data..."
    rm -rf "${PROJECT_DIR}/logs" "${PROJECT_DIR}/uploads" "${PROJECT_DIR}/data" 2>/dev/null || true
    echo "✅ 数据目录已清理 / Data dirs removed"
else
    echo "ℹ️  保留 logs/、uploads/、data/（不设 REMOVE_DATA 则保留）/ Keeping logs, uploads, data"
fi

echo ""
echo "======================================"
echo "  ✅ 卸载完成 / Uninstall done"
echo "======================================"
echo "未移除：系统 apt 包、python3-picamera2、全局 Poetry / Not removed: apt packages, picamera2, global Poetry"
echo "若需重装：./scripts/install.sh / To reinstall: ./scripts/install.sh"
echo ""

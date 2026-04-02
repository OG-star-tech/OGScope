#!/usr/bin/env bash
# 为已存在 network.env 的老部署补 systemd drop-in，使 ogscope 加载 OGSCOPE_* 变量
# Install systemd drop-in for existing deployments so ogscope loads network.env
#
# 用法 / Usage:
#   sudo ./scripts/ensure-ogscope-systemd-network-env.sh
#
# 等价于 / Equivalent: sudo ./scripts/ogscope-network-init.sh ensure-systemd

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${EUID}" -ne 0 ]]; then
    exec sudo "${SCRIPT_DIR}/ogscope-network-init.sh" ensure-systemd
fi
exec "${SCRIPT_DIR}/ogscope-network-init.sh" ensure-systemd

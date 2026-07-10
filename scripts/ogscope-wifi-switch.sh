#!/usr/bin/env bash
# OGScope WiFi 模式切换（NetworkManager / nmcli）
# OGScope WiFi mode switch (NetworkManager) — STA (client) vs AP (hotspot)
#
# 用法 / Usage:
#   ogscope-wifi-switch.sh status|ap|sta
#
# 环境变量（与 systemd 或 .env 中 OGSCOPE_* 对齐）/ Environment (match OGSCOPE_* in systemd/.env):
#   OGSCOPE_WIFI_STA_CONNECTION   — STA 连接名（连路由器）/ connection name for DHCP client mode
#   OGSCOPE_WIFI_AP_CONNECTION  — AP 热点连接名 / connection name for access point mode
#   OGSCOPE_WIFI_INTERFACE      — 无线接口，默认 wlan0 / wireless iface, default wlan0
#
# 部署 / Deployment:
#   sudo install -m 755 scripts/ogscope-wifi-switch.sh /usr/local/bin/ogscope-wifi-switch
# sudoers（将 %USER% 与路径替换为实际值）/ sudoers example:
#   %USER% ALL=(ALL) NOPASSWD: /usr/local/bin/ogscope-wifi-switch
#
# 首次需在板上用 nmcli 创建两个 Profile（STA 与 AP），名称与上述变量一致。
# Create both profiles once on the board with nmcli; names must match the variables above.

set -euo pipefail

# sudo 默认不传子进程环境（且 many sudoers 禁止 sudo -E），从 network.env 补全（与 systemd 同源）
# sudo often strips env; sudoers may reject -E — load network.env (same as systemd EnvironmentFile)
_DEFAULT_ENV="/data/ogscope/network.env"
if [[ -r "${_DEFAULT_ENV}" ]] && {
    [[ -z "${OGSCOPE_WIFI_STA_CONNECTION:-}" ]] || [[ -z "${OGSCOPE_WIFI_AP_CONNECTION:-}" ]];
}; then
    set -a
    # shellcheck disable=SC1090
    source "${_DEFAULT_ENV}"
    set +a
fi

SCRIPT_NAME="$(basename "$0")"
CMD="${1:-}"

STA="${OGSCOPE_WIFI_STA_CONNECTION:-}"
AP="${OGSCOPE_WIFI_AP_CONNECTION:-}"
IFACE="${OGSCOPE_WIFI_INTERFACE:-wlan0}"

if ! command -v nmcli >/dev/null 2>&1; then
    echo "ERROR=nmcli_not_found" >&2
    exit 127
fi

if [[ -z "$STA" || -z "$AP" ]]; then
    echo "ERROR=missing_env_OGSCOPE_WIFI_STA_CONNECTION_or_OGSCOPE_WIFI_AP_CONNECTION" >&2
    exit 2
fi

# 当前活动连接名（指定接口）/ Active connection name for the wireless interface
_active_connection() {
    nmcli -t -f GENERAL.CONNECTION device show "$IFACE" 2>/dev/null | sed -n 's/^GENERAL.CONNECTION://p' | head -n1 || true
}

# AP 配置的 IPv4 地址（用于 status 展示）/ IPv4 addresses from AP profile
_ap_ipv4() {
    nmcli -g ipv4.addresses connection show "$AP" 2>/dev/null | head -n1 || true
}

case "$CMD" in
status)
    ACTIVE="$(_active_connection)"
    MODE="unknown"
    if [[ "$ACTIVE" == "$AP" ]]; then
        MODE="ap"
    elif [[ "$ACTIVE" == "$STA" ]]; then
        MODE="sta"
    elif [[ -z "$ACTIVE" || "$ACTIVE" == "--" ]]; then
        MODE="unknown"
    fi
    echo "MODE=${MODE}"
    echo "ACTIVE_CONNECTION=${ACTIVE:-}"
    echo "WIRELESS_INTERFACE=${IFACE}"
    echo "STA_CONNECTION=${STA}"
    echo "AP_CONNECTION=${AP}"
    if [[ "$MODE" == "ap" ]]; then
        echo "AP_IPV4=$(_ap_ipv4)"
    else
        echo "AP_IPV4="
    fi
    ;;
ap)
    nmcli connection down "$STA" 2>/dev/null || true
    nmcli connection up "$AP" ifname "$IFACE"
    ;;
sta)
    nmcli connection down "$AP" 2>/dev/null || true
    nmcli connection up "$STA" ifname "$IFACE"
    ;;
*)
    echo "Usage: ${SCRIPT_NAME} status|ap|sta" >&2
    exit 1
    ;;
esac

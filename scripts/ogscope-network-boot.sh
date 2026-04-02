#!/usr/bin/env bash
# OGScope 开机无线引导：等待 STA 获 IPv4，失败则切 AP（root / systemd oneshot）
# Boot WiFi: wait for STA IPv4, else bring up AP (root, independent of ogscope.service)
#
# 环境变量 / Environment (optional; defaults match ogscope-network-init):
#   OGSCOPE_WIFI_STA_CONNECTION — STA 连接名 / STA profile name
#   OGSCOPE_WIFI_AP_CONNECTION  — AP 连接名 / AP profile name
#   OGSCOPE_WIFI_INTERFACE      — 无线接口 / Wireless iface (default wlan0)
#   OGSCOPE_BOOT_STA_WAIT_SEC   — 首轮等待 STA 获 IPv4 的总秒数 / First wait for IPv4 (default 55)
#   OGSCOPE_BOOT_POLL_SEC       — 轮询间隔 / Poll interval (default 3)
#   OGSCOPE_BOOT_STA_UP_RETRIES — 尝试 connection up STA 次数 / nmcli up STA retries (default 2)
#   OGSCOPE_BOOT_POST_UP_WAIT   — 每次 up STA 后再等待秒数 / Wait after each up (default 20)

set -euo pipefail

ENV_FILE="/etc/ogscope/network.env"
if [[ -r "${ENV_FILE}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
fi

STA="${OGSCOPE_WIFI_STA_CONNECTION:-OGScope-STA}"
AP="${OGSCOPE_WIFI_AP_CONNECTION:-OGScope-AP}"
IFACE="${OGSCOPE_WIFI_INTERFACE:-wlan0}"
WAIT_TOTAL="${OGSCOPE_BOOT_STA_WAIT_SEC:-55}"
POLL="${OGSCOPE_BOOT_POLL_SEC:-3}"
RETRIES="${OGSCOPE_BOOT_STA_UP_RETRIES:-2}"
POST_UP="${OGSCOPE_BOOT_POST_UP_WAIT:-20}"

log() { logger -t ogscope-network-boot -- "$@" || true; echo "[ogscope-network-boot] $*"; }

has_usable_ipv4() {
    local iface="$1"
    local line ip
    while IFS= read -r line; do
        [[ -z "${line}" || "${line}" == "--" ]] && continue
        ip="${line%%/*}"
        if [[ "${ip}" =~ ^169\.254\. ]]; then
            continue
        fi
        if [[ "${ip}" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            return 0
        fi
    done < <(nmcli -g IP4.ADDRESS device show "${iface}" 2>/dev/null || true)
    return 1
}

wait_iface_and_nmcli() {
    local n=0
    while [[ ! -r "/sys/class/net/${IFACE}/address" ]]; do
        n=$((n + 1))
        if [[ "${n}" -gt 40 ]]; then
            log "timeout waiting for ${IFACE}"
            return 1
        fi
        sleep 0.5
    done
    n=0
    while ! command -v nmcli >/dev/null 2>&1; do
        n=$((n + 1))
        if [[ "${n}" -gt 20 ]]; then
            log "nmcli not found"
            return 1
        fi
        sleep 0.5
    done
    return 0
}

skip_if_other_default_route() {
    # 已有默认路由且不在无线口上则跳过（有线已联网）/ Skip if default route is not on wifi
    if ip -4 route show default 2>/dev/null | grep -q "dev ${IFACE}"; then
        return 1
    fi
    if ip -4 route show default 2>/dev/null | grep -q .; then
        log "skip: default IPv4 route uses another interface (not ${IFACE})"
        return 0
    fi
    return 1
}

main() {
    if ! wait_iface_and_nmcli; then
        log "iface/nmcli unavailable; exit"
        exit 1
    fi

    if skip_if_other_default_route; then
        exit 0
    fi

    local elapsed=0
    while [[ "${elapsed}" -lt "${WAIT_TOTAL}" ]]; do
        if has_usable_ipv4 "${IFACE}"; then
            log "STA has usable IPv4 on ${IFACE}, done"
            exit 0
        fi
        sleep "${POLL}"
        elapsed=$((elapsed + POLL))
    done

    log "no IPv4 after ${WAIT_TOTAL}s, trying nmcli connection up ${STA}"
    local r=0
    while [[ "${r}" -lt "${RETRIES}" ]]; do
        r=$((r + 1))
        nmcli connection up "${STA}" ifname "${IFACE}" 2>/dev/null || log "nmcli up ${STA} attempt ${r} failed"
        sleep "${POST_UP}"
        if has_usable_ipv4 "${IFACE}"; then
            log "STA connected after up retry ${r}"
            exit 0
        fi
    done

    log "fallback: switching to AP ${AP}"
    nmcli connection down "${AP}" 2>/dev/null || true
    nmcli connection down "${STA}" 2>/dev/null || true
    nmcli connection up "${AP}" ifname "${IFACE}" || {
        log "failed to bring up AP ${AP}"
        exit 1
    }
    log "AP ${AP} is up"
    exit 0
}

main "$@"

#!/usr/bin/env bash
# OGScope 树莓派网络环境初始化（NetworkManager + Avahi）
# Raspberry Pi network bootstrap for OGScope (NM + Avahi)
#
# 用法 / Usage:
#   sudo ./ogscope-network-init.sh init [--yes]
#   sudo ./ogscope-network-init.sh diag
#   sudo ./ogscope-network-init.sh ensure-systemd
#   sudo ./ogscope-network-init.sh reset [--yes]
#
# 环境 / Environment:
#   OGSCOPE_SKIP_NETWORK_INIT — install.sh 可跳过 / skip when set by installer

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

STA_NAME="OGScope-STA"
AP_NAME="OGScope-AP"
IFACE="${OGSCOPE_WIFI_INTERFACE:-wlan0}"
AP_IPV4="192.168.4.1/24"
AP_PSK="ogscopeadmin"

STATE_DIR="/var/lib/ogscope"
ENV_DIR="/etc/ogscope"
ENV_FILE="${ENV_DIR}/network.env"
ID_FILE="${STATE_DIR}/network-id.txt"
SWITCH_SRC="${SCRIPT_DIR}/ogscope-wifi-switch.sh"
SWITCH_DST="/usr/local/bin/ogscope-wifi-switch"
SUDOERS_D="/etc/sudoers.d/ogscope-wifi"
SUDOERS_NMCLI="/etc/sudoers.d/ogscope-nmcli"
# systemd drop-in：老部署主 unit 可能无 EnvironmentFile / Drop-in for units missing EnvironmentFile
SYSTEMD_DROPIN_DIR="/etc/systemd/system/ogscope.service.d"
SYSTEMD_NETWORK_ENV_CONF="${SYSTEMD_DROPIN_DIR}/ogscope-network-env.conf"

die() { echo "❌ $*" >&2; exit 1; }
info() { echo "ℹ️  $*"; }
ok() { echo "✅ $*"; }

require_root() {
    if [[ "${EUID}" -ne 0 ]]; then
        die "请使用 root 或 sudo 运行 / Run as root or sudo"
    fi
}

# wlan0 MAC 取后 4 位十六进制作为设备后缀 / Last 4 hex chars from wlan0 MAC
compute_suffix() {
    local mac hex
    if [[ ! -r "/sys/class/net/${IFACE}/address" ]]; then
        die "未找到 ${IFACE}，请连接网卡或设置 OGSCOPE_WIFI_INTERFACE / Interface not found"
    fi
    mac="$(tr -d ' \n' <"/sys/class/net/${IFACE}/address")"
    hex="${mac//:/}"
    if [[ ${#hex} -lt 4 ]]; then
        die "MAC 地址无效 / Invalid MAC: ${mac}"
    fi
    echo "${hex: -4}" | tr '[:upper:]' '[:lower:]'
}

ensure_dirs() {
    mkdir -p "${STATE_DIR}" "${ENV_DIR}"
    chmod 755 "${STATE_DIR}" "${ENV_DIR}" 2>/dev/null || true
}

install_switch_script() {
    if [[ ! -f "${SWITCH_SRC}" ]]; then
        die "未找到 ${SWITCH_SRC} / Switch script missing"
    fi
    install -m 755 "${SWITCH_SRC}" "${SWITCH_DST}"
    ok "已安装 ${SWITCH_DST}"
}

write_sudoers() {
    local run_user="${OGSCOPE_SERVICE_USER:-${SUDO_USER:-}}"
    if [[ -z "${run_user}" ]]; then
        info "未设置 OGSCOPE_SERVICE_USER/SUDO_USER，跳过 sudoers（可手动添加 NOPASSWD ${SWITCH_DST}）"
        return 0
    fi
    umask 077
    echo "${run_user} ALL=(ALL) NOPASSWD: ${SWITCH_DST}" >"${SUDOERS_D}.tmp"
    chmod 440 "${SUDOERS_D}.tmp"
    mv "${SUDOERS_D}.tmp" "${SUDOERS_D}"
    ok "已写入 ${SUDOERS_D}（用户 ${run_user}）"
}

# Web API 直接调用 nmcli 时需免密，否则 polkit 报 Not authorized / NOPASSWD nmcli for API
write_sudoers_nmcli() {
    local run_user="${OGSCOPE_SERVICE_USER:-${SUDO_USER:-}}"
    local nmcli_bin
    nmcli_bin="$(command -v nmcli 2>/dev/null || true)"
    if [[ -z "${run_user}" ]]; then
        info "未设置 OGSCOPE_SERVICE_USER/SUDO_USER，跳过 nmcli sudoers / Skipping nmcli sudoers"
        return 0
    fi
    if [[ -z "${nmcli_bin}" ]]; then
        info "未找到 nmcli，跳过 ogscope-nmcli sudoers / nmcli not found"
        return 0
    fi
    umask 077
    echo "${run_user} ALL=(ALL) NOPASSWD: ${nmcli_bin}" >"${SUDOERS_NMCLI}.tmp"
    chmod 440 "${SUDOERS_NMCLI}.tmp"
    mv "${SUDOERS_NMCLI}.tmp" "${SUDOERS_NMCLI}"
    ok "已写入 ${SUDOERS_NMCLI}（免密 ${nmcli_bin}，Web「激活」已保存 WiFi 等）"
}

write_network_env() {
    local suffix="$1"
    umask 077
    cat >"${ENV_FILE}.tmp" <<EOF
# OGScope 网络环境（由 ogscope-network-init.sh 生成，勿提交仓库）
# OGScope network env (generated; do not commit)
OGSCOPE_WIFI_STA_CONNECTION=${STA_NAME}
OGSCOPE_WIFI_AP_CONNECTION=${AP_NAME}
OGSCOPE_WIFI_INTERFACE=${IFACE}
OGSCOPE_DEVICE_ID_SUFFIX=${suffix}
OGSCOPE_WIFI_AP_SSID=OGScope_${suffix}
EOF
    chmod 600 "${ENV_FILE}.tmp"
    mv "${ENV_FILE}.tmp" "${ENV_FILE}"
    ok "已写入 ${ENV_FILE}"
}

# 同步 /etc/hosts 中 127.0.1.1，避免 hostnamectl 后 sudo 无法解析主机名
# Sync 127.0.1.1 in /etc/hosts so sudo resolves hostname after hostnamectl
sync_hosts_for_hostname() {
    local host="$1"
    local hosts="/etc/hosts"
    if [[ ! -f "${hosts}" ]]; then
        info "无 ${hosts}，跳过 / No hosts file; skipping"
        return 0
    fi
    if grep -qE '^127\.0\.1\.1[[:space:]]' "${hosts}" 2>/dev/null; then
        grep -vE '^127\.0\.1\.1[[:space:]]' "${hosts}" >"${hosts}.ogscope.tmp" \
            && mv "${hosts}.ogscope.tmp" "${hosts}"
    fi
    printf '127.0.1.1\t%s\n' "${host}" >>"${hosts}"
    ok "已同步 ${hosts}：127.0.1.1 -> ${host}"
}

# 写入 systemd drop-in，使 ogscope 进程加载 network.env（与 install.sh 主 unit 等价）
# Install systemd drop-in so ogscope loads network.env (same as install.sh main unit)
ensure_ogscope_systemd_network_env() {
    if ! command -v systemctl >/dev/null 2>&1; then
        info "无 systemctl，跳过 drop-in / No systemctl; skipping drop-in"
        return 0
    fi
    mkdir -p "${SYSTEMD_DROPIN_DIR}"
    umask 022
    cat >"${SYSTEMD_NETWORK_ENV_CONF}.tmp" <<'EOF'
[Service]
EnvironmentFile=-/etc/ogscope/network.env
EOF
    mv "${SYSTEMD_NETWORK_ENV_CONF}.tmp" "${SYSTEMD_NETWORK_ENV_CONF}"
    chmod 644 "${SYSTEMD_NETWORK_ENV_CONF}"
    systemctl daemon-reload
    ok "已写入 ${SYSTEMD_NETWORK_ENV_CONF} 并 systemctl daemon-reload"
}

create_nm_connections() {
    local suffix="$1"
    local ssid="OGScope_${suffix}"

    if ! command -v nmcli >/dev/null 2>&1; then
        die "未安装 nmcli，请 apt install network-manager / nmcli not found"
    fi

    # 删除同名旧连接（若存在）/ Remove stale connections
    nmcli connection delete "${AP_NAME}" 2>/dev/null || true
    nmcli connection delete "${STA_NAME}" 2>/dev/null || true

    # AP：热点 + 共享 IPv4（dnsmasq DHCP，避免客户端仅 169.254）/ Shared IPv4 + DHCP for clients
    # 仅 WPA2（RSN+CCMP），避免部分系统提示弱加密 / WPA2-only to avoid weak-security warnings
    nmcli connection add \
        type wifi \
        ifname "${IFACE}" \
        con-name "${AP_NAME}" \
        autoconnect no \
        wifi.mode ap \
        wifi.ssid "${ssid}" \
        wifi-sec.key-mgmt wpa-psk \
        wifi-sec.psk "${AP_PSK}" \
        wifi-sec.proto rsn \
        wifi-sec.pairwise ccmp \
        wifi-sec.group ccmp \
        ipv4.method shared \
        ipv4.addresses "${AP_IPV4}" \
        ipv6.method ignore

    # STA：占位 SSID（开放），供后续 API 改为 WPA / Placeholder STA; API sets WPA-PSK
    nmcli connection add \
        type wifi \
        ifname "${IFACE}" \
        con-name "${STA_NAME}" \
        autoconnect no \
        wifi.mode infrastructure \
        wifi.ssid "__ogscope_sta_pending__" \
        wifi-sec.key-mgmt none \
        ipv4.method auto \
        ipv6.method ignore

    ok "已创建 NM 连接 ${AP_NAME}（SSID ${ssid}）与 ${STA_NAME}"
}

set_hostname_avahi() {
    local suffix="$1"
    local host="ogscope-${suffix}"
    if command -v hostnamectl >/dev/null 2>&1; then
        hostnamectl set-hostname "${host}" || info "hostnamectl 失败，可忽略 / hostnamectl failed"
    fi
    sync_hosts_for_hostname "${host}"
    if command -v avahi-daemon >/dev/null 2>&1; then
        systemctl enable avahi-daemon 2>/dev/null || true
        systemctl restart avahi-daemon 2>/dev/null || true
        ok "Avahi 已启用；尝试访问 http://${host}.local / Avahi enabled"
    else
        info "未安装 avahi-daemon，mDNS 不可用 / Install avahi-daemon for .local"
    fi
}

cmd_init() {
    local yes_flag="${1:-}"
    require_root
    ensure_dirs

    local suffix
    if [[ -f "${ID_FILE}" ]]; then
        suffix="$(tr -d ' \n' <"${ID_FILE}")"
        info "复用已保存后缀 / Reusing suffix: ${suffix}"
    else
        suffix="$(compute_suffix)"
        echo "${suffix}" >"${ID_FILE}"
        chmod 644 "${ID_FILE}"
        ok "新建设备后缀 / Device suffix: ${suffix}"
    fi

    if [[ "${yes_flag}" != "--yes" ]]; then
        echo "将创建 SSID: OGScope_${suffix}，密码: ${AP_PSK}"
        read -r -p "继续? [y/N] " confirm
        if [[ ! "${confirm}" =~ ^[yY]$ ]]; then
            die "已取消 / Aborted"
        fi
    fi

    # 重建 wlan0 的 NM 连接会中断当前 WiFi（含经 WiFi 的 SSH）/ Recreating NM WiFi drops link (SSH over Wi-Fi included)
    info "⚠️  若当前经 WiFi 连接本机（含 SSH），下面步骤会重建无线配置，SSH 可能立即断开；请优先用有线网口、串口或本地控制台执行。"
    info "   If connected via Wi-Fi (including SSH), the next steps may drop this session; prefer Ethernet, serial, or local console."

    install_switch_script
    create_nm_connections "${suffix}"
    write_network_env "${suffix}"
    ensure_ogscope_systemd_network_env
    write_sudoers
    write_sudoers_nmcli
    set_hostname_avahi "${suffix}"

    ok "init 完成。请 systemctl restart ogscope 并连接热点 OGScope_${suffix} / init done"
}

cmd_ensure_systemd() {
    require_root
    if [[ ! -f "${ENV_FILE}" ]]; then
        die "缺少 ${ENV_FILE}，请先 init / Missing network.env; run init first"
    fi
    # 与 init 一致：补 127.0.1.1，减轻 sudo unable to resolve host（同次 sudo 首行仍可能先警告一次）
    # Match init: fix 127.0.1.1 for sudo; first sudo line may still warn before this runs
    local hn=""
    if [[ -f "${ID_FILE}" ]]; then
        hn="ogscope-$(tr -d ' \n' <"${ID_FILE}")"
    fi
    if [[ -z "${hn}" ]]; then
        hn="$(hostname 2>/dev/null | tr -d ' \n' || true)"
    fi
    if [[ -n "${hn}" ]]; then
        sync_hosts_for_hostname "${hn}"
    fi
    ensure_ogscope_systemd_network_env
    write_sudoers_nmcli
    info "请执行: sudo systemctl restart ogscope / Please run: sudo systemctl restart ogscope"
}

cmd_diag() {
    info "=== OGScope 网络诊断 / Network diagnostics ==="
    command -v nmcli >/dev/null && ok "nmcli: OK" || echo "❌ nmcli 缺失"
    [[ -r "/sys/class/net/${IFACE}/address" ]] && ok "${IFACE} 存在" || echo "❌ ${IFACE} 不存在"
    [[ -f "${ENV_FILE}" ]] && ok "network.env 存在: ${ENV_FILE}" || echo "⚠️  无 ${ENV_FILE}"
    [[ -f "${SWITCH_DST}" ]] && ok "切换脚本: ${SWITCH_DST}" || echo "⚠️  无 ${SWITCH_DST}"
    [[ -f "${SUDOERS_D}" ]] && ok "sudoers: ${SUDOERS_D}" || echo "⚠️  无 sudoers"
    [[ -f "${SUDOERS_NMCLI}" ]] && ok "sudoers nmcli: ${SUDOERS_NMCLI}" || echo "⚠️  无 ${SUDOERS_NMCLI}（Web 激活 WiFi 可能报 Not authorized）"
    command -v avahi-daemon >/dev/null && ok "avahi-daemon 已安装" || echo "⚠️  avahi-daemon 未安装"
    if command -v nmcli >/dev/null; then
        nmcli connection show "${AP_NAME}" >/dev/null 2>&1 && ok "连接 ${AP_NAME} 存在" || echo "⚠️  无 ${AP_NAME}"
        nmcli connection show "${STA_NAME}" >/dev/null 2>&1 && ok "连接 ${STA_NAME} 存在" || echo "⚠️  无 ${STA_NAME}"
        if nmcli connection show "${AP_NAME}" >/dev/null 2>&1; then
            local ap_method
            ap_method="$(nmcli -g ipv4.method connection show "${AP_NAME}" 2>/dev/null | head -n1 || true)"
            if [[ "${ap_method}" == "manual" ]]; then
                echo "⚠️  ${AP_NAME} 为 ipv4.method manual：客户端可能仅有 169.254，无法访问 192.168.4.1"
                echo "   请执行: sudo ${SCRIPT_DIR}/$(basename "$0") init --yes（重建 AP 为 shared + DHCP）"
                echo "   Or: sudo ${SCRIPT_DIR}/$(basename "$0") init --yes to recreate AP (shared + DHCP)"
            fi
        fi
    fi
    if [[ -f "${ID_FILE}" ]]; then
        info "后缀 / Suffix: $(cat "${ID_FILE}")"
    fi
    if command -v systemctl >/dev/null 2>&1 && systemctl cat ogscope >/dev/null 2>&1; then
        if systemctl cat ogscope 2>/dev/null | grep -qE 'EnvironmentFile=.*etc/ogscope/network\.env'; then
            ok "ogscope.service 已加载 network.env（主 unit 或 drop-in）"
        else
            echo "⚠️  ogscope 未引用 /etc/ogscope/network.env；API 可能显示 wifi_not_configured"
            echo "   可执行: sudo ${0} ensure-systemd && sudo systemctl restart ogscope"
        fi
    else
        info "无 ogscope systemd 单元或未安装 systemctl / No ogscope unit or no systemctl"
    fi
    local hn
    hn="$(hostname 2>/dev/null || true)"
    if [[ -n "${hn}" ]] && grep -qE "^127\.0\.1\.1[[:space:]].*${hn}" /etc/hosts 2>/dev/null; then
        ok "/etc/hosts 含 127.0.1.1 -> ${hn}"
    elif [[ -n "${hn}" ]]; then
        echo "⚠️  /etc/hosts 可能缺少 127.0.1.1 ${hn}，sudo 或提示 unable to resolve host"
        echo "   可重新 init 或手动编辑 /etc/hosts"
    fi
}

cmd_reset() {
    local yes_flag="${1:-}"
    require_root
    if [[ "${yes_flag}" != "--yes" ]]; then
        read -r -p "将删除 ${AP_NAME}、${STA_NAME} 与 ${ENV_FILE}，确认? [y/N] " confirm
        if [[ ! "${confirm}" =~ ^[yY]$ ]]; then
            die "已取消"
        fi
    fi
    nmcli connection delete "${AP_NAME}" 2>/dev/null || true
    nmcli connection delete "${STA_NAME}" 2>/dev/null || true
    rm -f "${ENV_FILE}"
    ok "reset 完成 / reset done"
}

main() {
    local sub="${1:-}"
    shift || true
    case "${sub}" in
    init) cmd_init "${1:-}" ;;
    diag) cmd_diag ;;
    ensure-systemd) cmd_ensure_systemd ;;
    reset) cmd_reset "${1:-}" ;;
    *)
        echo "Usage: sudo $0 init [--yes] | diag | ensure-systemd | reset [--yes]" >&2
        exit 1
        ;;
    esac
}

main "$@"

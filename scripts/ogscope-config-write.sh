#!/usr/bin/env bash
# 受控写入 /etc/ogscope/*.env（供 Web 配置 API 经 sudo 调用）
# Controlled write to /etc/ogscope/*.env (invoked via sudo from Web config API)
#
# 用法 / Usage:
#   echo "KEY=value" | sudo -n ogscope-config-write /etc/ogscope/ogscope.env [mode] [group]
#
set -euo pipefail

die() {
    echo "ogscope-config-write: $*" >&2
    exit 1
}

dest="${1:-}"
mode="${2:-640}"
group="${3:-}"

ALLOWED=(
    "/etc/ogscope/ogscope.env"
    "/etc/ogscope/network.env"
)

[[ -n "${dest}" ]] || die "missing destination path"

allowed=0
for path in "${ALLOWED[@]}"; do
    if [[ "${dest}" == "${path}" ]]; then
        allowed=1
        break
    fi
done
[[ "${allowed}" -eq 1 ]] || die "destination not allowed: ${dest}"

if [[ ! "${mode}" =~ ^[0-7]{3,4}$ ]]; then
    die "invalid mode: ${mode}"
fi

if [[ -z "${group}" ]]; then
    if [[ -e "${dest}" ]]; then
        group="$(stat -c '%G' "${dest}" 2>/dev/null || true)"
    fi
    group="${group:-ogscope}"
fi

mkdir -p "$(dirname "${dest}")"
tmp="$(mktemp "${dest}.tmp.XXXXXX")"
trap 'rm -f "${tmp}"' EXIT
cat >"${tmp}"
chown "root:${group}" "${tmp}"
chmod "${mode}" "${tmp}"
mv -f "${tmp}" "${dest}"
trap - EXIT

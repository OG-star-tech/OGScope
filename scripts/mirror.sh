# OGScope 安装镜像辅助 / Mirror helpers for OGScope install scripts
# 由 install.sh / board-update.sh 用 `source` 加载 / Sourced by install.sh and board-update.sh
#
# 说明：Poetry 本体仍由官方 install.python-poetry.org 引导安装（避免 PEP 668）；
# cn 模式主要加速 apt 与「项目依赖」的 PyPI 下载 / Poetry bootstrap stays official; cn speeds apt + project wheels
#
# 环境变量 / Environment:
#   OGSCOPE_MIRROR=auto|cn|international
#     auto — 根据 LANG/LC_* 与系统时区启发式判断（可误判，可显式覆盖）
#     cn — 使用中国大陆常用镜像（apt + PyPI）
#     international — 使用系统默认与官方 PyPI，不替换 apt 源
#
# 启发式说明 / Heuristic: 非中文环境用户若在国内，请显式设置 OGSCOPE_MIRROR=cn
# / Users in China with English locale should set OGSCOPE_MIRROR=cn explicitly.

# 从 /etc/os-release 加载发行版信息（供检测与安全判断）/ Load distro info from /etc/os-release
# 导出 OGSCOPE_OS_* / Exports OGSCOPE_OS_ID, VERSION_ID, PRETTY_NAME, ID_LIKE, VARIANT, etc.
ogscope_load_os_release() {
    if [ ! -r /etc/os-release ]; then
        echo "❌ 未找到 /etc/os-release，无法识别发行版 / Missing /etc/os-release; cannot detect OS" >&2
        return 1
    fi
    # shellcheck disable=SC1091
    . /etc/os-release
    export OGSCOPE_OS_ID="${ID:-unknown}"
    export OGSCOPE_OS_VERSION_ID="${VERSION_ID:-}"
    export OGSCOPE_OS_VERSION_CODENAME="${VERSION_CODENAME:-}"
    export OGSCOPE_OS_PRETTY_NAME="${PRETTY_NAME:-}"
    export OGSCOPE_OS_ID_LIKE="${ID_LIKE:-}"
    export OGSCOPE_OS_VARIANT="${VARIANT:-}"
    export OGSCOPE_OS_VARIANT_ID="${VARIANT_ID:-}"
    return 0
}

# 是否为 apt + Debian 系（含 Raspberry Pi OS、Ubuntu、Armbian 等）/ True if apt-based Debian family
# Raspberry Pi OS 通常 ID=debian；旧版可能为 raspbian / RPi OS is usually ID=debian; older may be raspbian
ogscope_is_debian_family() {
    case "${OGSCOPE_OS_ID:-}" in
    debian | ubuntu | raspbian | linuxmint | pop | zorin | kali)
        return 0
        ;;
    esac
    case ",${OGSCOPE_OS_ID_LIKE:-}," in
    *,debian,*) return 0 ;;
    *,ubuntu,*) return 0 ;;
    esac
    return 1
}

# 安装脚本入口：非 Debian 系则退出，避免误改软件源 / Abort install on non-Debian systems (safety)
ogscope_require_debian_family_apt() {
    if ! ogscope_is_debian_family; then
        echo "❌ 本脚本仅支持 Debian/Ubuntu 系发行版（含 Raspberry Pi OS、Orange Pi Debian 镜像）。" >&2
        echo "❌ This installer only supports Debian/Ubuntu family (incl. Raspberry Pi OS, Armbian Debian)." >&2
        echo "   当前 ID=${OGSCOPE_OS_ID:-?} ID_LIKE=${OGSCOPE_OS_ID_LIKE:-?} / Current OS ID shown above." >&2
        return 1
    fi
    if ! command -v apt >/dev/null 2>&1 && ! command -v apt-get >/dev/null 2>&1; then
        echo "❌ 未找到 apt/apt-get / apt not found" >&2
        return 1
    fi
    return 0
}

# 打印已识别系统（中英）/ Print detected OS (bilingual)
ogscope_print_os_summary() {
    echo "🖥️  发行版 / OS: ${OGSCOPE_OS_PRETTY_NAME:-${OGSCOPE_OS_ID:-unknown}}"
    echo "   ID=${OGSCOPE_OS_ID:-?} VERSION_ID=${OGSCOPE_OS_VERSION_ID:-?} CODENAME=${OGSCOPE_OS_VERSION_CODENAME:-?}"
    if [ -n "${OGSCOPE_OS_VARIANT:-}" ]; then
        echo "   VARIANT=${OGSCOPE_OS_VARIANT:-} / VARIANT_ID=${OGSCOPE_OS_VARIANT_ID:-}"
    fi
    if [ -f /proc/device-tree/model ]; then
        echo "   硬件型号 / Hardware: $(tr -d '\0' </proc/device-tree/model 2>/dev/null || echo '?')"
    fi
}

# 解析镜像模式，标准输出为 cn 或 international / Resolve mode; prints cn or international
ogscope_resolve_mirror() {
    local m="${OGSCOPE_MIRROR:-auto}"
    case "${m}" in
    cn | CN | china | China)
        echo cn
        return 0
        ;;
    # 境外 / Outside mainland China (explicit)
    international | global | intl | default | us | US | eu | EU)
        echo international
        return 0
        ;;
    auto | "")
        ;;
    *)
        echo "⚠️ 未知 OGSCOPE_MIRROR=${m}，按 auto / Unknown OGSCOPE_MIRROR, using auto" >&2
        ;;
    esac

    case "${LANG:-}" in *zh_CN*) echo cn && return 0 ;; esac
    case "${LC_ALL:-}" in *zh_CN*) echo cn && return 0 ;; esac
    case "${LC_MESSAGES:-}" in *zh_CN*) echo cn && return 0 ;; esac

    # 时区启发 / Timezone heuristic (common China zones)
    local tz=""
    if [ -r /etc/timezone ]; then
        tz="$(tr -d '\r\n' </etc/timezone)"
    elif command -v timedatectl >/dev/null 2>&1; then
        tz="$(timedatectl show -p Timezone --value 2>/dev/null || true)"
    fi
    case "${tz}" in
    Asia/Shanghai | Asia/Chongqing | Asia/Harbin | Asia/Urumqi | Asia/Hong_Kong | Asia/Macau | Asia/Taipei)
        echo cn
        return 0
        ;;
    esac

    echo international
}

# 导出中国大陆 PyPI 环境变量（清华）/ Export env for Tsinghua PyPI mirror
ogscope_export_pypi_mirror_cn() {
    export PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
    export PIP_TRUSTED_HOST="pypi.tuna.tsinghua.edu.cn"
    export UV_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
    # Poetry / urllib 部分场景会读 REQUESTS_*；延长超时利于弱网 / Longer timeout for slow links
    export POETRY_REQUESTS_TIMEOUT="${POETRY_REQUESTS_TIMEOUT:-120}"
}

# 取消国内 PyPI 覆盖，使用默认官方索引 / Unset CN overrides; use default PyPI
ogscope_export_pypi_mirror_international() {
    unset PIP_INDEX_URL PIP_TRUSTED_HOST UV_INDEX_URL || true
}

# 将 apt 源替换为清华镜像（需 sudo）/ Replace apt sources with Tsinghua mirror (requires sudo)
ogscope_apply_apt_mirror_cn() {
    local stamp
    stamp="$(date +%s)"
    echo "🌏 配置 apt 使用中国大陆镜像（清华）… / Configuring apt for China mirror (Tsinghua)…"

    if [ ! -d /etc/apt ]; then
        echo "⚠️ 未找到 /etc/apt，跳过 apt 镜像 / No /etc/apt, skipping"
        return 0
    fi

    sudo cp -a /etc/apt/sources.list "/etc/apt/sources.list.bak.ogscope.${stamp}" 2>/dev/null || true
    if [ -d /etc/apt/sources.list.d ]; then
        sudo find /etc/apt/sources.list.d -maxdepth 1 -type f \( -name '*.list' -o -name '*.sources' \) -exec \
            cp -a {} {}.bak.ogscope."${stamp}" \; 2>/dev/null || true
    fi

    # Ubuntu / Ubuntu ports / Debian 常见写法 / Common Ubuntu & Debian patterns
    sudo find /etc/apt -type f \( -name 'sources.list' -o -name '*.list' -o -name '*.sources' \) -print0 2>/dev/null |
        while IFS= read -r -d '' f; do
            [ -z "${f}" ] && continue
            sudo sed -i \
                -e 's|http://archive.ubuntu.com/ubuntu|https://mirrors.tuna.tsinghua.edu.cn/ubuntu|g' \
                -e 's|https://archive.ubuntu.com/ubuntu|https://mirrors.tuna.tsinghua.edu.cn/ubuntu|g' \
                -e 's|http://ports.ubuntu.com/ubuntu-ports|https://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports|g' \
                -e 's|https://ports.ubuntu.com/ubuntu-ports|https://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports|g' \
                -e 's|http://security.ubuntu.com/ubuntu|https://mirrors.tuna.tsinghua.edu.cn/ubuntu|g' \
                -e 's|https://security.ubuntu.com/ubuntu|https://mirrors.tuna.tsinghua.edu.cn/ubuntu|g' \
                -e 's|http://deb.debian.org/debian|https://mirrors.tuna.tsinghua.edu.cn/debian|g' \
                -e 's|https://deb.debian.org/debian|https://mirrors.tuna.tsinghua.edu.cn/debian|g' \
                -e 's|http://security.debian.org/debian-security|https://mirrors.tuna.tsinghua.edu.cn/debian-security|g' \
                -e 's|https://security.debian.org/debian-security|https://mirrors.tuna.tsinghua.edu.cn/debian-security|g' \
                "${f}" 2>/dev/null || true
        done

    echo "✅ apt 镜像已写入（已备份 *.bak.ogscope.${stamp}）/ Apt mirror applied (backups created)"
}

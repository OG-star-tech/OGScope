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
#   OGSCOPE_NONINTERACTIVE=1 — 跳过交互式网络环境询问（CI/无人值守）/ Skip region prompt (CI, automation)
#
# 启发式说明 / Heuristic: 非中文环境用户若在国内，请显式设置 OGSCOPE_MIRROR=cn
# / Users in China with English locale should set OGSCOPE_MIRROR=cn explicitly.
# 交互安装时若未显式指定 cn/international，将询问国内/国外/自动 / Interactive installs prompt
# unless OGSCOPE_MIRROR is already cn or international.

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
        echo "❌ 本脚本仅支持 Debian/Ubuntu 系发行版（含 Raspberry Pi OS）。" >&2
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

# 交互式选择 apt/PyPI 镜像（cn / international / auto）；已显式设置时跳过 / Interactive mirror choice;
# skipped when OGSCOPE_MIRROR is already set to cn or international.
ogscope_prompt_mirror_if_needed() {
    if [ -n "${OGSCOPE_MIRROR_PROMPT_DONE:-}" ]; then
        return 0
    fi
    # CI、管道、非 TTY、显式非交互 / CI, pipes, non-TTY, explicit non-interactive
    if [ ! -t 0 ] || [ ! -t 1 ] || [ "${CI:-}" = "true" ] || [ "${OGSCOPE_NONINTERACTIVE:-}" = "1" ]; then
        return 0
    fi
    case "${OGSCOPE_MIRROR:-}" in
    cn | CN | china | China | international | global | intl | default | us | US | eu | EU)
        export OGSCOPE_MIRROR_PROMPT_DONE=1
        return 0
        ;;
    esac

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  软件下载源 / Download mirrors (apt & PyPI)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  影响 apt 与 Poetry 下载速度；请按网络情况选择。"
    echo "  Affects apt & Poetry download speed; pick what works best."
    echo ""
    echo "    1) 全球（上游 Debian/Ubuntu + PyPI.org）/ Global (upstream mirrors)"
    echo "    2) 中国大陆（清华镜像）/ Mainland China (Tsinghua mirror)"
    echo "    3) 自动（语言与时区启发，可能不准）/ Auto (locale & timezone heuristic)"
    echo ""
    read -r -p "  请输入 1–3 / Enter 1–3 [default: 1]: " _ogscope_mirror_choice || true
    case "${_ogscope_mirror_choice:-1}" in
    1)
        OGSCOPE_MIRROR=international
        echo "  → 已选：全球 / Selected: Global (international)"
        ;;
    2)
        OGSCOPE_MIRROR=cn
        echo "  → 已选：中国大陆 / Selected: Mainland China (cn)"
        ;;
    3)
        OGSCOPE_MIRROR=auto
        echo "  → 已选：自动 / Selected: Auto"
        ;;
    *)
        echo "  ⚠️ 无效输入，使用自动 / Invalid input; using auto"
        OGSCOPE_MIRROR=auto
        ;;
    esac
    export OGSCOPE_MIRROR
    export OGSCOPE_MIRROR_PROMPT_DONE=1
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

# 验证 venv 中 numpy/scipy 可导入 / Verify numpy & scipy import (catches stale Poetry state)
# Poetry 有时显示「无依赖更新」但大 wheel 未实际安装 / Poetry may skip while wheels missing
ogscope_verify_numpy_scipy() {
    poetry run python -c "import numpy, scipy" 2>/dev/null
}

# 验证 TurboJPEG Python 绑定与系统库均可用 / Verify Python binding and system lib are usable.
ogscope_verify_turbojpeg() {
    poetry run python - <<'PY' >/dev/null 2>&1
from turbojpeg import TurboJPEG

TurboJPEG()
PY
}

# 若 systemd 已存在但 ExecStart 不是当前 Poetry venv，则修正（避免 ~/.virtualenvs/ 与项目 .venv 混用）
# If unit exists but ExecStart points elsewhere than current Poetry venv, fix it (avoids ~/.virtualenvs vs .venv mismatch)
# 参数 / Args: $1 = unit 文件路径 / unit file path, $2 = venv 内 python 可执行文件绝对路径 / absolute path to venv python
ogscope_sync_systemd_execstart_if_needed() {
    local unit_path="${1:?}"
    local venv_python="${2:?}"
    local expected_line="ExecStart=${venv_python} -m ogscope.main"

    if [ ! -f "${unit_path}" ]; then
        echo "ℹ️  未找到 ${unit_path}，跳过 ExecStart 同步（请先运行 install.sh）/ No unit; skip sync (run install.sh first)"
        return 0
    fi
    if [ ! -x "${venv_python}" ]; then
        echo "❌ 解释器不可执行 / Python not executable: ${venv_python}" >&2
        return 1
    fi

    local cur_line
    cur_line="$(grep '^ExecStart=' "${unit_path}" | head -n1 || true)"
    if [ -z "${cur_line}" ]; then
        echo "❌ ${unit_path} 中无 ExecStart / No ExecStart in unit" >&2
        return 1
    fi

    if [ "${cur_line}" = "${expected_line}" ]; then
        echo "✅ systemd ExecStart 与当前 Poetry venv 一致 / ExecStart matches Poetry venv"
        return 0
    fi

    echo "⚙️  修正 systemd ExecStart（曾指向旧虚拟环境路径）/ Fixing ExecStart (was stale venv path)"
    echo "   旧 / Old: ${cur_line}"
    echo "   新 / New: ${expected_line}"
    sudo sed -i "s|^ExecStart=.*|${expected_line}|" "${unit_path}"
    echo "✅ 已更新 ${unit_path} / Unit updated"
}

# 若 systemd unit 缺少主配置 EnvironmentFile，则补齐 / Ensure primary config EnvironmentFile exists in unit
# 参数 / Args: $1 = unit 文件路径 / unit file path
ogscope_ensure_systemd_primary_envfile() {
    local unit_path="${1:?}"
    local marker="EnvironmentFile=-/etc/ogscope/ogscope.env"

    if [ ! -f "${unit_path}" ]; then
        echo "ℹ️  未找到 ${unit_path}，跳过 EnvironmentFile 检查 / Unit missing; skip envfile check"
        return 0
    fi
    if grep -qF "${marker}" "${unit_path}" 2>/dev/null; then
        return 0
    fi
    echo "⚙️  为 unit 补充主配置 EnvironmentFile / Injecting primary EnvironmentFile into unit..."
    sudo awk -v marker="${marker}" '
        /^\[Service\]$/ { print; print marker; next }
        { print }
    ' "${unit_path}" >"${unit_path}.ogscope.tmp"
    sudo mv "${unit_path}.ogscope.tmp" "${unit_path}"
    echo "✅ 已补充 ${marker} / Injected"
}

# 若项目目录变更，同步 ogscope-network-boot.service 的 ExecStart（与 install.sh 一致）
# If project path changed, sync ExecStart in ogscope-network-boot.service (matches install.sh)
# 参数 / Args: $1 = 项目根目录绝对路径 / absolute project root
ogscope_sync_network_boot_unit_if_needed() {
    local project_dir="${1:?}"
    local unit_path="/etc/systemd/system/ogscope-network-boot.service"
    local script_path="${project_dir}/scripts/ogscope-network-boot.sh"
    local expected_line="ExecStart=${script_path}"

    if [ ! -f "${unit_path}" ]; then
        echo "ℹ️  未找到 ${unit_path}，跳过开机网络 boot 同步（未安装或已移除）/ No boot unit; skip sync"
        return 0
    fi
    if [ ! -f "${script_path}" ]; then
        echo "⚠️  项目内缺少 ${script_path}，跳过 ExecStart 同步 / Script missing; skip ExecStart sync" >&2
        return 0
    fi

    local cur_line
    cur_line="$(grep '^ExecStart=' "${unit_path}" | head -n1 || true)"
    if [ -z "${cur_line}" ]; then
        echo "⚠️  ${unit_path} 中无 ExecStart / No ExecStart in unit" >&2
        return 0
    fi

    if [ "${cur_line}" = "${expected_line}" ]; then
        echo "✅ ogscope-network-boot ExecStart 与当前项目目录一致 / Boot unit ExecStart matches project"
        return 0
    fi

    echo "⚙️  修正 ogscope-network-boot ExecStart（项目目录可能已变更）/ Fixing boot unit ExecStart"
    echo "   旧 / Old: ${cur_line}"
    echo "   新 / New: ${expected_line}"
    sudo sed -i "s|^ExecStart=.*|${expected_line}|" "${unit_path}"
    echo "✅ 已更新 ${unit_path} / Unit updated"
}

# 解析 vendored tetra3 内 default_database.npz 路径（不依赖 import ogscope，避免路径注入异常）
# Resolve path to default_database.npz in vendored tetra3 (no import ogscope; avoids path edge cases)
# 参数 / Args: $1 = 项目根目录绝对路径 / absolute project root
# 标准输出：若存在则打印绝对路径，否则空 / Prints absolute path if file exists, else empty
ogscope_resolve_plate_solve_database_src_from_venv() {
    local project_dir="${1:?}"
    (
        cd "${project_dir}" && PROJECT_ROOT="${project_dir}" poetry run python - <<'PY'
import os
import sys
from pathlib import Path

project = Path(os.environ["PROJECT_ROOT"]).resolve()
vendor = project / "ogscope" / "vendor"
if vendor.is_dir():
    sys.path.insert(0, str(vendor))
import tetra3  # noqa: E402 — after vendor path

p = Path(tetra3.__file__).resolve().parent / "data" / "default_database.npz"
print(p if p.is_file() else "", end="")
PY
    )
}

# 将 default_database.npz 复制到 data/plate_solve/（与 solver 优先路径一致）
# Copy default_database.npz into data/plate_solve/ (matches solver resolution order)
# 参数 / Args: $1 = 项目根目录绝对路径 / absolute project root
# 环境 / Env: OGSCOPE_SKIP_PLATE_DB=1 跳过；OGSCOPE_FORCE_PLATE_DB=1 覆盖已存在目标 / skip; overwrite dest
ogscope_sync_plate_solve_database_if_needed() {
    local project_dir="${1:?}"
    local dest="${project_dir}/data/plate_solve/default_database.npz"
    local vendor_src="${project_dir}/ogscope/vendor/tetra3/data/default_database.npz"

    if [ "${OGSCOPE_SKIP_PLATE_DB:-}" = "1" ]; then
        echo "⏭️  跳过图案库复制（OGSCOPE_SKIP_PLATE_DB=1）/ Skipping plate DB copy"
        return 0
    fi

    mkdir -p "${project_dir}/data/plate_solve"

    if [ -f "${dest}" ] && [ "${OGSCOPE_FORCE_PLATE_DB:-}" != "1" ]; then
        echo "ℹ️  已存在 ${dest}，跳过复制（覆盖：OGSCOPE_FORCE_PLATE_DB=1）/ Already present; skip (overwrite: OGSCOPE_FORCE_PLATE_DB=1)"
        return 0
    fi

    local src=""
    if [ -f "${vendor_src}" ]; then
        src="${vendor_src}"
    else
        src="$(ogscope_resolve_plate_solve_database_src_from_venv "${project_dir}" || true)"
    fi

    if [ -z "${src}" ] || [ ! -f "${src}" ]; then
        echo "⚠️  未找到可复制的 default_database.npz（请放入 ogscope/vendor/tetra3/data/ 或手动复制到 data/plate_solve/）"
        echo "⚠️  No default_database.npz to copy; see docs/development/plate-solve-data.md"
        return 0
    fi

    echo "📋 复制 Tetra3 图案库到 data/plate_solve/default_database.npz ..."
    echo "📋 Copying Tetra3 pattern database to data/plate_solve/default_database.npz ..."
    cp -a "${src}" "${dest}"
    echo "✅ 图案库已就绪 / Pattern database ready: ${dest}"
}

# 安装/升级后校验 data/plate_solve/default_database.npz 是否存在（主动检查）
# Verify default_database.npz after install/update (explicit check)
# 参数 / Args: $1 = 项目根目录绝对路径 / absolute project root
ogscope_report_plate_solve_database_status() {
    local project_dir="${1:?}"
    local dest="${project_dir}/data/plate_solve/default_database.npz"

    if [ "${OGSCOPE_SKIP_PLATE_DB:-}" = "1" ]; then
        echo "ℹ️  已跳过图案库步骤（OGSCOPE_SKIP_PLATE_DB=1）；未校验 ${dest} / Skipped plate DB step"
        return 0
    fi

    if [ -f "${dest}" ]; then
        local sz
        sz="$(du -h "${dest}" 2>/dev/null | awk '{print $1}' || echo "?")"
        echo "✅ 星图解算图案库 / Plate DB: data/plate_solve/default_database.npz（${sz}）"
        echo "✅ Plate DB: data/plate_solve/default_database.npz (${sz})"
        return 0
    fi

    echo "⚠️  星图解算需 default_database.npz，但未在 data/plate_solve/ 找到。"
    echo "   请将文件放入 ogscope/vendor/tetra3/data/ 后重装/重跑本脚本，或手动复制到 data/plate_solve/；见 docs/development/plate-solve-data.md"
    echo "⚠️  Plate solving needs default_database.npz under data/plate_solve/; see docs/development/plate-solve-data.md"
}

# 增量更新：同步网络相关工件（与近期 wifi-nm / systemd 文档一致）
# Board update: sync network artifacts (matches wifi-nm + systemd docs)
# 参数 / Args: $1 = 项目根目录绝对路径 / absolute project root
# 环境 / Env: OGSCOPE_SKIP_NETWORK_SYNC=1 跳过；需 sudo（免密或交互）/ skip; requires sudo
ogscope_sync_network_board_artifacts_if_needed() {
    local project_dir="${1:?}"
    local init_script="${project_dir}/scripts/ogscope-network-init.sh"
    local switch_src="${project_dir}/scripts/ogscope-wifi-switch.sh"
    local switch_dst="/usr/local/bin/ogscope-wifi-switch"

    if [ "${OGSCOPE_SKIP_NETWORK_SYNC:-}" = "1" ]; then
        echo "⏭️  跳过网络工件同步（OGSCOPE_SKIP_NETWORK_SYNC=1）/ Skipping network artifact sync"
        return 0
    fi

    chmod +x "${project_dir}/scripts/ogscope-network-boot.sh" 2>/dev/null || true
    chmod +x "${init_script}" 2>/dev/null || true

    if [ -f "${switch_src}" ]; then
        if [ ! -f "${switch_dst}" ] || ! cmp -s "${switch_src}" "${switch_dst}" 2>/dev/null; then
            echo "📋 同步 WiFi 切换脚本 / Syncing WiFi switch script → ${switch_dst} ..."
            if sudo -n true 2>/dev/null; then
                sudo install -m 755 "${switch_src}" "${switch_dst}"
                echo "✅ 已更新 ${switch_dst} / Updated"
            else
                echo "⚠️  无法免密 sudo，未更新 ${switch_dst}；请手动: sudo install -m 755 ${switch_src} ${switch_dst}"
                echo "⚠️  Non-interactive sudo unavailable; install switch script manually (see wifi-nm.md)"
            fi
        else
            echo "✅ ogscope-wifi-switch 已是最新 / WiFi switch script up to date"
        fi
    fi

    if [ ! -f "/etc/ogscope/network.env" ]; then
        echo "ℹ️  无 /etc/ogscope/network.env，跳过 ensure-systemd（首次部署请运行 install.sh）/ No network.env; skip ensure-systemd"
        return 0
    fi

    echo "🌐 同步 systemd network.env 与 nmcli sudoers（ensure-systemd）/ Syncing ensure-systemd ..."
    if sudo -n true 2>/dev/null; then
        sudo env OGSCOPE_SERVICE_USER="${USER}" "${init_script}" ensure-systemd \
            || echo "⚠️  ensure-systemd 失败；可手动: sudo env OGSCOPE_SERVICE_USER=\$USER ${init_script} ensure-systemd"
    else
        echo "⚠️  无法免密 sudo，未运行 ensure-systemd；若 Web WiFi 异常请手动执行上述命令（见 docs/development/wifi-nm.md）"
        echo "⚠️  Non-interactive sudo unavailable; run ensure-systemd manually if WiFi/API issues"
    fi
}

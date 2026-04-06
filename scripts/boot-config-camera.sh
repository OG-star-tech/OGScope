# OGScope 树莓派 /boot 摄像头设备树配置 / Raspberry Pi boot config (CSI camera)
# 由 install.sh、board-update.sh 用 `source` 加载 / Sourced by install.sh and board-update.sh
#
# 环境变量 / Environment:
#   OGSCOPE_CAMERA=imx327|skip — 非交互时指定摄像头型号或跳过 / Preset camera model or skip (non-interactive)
#   OGSCOPE_SKIP_BOOT_CAMERA=1 — 不询问、不修改 /boot 配置 / Do not prompt or modify boot config
#   OGSCOPE_NONINTERACTIVE=1 — 无 TTY 时不提示；未设 OGSCOPE_CAMERA 时等同 skip / No prompt; default skip without OGSCOPE_CAMERA

# 返回可写的 config.txt 路径（Bookworm 多为 /boot/firmware/config.txt）/ Resolve config.txt path
ogscope_boot_config_path() {
    if [ -f /boot/firmware/config.txt ]; then
        echo "/boot/firmware/config.txt"
    elif [ -f /boot/config.txt ]; then
        echo "/boot/config.txt"
    else
        echo ""
    fi
}

# 将 camera_auto_detect 设为 0（保留一行有效配置）/ Force camera_auto_detect=0
ogscope_boot_config_set_camera_auto_detect_off() {
    local cfg="$1"
    if grep -qE '^[[:space:]]*#?[[:space:]]*camera_auto_detect=' "${cfg}" 2>/dev/null; then
        sudo sed -i \
            -e 's/^[[:space:]]*#camera_auto_detect=.*/camera_auto_detect=0/' \
            -e 's/^[[:space:]]*# camera_auto_detect=.*/camera_auto_detect=0/' \
            -e 's/^[[:space:]]*camera_auto_detect=.*/camera_auto_detect=0/' \
            "${cfg}"
    else
        printf '\n# OGScope: disable camera auto-detect for manual CSI overlay\ncamera_auto_detect=0\n' | sudo tee -a "${cfg}" >/dev/null
    fi
}

# 删除由本脚本管理的 OGScope 摄像头配置块 / Remove managed OGScope camera block
ogscope_boot_config_remove_ogscope_camera_block() {
    local cfg="$1"
    if grep -q "OGScope camera begin" "${cfg}" 2>/dev/null; then
        sudo sed -i '/# OGScope camera begin/,/# OGScope camera end/d' "${cfg}"
    fi
}

# 写入 IMX327 设备树块（幂等：先删旧块再追加）/ Write IMX327 dtoverlay block (idempotent)
ogscope_boot_config_apply_imx327() {
    local cfg="$1"
    ogscope_boot_config_remove_ogscope_camera_block "${cfg}"
    ogscope_boot_config_set_camera_auto_detect_off "${cfg}"
    if grep -qE '^[[:space:]]*dtoverlay=imx327([[:space:]]|$)' "${cfg}" 2>/dev/null; then
        echo "ℹ️  已存在 dtoverlay=imx327，仅保留 camera_auto_detect=0 / dtoverlay=imx327 already present; kept auto-detect off"
        return 0
    fi
    {
        echo ""
        echo "# OGScope camera begin"
        echo "# IMX327 Camera configuration"
        echo "dtoverlay=imx327"
        echo "# OGScope camera end"
    } | sudo tee -a "${cfg}" >/dev/null
}

# 应用 IMX327：存在 boot 配置则写入；否则仅提示 / Apply IMX327 if boot config exists
ogscope_apply_boot_camera_imx327() {
    local cfg
    cfg="$(ogscope_boot_config_path)"
    if [ -z "${cfg}" ]; then
        echo "ℹ️  未找到 /boot/firmware/config.txt 或 /boot/config.txt（可能非树莓派或仅本地开发机），已跳过摄像头 boot 配置 / No Pi boot config found; skipped camera boot changes"
        return 0
    fi
    echo "📷 写入 IMX327 设备树配置 / Writing IMX327 overlay: ${cfg}"
    ogscope_boot_config_apply_imx327 "${cfg}"
    echo "✅ 已更新 ${cfg}（camera_auto_detect=0；含 dtoverlay=imx327 或已存在）/ Boot config updated"
    echo "📋 相关行（请核对）/ Relevant lines:"
    grep -nE '^camera_auto_detect=|^# OGScope camera|^dtoverlay=imx327' "${cfg}" 2>/dev/null \
        || sudo grep -nE '^camera_auto_detect=|^# OGScope camera|^dtoverlay=imx327' "${cfg}" 2>/dev/null \
        || echo "  (grep 失败，请手动检查 / grep failed; check file manually)"
    echo "⚠️  CSI overlay 需重启后生效 / Reboot required for CSI overlay"
}

# 解析交互或非交互下的摄像头选择 / Resolve camera choice (imx327 | skip)
ogscope_resolve_camera_choice() {
    local choice="${OGSCOPE_CAMERA:-}"

    if [ "${OGSCOPE_SKIP_BOOT_CAMERA:-}" = "1" ]; then
        echo "skip"
        return 0
    fi

    if [ -n "${choice}" ]; then
        case "${choice}" in
        imx327 | IMX327)
            echo "imx327"
            ;;
        skip | none | off | "")
            echo "skip"
            ;;
        *)
            echo "⚠️ 未知 OGSCOPE_CAMERA=${choice}，按 skip 处理 / Unknown OGSCOPE_CAMERA; using skip" >&2
            echo "skip"
            ;;
        esac
        return 0
    fi

    if [ "${OGSCOPE_NONINTERACTIVE:-}" = "1" ]; then
        echo "skip"
        return 0
    fi

    if [ ! -t 0 ]; then
        echo "skip"
        return 0
    fi

    # 菜单必须写到 stderr：本函数返回值通过 stdout 供 $(...) 捕获；若用 echo 打菜单会吞掉且污染返回值。
    # Menus go to stderr; only the final choice ("imx327"|"skip") may go to stdout for command substitution.
    echo "" >&2
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >&2
    echo "📷 树莓派 CSI 摄像头：是否写入 /boot 下的 config.txt？" >&2
    echo "   Raspberry Pi CSI: edit boot config.txt (firmware path on Bookworm)?" >&2
    echo "" >&2
    echo "   与代码更新无关；仅写入 device tree 行以便内核加载 IMX327。" >&2
    echo "   Unrelated to app code; adds boot lines for IMX327 CSI overlay." >&2
    echo "" >&2
    echo "  1) 写入 IMX327：camera_auto_detect=0 + dtoverlay=imx327（需重启生效）" >&2
    echo "     Write IMX327; reboot to apply CSI overlay." >&2
    echo "  2) 不修改 config.txt（已手配 / 暂不折腾摄像头）" >&2
    echo "     Do not change config.txt." >&2
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >&2
    read -r -p "请输入 1 或 2（默认 1）/ Enter 1 or 2 [default 1]: " _cam_in </dev/tty
    case "${_cam_in:-1}" in
    2)
        echo "skip"
        ;;
    *)
        echo "imx327"
        ;;
    esac
}

# 安装/升级入口：询问（若可）并应用 / Entry: prompt and apply for install & upgrade
ogscope_prompt_camera_model_and_apply() {
    local resolved
    resolved="$(ogscope_resolve_camera_choice)"

    case "${resolved}" in
    imx327)
        ogscope_apply_boot_camera_imx327
        ;;
    skip)
        if [ "${OGSCOPE_SKIP_BOOT_CAMERA:-}" = "1" ]; then
            echo "⏭️  OGSCOPE_SKIP_BOOT_CAMERA=1，未修改 boot 配置 / Skipped per env"
        elif [ -n "${OGSCOPE_CAMERA:-}" ]; then
            echo "⏭️  OGSCOPE_CAMERA=${OGSCOPE_CAMERA}，未修改 boot 配置 / Skipped per OGSCOPE_CAMERA"
        elif [ "${OGSCOPE_NONINTERACTIVE:-}" = "1" ]; then
            :
        else
            echo "⏭️  已跳过 boot 摄像头配置 / Skipped boot camera configuration"
        fi
        ;;
    esac
}

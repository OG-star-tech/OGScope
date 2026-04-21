# OGScope 树莓派 /boot I²C（硬件 i2c_arm）配置 / Raspberry Pi boot: enable ARM I2C for /dev/i2c-1 (GPIO2/3)
# 由 install.sh、board-update.sh 用 `source` 加载 / Sourced by install.sh and board-update.sh
#
# 环境变量 / Environment:
#   OGSCOPE_SKIP_BOOT_I2C=1 — 不写入 config.txt 中的 dtparam=i2c_arm=on / Do not modify boot config for I2C

# 返回可写的 config.txt 路径（与 boot-config-camera.sh 一致）/ Same resolution as camera boot helper
ogscope_boot_config_path_i2c() {
    if [ -f /boot/firmware/config.txt ]; then
        echo "/boot/firmware/config.txt"
    elif [ -f /boot/config.txt ]; then
        echo "/boot/config.txt"
    else
        echo ""
    fi
}

# 是否已有「生效的」i2c_arm=on（非注释行）/ Whether an active dtparam enables i2c_arm
ogscope_boot_config_i2c_arm_already_on() {
    local cfg="$1"
    sudo grep -qE '^[[:space:]]*dtparam=i2c_arm=on([[:space:],]|$)' "${cfg}" 2>/dev/null
}

# 幂等：确保存在 dtparam=i2c_arm=on / Idempotent: ensure dtparam=i2c_arm=on
# 成功写入新行时设置 OGSCOPE_I2C_BOOT_CHANGED=1（供调用方提示重启）/ Sets OGSCOPE_I2C_BOOT_CHANGED=1 when file was modified
ogscope_boot_config_ensure_i2c_arm_on() {
    OGSCOPE_I2C_BOOT_CHANGED=0
    local cfg
    cfg="$(ogscope_boot_config_path_i2c)"
    if [ -z "${cfg}" ]; then
        echo "ℹ️  未找到 /boot/firmware/config.txt 或 /boot/config.txt，跳过 I²C 固件项 / No Pi boot config; skipped I2C dtparam"
        return 0
    fi
    if ! sudo test -r "${cfg}"; then
        echo "⚠️  无法读取 ${cfg}，跳过 I²C 固件配置 / Cannot read boot config; skipped"
        return 0
    fi

    if ogscope_boot_config_i2c_arm_already_on "${cfg}"; then
        echo "ℹ️  已启用 dtparam=i2c_arm=on / dtparam=i2c_arm=on already present"
        return 0
    fi

    echo "⚙️  写入 I²C 固件项（dtparam=i2c_arm=on）/ Writing I2C boot option: ${cfg}"
    sudo cp -a "${cfg}" "${cfg}.bak.ogscope-i2c.$(date +%s)"
    {
        echo ""
        echo "# OGScope: ARM I2C (GPIO2/3 -> /dev/i2c-1) for AK09911 / MPU-6050 debug"
        echo "dtparam=i2c_arm=on"
    } | sudo tee -a "${cfg}" >/dev/null
    sudo chown root:root "${cfg}" 2>/dev/null || true
    sudo chmod 644 "${cfg}" 2>/dev/null || true
    OGSCOPE_I2C_BOOT_CHANGED=1
    echo "✅ 已追加 dtparam=i2c_arm=on / Appended dtparam=i2c_arm=on"
}

# 将运行用户加入 i2c 组（便于访问 /dev/i2c-*）/ Add current user to i2c group
# 若本次执行了 usermod，设置 OGSCOPE_I2C_GROUP_ADDED=1（供 install 提示重新登录）/ Set flag when usermod ran
ogscope_i2c_add_user_to_group() {
    OGSCOPE_I2C_GROUP_ADDED=0
    if ! getent group i2c >/dev/null 2>&1; then
        echo "⚠️  系统无 i2c 组，跳过 usermod / No i2c group; skipped usermod"
        return 0
    fi
    if id -nG "${USER}" 2>/dev/null | tr ' ' '\n' | grep -qx i2c; then
        echo "ℹ️  用户已在 i2c 组 / User already in group i2c"
        return 0
    fi
    sudo usermod -aG i2c "${USER}"
    OGSCOPE_I2C_GROUP_ADDED=1
    echo "✅ 已将 ${USER} 加入 i2c 组 / Added ${USER} to group i2c"
}

# 安装 i2c-tools（i2cdetect 等）；幂等 / Install i2c-tools; idempotent
ogscope_i2c_apt_install_tools() {
    echo "📦 安装 i2c-tools（i2cdetect）/ Installing i2c-tools..."
    sudo apt install -y i2c-tools
}

# 组合：工具包、用户组、boot 配置（install.sh 在已 apt install i2c-tools 后可只调后两项）/
# Full host setup: tools, group, boot (skip tools if already done in same apt batch)
ogscope_i2c_host_setup_full() {
    local install_tools="${1:-1}"
    OGSCOPE_I2C_BOOT_CHANGED=0
    if [ "${install_tools}" = "1" ]; then
        ogscope_i2c_apt_install_tools
    fi
    ogscope_i2c_add_user_to_group
    if [ "${OGSCOPE_SKIP_BOOT_I2C:-}" = "1" ]; then
        echo "⏭️  跳过写入 I²C boot 配置（OGSCOPE_SKIP_BOOT_I2C=1）/ Skipping boot I2C config"
        return 0
    fi
    ogscope_boot_config_ensure_i2c_arm_on
}

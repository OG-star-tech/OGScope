# WiFi：STA / AP 与 NetworkManager

本文档为 **Raspberry Pi OS** 上 OGScope **网络能力的唯一详解**：热点/STA 密码与访问、`network.env`、sudoers、`/debug/system`、Web API，以及 **开机网络引导**（`ogscope-network-boot`）与 **运行时 STA 回滚**（`wifi_sta_rollback_*`）的分工。开发板 **Poetry、`install.sh` / `board-update.sh` 总流程**见 [开发指南（部署速查）](README.md) **§0.2**、**§0.5**；以下按「用户说明 → 初始化 → 环境变量 → sudoers → API → 验证」展开。

## 用户操作说明（密码、访问与安全）

以下为 **终端用户 / 现场操作** 常用信息；技术细节见后文各节。

### 默认热点（AP 模式）

| 项目 | 说明 |
|------|------|
| **SSID** | `OGScope_xxxx`，其中 `xxxx` 为 **wlan0 MAC 地址后 4 位**（十六进制，小写），每台设备不同。可在设备标签或执行 `init` 后的日志 / `diag` 中确认。 |
| **密码（PSK）** | 固定为 **`ogscopeadmin`**（由 [`ogscope-network-init.sh`](../../scripts/ogscope-network-init.sh) 写入 NetworkManager，**非随机**）。 |
| **网关 / 固定地址** | 热点模式下无线侧一般为 **`192.168.4.1/24`**（与 NM 中 `OGScope-AP` 配置一致）。 |
| **Web 访问** | 手机/电脑连上该热点后，浏览器打开 **`http://192.168.4.1:<端口>`**；HTTP 端口以设备上 OGScope 配置为准（常见为 **8000**，见应用或 `ogscope` 服务环境变量）。 |
| **mDNS 主机名** | 初始化后主机名形如 **`ogscope-xxxx`**（`xxxx` 与 SSID 后缀一致），局域网内可尝试 **`http://ogscope-xxxx.local:<端口>/debug/system`**（需 **Avahi** 与 DNS 解析正常）。 |

### 连接家中路由器（STA 模式）

1. 连上 OGScope 热点后打开 **`/debug/system`**（系统调试页）。
2. 使用 **「扫描 WiFi」**（由设备执行 `nmcli`，列表可能为空，见下）或 **「手动输入 SSID + 密码」**。
3. 提交后设备会切到 STA 并尝试连接；若超时未拿到局域网 IPv4，会按配置 **自动切回 AP**，避免彻底失联。

**说明**：浏览器 **不能** 读取你手机里的 WiFi 列表；列表必须由 **树莓派上的 NetworkManager** 生成，或你 **手动输入** 家中 SSID/密码。

### 已保存的 WiFi 列表与「激活」

- **作用**：列出 NetworkManager 里 **已保存的 WiFi 连接**（不含热点 `OGScope-AP`）。**「激活」** 表示对该 profile 执行 `nmcli connection up`，在 **不切热点脚本路径** 的情况下直接连上该 SSID（适合以前连过、密码已保存在系统中的网络）。
- **与「手动连接 / 扫描后连接」的区别**：后者会改 **`OGScope-STA`** 的 SSID/密码再切 STA；「激活」用于 **其他已命名连接**（若存在）。
- **报错 `Not authorized to control networking`**：服务用户（如 `ogstartech`）默认受 **polkit** 限制，不能直接 `nmcli connection up`。初始化脚本会写入 **`/etc/sudoers.d/ogscope-nmcli`**，允许该用户 **免密执行 `nmcli` 二进制**；应用内对 `nmcli` 使用 **`sudo -n`**（见 `OGSCOPE_WIFI_NMCLI_USE_SUDO`，默认开启）。若仍报错，请执行  
  `sudo ./scripts/ogscope-network-init.sh ensure-systemd`（会补写 `ogscope-nmcli` sudoers）或对照后文 **§3** 手动添加，然后 **`sudo systemctl restart ogscope`**。

### 注意事项（必读）

1. **默认热点密码是公开的**（`ogscopeadmin`），仅适合现场调试与封闭环境。若长期暴露热点，请在 NetworkManager 中 **修改 `OGScope-AP` 的 PSK**，并自行记录；修改后需与现场人员同步。
2. **单频网卡在 AP 模式下**，往往 **无法同时列出周边 WiFi**（扫描结果可能为 0）；此时请 **直接手动输入** 家中 SSID 与密码。
3. **从 STA 切回 AP** 或 **换网** 后，当前浏览器会话可能断开；请重新连接热点 `OGScope_xxxx` 或在本机局域网用 **mDNS / 路由器管理页** 查找设备 IP。
4. **HTTPS 页面无法混合访问 HTTP API**：若用纯 HTTPS 入口访问，设备上的 **`/health` 局域网探测** 可能受限；优先使用 **HTTP** 同网段访问调试页（见页面提示）。
5. 更新代码后若 WiFi 相关异常，需同步 **`ogscope-wifi-switch` 脚本** 到 `/usr/local/bin` 并 **重启 `ogscope` 服务**（见后文「验证 nmcli」与 `board-update.sh`）。

### 安全与隐私（简要）

- **`/etc/ogscope/network.env`** 含连接名与设备后缀，权限为 **600**，勿提交版本库。
- **sudoers**：仅允许指定用户免密运行 **`/usr/local/bin/ogscope-wifi-switch`** 与 **`nmcli` 绝对路径**（`/etc/sudoers.d/ogscope-wifi`、`ogscope-nmcli`）；勿改为无限制 `NOPASSWD: ALL`。
- 现场请勿在不可信网络中开启长期 AP；生产环境请结合路由器 ACL、强密码与固件更新策略。

---

## 1. 推荐：一键初始化（`ogscope-network-init.sh`）

完整 **`install.sh` 行为与可选环境变量**摘要见 [开发指南 §0.2](README.md#02-首次安装)。

安装脚本 [scripts/install.sh](../../scripts/install.sh) 会在部署阶段安装 `network-manager`、`avahi-daemon`，并执行：

```bash
sudo env OGSCOPE_SERVICE_USER="$USER" ./scripts/ogscope-network-init.sh init --yes
```

- 根据 **wlan0 MAC 后 4 位十六进制** 生成热点 SSID：`OGScope_xxxx`，密码固定 **`ogscopeadmin`**。
- 创建 NM 连接 **`OGScope-STA`**（占位，供 Web 填写 SSID/密码）与 **`OGScope-AP`**（网关 `192.168.4.1/24`）。
- 写入 **`/etc/ogscope/network.env`**（供 systemd `EnvironmentFile` 加载）。
- 安装 **`/usr/local/bin/ogscope-wifi-switch`** 并配置 **sudoers**（免密执行该脚本；另写入 **`ogscope-nmcli`**，供 Web API 调用 **`nmcli`**，避免 polkit 拒绝）。
- 设置主机名为 **`ogscope-xxxx`**，并同步 **`/etc/hosts`** 中 `127.0.1.1`（减轻 `sudo: unable to resolve host`）。
- 写入 **systemd drop-in**：`/etc/systemd/system/ogscope.service.d/ogscope-network-env.conf`，使 **`ogscope` 服务加载 `/etc/ogscope/network.env`**（与新版 [`install.sh`](../../scripts/install.sh) 主 unit 中的 `EnvironmentFile=-/etc/ogscope/network.env` 一致；**仅跑过旧版 install、未含该行的部署**此前会在 Web/API 中看到 `wifi_not_configured`）。
- 便于 **`http://ogscope-xxxx.local:端口`** 访问（需 Avahi）。
- **[`install.sh`](../../scripts/install.sh)** 还会安装 **`ogscope-network-boot.service`**（**root**、`Type=oneshot`、`Before=ogscope.service`），执行 [`scripts/ogscope-network-boot.sh`](../../scripts/ogscope-network-boot.sh)：开机后若 **默认 IPv4 路由已在非无线口**（例如有线已联网）则**跳过**；否则在 **`OGSCOPE_BOOT_STA_WAIT_SEC`**（默认 55）秒内轮询 **`wlan0` 是否获得非 169.254 的 IPv4**（与 Python 侧 `sta_interface_has_usable_ipv4` 语义一致）；仍无则尝试 **`nmcli connection up` STA**（次数由 **`OGSCOPE_BOOT_STA_UP_RETRIES`** 等控制），最后仍失败则 **拉起 AP**，避免冷启动无网。跳过该单元：`OGSCOPE_SKIP_NETWORK_BOOT=1 ./scripts/install.sh`。日志：`journalctl -u ogscope-network-boot -b`。
- **与进程内 STA 回滚的区别**：**开机引导**不依赖 `ogscope` 进程；应用内 **`wifi_sta_rollback_*`** 仅在用户通过 Web/API **切 STA 成功后** 监视超时并回滚 AP。

跳过初始化：`OGSCOPE_SKIP_NETWORK_INIT=1 ./scripts/install.sh`

诊断与重置：

```bash
sudo ./scripts/ogscope-network-init.sh diag
sudo ./scripts/ogscope-network-init.sh ensure-systemd   # 补 systemd drop-in + /etc/hosts 127.0.1.1（需已有 network.env）
sudo ./scripts/ensure-ogscope-systemd-network-env.sh      # 同上，薄封装
sudo ./scripts/ogscope-network-init.sh reset   # 交互确认
sudo ./scripts/ogscope-network-init.sh reset --yes
```

### 已部署过旧代码、只缺 WiFi 或只缺 systemd 加载 env

1. 同步代码后若 **`/etc/ogscope/network.env` 已存在**，但控制台仍显示 **`wifi_not_configured`**：先执行  
   `sudo ./scripts/ogscope-network-init.sh ensure-systemd`，再 **`sudo systemctl restart ogscope`**。  
   （`diag` 会检查 `systemctl cat ogscope` 是否包含对 `network.env` 的 `EnvironmentFile`。）
2. 若从未生成 `network.env`，仍用 **`init`** 完整初始化。
3. **`/etc/hosts` 未随主机名更新** 时，`sudo` 可能出现 `unable to resolve host`；重新 **`init`** 会写入 `127.0.1.1 ogscope-xxxx`，或手动编辑 `/etc/hosts`。

## 2. 环境变量（`/etc/ogscope/network.env` 或 `.env`）

与 [ogscope/config.py](../../ogscope/config.py) 中 `OGSCOPE_` 前缀一致：

| 变量 | 含义 |
|------|------|
| `OGSCOPE_WIFI_STA_CONNECTION` | STA 连接名（默认 `OGScope-STA`） |
| `OGSCOPE_WIFI_AP_CONNECTION` | AP 连接名（默认 `OGScope-AP`） |
| `OGSCOPE_WIFI_INTERFACE` | 无线接口，默认 `wlan0` |
| `OGSCOPE_DEVICE_ID_SUFFIX` | 4 位 hex 后缀（与热点 SSID 一致） |
| `OGSCOPE_WIFI_AP_SSID` | 热点 SSID 全文（如 `OGScope_a1b2`） |
| `OGSCOPE_WIFI_NMCLI_USE_SUDO` | 默认 `true`：非 root 进程用 `sudo -n nmcli`；需 **`ogscope-nmcli` sudoers** |

## 3. 手动安装切换脚本与 sudoers

```bash
sudo install -m 755 scripts/ogscope-wifi-switch.sh /usr/local/bin/ogscope-wifi-switch
sudo visudo -f /etc/sudoers.d/ogscope-wifi
# Web 扫描 / 激活已保存 WiFi 需 nmcli 免密（路径以 which 为准）：
# sudo visudo -f /etc/sudoers.d/ogscope-nmcli
```

示例：

```
ogstartech ALL=(ALL) NOPASSWD: /usr/local/bin/ogscope-wifi-switch
```

`nmcli`（与 `init` 脚本自动生成的一致，`which nmcli` 多为 `/usr/bin/nmcli`）：

```
ogstartech ALL=(ALL) NOPASSWD: /usr/bin/nmcli
```

## 4. Web API 与 STA 回滚

- `GET /api/network/wifi/scan`：由设备执行 `nmcli` 扫描（**浏览器无法在客户端扫周围 WiFi**，无 Web API）。响应中 `networks` 为列表，**`hint` 可为空**；若当前为热点(AP)模式且列表为空，会给出说明（单频网卡常无法同时列出周边 BSS）。
- `POST /api/network/wifi/sta/connect`：填写 SSID/密码后切 STA；若 **`wifi_sta_rollback_timeout_seconds`** 内未获得可用 IPv4，则**自动切回 AP**，防止失联。
- `GET /api/network/wifi/profiles`：已保存的 WiFi 连接（NetworkManager 持久化）。
- `POST /api/network/wifi/profile/activate`：**激活**某条已保存连接（`nmcli connection up`）；需 **`ogscope-nmcli` sudoers** 或等价 polkit 授权，否则会报 **Not authorized**。
- 系统调试页：`/debug/system`（引导、mDNS 提示、局域网 `/health` 探测）。
- 环境变量 **`OGSCOPE_WIFI_NMCLI_USE_SUDO`**（默认 `true`）：为 `false` 时直接调用 `nmcli`（仅当运行用户已被 polkit 允许控制 NM 时使用）。

## 5. 验证 nmcli

```bash
sudo /usr/local/bin/ogscope-wifi-switch status
sudo /usr/local/bin/ogscope-wifi-switch ap
sudo /usr/local/bin/ogscope-wifi-switch sta
```

脚本在 **未继承环境变量** 时会自动 `source /etc/ogscope/network.env`（与 systemd 一致）。若仍用旧习惯 `sudo -E`，部分系统 sudoers 会报 **user not allowed to preserve the environment**，可省略 `-E`。

# WiFi：STA / AP 与 NetworkManager

中文说明如何在 **Raspberry Pi OS**（已启用 **NetworkManager**）上为 OGScope 准备两个互斥连接，并与 `scripts/ogscope-wifi-switch.sh` 配合使用。

## 1. 环境变量

在 `ogscope.service` 的 `Environment=` 或 `.env` 中设置（与 [ogscope/config.py](../../ogscope/config.py) 中 `OGSCOPE_` 前缀一致）：

| 变量 | 含义 |
|------|------|
| `OGSCOPE_WIFI_STA_CONNECTION` | 连家中路由器的连接名（DHCP） |
| `OGSCOPE_WIFI_AP_CONNECTION` | 热点连接名（建议网关 `192.168.4.1/24`） |
| `OGSCOPE_WIFI_INTERFACE` | 可选，默认 `wlan0` |

## 2. 安装脚本与 sudoers

```bash
sudo install -m 755 scripts/ogscope-wifi-switch.sh /usr/local/bin/ogscope-wifi-switch
sudo visudo -f /etc/sudoers.d/ogscope-wifi
```

`ogscope-wifi` 示例（将用户名与路径改为实际值）：

```
ogstartech ALL=(ALL) NOPASSWD: /usr/local/bin/ogscope-wifi-switch
```

## 3. 首次创建连接（示例）

名称需与 `OGSCOPE_WIFI_*_CONNECTION` 一致。具体选项以你现场 `nmcli` 版本为准。

- **STA**：可用 `nmcli device wifi connect <SSID> password <PWD>` 生成连接后，用 `nmcli connection modify "<name>" connection.id <OGSCOPE_WIFI_STA_CONNECTION>` 统一命名。
- **AP**：可用 `nmcli device wifi hotspot` 创建热点，再 `nmcli connection modify "<AP名称>" ipv4.addresses 192.168.4.1/24 ipv4.method manual`（或按发行版文档使用 `shared`）；并设置 `wifi-sec`、国家码等。

AP 与 STA 为两个独立 **connection**；切换时脚本对一方 `down`、另一方 `up`，STA 模式不会保留 AP 的静态地址。

## 4. 验证

```bash
sudo -E /usr/local/bin/ogscope-wifi-switch status
sudo -E /usr/local/bin/ogscope-wifi-switch ap
sudo -E /usr/local/bin/ogscope-wifi-switch sta
```

`-E` 保留当前 shell 中的 `OGSCOPE_*` 环境变量。

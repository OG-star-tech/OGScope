# OGScope 快速开始指南

中文 | [English](QUICK_START_EN.md)

本指南用于在 Raspberry Pi Zero 2W 上完成首次安装和基础验证。完整安装参数、WiFi、低内存优化与日常升级见[开发指南](development/README.md)。

## 1. 准备

### 硬件

- Raspberry Pi Zero 2W
- IMX327 MIPI 相机
- 32 GB 或更大的 MicroSD 卡
- 5 V / 2 A 或更高规格的稳定电源

### 软件

- Raspberry Pi OS Lite 64-bit（Debian/apt 系）
- Python 3.10+
- Git
- 首次安装时可访问 apt、PyPI 和 GitHub

建议在 Raspberry Pi Imager 中预先设置主机名、SSH、公钥或初始用户。不要依赖历史默认用户名或默认密码。

## 2. 连接开发板

```bash
ssh <user>@raspberrypi.local
# mDNS 不可用时改用路由器分配的 IP
ssh <user>@<board-ip>
```

推荐配置 SSH 公钥：

```bash
ssh-copy-id <user>@<board-ip>
ssh -o BatchMode=yes <user>@<board-ip> true
```

## 3. 克隆并安装

```bash
git clone https://github.com/OG-star-tech/OGScope.git
cd OGScope
chmod +x scripts/bootstrap.sh
./scripts/bootstrap.sh
```

`bootstrap.sh` 会把运行代码部署到默认目录 `/opt/ogscope`，然后调用安装流程创建项目虚拟环境、补齐系统依赖并注册 `ogscope.service`。

国内网络可显式选择镜像：

```bash
export OGSCOPE_MIRROR=cn
./scripts/bootstrap.sh
```

只需要最小运行环境时：

```bash
OGSCOPE_BOOTSTRAP_MODE=min ./scripts/bootstrap.sh
```

如果代码已经位于目标运行目录，也可以直接执行：

```bash
./scripts/install.sh
```

## 4. 验证

```bash
sudo systemctl status ogscope --no-pager
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/api/core/v1/system/status
```

浏览器访问：

- 首页：`http://<board-ip>:8000/`
- 调试控制台：`http://<board-ip>:8000/debug`
- API 文档：`http://<board-ip>:8000/docs`

相机检查：

```bash
rpicam-hello --list-cameras 2>/dev/null || libcamera-hello --list-cameras
curl -fsS http://127.0.0.1:8000/api/core/v1/camera/status
```

`POST /api/core/v1/camera/start` 只有在相机确认 `connected=true` 且 `streaming=true` 时才返回成功。

## 5. 日常更新

```bash
cd /opt/ogscope
./scripts/board-update.sh
```

需要开发依赖时：

```bash
OGSCOPE_INSTALL_DEV=1 ./scripts/board-update.sh
```

## 6. 本地开发

```bash
poetry install
poetry run pytest -q

cd web/spa
npm ci
npm run build
```

涉及相机、GPIO、I2C 或 systemd 的修改必须在真实开发板上复验。开发板同步流程见[开发指南](development/README.md)和 `scripts/sync_dev_board.sh`。

## 7. 常见问题

### 服务启动失败

```bash
sudo journalctl -u ogscope -b --no-pager -n 200
sudo systemctl cat ogscope
```

### 相机不可用

```bash
rpicam-hello --list-cameras 2>/dev/null || libcamera-hello --list-cameras
sudo journalctl -u ogscope -b --no-pager | grep -i -E 'camera|libcamera|imx327'
```

确认相机 overlay、排线方向和 `/boot/firmware/config.txt` 后再重启。

### 网络或热点问题

以 [WiFi / NetworkManager 指南](development/wifi-nm.md)为准，不要同时使用多套网络初始化脚本。

## 8. 后续文档

- [文档索引](README.md) | [English](README_EN.md)
- [开发指南](development/README.md) | [English](development/README_EN.md)
- [Core REST v1 契约](contracts/core-rest-v1.md) | [English](contracts/core-rest-v1_EN.md)
- [调试控制台](DEBUG_CONSOLE.md) | [English](DEBUG_CONSOLE_EN.md)
- [问题反馈](https://github.com/OG-star-tech/OGScope/issues)

# OGScope 快速开始指南

本指南将帮助你快速搭建 OGScope 开发环境。

English | [中文](QUICK_START.md)

## 🎯 目标

- ✅ 在 Orange Pi Zero 2W 上运行 OGScope
- ✅ 配置 PyCharm Professional 远程开发
- ✅ 通过 Web 界面访问系统

## 📋 准备工作

### 硬件要求

- Raspberry Pi Zero 2W
- IMX327 相机模块
- MicroSD 卡 (32GB+)
- 5V 3A 电源适配器
- （可选）2.4寸 SPI LCD 屏幕

### 软件要求

#### 开发机 (Mac)
- macOS
- PyCharm Professional 2021.1.3 或更高版本
- Git

#### Raspberry Pi
- Raspberry Pi OS（官方镜像）
- Python 3.9+
- 网络连接（WiFi 或有线）

## 🚀 第一步：Raspberry Pi 系统配置

### 1.1 烧录系统

```bash
# 1. 下载 Raspberry Pi Imager 工具
# 访问: https://www.raspberrypi.org/downloads/

# 2. 使用 Raspberry Pi Imager 烧录 Raspberry Pi OS Lite
# 或使用 dd 命令烧录到 SD 卡
# macOS/Linux:
sudo dd if=2024-01-15-raspios-bookworm-armhf-lite.img of=/dev/diskX bs=4m status=progress
```

### 1.2 首次启动

```bash
# 1. 插入 SD 卡并启动 Raspberry Pi
# 2. 默认用户名: pi
# 3. 默认密码: raspberry

# 首次登录后，建议修改密码
passwd
```

### 1.3 配置网络

```bash
# 方法 1: WiFi 连接
sudo nmcli dev wifi connect "WiFi名称" password "密码"

# 方法 2: 配置静态 IP（可选）
sudo nano /etc/network/interfaces

# 查看 IP 地址
ip addr show wlan0  # WiFi
ip addr show eth0   # 有线
```

### 1.4 SSH 访问

```bash
# 在 Mac 上测试 SSH 连接
ssh pi@raspberrypi.local
# 或使用 IP 地址
ssh pi@192.168.1.xxx
```

## 🔧 第二步：安装 OGScope

### 2.1 自动安装（推荐）

```bash
# 在 Raspberry Pi 上执行
cd ~
git clone https://github.com/your-username/OGScope.git
cd OGScope
chmod +x scripts/install.sh
./scripts/install.sh
```

安装脚本会自动：
- 安装系统依赖
- 安装 Poetry
- 创建 Python 虚拟环境
- 安装项目依赖
- 配置 systemd 服务

### 2.2 手动安装

如果自动安装失败，可以手动执行：

```bash
# 1. 更新系统
sudo apt update && sudo apt upgrade -y

# 2. 安装系统依赖
sudo apt install -y python3.9 python3-pip python3-venv git \
    build-essential libopencv-dev libjpeg-dev libpng-dev \
    libspidev-dev v4l-utils

# 3. 安装 Poetry
curl -sSL https://install.python-poetry.org | python3 -
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# 4. 克隆项目（如果还没有）
cd ~
git clone https://github.com/your-username/OGScope.git
cd OGScope

# 5. 安装 Python 依赖
poetry install

# 6. 运行测试
poetry run python -m ogscope.main
```

## 💻 第三步：配置 PyCharm 远程开发

### 3.1 配置 SSH 免密登录

在 **Mac** 上执行：

```bash
# 生成 SSH 密钥（如果还没有）
ssh-keygen -t ed25519 -C "ogscope-dev"

# 复制公钥到 Orange Pi
ssh-copy-id orangepi@orangepi.local

# 配置 SSH config
cat >> ~/.ssh/config << 'EOF'
Host orangepi
    HostName orangepi.local
    User orangepi
    Port 22
    ForwardAgent yes
    ServerAliveInterval 60
EOF

# 测试连接
ssh orangepi
```

### 3.2 PyCharm 配置

详细步骤见 [PyCharm 远程开发配置](./development/pycharm-remote.md)

**快速版本**：

1. **添加远程解释器**
   - `File` → `Settings` → `Project` → `Python Interpreter`
   - 点击 ⚙️ → `Add...` → `SSH Interpreter`
   - Host: `orangepi.local`, User: `orangepi`
   - Interpreter: `/home/orangepi/.local/bin/poetry`

2. **配置自动部署**
   - `Tools` → `Deployment` → `Configuration`
   - 添加 SFTP 服务器
   - 设置路径映射

3. **启用自动上传**
   - `Tools` → `Deployment` → `Automatic Upload` ✅

## 🌐 第四步：访问 Web 界面

### 4.1 启动服务

```bash
# 方法 1: 手动启动（开发模式）
cd ~/OGScope
poetry run python -m ogscope.main

# 方法 2: 使用 systemd（生产模式）
sudo systemctl start ogscope
sudo systemctl status ogscope
```

### 4.2 访问界面

在浏览器中打开：
```
http://orangepi.local:8000
# 或使用 IP 地址
http://192.168.1.xxx:8000
```

### 4.3 API 文档

FastAPI 自动生成的文档：
```
http://orangepi.local:8000/docs     # Swagger UI
http://orangepi.local:8000/redoc    # ReDoc
```

## 🔍 验证安装

### 检查清单

- [ ] Orange Pi 可以正常启动
- [ ] SSH 可以连接
- [ ] Poetry 已安装
- [ ] OGScope 依赖已安装
- [ ] Web 服务可以启动
- [ ] 浏览器可以访问界面
- [ ] PyCharm 可以远程连接

### 运行测试

```bash
# 在 Orange Pi 上
cd ~/OGScope
poetry run pytest tests/unit/
```

## 🐛 故障排除

### 问题 1: 找不到 Orange Pi

```bash
# 方法 1: 使用 IP 地址
ip addr show wlan0

# 方法 2: 路由器管理界面查看
# 方法 3: 使用 nmap 扫描
nmap -sn 192.168.1.0/24
```

### 问题 2: Poetry 安装失败

```bash
# 使用 pip 安装（备选）
pip3 install poetry
```

### 问题 3: Web 服务无法启动

```bash
# 查看日志
journalctl -u ogscope -f

# 检查端口占用
sudo netstat -tunlp | grep 8000

# 手动启动查看错误
cd ~/OGScope
poetry run python -m ogscope.main
```

### 问题 4: PyCharm 无法连接

```bash
# 检查 SSH 服务
sudo systemctl status ssh

# 检查防火墙
sudo ufw status

# 测试 SSH 连接
ssh -v orangepi@orangepi.local
```

## 📚 下一步

- 阅读 [用户手册](./user_guide/user-manual.md)
- 查看 [开发文档](./development/README.md)
- 开始 [硬件组装](./hardware/assembly-guide.md)

## 🆘 获取帮助

- [GitHub Issues](https://github.com/your-username/OGScope/issues)
- [GitHub Discussions](https://github.com/your-username/OGScope/discussions)
- [查看文档](./README.md)

---

祝你使用愉快！🎉


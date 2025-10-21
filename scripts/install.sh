#!/bin/bash
# OGScope 安装脚本
# 适用于 Raspberry Pi Zero 2W (Raspberry Pi OS)

set -e  # 遇到错误立即退出

echo "======================================"
echo "  OGScope 安装脚本"
echo "======================================"

# 检查是否为 root
if [ "$EUID" -eq 0 ]; then 
    echo "❌ 请不要使用 root 用户运行此脚本"
    exit 1
fi

# 更新系统
echo "📦 更新系统包..."
sudo apt update
sudo apt upgrade -y

# 安装系统依赖
echo "📦 安装系统依赖..."
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    git \
    build-essential \
    libopencv-dev \
    libjpeg-dev \
    libpng-dev \
    libfreetype6-dev \
    libatlas-base-dev \
    libspidev-dev \
    python3-picamera2 \
    python3-numpy

# 安装 Poetry
if ! command -v poetry &> /dev/null; then
    echo "📦 安装 Poetry..."
    curl -sSL https://install.python-poetry.org | python3 -
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    export PATH="$HOME/.local/bin:$PATH"
else
    echo "✅ Poetry 已安装"
fi

# 验证 Poetry 安装
poetry --version || {
    echo "❌ Poetry 安装失败"
    exit 1
}

# 启用树莓派相机接口
echo "📷 启用树莓派相机接口..."
sudo raspi-config nonint do_camera 0

# 创建项目目录
INSTALL_DIR="$HOME/OGScope"
if [ ! -d "$INSTALL_DIR" ]; then
    echo "📁 创建项目目录: $INSTALL_DIR"
    mkdir -p "$INSTALL_DIR"
else
    echo "✅ 项目目录已存在: $INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# 克隆或更新代码（如果是从 GitHub 安装）
if [ -d ".git" ]; then
    echo "🔄 更新代码..."
    git pull
else
    echo "⚠️  请手动克隆代码或复制文件到 $INSTALL_DIR"
fi

# 安装 Python 依赖
echo "📦 安装 Python 依赖..."
poetry install --no-interaction --no-root

# 创建必要的目录
echo "📁 创建数据目录..."
mkdir -p logs data uploads

# 创建配置文件
if [ ! -f "config.json" ]; then
    echo "⚙️  创建配置文件..."
    cp default_config.json config.json
    echo "⚠️  请编辑 config.json 修改配置"
fi

# 配置 systemd 服务
echo "⚙️  配置系统服务..."
sudo tee /etc/systemd/system/ogscope.service > /dev/null <<EOF
[Unit]
Description=OGScope Electronic Polar Scope
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$HOME/.local/bin/poetry run python -m ogscope.main
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 重新加载 systemd
sudo systemctl daemon-reload

# 启用服务
echo "🚀 启用 OGScope 服务..."
sudo systemctl enable ogscope.service

echo ""
echo "======================================"
echo "  ✅ 安装完成！"
echo "======================================"
echo ""
echo "下一步："
echo "1. 编辑配置: nano $INSTALL_DIR/config.json"
echo "2. 启动服务: sudo systemctl start ogscope"
echo "3. 查看状态: sudo systemctl status ogscope"
echo "4. 查看日志: journalctl -u ogscope -f"
echo "5. 访问 Web: http://$(hostname -I | awk '{print $1}'):8000"
echo ""


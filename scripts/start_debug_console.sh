#!/bin/bash
# OGScope 调试控制台启动脚本

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查是否在项目根目录
if [ ! -f "pyproject.toml" ]; then
    print_error "请在项目根目录运行此脚本"
    exit 1
fi

print_info "启动 OGScope 调试控制台..."

# 检查Poetry是否安装
if ! command -v poetry &> /dev/null; then
    print_error "Poetry 未安装，请先安装 Poetry"
    print_info "安装命令: curl -sSL https://install.python-poetry.org | python3 -"
    exit 1
fi

# 检查依赖是否安装
print_info "检查依赖..."
if ! poetry check &> /dev/null; then
    print_warning "依赖未完全安装，正在安装..."
    poetry install
fi

# 创建必要的目录
print_info "创建必要的目录..."
mkdir -p ~/dev_captures
mkdir -p logs

# 检查相机权限
print_info "检查相机权限..."
if [ ! -w /dev/video0 ] && [ ! -w /dev/video1 ]; then
    print_warning "相机设备权限可能不足，请确保用户有相机访问权限"
fi

# 启动服务
print_info "启动 Web 服务..."
print_success "调试控制台将在以下地址启动:"
print_success "  主界面: http://localhost:8000/"
print_success "  调试控制台: http://localhost:8000/debug"
print_success "  API文档: http://localhost:8000/docs"
echo ""

# 树莓派相机依赖环境变量（使用系统 picamera2 与 libcamera）
export PYTHONPATH="/usr/lib/python3/dist-packages:/usr/local/lib/python3.13/dist-packages:${PYTHONPATH}"
export LD_LIBRARY_PATH="/usr/lib/aarch64-linux-gnu:${LD_LIBRARY_PATH}"

# 使用Poetry启动服务（主入口）
poetry run python -m ogscope.main

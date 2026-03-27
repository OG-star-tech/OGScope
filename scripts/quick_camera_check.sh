#!/bin/bash
# 快速相机状态检查脚本 / Quick camera status check script

echo "🔍 OGScope 相机快速诊断"
echo "=========================="

# 检查服务状态 / Check service status
echo "📋 检查服务状态..."
sudo systemctl status ogscope --no-pager -l

echo ""
echo "📋 检查最近的服务日志..."
sudo journalctl -u ogscope --no-pager -l -n 20

echo ""
echo "📋 检查相机设备..."
ls -la /dev/video* 2>/dev/null || echo "未找到 /dev/video* 设备"

echo ""
echo "📋 检查 libcamera..."
if command -v libcamera-hello >/dev/null 2>&1; then
    echo "libcamera-hello 可用，检测相机:"
    timeout 10 libcamera-hello --list-cameras 2>/dev/null || echo "libcamera-hello 执行失败"
else
    echo "libcamera-hello 不可用"
fi

echo ""
echo "📋 检查 Python 依赖..."
python3 -c "
try:
    import picamera2
    print('✅ Picamera2 已安装')
except ImportError:
    print('❌ Picamera2 未安装')

try:
    import cv2
    print('✅ OpenCV 已安装')
except ImportError:
    print('⚠️  OpenCV 未安装 (直方图功能需要)')

try:
    import numpy
    print('✅ NumPy 已安装')
except ImportError:
    print('❌ NumPy 未安装')
"

echo ""
echo "📋 测试 API 端点..."
if command -v curl >/dev/null 2>&1; then
    echo "测试相机状态 API..."
    curl -s http://localhost:8000/api/debug/camera/status | python3 -m json.tool 2>/dev/null || echo "API 请求失败"
else
    echo "curl 不可用，无法测试 API"
fi

echo ""
echo "🎯 建议的修复步骤:"
echo "1. 如果服务未运行: sudo systemctl start ogscope"
echo "2. 如果 Picamera2 未安装: sudo apt install python3-picamera2"
echo "3. 如果 OpenCV 未安装: sudo apt install python3-opencv"
echo "4. 如果相机设备不存在，检查硬件连接"
echo "5. 重启服务: sudo systemctl restart ogscope"

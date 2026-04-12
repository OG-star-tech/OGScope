#!/bin/bash
# 部署板块求解到远程目标 / Deploy plate solving to remote target

set -e

# 配置 / Configuration
REMOTE_USER="rpi"
REMOTE_HOST="192.168.0.150"
REMOTE_DIR="~/OGScope"
REMOTE_VENV="/home/rpi/.cache/pypoetry/virtualenvs/ogscope-SzeLaCQe-py3.13"

echo "========================================="
echo "部署 OGScope 板块求解到远程目标"
echo "Deploy OGScope Plate Solving to Remote"
echo "========================================="
echo ""
echo "目标: ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}"
echo ""

# 1. 同步代码 / Sync code
echo "[1/4] 同步代码到远程... / Syncing code to remote..."
rsync -avz --progress \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.venv' \
  --exclude 'PiFinder-release' \
  --exclude 'logs' \
  --exclude 'data' \
  --exclude 'uploads' \
  --exclude '.pytest_cache' \
  --exclude '.mypy_cache' \
  --exclude '.ruff_cache' \
  --exclude 'node_modules' \
  . ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/

echo ""
echo "[2/4] 安装 astrometry 包... / Installing astrometry package..."
ssh ${REMOTE_USER}@${REMOTE_HOST} "bash -l -c '
  cd ${REMOTE_DIR} && \
  export PATH=/home/rpi/.local/bin:\$PATH && \
  poetry add astrometry && \
  poetry install
'"

echo ""
echo "[3/4] 测试导入... / Testing import..."
ssh ${REMOTE_USER}@${REMOTE_HOST} "bash -l -c '
  export PYTHONPATH=/usr/lib/python3/dist-packages:/usr/lib/python3.13/site-packages && \
  export LD_LIBRARY_PATH=/usr/lib/aarch64-linux-gnu:\$LD_LIBRARY_PATH && \
  ${REMOTE_VENV}/bin/python -c \"from ogscope.algorithms.plate_solver import PlateSolver; s = PlateSolver(); print(f\\\"Astrometry available: {s.is_available}\\\")\"
'"

echo ""
echo "[4/4] 重启服务... / Restarting service..."
ssh ${REMOTE_USER}@${REMOTE_HOST} "sudo systemctl restart ogscope"

echo ""
echo "等待服务启动... / Waiting for service to start..."
sleep 3

echo ""
echo "检查服务状态... / Checking service status..."
ssh ${REMOTE_USER}@${REMOTE_HOST} "sudo systemctl status ogscope --no-pager -l | head -20"

echo ""
echo "========================================="
echo "✅ 部署完成! / Deployment Complete!"
echo "========================================="
echo ""
echo "访问调试界面: http://${REMOTE_HOST}:8000/debug"
echo "Access debug UI: http://${REMOTE_HOST}:8000/debug"
echo ""
echo "功能 / Features:"
echo "  1. ⭐ 单次求解 - 对当前预览帧进行一次板块求解"
echo "     Single solve - Solve current preview frame once"
echo ""
echo "  2. 🔄 连续求解 - 每5秒自动求解并叠加显示"
echo "     Continuous solve - Auto-solve every 5 seconds with overlay"
echo ""
echo "  3. 📤 上传图像测试 - 上传静态图像文件测试板块求解"
echo "     Upload image test - Upload static image file for testing"
echo ""
echo "测试板块求解 API:"
echo "curl http://${REMOTE_HOST}:8000/api/platesolve/status"
echo ""

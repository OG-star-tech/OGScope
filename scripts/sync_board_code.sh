#!/usr/bin/env bash
# 同步 OGScope 源码到开发板并执行 board-update（保留 uploads/logs/data）
# Sync OGScope source to dev board and run board-update (keeps uploads/logs/data)
#
# 用法 / Usage:
#   export OGSCOPE_DEV_HOST=192.168.31.231
#   export OGSCOPE_DEV_USER=ogscope
#   # 可选：非 IMX327 板卡可跳过摄像头 boot 配置 / Optional: skip camera boot config on non-IMX327 boards
#   # export OGSCOPE_CAMERA=skip
#   ./scripts/sync_board_code.sh
#
# 注意：勿对整仓使用 rsync --delete 且不排除 uploads/，否则会删除板上已上传的测试图片。
# Note: Never full-repo rsync --delete without excluding uploads/ — it wipes board uploads.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEV_HOST="${OGSCOPE_DEV_HOST:-192.168.31.231}"
DEV_USER="${OGSCOPE_DEV_USER:-ogscope}"
DEV_PATH="${OGSCOPE_DEV_PATH:-/opt/ogscope}"
REMOTE="${DEV_USER}@${DEV_HOST}"

RSYNC_SSH="ssh -o ConnectTimeout=15 -o BatchMode=yes"

# 仅透传部署相关开关，避免把开发机的整个环境泄露到板端。
# Forward only deployment switches, not the whole dev-machine environment.
_remote_update_env=""
for _env_name in \
  OGSCOPE_CAMERA \
  OGSCOPE_CAMERA_DEFAULT \
  OGSCOPE_SKIP_BOOT_CAMERA \
  OGSCOPE_SKIP_CAMERA_STACK \
  OGSCOPE_MIRROR \
  OGSCOPE_NONINTERACTIVE \
  POETRY_INSTALLER_MAX_WORKERS \
  OGSCOPE_DEVELOPMENT_MODE
do
  if [ -n "${!_env_name+x}" ]; then
    printf -v _env_value_quoted '%q' "${!_env_name}"
    _remote_update_env+="${_env_name}=${_env_value_quoted} "
  fi
done

echo "== Sync OGScope code → ${REMOTE}:${DEV_PATH} (uploads/logs/data preserved) =="

rsync -avz --delete \
  -e "${RSYNC_SSH}" \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude 'node_modules/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '.coverage' \
  --exclude 'htmlcov/' \
  --exclude 'uploads/' \
  --exclude 'logs/' \
  --exclude 'data/' \
  "${ROOT}/" "${REMOTE}:${DEV_PATH}/"

echo "== Remote board-update =="
echo "   Camera default: ${OGSCOPE_CAMERA:-${OGSCOPE_CAMERA_DEFAULT:-imx327}} (override with OGSCOPE_CAMERA=skip)"
ssh -o ConnectTimeout=15 -o BatchMode=yes "${REMOTE}" \
  "cd '${DEV_PATH}' && ${_remote_update_env}bash scripts/board-update.sh"

echo "✅ OGScope sync complete"
echo "   Health: http://${DEV_HOST}:8000/health"

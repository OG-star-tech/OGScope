#!/usr/bin/env bash
# 同步 OGScope 源码到开发板并执行 board-update（保留 uploads/logs/data）
# Sync OGScope source to dev board and run board-update (keeps uploads/logs/data)
#
# 用法 / Usage:
#   export OGSCOPE_DEV_HOST=192.168.31.231
#   export OGSCOPE_DEV_USER=ogscope
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
ssh -o ConnectTimeout=15 -o BatchMode=yes "${REMOTE}" \
  "cd '${DEV_PATH}' && bash scripts/board-update.sh"

echo "✅ OGScope sync complete"
echo "   Health: http://${DEV_HOST}:8000/health"

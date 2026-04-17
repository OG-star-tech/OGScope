#!/usr/bin/env bash
# 本地 build 后同步到开发板 / Build locally then rsync to dev board
# 用法 / Usage:
#   export OGSCOPE_DEV_USER=ogstartech
#   export OGSCOPE_DEV_HOST=192.168.31.16
#   export OGSCOPE_DEV_PATH=/path/to/OGScope
#   ./scripts/sync_dev_board.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/web/spa"
npm run build
if [[ -z "${OGSCOPE_DEV_HOST:-}" || -z "${OGSCOPE_DEV_PATH:-}" ]]; then
  echo "请设置 OGSCOPE_DEV_HOST 与 OGSCOPE_DEV_PATH（可选 OGSCOPE_DEV_USER）" >&2
  echo "Set OGSCOPE_DEV_HOST and OGSCOPE_DEV_PATH (optional OGSCOPE_DEV_USER)" >&2
  exit 1
fi
RSYNC_TARGET="${OGSCOPE_DEV_USER:+$OGSCOPE_DEV_USER@}$OGSCOPE_DEV_HOST:$OGSCOPE_DEV_PATH"
rsync -avz --delete \
  "$ROOT/web/static/analysis-lab/" \
  "$RSYNC_TARGET/web/static/analysis-lab/"
rsync -avz \
  "$ROOT/web/static/css/hud-home.css" \
  "$ROOT/web/static/css/hud-home.bundle.css" \
  "$RSYNC_TARGET/web/static/css/"
rsync -avz --delete \
  "$ROOT/web/static/fonts/" \
  "$RSYNC_TARGET/web/static/fonts/"
echo "已同步 analysis-lab、主页 HUD CSS 与字体到 $RSYNC_TARGET"
echo "Synced analysis-lab, HUD CSS, and fonts to \$RSYNC_TARGET"
echo "可选 / Optional: ssh ${OGSCOPE_DEV_USER:+$OGSCOPE_DEV_USER@}$OGSCOPE_DEV_HOST 'sudo systemctl restart ogscope'"

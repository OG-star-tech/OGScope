#!/usr/bin/env bash
# 在 GitHub 上启用 main / develop 分支保护（需仓库 admin + gh 已登录）
# Enable GitHub branch protection for main and develop (requires admin + gh auth)
#
# 用法 / Usage:
#   gh auth login
#   ./.github/scripts/apply-branch-protection.sh

set -euo pipefail

REPO="${GITHUB_REPOSITORY:-OG-star-tech/OGScope}"

if ! command -v gh >/dev/null 2>&1; then
  echo "❌ 需要 GitHub CLI (gh) / gh is required"
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "❌ 请先 gh auth login / Please run: gh auth login"
  exit 1
fi

echo "🔒 配置 main：禁止直接 push，仅允许 PR（建议 base=develop 合入后再 PR 到 main）"
echo "   Configure main: block direct pushes; merge via PR only"

gh api "repos/${REPO}/branches/main/protection" -X PUT \
  -f required_status_checks[strict]=false \
  -f enforce_admins=true \
  -f required_pull_request_reviews[dismiss_stale_reviews]=false \
  -f required_pull_request_reviews[required_approving_review_count]=0 \
  -f restrictions=null \
  -f allow_force_pushes=false \
  -f allow_deletions=false \
  -F required_status_checks[contexts][]=test \
  -F required_status_checks[contexts][]=lint \
  -F required_status_checks[contexts][]=block-direct-push-to-main \
  2>/dev/null || {
  echo "⚠️  main 保护需 classic protection 或 Rulesets 权限；若失败请在 GitHub UI 手动设置："
  echo "    Settings → Branches → Add rule for main"
  echo "    - Require a pull request before merging"
  echo "    - Do not allow bypassing"
  echo "    - Restrict pushes that create files (optional)"
}

echo ""
echo "🔒 配置 develop：禁止直接 push 到 main 的替代——develop 允许 PR 合并"
gh api "repos/${REPO}/branches/develop/protection" -X PUT \
  -f required_status_checks[strict]=false \
  -f enforce_admins=false \
  -f required_pull_request_reviews[required_approving_review_count]=0 \
  -f restrictions=null \
  -f allow_force_pushes=false \
  -f allow_deletions=false \
  -F required_status_checks[contexts][]=test \
  -F required_status_checks[contexts][]=lint \
  2>/dev/null || {
  echo "⚠️  develop 保护可选；建议在 UI 为 develop 启用 Require PR（feature → develop）"
}

echo ""
echo "✅ 完成（或见上方 UI 手动指引）/ Done (or follow manual UI steps above)"

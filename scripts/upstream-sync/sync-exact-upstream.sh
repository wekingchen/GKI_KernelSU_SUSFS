#!/usr/bin/env bash
# 无人值守同步 zz h20188/dev 的所有原始文件；仅提交上游本身的合并结果。
# 本仓私有文件不得覆盖上游，自动合入前必须通过真实 GitHub CI 门禁。
set -euo pipefail
[[ "${GITHUB_REPOSITORY:-}" == "wekingchen/GKI_KernelSU_SUSFS" ]] || exit 1
[[ "${GITHUB_REF:-}" == "refs/heads/dev" ]] || exit 1
[[ -n "${GH_TOKEN:-}" ]] || {
  echo "::error::缺少 UPSTREAM_SYNC_PAT，禁止使用无 workflow 权限的 GITHUB_TOKEN"
  exit 1
}
cd "$(git rev-parse --show-toplevel)"
FORK_BASE="$(git rev-parse HEAD)"
UPSTREAM_URL="https://github.com/zzh20188/GKI_KernelSU_SUSFS.git"
git fetch -q --no-tags "$UPSTREAM_URL" refs/heads/dev
UPSTREAM_SHA="$(git rev-parse FETCH_HEAD)"

# 已合并过的上游无需重建；但仍检查本仓源文件是否保持原样。
if git merge-base --is-ancestor "$UPSTREAM_SHA" "$FORK_BASE"; then
  bash scripts/xiaomi-os4/check-upstream-isolation.sh "$FORK_BASE"
  echo "上游无新增提交，fork 共享文件仍完全一致。" >> "$GITHUB_STEP_SUMMARY"
  exit 0
fi

# 只允许本仓持有独立路径；此前继承的上游文件如果发生本地修改，绝不自动覆盖。
LAST_UPSTREAM="$(git merge-base "$FORK_BASE" "$UPSTREAM_SHA")"
mapfile -t modified_shared < <(
  git diff --no-renames --name-only --diff-filter=DMT "$LAST_UPSTREAM" "$FORK_BASE"
)
if (( ${#modified_shared[@]} )); then
  echo "::error::存在未经隔离的上游文件修改，拒绝自动合并："
  printf '  - %s\n' "${modified_shared[@]}"
  exit 1
fi

# 新增工作流需要人工复核，避免在无人值守时引入未经检查的高权限入口。
mapfile -t new_workflows < <(
  git diff --no-renames --name-only --diff-filter=A "$LAST_UPSTREAM" "$UPSTREAM_SHA" -- .github/workflows
)
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
BRANCH="auto/upstream-exact-$GITHUB_RUN_ID"
git switch -c "$BRANCH"
if ! git merge --no-ff --no-commit "$UPSTREAM_SHA"; then
  git merge --abort >/dev/null 2>&1 || true
  echo "::error::上游出现文件级冲突，保留 dev 并停止自动同步"
  exit 1
fi

# 本仓的私有入口从本次上游原件重新生成；只有固定补丁能够无歧义重放时才继续。
# 如果上游 Manager / 自定义构建接口发生不可兼容变更，在此失败关闭，不覆盖旧 dev。
python3 scripts/generic-custom/sync_fork_custom_entry.py --write
python3 scripts/generic-custom/sync_fork_manager.py --write
git add .github/workflows/kernel-custom-fork.yml .github/workflows/get-manager-fork.yml

# 验证合并结果没有修改、删除或改变上游文件类型（新增私有路径允许）。
mapfile -t unexpected < <(
  git diff --no-renames --cached --name-only --diff-filter=DMT "$UPSTREAM_SHA"
)
if (( ${#unexpected[@]} )); then
  echo "::error::合并候选不满足上游原件完整性："
  printf '  - %s\n' "${unexpected[@]}"
  git merge --abort >/dev/null 2>&1 || true
  exit 1
fi
git commit -m "merge(upstream): exact original dev at $UPSTREAM_SHA"
CANDIDATE_SHA="$(git rev-parse HEAD)"
bash scripts/xiaomi-os4/check-upstream-isolation.sh "$FORK_BASE"

# 固定候选来源；上游或本仓 dev 在此期间发生变化则失败关闭，避免静默覆盖。
LIVE_UPSTREAM="$(git ls-remote "$UPSTREAM_URL" refs/heads/dev | cut -f1)"
LIVE_DEV="$(git ls-remote origin refs/heads/dev | cut -f1)"
[[ "$LIVE_UPSTREAM" == "$UPSTREAM_SHA" && "$LIVE_DEV" == "$FORK_BASE" ]] || {
  echo "::error::上游或 fork dev 在同步期间已更新，本次候选作废"
  exit 1
}
git push origin "$BRANCH"
gh pr create --repo "$GITHUB_REPOSITORY" --base dev --head "$BRANCH" \
  --title "自动同步上游原件 $UPSTREAM_SHA" \
  --body "仅合并上游 dev 原始提交，不覆盖任何 fork-only OS4 或 K50 Pro 文件。自动合入须通过严格隔离 CI；不触发 LKG 晋升。"
PR_NUMBER="$(gh pr view "$BRANCH" --repo "$GITHUB_REPOSITORY" --json number --jq .number)"
echo "同步候选 PR #$PR_NUMBER：https://github.com/$GITHUB_REPOSITORY/pull/$PR_NUMBER" >> "$GITHUB_STEP_SUMMARY"

if (( ${#new_workflows[@]} )); then
  echo "::warning::上游新增 Actions 工作流，须人工复核；候选保留为开放 PR"
  printf '  - %s\n' "${new_workflows[@]}"
  exit 0
fi

# 等待真正由 PR 事件触发的上游隔离 CI，不能仅凭本地脚本成功就合并。
PASS=false
for attempt in $(seq 1 90); do
  RUNS="$(gh api "repos/$GITHUB_REPOSITORY/actions/runs?event=pull_request&head_sha=$CANDIDATE_SHA&per_page=20")"
  GATE="$(jq -c --arg sha "$CANDIDATE_SHA" \
    '[.workflow_runs[] | select(.name=="小米内核 / 上游文件隔离门禁" and .head_sha==$sha)] | sort_by(.id) | last // empty' <<< "$RUNS")"
  if [[ -n "$GATE" && "$GATE" != null ]]; then
    CONCLUSION="$(jq -r .conclusion <<< "$GATE")"
    STATE="$(jq -r .status <<< "$GATE")"
    if [[ "$STATE" == completed ]]; then
      [[ "$CONCLUSION" == success ]] && PASS=true
      break
    fi
  fi
  sleep 10
done
[[ "$PASS" == true ]] || {
  echo "::error::同步 PR 的上游隔离 CI 未通过；不合并并保留 PR 供排查"
  exit 1
}

LIVE_DEV="$(git ls-remote origin refs/heads/dev | cut -f1)"
LIVE_UPSTREAM="$(git ls-remote "$UPSTREAM_URL" refs/heads/dev | cut -f1)"
[[ "$LIVE_DEV" == "$FORK_BASE" && "$LIVE_UPSTREAM" == "$UPSTREAM_SHA" ]] || {
  echo "::error::同步 CI 期间分支又移动，拒绝合并"
  exit 1
}
gh api --method PUT "repos/$GITHUB_REPOSITORY/pulls/$PR_NUMBER/merge" \
  -f merge_method=merge -f sha="$CANDIDATE_SHA" \
  -f commit_title="merge: upstream exact mirror $UPSTREAM_SHA" > /dev/null
gh api --method DELETE "repos/$GITHUB_REPOSITORY/git/refs/heads/$BRANCH" || true
echo "上游完整原件已自动合并（PR #$PR_NUMBER），OS4 LKG 未改变。" >> "$GITHUB_STEP_SUMMARY"

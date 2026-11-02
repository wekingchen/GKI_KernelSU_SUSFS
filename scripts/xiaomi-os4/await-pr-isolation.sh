#!/usr/bin/env bash
# GITHUB_TOKEN-created PRs do not trigger pull_request workflows. Explicitly
# dispatch the independent check on the exact head; never bypass protection.
set -euo pipefail
BRANCH="${1:?branch}"; EXPECTED="${2:?head SHA}"
[[ "$GITHUB_REPOSITORY" == wekingchen/GKI_KernelSU_SUSFS && "$EXPECTED" =~ ^[a-f0-9]{40}$ ]]
[[ "$BRANCH" =~ ^[A-Za-z0-9._/-]+$ ]]
[[ "$(gh api "repos/$GITHUB_REPOSITORY/git/ref/heads/$BRANCH" --jq .object.sha)" == "$EXPECTED" ]]
gh workflow run xiaomi-upstream-isolation-guard.yml --repo "$GITHUB_REPOSITORY" \
  --ref "$BRANCH" --field expected_head="$EXPECTED"
for attempt in {1..80}; do
  RUNS="$(gh api "repos/$GITHUB_REPOSITORY/actions/workflows/xiaomi-upstream-isolation-guard.yml/runs?event=workflow_dispatch&per_page=100")"
  RUN="$(jq -c --arg sha "$EXPECTED" --arg branch "$BRANCH" \
    '[.workflow_runs[] | select(.head_sha==$sha and .head_branch==$branch and .path==".github/workflows/xiaomi-upstream-isolation-guard.yml")] | sort_by(.id) | last // empty' <<<"$RUNS")"
  if [[ -n "$RUN" && "$(jq -r .status <<<"$RUN")" == completed ]]; then
    [[ "$(jq -r .conclusion <<<"$RUN")" == success ]] || { echo '::error::独立隔离门禁未通过，保留 PR'; exit 1; }
    ID="$(jq -r .id <<<"$RUN")"
    gh api "repos/$GITHUB_REPOSITORY/actions/runs/$ID/jobs?per_page=100" \
      | jq -e '[.jobs[] | select(.name=="isolation" and .conclusion=="success")] | length == 1' >/dev/null
    [[ "$(gh api "repos/$GITHUB_REPOSITORY/git/ref/heads/$BRANCH" --jq .object.sha)" == "$EXPECTED" ]]
    exit 0
  fi
  sleep 8
done
echo '::error::独立隔离门禁等待超时，保留 PR，不自动合并'
exit 1

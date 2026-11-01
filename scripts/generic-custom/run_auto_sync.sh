#!/usr/bin/env bash
# Unattended fork-only upstream sync. No shared upstream path may be changed.
# Do not publish a generated build until a complete K50 Pro 5.10 smoke run
# succeeds with the same feature choices as the last proven Run 41239924766.
set -euo pipefail

[[ "$GITHUB_REPOSITORY" == "wekingchen/GKI_KernelSU_SUSFS" ]] || exit 1
[[ "$GITHUB_REF" == "refs/heads/dev" ]] || exit 1
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
BASE_SHA="$(git rev-parse HEAD)"
WORK="$(mktemp -d)"
BRANCH=""
STAGED_SHA=""

cleanup() {
  if [[ -n "$BRANCH" && -n "$STAGED_SHA" ]]; then
    CURR="$(gh api "repos/$GITHUB_REPOSITORY/git/ref/heads/$BRANCH" --jq .object.sha 2>/dev/null || true)"
    if [[ "$CURR" == "$STAGED_SHA" ]]; then
      gh api -X DELETE "repos/$GITHUB_REPOSITORY/git/refs/heads/$BRANCH" >/dev/null || true
    fi
  fi
  rm -rf "$WORK"
}
trap cleanup EXIT

STATE=".github/config/generic-custom-upstream-sync.json"
FORK=".github/workflows/build-fork-custom.yml"
jq -e '.schema==1 and .upstream_repository=="zzh20188/GKI_KernelSU_SUSFS" and
       .upstream_ref=="dev" and (.upstream_blob_sha|test("^[a-f0-9]{40}$")) and
       (.private_base_blob_sha|test("^[a-f0-9]{40}$"))' "$STATE" >/dev/null
PREVIOUS="$(jq -r .upstream_blob_sha "$STATE")"
gh api "repos/zzh20188/GKI_KernelSU_SUSFS/git/blobs/$PREVIOUS" \
  --jq '.content' | base64 -d > "$WORK/previous.yml"
[[ -s "$WORK/previous.yml" ]] || exit 1
git fetch -q --depth 1 --no-tags \
  https://github.com/zzh20188/GKI_KernelSU_SUSFS.git refs/heads/dev
SOURCE_COMMIT="$(git rev-parse FETCH_HEAD)"
NEW_BLOB="$(git rev-parse 'FETCH_HEAD:.github/workflows/build.yml')"
git show 'FETCH_HEAD:.github/workflows/build.yml' > "$WORK/latest.yml"
echo "Tracked upstream $PREVIOUS; latest upstream $NEW_BLOB"

python3 scripts/generic-custom/sync_fork_build.py \
  --previous-upstream "$WORK/previous.yml" \
  --latest-upstream "$WORK/latest.yml" \
  --private-build "$FORK" --state "$STATE" \
  --output-build "$WORK/generated.yml" \
  --output-state "$WORK/state.json" | tee "$WORK/sync-status.txt"
source "$WORK/sync-status.txt"
[[ "$UPSTREAM_BLOB_SHA" == "$NEW_BLOB" ]] || exit 1
if [[ "$UPSTREAM_CHANGED" == false ]]; then
  echo "上游 build.yml 没有变化，不重复构建，也不更改 dev。" >> "$GITHUB_STEP_SUMMARY"
  exit 0
fi

cp "$WORK/generated.yml" "$FORK"
cp "$WORK/state.json" "$STATE"
ruby -ryaml -e 'ARGV.each { |p| YAML.parse_file(p) }' \
  "$FORK" ".github/workflows/kernel-custom-fork.yml"
bash -n scripts/generic-custom/prepare-host-linker.sh
python3 -m unittest discover -s scripts/generic-custom -p 'test_*.py' -v
[[ -z "$(git status --porcelain -- .github/workflows/build.yml .github/workflows/kernel-custom.yml)" ]] || exit 1
CHANGES="$(git diff --name-only)"
[[ "$(printf '%s\n' "$CHANGES" | grep -c .)" == 2 ]] || {
  echo "::error::同步只能修改私有隔离副本及其状态文件"; exit 1;
}
printf '%s\n' "$CHANGES" | grep -Fxq "$FORK"
printf '%s\n' "$CHANGES" | grep -Fxq "$STATE"

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
BRANCH="auto/k50pro-build-upstream-$GITHUB_RUN_ID"
git switch -c "$BRANCH"
git add "$FORK" "$STATE"
git commit -m "chore(generic): sync private build to upstream blob $NEW_BLOB"
STAGED_SHA="$(git rev-parse HEAD)"
git push origin "$BRANCH"

# This exact configuration passed in real-device K50 Pro build 41239924766.
gh workflow run kernel-custom-fork.yml --repo "$GITHUB_REPOSITORY" --ref "$BRANCH" \
  -f kernel_version="5.10" \
  -f os_patch_level="2024-05" \
  -f kernelsu_variant="BakaSU" \
  -f ksu_mode="关闭" \
  -f use_kpm="disabled (关闭)" \
  -f use_zram="true" \
  -f use_bbg="true" \
  -f use_rekernel="true" \
  -f use_nomount="true" \
  -f use_networking="true" \
  -f cve_2026_43499_patch="true" \
  -f droidspaces="678" \
  -f droidspaces_ntsync="false" \
  -f supp_op="false" \
  -f artifact_upload_mode="仅上传 AnyKernel3.zip"

RUN_ID=""
for attempt in $(seq 1 30); do
  RUN_ID="$(gh run list --repo "$GITHUB_REPOSITORY" \
    --workflow kernel-custom-fork.yml --branch "$BRANCH" \
    --event workflow_dispatch --limit 10 \
    --json databaseId,headSha \
    --jq ".[] | select(.headSha==\"$STAGED_SHA\") | .databaseId" | head -n 1)"
  [[ "$RUN_ID" =~ ^[1-9][0-9]*$ ]] && break
  sleep 6
done
[[ "$RUN_ID" =~ ^[1-9][0-9]*$ ]] || {
  echo "::error::候选完整内核构建 Run 未创建，禁止更新 dev"; exit 1;
}
echo "测试候选: https://github.com/$GITHUB_REPOSITORY/actions/runs/$RUN_ID" >> "$GITHUB_STEP_SUMMARY"

OK=false
for attempt in $(seq 1 325); do
  INFO="$(gh api "repos/$GITHUB_REPOSITORY/actions/runs/$RUN_ID")"
  [[ "$(jq -r '.head_sha' <<< "$INFO")" == "$STAGED_SHA" ]] || exit 1
  if [[ "$(jq -r '.status' <<< "$INFO")" == completed ]]; then
    [[ "$(jq -r '.conclusion' <<< "$INFO")" == success ]] && OK=true
    break
  fi
  sleep 60
done
[[ "$OK" == true ]] || {
  echo "::error::K50 Pro 新版完整构建未通过，已保留 dev 的可用旧版"; exit 1;
}

JOBS="$(gh api "repos/$GITHUB_REPOSITORY/actions/runs/$RUN_ID/jobs?per_page=100")"
jq -e '[.jobs[] | select(.name | contains("5.10.209-android12-2024-05-BakaSU")) |
         select(.conclusion=="success")] | length==1' <<< "$JOBS" >/dev/null
ARTIFACTS="$(gh api "repos/$GITHUB_REPOSITORY/actions/runs/$RUN_ID/artifacts?per_page=100")"
jq -e '[.artifacts[] |
       select(.name=="BakaSU_kernel-android12-5.10-209-AnyKernel3" and
              .expired==false and .size_in_bytes>5000000)] | length==1' \
       <<< "$ARTIFACTS" >/dev/null

CURRENT_DEV="$(git ls-remote origin refs/heads/dev | cut -f1)"
[[ "$CURRENT_DEV" == "$BASE_SHA" ]] || {
  echo "::error::dev 已更新，拒绝并发覆盖；下次重新三方合并"; exit 1;
}
CURRENT_UPSTREAM="$(git ls-remote \
  https://github.com/zzh20188/GKI_KernelSU_SUSFS.git refs/heads/dev | cut -f1)"
git fetch -q --depth 1 --no-tags \
  https://github.com/zzh20188/GKI_KernelSU_SUSFS.git "$CURRENT_UPSTREAM"
[[ "$(git rev-parse 'FETCH_HEAD:.github/workflows/build.yml')" == "$NEW_BLOB" ]] || {
  echo "::error::构建测试期间上游又更新，拒绝发布落后版本"; exit 1;
}
[[ "$(git rev-parse HEAD)" == "$STAGED_SHA" ]] || exit 1
git push origin HEAD:dev
echo "K50 Pro 全功能内核自动构建成功，安全更新 dev 的私有 build-fork-custom.yml；测试 Run #$RUN_ID" >> "$GITHUB_STEP_SUMMARY"

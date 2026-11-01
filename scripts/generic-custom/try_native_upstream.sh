#!/usr/bin/env bash
# Test upstream's *unmodified* build and original custom workflow on an ephemeral
# branch. No phone confirmation required. Never retire the fallback after a
# green test of the fork's modified shared build.yml or a partial build.
set -euo pipefail
[[ "$GITHUB_REPOSITORY" == "wekingchen/GKI_KernelSU_SUSFS" ]] || exit 1
[[ "$GITHUB_REF" == "refs/heads/dev" ]] || exit 1
cd "$(git rev-parse --show-toplevel)"
BASE="$(git rev-parse HEAD)"
ROUTE=".github/config/generic-custom-route.json"
WORK="$(mktemp -d)"
BRANCH=""
CANDIDATE_SHA=""
REMOTE_SHA=""

cleanup_native_candidate() {
  # A rejected original candidate must restore the checked-out dev before
  # the existing private fallback sync may run in this SAME job.
  if [[ -n "$BRANCH" && "$(git branch --show-current)" == "$BRANCH" ]]; then
    git switch -f dev >/dev/null || true
  fi
  if [[ -n "$BRANCH" && -n "$REMOTE_SHA" ]]; then
    CURRENT="$(gh api "repos/$GITHUB_REPOSITORY/git/ref/heads/$BRANCH" \
      --jq .object.sha 2>/dev/null || true)"
    if [[ "$CURRENT" == "$REMOTE_SHA" ]]; then
      gh api -X DELETE "repos/$GITHUB_REPOSITORY/git/refs/heads/$BRANCH" >/dev/null || true
    fi
  fi
  rm -rf "$WORK"
}
trap cleanup_native_candidate EXIT

MODE="$(jq -er '.mode | select(.=="fork" or .=="upstream")' "$ROUTE")"
git fetch -q --depth 1 --no-tags \
  https://github.com/zzh20188/GKI_KernelSU_SUSFS.git refs/heads/dev
UPSTREAM_COMMIT="$(git rev-parse FETCH_HEAD)"
UPSTREAM_BUILD_SHA="$(git rev-parse 'FETCH_HEAD:.github/workflows/build.yml')"
UPSTREAM_CUSTOM_SHA="$(git rev-parse 'FETCH_HEAD:.github/workflows/kernel-custom.yml')"
git show 'FETCH_HEAD:.github/workflows/build.yml' > "$WORK/upstream-build.yml"
git show 'FETCH_HEAD:.github/workflows/kernel-custom.yml' > "$WORK/upstream-custom.yml"

if [[ "$UPSTREAM_BUILD_SHA" == "$(jq -r .upstream_build_blob "$ROUTE")" &&
      "$UPSTREAM_CUSTOM_SHA" == "$(jq -r .upstream_custom_blob "$ROUTE")" ]]; then
  echo "上游原版 build.yml 和 kernel-custom.yml 没有新变化，当前模式：$MODE" >> "$GITHUB_STEP_SUMMARY"
  [[ "$MODE" == upstream ]] && exit 0
  exit 1   # fork remains primary; let the existing fallback sync check run.
fi

# Do not silently switch to a changed/unverified kernel configuration.
if ! python3 scripts/generic-custom/native_upstream_policy.py \
    --check-only \
    --route "$ROUTE" \
    --build "$WORK/upstream-build.yml" \
    --custom "$WORK/upstream-custom.yml" \
    --build-blob "$UPSTREAM_BUILD_SHA" \
    --custom-blob "$UPSTREAM_CUSTOM_SHA" \
    --commit "$UPSTREAM_COMMIT"; then
  echo "::warning::上游原版当前不满足 K50 Pro 的安全/功能约束，保留既有稳定模式"
  [[ "$MODE" == upstream ]] && exit 0
  exit 1
fi

# The candidate uses the *actual* upstream versions of BOTH shared files,
# never the fork's modified build.yml or the fallback's build-fork-custom.yml.
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
BRANCH="auto/k50pro-native-upstream-$GITHUB_RUN_ID"
git switch -c "$BRANCH"
cp "$WORK/upstream-build.yml" .github/workflows/build.yml
cp "$WORK/upstream-custom.yml" .github/workflows/kernel-custom.yml
[[ "$(git hash-object .github/workflows/build.yml)" == "$UPSTREAM_BUILD_SHA" ]] || exit 1
[[ "$(git hash-object .github/workflows/kernel-custom.yml)" == "$UPSTREAM_CUSTOM_SHA" ]] || exit 1
if git diff --quiet -- .github/workflows/build.yml .github/workflows/kernel-custom.yml; then
  echo "::error::上游文件与当前代码相同但来源状态不匹配，禁止无根据晋升"
  exit 1
fi
git add .github/workflows/build.yml .github/workflows/kernel-custom.yml
git commit -m "test(K50Pro): candidate exact native upstream generic build"
CANDIDATE_SHA="$(git rev-parse HEAD)"
git push origin "$BRANCH"
REMOTE_SHA="$CANDIDATE_SHA"

# Reuse all features from the already flashed Run #41239924766.
gh workflow run kernel-custom.yml --repo "$GITHUB_REPOSITORY" --ref "$BRANCH" \
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

RUN=""
for attempt in $(seq 1 30); do
  RUN="$(gh run list --repo "$GITHUB_REPOSITORY" \
    --workflow kernel-custom.yml --branch "$BRANCH" --event workflow_dispatch \
    --limit 20 --json databaseId,headSha \
    --jq ".[] | select(.headSha==\"$CANDIDATE_SHA\") | .databaseId" | head -n1)"
  [[ "$RUN" =~ ^[1-9][0-9]*$ ]] && break
  sleep 6
done
[[ "$RUN" =~ ^[1-9][0-9]*$ ]] || {
  echo "::error::没有发现原版内核的真实测试 Run，保留原模式"; exit 1;
}
echo "上游原版完整内核测试： https://github.com/$GITHUB_REPOSITORY/actions/runs/$RUN" >> "$GITHUB_STEP_SUMMARY"

SUCCESS=false
for attempt in $(seq 1 145); do
  INFO="$(gh api "repos/$GITHUB_REPOSITORY/actions/runs/$RUN")"
  [[ "$(jq -r .head_sha <<< "$INFO")" == "$CANDIDATE_SHA" ]] || exit 1
  [[ "$(jq -r .path <<< "$INFO")" == ".github/workflows/kernel-custom.yml" ]] || exit 1
  if [[ "$(jq -r .status <<< "$INFO")" == completed ]]; then
    [[ "$(jq -r .conclusion <<< "$INFO")" == success ]] && SUCCESS=true
    break
  fi
  sleep 60
done
if [[ "$SUCCESS" != true ]]; then
  echo "::warning::上游原版真实构建失败或超时：继续使用当前已验证方案"
  [[ "$MODE" == upstream ]] && exit 0
  exit 1
fi

ALLJOBS="$(gh api "repos/$GITHUB_REPOSITORY/actions/runs/$RUN/jobs?per_page=100")"
KERNELJOB="$(jq -er '[.jobs[] |
  select(.name | contains("5.10.209-android12-2024-05-BakaSU")) |
  select(.conclusion=="success")] | if length==1 then .[0].id else empty end' <<< "$ALLJOBS")"
ARTIFACTS="$(gh api "repos/$GITHUB_REPOSITORY/actions/runs/$RUN/artifacts?per_page=100")"
jq -e '[.artifacts[] |
  select(.name=="BakaSU_kernel-android12-5.10-209-AnyKernel3" and
  .expired==false and .size_in_bytes>5000000)] | length == 1' \
  <<< "$ARTIFACTS" >/dev/null

# A "successful" upstream job may still have soft-failed BBG genheaders.
# Inspect the build job log for the precise known unresolved failure.
gh api "repos/$GITHUB_REPOSITORY/actions/jobs/$KERNELJOB/logs" > "$WORK/native-kernel.log"
[[ -s "$WORK/native-kernel.log" ]] || exit 1
if grep -Eq '^20[0-9]{2}-.*Z (clang-[0-9]+: error: unable to execute command: Executable "ld"|make\[[0-9]+\]: \./genheaders: No such file|.*susfs_compat\.mk:.*Please wait)' "$WORK/native-kernel.log"; then
  echo "::warning::原版构建记录存在 BBG/SUSFS 隐性错误，不能仅凭绿色 CI 停用补丁"
  [[ "$MODE" == upstream ]] && exit 0
  exit 1
fi
grep -Fq -- 'BBG was enabled!' "$WORK/native-kernel.log" || {
  echo "::error::原版日志中缺少 BBG 已启用的证据"; exit 1;
}
grep -Eq 'LTO[[:space:]]+vmlinux\.o' "$WORK/native-kernel.log" || {
  echo "::error::原版日志未确认 LTO 阶段完成"; exit 1;
}

python3 scripts/generic-custom/native_upstream_policy.py \
  --route "$ROUTE" \
  --build "$WORK/upstream-build.yml" \
  --custom "$WORK/upstream-custom.yml" \
  --build-blob "$UPSTREAM_BUILD_SHA" \
  --custom-blob "$UPSTREAM_CUSTOM_SHA" \
  --commit "$UPSTREAM_COMMIT" --run-id "$RUN" \
  --output "$WORK/validated-route.json"
cp "$WORK/validated-route.json" "$ROUTE"
# The production branch must remain green *after* switching mode. Verify
# recovery tests (which must handle either route) before writing dev.
ruby -ryaml -e 'ARGV.each { |p| YAML.parse_file(p) }' \
  .github/workflows/build.yml .github/workflows/kernel-custom.yml \
  .github/workflows/build-fork-custom.yml .github/workflows/kernel-custom-fork.yml
python3 -m unittest discover -s scripts/generic-custom -p 'test_*.py' -v
[[ "$(git hash-object .github/workflows/build.yml)" == "$UPSTREAM_BUILD_SHA" ]] || exit 1
[[ "$(git hash-object .github/workflows/kernel-custom.yml)" == "$UPSTREAM_CUSTOM_SHA" ]] || exit 1
git add "$ROUTE"
git commit -m "chore(K50Pro): retire private autosync after exact native upstream CI success"
CANDIDATE_SHA="$(git rev-parse HEAD)"
[[ "$(git diff --name-only HEAD~1 HEAD)" == "$ROUTE" ]] || exit 1

LIVE_DEV="$(git ls-remote origin refs/heads/dev | cut -f1)"
[[ "$LIVE_DEV" == "$BASE" ]] || {
  echo "::error::dev 在原版构建验证期间发生变化，下轮重新验证再切换"; exit 1;
}
LIVE_UPSTREAM="$(git ls-remote \
  https://github.com/zzh20188/GKI_KernelSU_SUSFS.git refs/heads/dev | cut -f1)"
git fetch -q --depth 1 --no-tags \
  https://github.com/zzh20188/GKI_KernelSU_SUSFS.git "$LIVE_UPSTREAM"
[[ "$(git rev-parse 'FETCH_HEAD:.github/workflows/build.yml')" == "$UPSTREAM_BUILD_SHA" ]] || exit 1
[[ "$(git rev-parse 'FETCH_HEAD:.github/workflows/kernel-custom.yml')" == "$UPSTREAM_CUSTOM_SHA" ]] || exit 1
[[ "$(git rev-parse HEAD)" == "$CANDIDATE_SHA" ]] || exit 1
git push origin HEAD:dev
echo "原版真实 CI #$RUN 和 AnyKernel3 均通过：已切换到上游原版并自动停用私有构建同步，不要求刷机确认。" >> "$GITHUB_STEP_SUMMARY"

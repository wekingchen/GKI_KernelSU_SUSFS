#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/.github/config/xiaomi-sm8850-os4-6.12.69.env"

OUTDIR="${1:-${RUNNER_TEMP:-/tmp}/bakasu-manager-out}"
TARGET_COMMIT="${2:-${XIAOMI_OS4_BAKASU_COMMIT:-}}"
TOKEN="${GH_TOKEN:-${GITHUB_TOKEN:-}}"
API_ROOT="https://api.github.com/repos/Baka-SU/BakaSU"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

mkdir -p "$OUTDIR"

curl_api() {
  local url="$1"
  local args=(
    --fail-with-body --silent --show-error --location
    --retry 3 --retry-all-errors --retry-delay 2
    --connect-timeout 15 --max-time 120
    -H "Accept: application/vnd.github+json"
    -H "X-GitHub-Api-Version: 2022-11-28"
  )
  if [[ -n "$TOKEN" ]]; then
    args+=( -H "Authorization: Bearer $TOKEN" )
  fi
  curl "${args[@]}" "$url"
}

git clone -q --filter=blob:none "$OS4_BAKASU_REPO" "$WORKDIR/BakaSU"
LATEST_SHA="$(git -C "$WORKDIR/BakaSU" rev-parse "origin/$OS4_BAKASU_REF")"
if [[ -z "$TARGET_COMMIT" ]]; then
  TARGET_COMMIT="$LATEST_SHA"
fi
if ! git -C "$WORKDIR/BakaSU" cat-file -e "$TARGET_COMMIT^{commit}" 2>/dev/null; then
  git -C "$WORKDIR/BakaSU" fetch -q --no-tags origin "$TARGET_COMMIT"
fi
git -C "$WORKDIR/BakaSU" cat-file -e "$TARGET_COMMIT^{commit}" 2>/dev/null || {
  echo "::error::无法取得 BakaSU 目标提交 $TARGET_COMMIT"
  exit 1
}

TARGET_GIT_COUNT="$(git -C "$WORKDIR/BakaSU" rev-list --count "$TARGET_COMMIT")"
TARGET_KSU_VERSION="$((30700 + TARGET_GIT_COUNT))"

echo "[BakaSU Manager] target commit: $TARGET_COMMIT"
echo "[BakaSU Manager] target KSU version: $TARGET_KSU_VERSION"
echo "[BakaSU Manager] latest upstream: $LATEST_SHA"

calculate_version() {
  local sha="$1"
  if ! git -C "$WORKDIR/BakaSU" cat-file -e "$sha^{commit}" 2>/dev/null; then
    git -C "$WORKDIR/BakaSU" fetch -q --no-tags origin "$sha" >/dev/null 2>&1 || return 1
  fi
  local count
  count="$(git -C "$WORKDIR/BakaSU" rev-list --count "$sha")" || return 1
  echo "$((30700 + count))"
}

BEST_VERSION=0
BEST_RUN_ID=""
BEST_HEAD_SHA=""
BEST_HEAD_BRANCH=""
BEST_ARTIFACTS=""

# The exact main commit may have been pushed seconds before this Xiaomi run.
# Wait for BakaSU's own signed Manager workflow to finish so the APK and kernel
# always come from the exact same source commit.
for ATTEMPT in $(seq 1 40); do
  echo "[BakaSU Manager] 查找与 $TARGET_COMMIT 完全匹配的成功构建（$ATTEMPT/40）"
  BEST_VERSION=0
  BEST_RUN_ID=""
  BEST_HEAD_SHA=""
  BEST_HEAD_BRANCH=""
  BEST_ARTIFACTS=""

  for PAGE in $(seq 1 10); do
    RUNS="$(curl_api "$API_ROOT/actions/workflows/build-manager.yml/runs?status=success&per_page=30&page=$PAGE")"
    RUN_COUNT="$(jq '.workflow_runs | length' <<<"$RUNS")"
    [[ "$RUN_COUNT" -gt 0 ]] || break

    for INDEX in $(seq 0 $((RUN_COUNT - 1))); do
      RUN_ID="$(jq -r ".workflow_runs[$INDEX].id" <<<"$RUNS")"
      HEAD_SHA="$(jq -r ".workflow_runs[$INDEX].head_sha" <<<"$RUNS")"
      HEAD_BRANCH="$(jq -r ".workflow_runs[$INDEX].head_branch // \"\"" <<<"$RUNS")"
      RUN_EVENT="$(jq -r ".workflow_runs[$INDEX].event // \"\"" <<<"$RUNS")"

      # PR workflows may build refs/pull/<n>/merge while exposing the PR head
      # SHA, so only use normal main/push/manual runs whose exposed SHA is the
      # actual source commit.
      if [[ "$RUN_EVENT" == "pull_request" ]]; then
        continue
      fi
      [[ "$HEAD_SHA" == "$TARGET_COMMIT" ]] || continue

      RUN_VERSION="$(calculate_version "$HEAD_SHA" || true)"
      [[ "$RUN_VERSION" =~ ^[0-9]+$ ]] || continue
      (( RUN_VERSION == TARGET_KSU_VERSION )) || continue

      ARTIFACTS="$(curl_api "$API_ROOT/actions/runs/$RUN_ID/artifacts?per_page=100")"
      CANDIDATES="$(jq -c '
        [.artifacts[]
         | select(.expired == false)
         | select(.name == "Manager-release" or .name == "Spoofed-Manager-release")
         | {name, archive_download_url}]
      ' <<<"$ARTIFACTS")"
      [[ "$(jq 'length' <<<"$CANDIDATES")" -gt 0 ]] || continue

      BEST_VERSION="$RUN_VERSION"
      BEST_RUN_ID="$RUN_ID"
      BEST_HEAD_SHA="$HEAD_SHA"
      BEST_HEAD_BRANCH="$HEAD_BRANCH"
      BEST_ARTIFACTS="$CANDIDATES"
      break 2
    done
  done

  [[ -n "$BEST_RUN_ID" ]] && break
  if (( ATTEMPT < 40 )); then
    echo "[BakaSU Manager] 精确提交的官方 Manager 尚未完成，30 秒后重试"
    sleep 30
  fi
done

[[ -n "$BEST_RUN_ID" && -n "$BEST_ARTIFACTS" ]] || {
  echo "::error::未找到与 BakaSU 提交 $TARGET_COMMIT / KSU $TARGET_KSU_VERSION 完全匹配的成功 Manager 构建"
  exit 1
}

echo "[BakaSU Manager] selected run: $BEST_RUN_ID"
echo "[BakaSU Manager] selected KSU version: $BEST_VERSION"
echo "[BakaSU Manager] selected head: $BEST_HEAD_SHA"

rm -rf "$OUTDIR"/*
while IFS=$'\t' read -r NAME URL; do
  [[ -n "$NAME" && -n "$URL" ]] || continue
  SAFE_NAME="$(tr '/ ' '__' <<<"$NAME")"
  ZIP="$WORKDIR/$SAFE_NAME.zip"
  EXTRACT="$WORKDIR/$SAFE_NAME"

  CURL_ARGS=(
    --fail-with-body --silent --show-error --location
    --retry 3 --retry-all-errors --retry-delay 2
    --connect-timeout 15 --max-time 180
  )
  if [[ -n "$TOKEN" ]]; then
    CURL_ARGS+=( -H "Authorization: Bearer $TOKEN" )
  fi
  curl "${CURL_ARGS[@]}" -o "$ZIP" "$URL"
  mkdir -p "$EXTRACT"
  unzip -q "$ZIP" -d "$EXTRACT"

  while IFS= read -r APK; do
    APK_NAME="$(basename "$APK")"
    [[ "$APK_NAME" != *debug* ]] || continue
    [[ "$APK_NAME" == *-arm64-v8a-release.apk ]] || continue

    if [[ "$APK_NAME" =~ _([0-9]+)-arm64-v8a-release\.apk$ ]]; then
      APK_KSU_VERSION="${BASH_REMATCH[1]}"
    else
      echo "::error::无法从 BakaSU Manager 文件名解析 KSU 版本: $APK_NAME"
      exit 1
    fi
    (( APK_KSU_VERSION == TARGET_KSU_VERSION )) || {
      echo "::error::Manager KSU $APK_KSU_VERSION 与目标内核 KSU $TARGET_KSU_VERSION 不一致: $APK_NAME"
      exit 1
    }

    OUTPUT_NAME="$APK_NAME"
    if [[ "$NAME" == "Spoofed-Manager-release" ]]; then
      OUTPUT_NAME="Spoofed-$APK_NAME"
    fi
    cp -f "$APK" "$OUTDIR/$OUTPUT_NAME"
    echo "[BakaSU Manager] keep: $OUTPUT_NAME"
  done < <(find "$EXTRACT" -type f -name '*.apk' -print)
done < <(jq -r '.[] | [.name, .archive_download_url] | @tsv' <<<"$BEST_ARTIFACTS")

mapfile -t APKS < <(find "$OUTDIR" -maxdepth 1 -type f -name '*-arm64-v8a-release.apk' -print | sort)
(( ${#APKS[@]} > 0 )) || {
  echo "::error::兼容 Manager artifact 中未找到 arm64-v8a release APK"
  exit 1
}

UPSTREAM_STATUS="AT_PIN"
if [[ "$LATEST_SHA" != "$OS4_BAKASU_COMMIT" ]]; then
  if git -C "$WORKDIR/BakaSU" merge-base --is-ancestor "$OS4_BAKASU_COMMIT" "$LATEST_SHA"; then
    AHEAD_COUNT="$(git -C "$WORKDIR/BakaSU" rev-list --count "$OS4_BAKASU_COMMIT..$LATEST_SHA")"
    UPSTREAM_STATUS="NEWER_AVAILABLE_$AHEAD_COUNT"
  else
    UPSTREAM_STATUS="DIVERGED"
  fi
fi

{
  echo "BAKASU_TARGET_COMMIT=$TARGET_COMMIT"
  echo "BAKASU_VALIDATED_REFERENCE=$OS4_BAKASU_COMMIT"
  echo "BAKASU_KERNEL_KSU_VERSION=$TARGET_KSU_VERSION"
  echo "BAKASU_UPSTREAM_HEAD=$LATEST_SHA"
  echo "BAKASU_UPSTREAM_STATUS=$UPSTREAM_STATUS"
  echo "MANAGER_RUN_ID=$BEST_RUN_ID"
  echo "MANAGER_HEAD_SHA=$BEST_HEAD_SHA"
  echo "MANAGER_HEAD_BRANCH=$BEST_HEAD_BRANCH"
  echo "MANAGER_KSU_VERSION=$BEST_VERSION"
  printf 'MANAGER_APKS='
  printf '%s;' "${APKS[@]##*/}"
  echo
} > "$OUTDIR/manager-metadata.txt"

(
  cd "$OUTDIR"
  sha256sum ./*.apk > MANAGER-SHA256SUMS.txt
)

cat "$OUTDIR/manager-metadata.txt"
cat "$OUTDIR/MANAGER-SHA256SUMS.txt"

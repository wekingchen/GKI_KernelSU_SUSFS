#!/usr/bin/env bash
# 上游完整镜像门禁：上游已存在的所有文件都必须在本仓保持原路径、原内容。
# 本仓功能只能使用新增的独立文件，或在构建期修改临时下载的内核源码。
set -euo pipefail

UPSTREAM_REPO="${XIAOMI_UPSTREAM_REPO:-https://github.com/zzh20188/GKI_KernelSU_SUSFS.git}"
UPSTREAM_REF="${XIAOMI_UPSTREAM_REF:-dev}"
BASE_REF="${1:-origin/dev}"
SCAN_MODE="${2:---committed}"
git rev-parse --is-inside-work-tree >/dev/null
git rev-parse --verify HEAD >/dev/null
git rev-parse --verify "$BASE_REF" >/dev/null || {
  echo "::error::Base ref not found: $BASE_REF"; exit 1;
}

if git remote get-url xiaomi-upstream >/dev/null 2>&1; then
  git remote set-url xiaomi-upstream "$UPSTREAM_REPO"
else
  git remote add xiaomi-upstream "$UPSTREAM_REPO"
fi
git fetch -q --no-tags xiaomi-upstream "$UPSTREAM_REF"
UPSTREAM_SHA="$(git rev-parse FETCH_HEAD)"

# 以上游为左侧做全量树比对。仅允许 fork 新增文件：
# M=共用文件遭修改，D=被删除，T=类型变化；重命名通过 --no-renames 当删除处理。
mapfile -t violations < <(
  git diff --no-renames --name-only --diff-filter=DMT "$UPSTREAM_SHA" HEAD
)

case "$SCAN_MODE" in
  --committed) ;;
  --worktree)
    # LKG 生成结果尚未提交时，也禁止修改或删除上游的共用文件。
    mapfile -t dirty < <(
      { git diff --name-only HEAD; git diff --cached --name-only HEAD; } | LC_ALL=C sort -u
    )
    for path in "${dirty[@]}"; do
      if git cat-file -e "$UPSTREAM_SHA:$path" 2>/dev/null; then
        violations+=("$path")
      fi
    done
    ;;
  *)
    echo "::error::Unknown isolation scan mode: $SCAN_MODE"
    exit 1
    ;;
esac

echo "Upstream exact mirror: $UPSTREAM_REPO@$UPSTREAM_REF ($UPSTREAM_SHA)"
echo "Fork HEAD: $(git rev-parse HEAD)"
if (( ${#violations[@]} )); then
  echo "::error::上游原始文件被修改、删除，或上游新增文件尚未同步："
  printf '  - %s\n' "${violations[@]}"
  echo "::error::请同步原始文件；本仓功能必须移入独立路径或构建时补丁。"
  exit 1
fi
echo "XIAOMI_UPSTREAM_EXACT_MIRROR=PASS"
echo "XIAOMI_UPSTREAM_ISOLATION=PASS"

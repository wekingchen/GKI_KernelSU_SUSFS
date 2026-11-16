#!/usr/bin/env bash
set -euo pipefail

UPSTREAM_REPO="${XIAOMI_UPSTREAM_REPO:-https://github.com/zzh20188/GKI_KernelSU_SUSFS.git}"
UPSTREAM_REF="${XIAOMI_UPSTREAM_REF:-dev}"
BASE_REF="${1:-origin/dev}"

git rev-parse --is-inside-work-tree >/dev/null
git rev-parse --verify HEAD >/dev/null

if ! git remote get-url xiaomi-upstream >/dev/null 2>&1; then
  git remote add xiaomi-upstream "$UPSTREAM_REPO"
else
  git remote set-url xiaomi-upstream "$UPSTREAM_REPO"
fi

git fetch -q --no-tags xiaomi-upstream "$UPSTREAM_REF"
UPSTREAM_SHA="$(git rev-parse FETCH_HEAD)"

if ! git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
  echo "::error::Base ref not found: $BASE_REF"
  exit 1
fi

SCAN_MODE="${2:---committed}"
case "$SCAN_MODE" in
  --committed)
    # PR changes relative to fork dev, including added/deleted paths.
    mapfile -t changed < <(git diff --name-only "$BASE_REF"...HEAD)
    ;;
  --worktree)
    # LKG promotion renders files before committing them. Include modified,
    # staged, and newly created (untracked) files in the isolation audit.
    mapfile -t changed < <(
      {
        git diff --name-only "$BASE_REF" --
        git diff --cached --name-only "$BASE_REF" --
        git ls-files --others --exclude-standard
      } | LC_ALL=C sort -u
    )
    ;;
  *)
    echo "::error::Unknown isolation scan mode: $SCAN_MODE"
    exit 1
    ;;
esac
# 合法上游同步专用例外：只接受以当前 fork base 为第一父提交、上游历史提交为
# 第二父提交的单次 merge，或 GitHub PR 自动生成的对应合并提交。
# 共享路径必须同时属于那次上游更新的文件集合；普通 Xiaomi PR 仍严格禁止改共享路径。
UPSTREAM_SYNC_ALLOW_PATHS=()
if [[ "$SCAN_MODE" == "--committed" ]]; then
  BASE_SHA="$(git rev-parse "$BASE_REF")"
  HEAD_SHA="$(git rev-parse HEAD)"
  PR_FIRST_PARENT="$(git rev-parse --verify HEAD^1 2>/dev/null || true)"
  PR_SECOND_PARENT="$(git rev-parse --verify HEAD^2 2>/dev/null || true)"
  for CANDIDATE in "$HEAD_SHA" "$PR_SECOND_PARENT"; do
    [[ -n "$CANDIDATE" ]] || continue
    read -r COMMIT_SHA FIRST_PARENT SECOND_PARENT EXTRA_PARENT < <(git rev-list -n 1 --parents "$CANDIDATE")
    [[ "$FIRST_PARENT" == "$BASE_SHA" && -n "${SECOND_PARENT:-}" && -z "${EXTRA_PARENT:-}" ]] || continue
    git merge-base --is-ancestor "$SECOND_PARENT" "$UPSTREAM_SHA" || continue
    if [[ "$CANDIDATE" != "$HEAD_SHA" ]]; then
      [[ "$PR_FIRST_PARENT" == "$BASE_SHA" && "$PR_SECOND_PARENT" == "$CANDIDATE" ]] || continue
    fi
    UPSTREAM_COMMON="$(git merge-base "$FIRST_PARENT" "$SECOND_PARENT")"
    mapfile -t UPSTREAM_SYNC_ALLOW_PATHS < <(git diff --name-only "$UPSTREAM_COMMON" "$SECOND_PARENT")
    echo "Verified upstream merge: $CANDIDATE (source $SECOND_PARENT)"
    break
  done
fi

violations=()

for path in "${changed[@]}"; do
  [[ -n "$path" ]] || continue
  if git cat-file -e "$UPSTREAM_SHA:$path" 2>/dev/null; then
    if (( ${#UPSTREAM_SYNC_ALLOW_PATHS[@]} )) && printf '%s\n' "${UPSTREAM_SYNC_ALLOW_PATHS[@]}" | grep -Fxq -- "$path"; then
      echo "Accepted upstream-only change: $path"
      continue
    fi
    violations+=("$path")
  fi
done

echo "Xiaomi isolation base: $BASE_REF (mode=$SCAN_MODE)"
echo "Upstream: $UPSTREAM_REPO@$UPSTREAM_REF ($UPSTREAM_SHA)"
echo "Changed files: ${#changed[@]}"

if (( ${#violations[@]} )); then
  echo "::error::Xiaomi customization modified upstream-shared files:"
  printf '  - %s\n' "${violations[@]}"
  echo "::error::Move Xiaomi changes into new dedicated files/directories instead."
  exit 1
fi

echo "XIAOMI_UPSTREAM_ISOLATION=PASS"

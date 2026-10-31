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
violations=()

for path in "${changed[@]}"; do
  [[ -n "$path" ]] || continue
  if git cat-file -e "$UPSTREAM_SHA:$path" 2>/dev/null; then
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

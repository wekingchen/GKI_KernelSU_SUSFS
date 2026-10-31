#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/.github/config/xiaomi-sm8850-os4-6.12.69.env"
source "$ROOT/.github/config/pandora-os4-full-parity-lkg.env"

OUT="${1:-${RUNNER_TEMP:-/tmp}/xiaomi-os4-resolved-upstreams.env}"
TOKEN="${GH_TOKEN:-${GITHUB_TOKEN:-}}"

mkdir -p "$(dirname "$OUT")"

github_api() {
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

resolve_branch() {
  local repo_url="$1" branch="$2"
  local sha
  sha="$(git ls-remote --heads "$repo_url" "refs/heads/$branch" | awk 'NR==1 {print $1}')"
  [[ "$sha" =~ ^[0-9a-f]{40}$ ]] || {
    echo "::error::无法解析稳定分支 $repo_url / $branch"
    return 1
  }
  printf '%s\n' "$sha"
}

resolve_tag_commit() {
  local repo_url="$1" tag="$2"
  local refs sha
  refs="$(git ls-remote "$repo_url" "refs/tags/$tag" "refs/tags/$tag^{}")"
  sha="$(awk '$2 ~ /\^\{\}$/ {print $1; exit}' <<<"$refs")"
  if [[ -z "$sha" ]]; then
    sha="$(awk '$2 !~ /\^\{\}$/ {print $1; exit}' <<<"$refs")"
  fi
  [[ "$sha" =~ ^[0-9a-f]{40}$ ]] || {
    echo "::error::无法解析稳定 tag $repo_url / $tag"
    return 1
  }
  printf '%s\n' "$sha"
}

resolve_github_release() {
  local slug="$1" repo_url="$2"
  local rel tag sha
  rel="$(github_api "https://api.github.com/repos/$slug/releases/latest")"
  [[ "$(jq -r '.draft' <<<"$rel")" == "false" ]] || {
    echo "::error::$slug latest release unexpectedly marked draft"
    return 1
  }
  [[ "$(jq -r '.prerelease' <<<"$rel")" == "false" ]] || {
    echo "::error::$slug latest release unexpectedly marked prerelease"
    return 1
  }
  tag="$(jq -r '.tag_name' <<<"$rel")"
  [[ -n "$tag" && "$tag" != "null" ]] || {
    echo "::error::$slug latest stable release has no tag"
    return 1
  }
  sha="$(resolve_tag_commit "$repo_url" "$tag")"
  printf '%s\t%s\n' "$tag" "$sha"
}

BAKASU_REF="$OS4_BAKASU_REF"
BAKASU_KIND="branch"
BAKASU_COMMIT="$(resolve_branch "$OS4_BAKASU_REPO" "$BAKASU_REF")"
BAKASU_VERSION="$BAKASU_REF"

SUSFS_REF="$OS4_SUSFS_BRANCH"
SUSFS_KIND="branch"
SUSFS_COMMIT="$(resolve_branch "$OS4_SUSFS_REPO" "$SUSFS_REF")"
SUSFS_VERSION="$SUSFS_REF"

read -r NOMOUNT_REF NOMOUNT_COMMIT < <(
  resolve_github_release "$OS4_NOMOUNT_GITHUB_SLUG" "$OS4_NOMOUNT_REPO"
)
NOMOUNT_KIND="tag"
NOMOUNT_VERSION="$NOMOUNT_REF"

read -r DROIDSPACES_REF DROIDSPACES_COMMIT < <(
  resolve_github_release "$OS4_DROIDSPACES_GITHUB_SLUG" "$OS4_DROIDSPACES_REPO"
)
DROIDSPACES_KIND="tag"
DROIDSPACES_VERSION="$DROIDSPACES_REF"

NTSYNC_REF="$OS4_NTSYNC_PATCH_REF"
NTSYNC_KIND="branch"
NTSYNC_COMMIT="$(resolve_branch "$OS4_NTSYNC_PATCH_REPO" "$NTSYNC_REF")"
NTSYNC_VERSION="$NTSYNC_REF"

read -r BBG_REF BBG_COMMIT < <(
  resolve_github_release "$OS4_BBG_GITHUB_SLUG" "$OS4_BBG_REPO"
)
BBG_KIND="tag"
BBG_VERSION="$BBG_REF"

read -r REKERNEL_REF REKERNEL_COMMIT < <(
  resolve_github_release "$OS4_REKERNEL_GITHUB_SLUG" "$OS4_REKERNEL_REPO"
)
REKERNEL_KIND="tag"
REKERNEL_VERSION="$REKERNEL_REF"

changed=()
[[ "$BAKASU_COMMIT" == "$LKG_BAKASU_COMMIT" ]] || changed+=(BAKASU)
[[ "$SUSFS_COMMIT" == "$LKG_SUSFS_COMMIT" ]] || changed+=(SUSFS)
[[ "$NOMOUNT_COMMIT" == "$LKG_NOMOUNT_COMMIT" ]] || changed+=(NOMOUNT)
[[ "$DROIDSPACES_COMMIT" == "$LKG_DROIDSPACES_COMMIT" ]] || changed+=(DROIDSPACES)
[[ "$NTSYNC_COMMIT" == "$LKG_NTSYNC_PATCH_COMMIT" ]] || changed+=(NTSYNC)
[[ "$BBG_COMMIT" == "$LKG_BBG_COMMIT" ]] || changed+=(BBG)
[[ "$REKERNEL_COMMIT" == "$LKG_REKERNEL_COMMIT" ]] || changed+=(REKERNEL)

UPSTREAMS_MATCH_LKG=1
if (( ${#changed[@]} > 0 )); then
  UPSTREAMS_MATCH_LKG=0
fi
CHANGED_COMPONENTS="$(IFS=,; echo "${changed[*]}")"

{
  echo "RESOLVED_BAKASU_KIND=$BAKASU_KIND"
  echo "RESOLVED_BAKASU_REF=$BAKASU_REF"
  echo "RESOLVED_BAKASU_VERSION=$BAKASU_VERSION"
  echo "RESOLVED_BAKASU_COMMIT=$BAKASU_COMMIT"

  echo "RESOLVED_SUSFS_KIND=$SUSFS_KIND"
  echo "RESOLVED_SUSFS_REF=$SUSFS_REF"
  echo "RESOLVED_SUSFS_VERSION=$SUSFS_VERSION"
  echo "RESOLVED_SUSFS_COMMIT=$SUSFS_COMMIT"

  echo "RESOLVED_NOMOUNT_KIND=$NOMOUNT_KIND"
  echo "RESOLVED_NOMOUNT_REF=$NOMOUNT_REF"
  echo "RESOLVED_NOMOUNT_VERSION=$NOMOUNT_VERSION"
  echo "RESOLVED_NOMOUNT_COMMIT=$NOMOUNT_COMMIT"

  echo "RESOLVED_DROIDSPACES_KIND=$DROIDSPACES_KIND"
  echo "RESOLVED_DROIDSPACES_REF=$DROIDSPACES_REF"
  echo "RESOLVED_DROIDSPACES_VERSION=$DROIDSPACES_VERSION"
  echo "RESOLVED_DROIDSPACES_COMMIT=$DROIDSPACES_COMMIT"

  echo "RESOLVED_NTSYNC_KIND=$NTSYNC_KIND"
  echo "RESOLVED_NTSYNC_REF=$NTSYNC_REF"
  echo "RESOLVED_NTSYNC_VERSION=$NTSYNC_VERSION"
  echo "RESOLVED_NTSYNC_COMMIT=$NTSYNC_COMMIT"

  echo "RESOLVED_BBG_KIND=$BBG_KIND"
  echo "RESOLVED_BBG_REF=$BBG_REF"
  echo "RESOLVED_BBG_VERSION=$BBG_VERSION"
  echo "RESOLVED_BBG_COMMIT=$BBG_COMMIT"

  echo "RESOLVED_REKERNEL_KIND=$REKERNEL_KIND"
  echo "RESOLVED_REKERNEL_REF=$REKERNEL_REF"
  echo "RESOLVED_REKERNEL_VERSION=$REKERNEL_VERSION"
  echo "RESOLVED_REKERNEL_COMMIT=$REKERNEL_COMMIT"

  echo "UPSTREAMS_MATCH_LKG=$UPSTREAMS_MATCH_LKG"
  echo "CHANGED_COMPONENTS=$CHANGED_COMPONENTS"
} > "$OUT"

UPSTREAM_SET_SHA256="$(
  grep '^RESOLVED_.*_COMMIT=' "$OUT" | LC_ALL=C sort | sha256sum | awk '{print $1}'
)"
echo "UPSTREAM_SET_SHA256=$UPSTREAM_SET_SHA256" >> "$OUT"

cat "$OUT"

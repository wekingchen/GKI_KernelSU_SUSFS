#!/usr/bin/env bash
set -euo pipefail

XIAOMI_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
XIAOMI_REPO_ROOT="$(cd "$XIAOMI_SCRIPT_DIR/../.." && pwd)"
XIAOMI_CONFIG="$XIAOMI_REPO_ROOT/.github/config/xiaomi-sm8850-android16-6.12.23.env"

[[ -f "$XIAOMI_CONFIG" ]] || { echo "Missing config: $XIAOMI_CONFIG" >&2; exit 1; }
# shellcheck disable=SC1090
source "$XIAOMI_CONFIG"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

note() {
  echo "[xiaomi-sm8850] $*"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

validate_device() {
  case "$1" in
    "$XIAOMI_17_CODENAME"|"$XIAOMI_17_PRO_CODENAME"|"$XIAOMI_17_PRO_MAX_CODENAME") ;;
    *) die "unsupported SM8850 device codename: $1 (allowed: $SUPPORTED_DEVICES)" ;;
  esac
}

validate_variant() {
  case "$1" in
    base|resukisu|resukisu-susfs) ;;
    *) die "unsupported variant: $1 (allowed: base, resukisu, resukisu-susfs)" ;;
  esac
}

validate_source_profile() {
  case "$1" in
    gold-cctv|ack-r51) ;;
    *) die "unsupported source profile: $1 (allowed: gold-cctv, ack-r51)" ;;
  esac
}

device_marketing_name() {
  case "$1" in
    "$XIAOMI_17_CODENAME") echo "Xiaomi 17" ;;
    "$XIAOMI_17_PRO_CODENAME") echo "Xiaomi 17 Pro" ;;
    "$XIAOMI_17_PRO_MAX_CODENAME") echo "Xiaomi 17 Pro Max" ;;
    *) return 1 ;;
  esac
}

config_is_y() {
  local file="$1" key="$2"
  grep -qx "${key}=y" "$file"
}

config_is_not_y() {
  local file="$1" key="$2"
  ! grep -qx "${key}=y" "$file"
}

append_config() {
  local fragment="$1" line="$2" key
  key="${line%%=*}"
  if [[ "$line" == "# "* ]]; then
    key="${line#\# }"
    key="${key%% *}"
  fi
  sed -i -E "/^(${key}=|# ${key} is not set$)/d" "$fragment"
  printf '%s\n' "$line" >> "$fragment"
}

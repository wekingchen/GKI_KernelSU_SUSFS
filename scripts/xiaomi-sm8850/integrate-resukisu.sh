#!/usr/bin/env bash
set -euo pipefail

# Compatibility wrapper for callers that still reference the pre-rename script.
# New code should call integrate-bakasu.sh directly.
exec "$(cd "$(dirname "$0")" && pwd)/integrate-bakasu.sh" "$@"

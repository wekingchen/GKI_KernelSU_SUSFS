#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
UPSTREAM_URL="https://github.com/zzh20188/GKI_KernelSU_SUSFS.git"
UPSTREAM_REF="dev"
REPORT="${1:-${RUNNER_TEMP:-/tmp}/xiaomi-os4-upstream-drift.txt}"

cd "$ROOT"

git remote remove xiaomi-upstream-check >/dev/null 2>&1 || true
git remote add xiaomi-upstream-check "$UPSTREAM_URL"
trap 'git remote remove xiaomi-upstream-check >/dev/null 2>&1 || true' EXIT

git fetch -q --no-tags xiaomi-upstream-check "$UPSTREAM_REF"
UPSTREAM_HEAD="$(git rev-parse FETCH_HEAD)"
FORK_HEAD="$(git rev-parse HEAD)"

SYNC_STATUS="REVIEW_REQUIRED"
if git merge-base --is-ancestor "$UPSTREAM_HEAD" "$FORK_HEAD"; then
  SYNC_STATUS="UP_TO_DATE_OR_AHEAD"
fi

TMP_WORKFLOW="$(mktemp)"
git show "$UPSTREAM_HEAD:.github/workflows/kernel-custom.yml" > "$TMP_WORKFLOW"

python3 - "$TMP_WORKFLOW" "$REPORT" "$UPSTREAM_HEAD" "$FORK_HEAD" "$SYNC_STATUS" <<'PY'
from pathlib import Path
import re
import sys

workflow_path, report_path, upstream_head, fork_head, sync_status = sys.argv[1:]
text = Path(workflow_path).read_text(errors="replace")

keys = set()
inside = False
for line in text.splitlines():
    if line == "    inputs:":
        inside = True
        continue
    if inside and line.startswith("jobs:"):
        break
    m = re.match(r"^      ([A-Za-z0-9_]+):\s*$", line)
    if inside and m:
        keys.add(m.group(1))

# These are either mapped into the Xiaomi OS4 workflow or intentionally
# version-fixed / irrelevant to pandora OS4 R62.
mapped = {
    "kernelsu_variant",
    "ksu_mode",
    "droidspaces",
    "artifact_upload_mode",
    "use_bbg",
    "use_rekernel",
    "use_nomount",
    "use_networking",
    "cve_2026_43499_patch",
    "droidspaces_ntsync",
}
intentionally_fixed = {
    "kernel_version",
    "os_patch_level",
    "version",
    "build_time",
    "supp_op",
    "use_kpm",
}
pending = {
    # ZRAM/LZ4K/LZ4KD is intentionally not exposed until the current OS4
    # module-safe adaptation and real-device validation are complete.
    "use_zram",
}

unknown = sorted(keys - mapped - intentionally_fixed - pending)

lines = [
    f"UPSTREAM_HEAD={upstream_head}",
    f"FORK_HEAD={fork_head}",
    f"UPSTREAM_SYNC_STATUS={sync_status}",
    "UPSTREAM_CUSTOM_INPUTS=" + ",".join(sorted(keys)),
    "UPSTREAM_PENDING_MAPPED_INPUTS=" + ",".join(sorted(keys & pending)),
    "UPSTREAM_UNKNOWN_INPUTS=" + ",".join(unknown),
]
Path(report_path).write_text("\n".join(lines) + "\n")
print("\n".join(lines))

if unknown:
    print("::warning::上游 kernel-custom.yml 出现尚未分类的新输入: " + ", ".join(unknown))
if sync_status != "UP_TO_DATE_OR_AHEAD":
    print("::warning::当前 fork dev 尚未包含上游 dev 最新提交；先审查再同步，禁止自动覆盖 Xiaomi 路径。")
if keys & pending:
    print("::notice::上游已有 ZRAM 开关；OS4 当前保持待适配状态，不自动映射。")
PY

rm -f "$TMP_WORKFLOW"

#!/usr/bin/env bash
# Read-only bridge between the production OEM ABI gate and the OTA V2 interpreter.
# The original checker alone decides eligibility. This bridge never grants it.
set -euo pipefail

if [[ "$#" != 3 ]]; then
  echo "usage: run-ota-v2-diagnostics.sh ABI_REPORT DIAGNOSTIC_JSON DIAGNOSTIC_MD" >&2
  exit 2
fi
raw="$1"
output="$2"
markdown="$3"
[[ -f "$raw" && -s "$raw" ]] || {
  echo "::error::V2 diagnostic cannot find original OEM ABI report" >&2
  exit 2
}
python3 scripts/xiaomi-os4/ota-v2-abi-diagnostics.py \
  --abi-report "$raw" --output "$output" --markdown "$markdown"
[[ -s "$output" && -s "$markdown" ]] || {
  echo "::error::V2 diagnostics did not produce both evidence files" >&2
  exit 2
}

# Do not trust interpretation alone. Reconcile original checker gate and
# eligibility against diagnostic status; never modify the original report.
jq -e --slurpfile v2 "$output" '
  ($v2 | length) == 1 and
  ($v2[0].schema == 1) and
  ($v2[0].oem_gate == .gate) and
  ($v2[0].fastboot_boot_eligible == .eligible_for_fastboot_boot) and
  ($v2[0].persistent_install_authorized == false) and
  ($v2[0].lkg_promotion_authorized == false) and
  ($v2[0].auto_waiver_applied == false) and
  (
    if .gate == "BLOCKED" then
      .eligible_for_fastboot_boot == false and
      ($v2[0].status == "ABI_BLOCKED_DIAGNOSABLE" or
       $v2[0].status == "AUDIT_OR_INPUT_BLOCKED_REQUIRES_MANUAL_REVIEW")
    else
      .eligible_for_fastboot_boot == true and
      $v2[0].status == "STATIC_ABI_PASS_REQUIRES_REAL_DEVICE_TEST"
    end
  )
' "$raw" >/dev/null || {
  echo "::error::V2 interpretation disagrees with the original fail-closed OEM gate" >&2
  exit 2
}

status="$(jq -er '.status' "$output")"
echo "OTA_V2_DIAGNOSTIC_STATUS=$status"
if [[ -v GITHUB_STEP_SUMMARY ]]; then
  cat "$markdown" >> "$GITHUB_STEP_SUMMARY"
fi

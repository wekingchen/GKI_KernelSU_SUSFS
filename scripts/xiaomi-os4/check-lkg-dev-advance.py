#!/usr/bin/env python3
"""Fail-closed policy for rebasing a verified, staged OTA LKG after benign dev changes.

This is NOT a general-purpose bypass of the LKG branch-immutability gate.
Only narrow OTA companion/evidence/docs changes can be absorbed. Kernel,
LKG, stock input, build/workflow policy and unknown paths must fail closed.
"""
from __future__ import annotations

import argparse
from pathlib import Path

BENIGN_PREFIXES = (
    "docs/",
    "tools/pandora-ota-companion/",
)
BENIGN_EXACT = frozenset({
    ".github/workflows/pandora-os4-ota-companion-emulator.yml",
    ".github/workflows/pandora-os4-ota-diagnostic-intake.yml",
    ".github/workflows/pandora-os4-ota-v2-evidence-replay.yml",
    ".github/workflows/xiaomi-sm8850-os4-ota-auto-candidate.yml",
    "scripts/xiaomi-os4/make-ota-v2-diagnostic-task.py",
    "scripts/xiaomi-os4/test_ota_v2_diagnostic_task.py",
    "scripts/xiaomi-os4/verify-ota-v2-diagnostic-evidence.py",
})


def rejected(paths: list[str]) -> list[str]:
    """Reject any unknown changes, malformed paths, or sensitive path."""
    invalid = []
    for path in paths:
        if (not path or path.startswith("/") or "\\" in path or
                ".." in path.split("/") or path.strip() != path or
                any(ord(ch) < 32 or ord(ch) > 126 for ch in path) or
                not (path in BENIGN_EXACT or
                     any(path.startswith(prefix) for prefix in BENIGN_PREFIXES))):
            invalid.append(path)
    return invalid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths-file", type=Path, required=True)
    args = ap.parse_args()
    paths = args.paths_file.read_text(encoding="utf-8").splitlines()
    if not paths:
        raise SystemExit("LKG DEV ADVANCE DENIED: empty change set")
    bad = rejected(paths)
    if bad:
        raise SystemExit("LKG DEV ADVANCE DENIED: non-benign or unsafe paths: " +
                         repr(bad[:20]))
    print(f"LKG_DEV_ADVANCE_BENIGN=PASS paths={len(paths)}")


if __name__ == "__main__":
    main()

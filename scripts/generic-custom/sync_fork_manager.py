#!/usr/bin/env python3
"""从上游 get-manager.yml 确定性生成 BakaSU Manager 隔离副本。"""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = ROOT / ".github/workflows/get-manager.yml"
PRIVATE = ROOT / ".github/workflows/get-manager-fork.yml"

# Upstream already filters BakaSU PR runs by event. Keep that upstream logic
# untouched; this private overlay only validates the APK's embedded KSU version.
ANCHOR = """            if ! download_bakasu_spoof; then
              echo "::warning::没有可下载且版本不高于目标内核的 BakaSU Spoofed Manager，本次仅附带普通版。"
            fi
            find manager-artifacts -type f -name "*.apk" -print""".encode("utf-8")

OVERLAY = """            if ! download_bakasu_spoof; then
              echo "::warning::没有可下载且版本不高于目标内核的 BakaSU Spoofed Manager，本次仅附带普通版。"
            fi

            mapfile -t BAKASU_APKS < <(find manager-artifacts -type f -name "*-arm64-v8a-release.apk" -print)
            if [ "${#BAKASU_APKS[@]}" -eq 0 ]; then
              echo "未找到 BakaSU arm64-v8a release 管理器。"
              exit 1
            fi

            for APK in "${BAKASU_APKS[@]}"; do
              APK_NAME=$(basename "$APK")
              if [[ "$APK_NAME" =~ _([0-9]+)-arm64-v8a-release\\.apk$ ]]; then
                APK_KSU_VERSION="${BASH_REMATCH[1]}"
              else
                echo "::error::无法从 BakaSU Manager 文件名解析版本码: $APK_NAME"
                exit 1
              fi
              if [ "$APK_KSU_VERSION" -gt "$TARGET_KSU_VERSION" ]; then
                echo "::error::BakaSU Manager 版本 $APK_KSU_VERSION 高于内核版本 $TARGET_KSU_VERSION: $APK_NAME"
                exit 1
              fi
              echo "BakaSU Manager 版本校验通过: $APK_NAME (KSU $APK_KSU_VERSION <= $TARGET_KSU_VERSION)"
            done

            printf '%s\\n' "${BAKASU_APKS[@]}" """.rstrip().encode("utf-8")


def generate() -> bytes:
    data = ORIGINAL.read_bytes()
    if OVERLAY in data:
        return data
    count = data.count(ANCHOR)
    if count != 1:
        raise RuntimeError(
            "上游 Manager BakaSU 下载区锚点变化，拒绝猜测式补丁重放；"
            f"expected=1 actual={count}"
        )
    return data.replace(ANCHOR, OVERLAY, 1)


def main():
    cli = argparse.ArgumentParser()
    modes = cli.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--write", action="store_true")
    args = cli.parse_args()
    data = generate()
    if args.write:
        PRIVATE.write_bytes(data)
        print("已从当前上游原件确定性生成 BakaSU Manager 隔离副本")
    else:
        actual = PRIVATE.read_bytes() if PRIVATE.exists() else b""
        if actual != data:
            limit = min(len(actual), len(data))
            first = next((i for i in range(limit) if actual[i] != data[i]), limit)
            raise SystemExit(
                "fork-only Manager 偏离了上游原件+确定性 BakaSU 版本校验叠加；"
                f"expected_bytes={len(data)} actual_bytes={len(actual)} first_diff={first} "
                f"expected={data[first:first+32]!r} actual={actual[first:first+32]!r}"
            )
        print("Manager 私有副本可复现：PASS")


if __name__ == "__main__":
    main()

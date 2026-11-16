#!/usr/bin/env python3
"""从原样上游 kernel-custom.yml 生成本仓 K50 Pro 隔离入口，来源不匹配则失败。"""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / ".github/workflows/kernel-custom.yml"
TARGET = ROOT / ".github/workflows/kernel-custom-fork.yml"

def replace_one(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError("上游自定义构建入口结构已变化，拒绝误改：" + old)
    return source.replace(old, new, 1)

def render():
    data = SOURCE.read_text(encoding="utf-8")
    for old, new in (
        ("name: Android 内核构建-自定义", "name: Android 内核构建-自定义（本仓隔离修复版）"),
        ("    uses: ./.github/workflows/build.yml", "    uses: ./.github/workflows/build-fork-custom.yml"),
        ("    uses: ./.github/workflows/get-manager.yml", "    uses: ./.github/workflows/get-manager-fork.yml"),
    ):
        data = replace_one(data, old, new)
    if "ksu_variant: ${{ inputs.kernelsu_variant }}" not in data:
        raise ValueError("KSU 变体参数不再透传，拒绝更新本仓隔离入口")
    return data.encode("utf-8")

def main():
    p = argparse.ArgumentParser()
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    opt = p.parse_args()
    data = render()
    if opt.write:
        TARGET.write_bytes(data)
        print("已更新独立 K50 Pro 入口")
    elif not TARGET.exists() or TARGET.read_bytes() != data:
        raise SystemExit("K50 Pro 私有入口与上游+独立补丁不一致")
    else:
        print("K50 Pro 入口来源验证通过")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""从上游 get-manager.yml + 私有补丁生成 BakaSU Manager 专用的隔离副本。"""
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = ROOT / ".github/workflows/get-manager.yml"
PRIVATE = ROOT / ".github/workflows/get-manager-fork.yml"
PATCH = ROOT / "scripts/generic-custom/get-manager-fork.patch"

def generate():
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / ".github/workflows/get-manager-fork.yml"
        output.parent.mkdir(parents=True)
        output.write_bytes(ORIGINAL.read_bytes())
        run = subprocess.run(
            ["patch", "--batch", "--fuzz=0", "-p1", "-d", tmp, "-i", str(PATCH)],
            capture_output=True, text=True, check=False)
        if run.returncode:
            raise RuntimeError("上游 Manager 接口变化，私有补丁无法无损重放："
                               + run.stdout + run.stderr)
        return output.read_bytes()

def main():
    cli = argparse.ArgumentParser()
    modes = cli.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--write", action="store_true")
    args = cli.parse_args()
    data = generate()
    if args.write:
        PRIVATE.write_bytes(data)
        print("已在 fork-only 工作流中重放 BakaSU Manager 修复")
    elif not PRIVATE.exists() or PRIVATE.read_bytes() != data:
        raise SystemExit("fork-only Manager 偏离了上游+补丁结果")
    else:
        print("Manager 私有副本可复现：PASS")

if __name__ == "__main__":
    main()

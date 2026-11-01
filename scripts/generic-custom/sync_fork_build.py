#!/usr/bin/env python3
"""Rebase the fork-only GKI build onto upstream without touching shared files.

Three-way merge (last fork-only base, previous upstream, latest upstream).
Conflicts, drift, and moved patch anchors must fail closed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

NAME_OLD = "name: 内核构建流程\n"
NAME_NEW = "name: 内核构建流程（本仓自定义隔离修复版）\n"
TIME_OLD = "    timeout-minutes: 60\n"
TIME_NEW = "    timeout-minutes: 360\n"
ENV_OLD = '      CCACHE_HARDLINK: "true"\n'
ENV_NEW = ENV_OLD + '      JOBS: "2"\n      MAKEFLAGS: "-j2 -l2"\n      NINJAFLAGS: "-j2"\n'
RETRY_OLD = "          timeout_minutes: 30\n          max_attempts: 3\n"
RETRY_NEW = "          timeout_minutes: 120\n          max_attempts: 2\n"
COMPILE_ANCHOR = "      - name: 编译内核\n"
PRIVATE_STEPS = r'''      # Private fork-only compatibility for the Android12 / 5.10 toolchain.
      - name: "修复 BBG HOST ld（仅修改 Runner 下载的构建树）"
        if: inputs.use_bbg && inputs.kernel_version == '5.10'
        shell: bash
        run: |
          set -euo pipefail
          bash "$GITHUB_WORKSPACE/scripts/generic-custom/prepare-host-linker.sh" "$KERNEL_ROOT"
      - name: "GKI LTO 资源保护（不修改内核编译选项）"
        shell: bash
        run: |
          set -euo pipefail
          echo "使用 JOBS=${JOBS} MAKEFLAGS=${MAKEFLAGS} 限制并行，保留实际 GKI LTO 编译模式"
          free -h
          df -h "$RUNNER_TEMP"
          avail="$(df -BG --output=avail "$RUNNER_TEMP" | tail -n 1 | tr -dc '0-9')"
          if [[ "$avail" =~ ^[0-9]+$ ]] && (( avail >= 25 )); then
            SWAP="/mnt/gki-generic-build.swap"
            if sudo fallocate -l 8G "$SWAP" &&
               sudo chmod 600 "$SWAP" &&
               sudo mkswap "$SWAP" >/dev/null &&
               sudo swapon "$SWAP"; then
              echo "已添加 8GiB swap 用于大型 LTO 链接"
            else
              echo "::warning::Runner 无法开启 swap，只使用低并发构建"
              sudo swapoff "$SWAP" 2>/dev/null || true
              sudo rm -f "$SWAP" || true
            fi
          else
            echo "::warning::磁盘不足 25GiB，避免 swap 造成磁盘耗尽"
          fi
          free -h

'''


def git_blob_sha(text: str) -> str:
    b = text.encode("utf-8")
    return hashlib.sha1(b"blob " + str(len(b)).encode() + b"\0" + b).hexdigest()


def replace_one(s: str, before: str, after: str) -> str:
    if s.count(before) != 1:
        raise ValueError("patch anchor changed or duplicated: " + repr(before[:80]))
    return s.replace(before, after, 1)


def render(base: str) -> str:
    s = base
    for old, new in ((NAME_OLD, NAME_NEW), (TIME_OLD, TIME_NEW),
                     (ENV_OLD, ENV_NEW), (RETRY_OLD, RETRY_NEW),
                     (COMPILE_ANCHOR, PRIVATE_STEPS + COMPILE_ANCHOR)):
        s = replace_one(s, old, new)
    return s


def unrender(custom: str) -> str:
    s = custom
    for old, new in ((PRIVATE_STEPS + COMPILE_ANCHOR, COMPILE_ANCHOR),
                     (RETRY_NEW, RETRY_OLD), (ENV_NEW, ENV_OLD),
                     (TIME_NEW, TIME_OLD), (NAME_NEW, NAME_OLD)):
        s = replace_one(s, old, new)
    return s


def validate(base: str, custom: str) -> None:
    if unrender(custom) != base or render(base) != custom:
        raise ValueError("private build is not a reversible deterministic overlay")
    for token in ("workflow_call:", "  build-kernel:", "      - name: 编译内核",
                  "retry_on: timeout", "nick-fields/retry@v4",
                  "inputs.use_bbg", "BUILD_CONFIG=common/build.config.gki.aarch64 build/build.sh",
                  "CONFIG_LTO_CLANG_THIN=y", "SUSFS", "BakaSU", "AnyKernel3"):
        if token not in custom:
            raise ValueError("required safety/build contract removed: " + token)


def three_way(local: str, old: str, new: str) -> str:
    if old == new:
        return local
    with tempfile.TemporaryDirectory() as tmp:
        paths = [Path(tmp) / n for n in ("local", "ancestor", "upstream")]
        for path, content in zip(paths, (local, old, new)):
            path.write_text(content, encoding="utf-8")
        result = subprocess.run(
            ["git", "merge-file", "-p", *(str(p) for p in paths)],
            capture_output=True, text=True, check=False)
        if result.returncode:
            raise ValueError("upstream incompatible with local changes; three-way merge "
                             "rejected: " + result.stderr[-1500:])
        if "<<<<<<<" in result.stdout or ">>>>>>>" in result.stdout:
            raise ValueError("unresolved merge marker")
        return result.stdout


def sync(state: dict, old: str, new: str, custom: str) -> tuple[dict, str, bool]:
    if (state.get("schema") != 1 or
            state.get("upstream_repository") != "zzh20188/GKI_KernelSU_SUSFS"):
        raise ValueError("untrusted upstream tracking metadata")
    if git_blob_sha(old) != state.get("upstream_blob_sha"):
        raise ValueError("prior upstream base SHA does not match metadata")
    base = unrender(custom)
    if git_blob_sha(base) != state.get("private_base_blob_sha"):
        raise ValueError("untracked changes to generated fork build; won't overwrite")
    validate(base, custom)
    if git_blob_sha(old) == git_blob_sha(new):
        return state, custom, False
    merged = three_way(base, old, new)
    updated = render(merged)
    validate(merged, updated)
    nxt = {**state, "upstream_blob_sha": git_blob_sha(new),
           "private_base_blob_sha": git_blob_sha(merged)}
    return nxt, updated, True


def main():
    ap = argparse.ArgumentParser()
    for name in ("previous-upstream", "latest-upstream", "private-build", "state",
                 "output-build", "output-state"):
        ap.add_argument("--" + name, type=Path, required=True)
    a = ap.parse_args()
    state, build, changed = sync(
        json.loads(a.state.read_text(encoding="utf-8")),
        a.previous_upstream.read_text(encoding="utf-8"),
        a.latest_upstream.read_text(encoding="utf-8"),
        a.private_build.read_text(encoding="utf-8"))
    a.output_build.write_text(build, encoding="utf-8")
    a.output_state.write_text(json.dumps(state, sort_keys=True, indent=2) + "\n",
                              encoding="utf-8")
    print("UPSTREAM_CHANGED=" + str(changed).lower())
    print("UPSTREAM_BLOB_SHA=" + state["upstream_blob_sha"])


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        sys.exit("AUTO_SYNC_REJECTED: " + str(exc))

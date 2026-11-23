#!/usr/bin/env python3
"""只拒绝与上游最终原件确实不同的已继承文件，而非只按历史 diff 判断。

已从上游原样提前同步的文件可能被 Git 记为 fork 自己修改过：
若同一路径的 mode/type/blob 完全一致，允许把缺失的上游提交纳入历史。
"""
import argparse
from pathlib import Path
import subprocess


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], stderr=subprocess.PIPE)


def tree_entry(commit: str, path: str) -> bytes:
    # ls-tree -z includes mode, type, SHA and path; verifies symlinks/file modes.
    output = git("ls-tree", "-z", commit, "--", path)
    chunks = [entry for entry in output.split(b"\0") if entry]
    needle = b"\t" + path.encode("utf-8", "surrogateescape")
    matches = [entry for entry in chunks if entry.endswith(needle)]
    return matches[0].split(b"\t", 1)[0] if len(matches) == 1 else b""


def differing_inherited_files(common: str, fork: str, upstream: str) -> list[str]:
    modified = git("diff", "--no-renames", "--name-only", "-z",
                   "--diff-filter=DMT", common, fork)
    paths = [
        p.decode("utf-8", "surrogateescape")
        for p in modified.split(b"\0") if p
    ]
    # A deleted file never matches a present upstream file; if both branches
    # independently delete the same inherited path that is safe to merge.
    return [
        p for p in paths
        if tree_entry(fork, p) != tree_entry(upstream, p)
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--common", required=True)
    parser.add_argument("--fork", required=True)
    parser.add_argument("--upstream", required=True)
    args = parser.parse_args()
    bad = differing_inherited_files(args.common, args.fork, args.upstream)
    if bad:
        print("::error::以下上游已继承文件与上游当前原件不一致，拒绝自动合并：")
        for p in bad:
            print(f"  - {p}")
        raise SystemExit(1)
    print("上游继承路径核验通过：既有变动均与上游最新的模式、类型和内容完全一致")


if __name__ == "__main__":
    main()

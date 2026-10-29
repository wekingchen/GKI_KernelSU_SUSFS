#!/usr/bin/env python3
"""Fail-closed SUSFS smaps_rollup compatibility for GKI android16-6.12-2026-03_r62.

Only the two obsolete upstream hunks for show_smaps_rollup() are removed.
The two skipped semantics are reintroduced through uniquely matched R62
source anchors. Never use on the legacy 6.12.23 Gold path.
"""
from __future__ import annotations

import argparse
from pathlib import Path

EXPECTED = {"rollup-obsolete-jump", "rollup-obsolete-label"}


def fail(reason: str) -> None:
    raise SystemExit(f"OS4 SUSFS compatibility ERROR: {reason}")


def classify(path: str | None, header: str, body: str) -> str | None:
    if path != "fs/proc/task_mmu.c" or "show_smaps_rollup" not in header:
        return None
    if "goto bypass_orig_flow;" in body:
        if "if (vma->vm_start < last_vma_end)" not in body:
            fail("obsolete jump hunk changed unexpectedly")
        return "rollup-obsolete-jump"
    if "+bypass_orig_flow:" in body:
        if "last_vma_end = vma->vm_end;" not in body:
            fail("obsolete label hunk changed unexpectedly")
        return "rollup-obsolete-label"
    return None


def filter_patch(src: Path, dst: Path) -> None:
    lines = src.read_text().splitlines(keepends=True)
    out: list[str] = []
    removed: list[str] = []
    current_file: str | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("diff --git "):
            fields = line.strip().split()
            if len(fields) != 4 or not fields[2].startswith("a/"):
                fail(f"invalid diff header: {line.strip()}")
            current_file = fields[2][2:]
            out.append(line)
            i += 1
            continue
        if line.startswith("@@ "):
            j = i + 1
            while j < len(lines) and not lines[j].startswith(("@@ ", "diff --git ")):
                j += 1
            hunk = "".join(lines[i:j])
            kind = classify(current_file, line, hunk)
            if kind is not None:
                removed.append(kind)
            else:
                out.extend(lines[i:j])
            i = j
            continue
        out.append(line)
        i += 1
    if len(removed) != len(set(removed)) or set(removed) != EXPECTED:
        fail(f"upstream SUSFS layout drift: expected {sorted(EXPECTED)}, got {removed}")
    dst.write_text("".join(out))
    print("OS4 SUSFS: removed exactly two R62-incompatible upstream hunks")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        fail(f"{label}: expected exactly one R62 anchor; found {count}")
    return text.replace(old, new, 1)


def port_source(target: Path) -> None:
    text = target.read_text()
    if "SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file))" not in text:
        fail("upstream show_smap hook missing; filtered upstream patch must be applied first")
    if "#include <linux/susfs_def.h>" not in text:
        fail("upstream SUSFS header hook is missing")
    if "susfs_bypass_rollup_vma" in text:
        fail("OS4 compatibility hook already present")

    original = (
        "\tvma_start = vma->vm_start;\n"
        "\tdo {\n"
        "\t\tsmap_gather_stats(vma, &mss, 0);\n"
        "\t\tlast_vma_end = vma->vm_end;\n"
    )
    replacement = (
        "\tvma_start = vma->vm_start;\n"
        "\tdo {\n"
        "#ifdef CONFIG_KSU_SUSFS_SUS_MAP\n"
        "\t\tif (!(vma->vm_file && SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file))))\n"
        "#endif\n"
        "\t\t\tsmap_gather_stats(vma, &mss, 0);\n"
        "\t\tlast_vma_end = vma->vm_end;\n"
    )
    text = replace_once(text, original, replacement, "primary rollup VMA loop")

    original = (
        "\t\t\tvma = vma_next(&vmi);\n"
        "\t\t\t/* Case 3 above */\n"
        "\t\t\tif (!vma)\n"
        "\t\t\t\tbreak;\n\n"
        "\t\t\t/* Case 1 and 2 above */\n"
    )
    replacement = (
        "\t\t\tvma = vma_next(&vmi);\n"
        "\t\t\t/* Case 3 above */\n"
        "\t\t\tif (!vma)\n"
        "\t\t\t\tbreak;\n\n"
        "#ifdef CONFIG_KSU_SUSFS_SUS_MAP\n"
        "\t\t\t/* Skip hidden VMA after mmap_lock contention, preserving range bounds. */\n"
        "\t\t\tif (vma->vm_file && SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file))) {\n"
        "\t\t\t\tif (vma->vm_end > last_vma_end)\n"
        "\t\t\t\t\tlast_vma_end = vma->vm_end;\n"
        "\t\t\t\tcontinue;\n"
        "\t\t\t}\n"
        "#endif\n\n"
        "\t\t\t/* Case 1 and 2 above */\n"
    )
    text = replace_once(text, original, replacement, "resumed rollup VMA loop")
    if text.count("SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file))") < 3:
        fail("missing SUSFS hidden-mapping hooks after port")
    target.write_text(text)
    print("OS4 SUSFS: primary and resumed R62 smaps_rollup hooks installed")


def main() -> None:
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="command", required=True)
    a = subs.add_parser("filter-patch")
    a.add_argument("input", type=Path)
    a.add_argument("output", type=Path)
    b = subs.add_parser("port-source")
    b.add_argument("task_mmu_file", type=Path)
    args = parser.parse_args()
    if args.command == "filter-patch":
        filter_patch(args.input, args.output)
    else:
        port_source(args.task_mmu_file)


if __name__ == "__main__":
    main()

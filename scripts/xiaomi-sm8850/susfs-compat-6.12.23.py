#!/usr/bin/env python3
"""Temporary Xiaomi Android 16 / Linux 6.12.23 SUSFS compatibility layer.

This helper is intentionally narrow. It is used only when the upstream
gki-android16-6.12 patch does not apply cleanly to the pinned 6.12.23 trees.
If upstream starts applying cleanly again, integrate-susfs.sh bypasses this
helper completely.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re

COMPAT_ID = "xiaomi-6.12.23-susfs-r1"

EXPECTED_DROPPED_HUNKS = {
    "exec-include",
    "task-show-smap",
    "task-rollup-skip",
    "task-rollup-label",
}


def fail(message: str):
    raise SystemExit(f"ERROR: {message}")


def identify_hunk(path: str | None, header: str, body: str) -> str | None:
    if path == "fs/exec.c":
        if (
            "#include <linux/susfs_def.h>" in body
            and "#include <linux/dma-buf.h>" in body
        ):
            return "exec-include"

    if path == "fs/proc/task_mmu.c" and "show_smap" in header:
        if "vma_data_pages(vma)" in body and "SUSFS_IS_INODE_SUS_MAP" in body:
            return "task-show-smap"

    if path == "fs/proc/task_mmu.c" and "show_smaps_rollup" in header:
        if "goto bypass_orig_flow;" in body:
            return "task-rollup-skip"
        if "+bypass_orig_flow:" in body:
            return "task-rollup-label"

    return None


def filter_patch(source: Path, destination: Path) -> None:
    lines = source.read_text().splitlines(keepends=True)
    out: list[str] = []
    removed: list[str] = []
    current_file: str | None = None

    i = 0
    while i < len(lines):
        line = lines[i]

        if line.startswith("diff --git "):
            parts = line.strip().split()
            if len(parts) != 4 or not parts[2].startswith("a/"):
                fail(f"unexpected diff header: {line.strip()}")
            current_file = parts[2][2:]
            out.append(line)
            i += 1
            continue

        if line.startswith("@@ "):
            j = i + 1
            while (
                j < len(lines)
                and not lines[j].startswith("@@ ")
                and not lines[j].startswith("diff --git ")
            ):
                j += 1
            hunk = "".join(lines[i:j])
            key = identify_hunk(current_file, line, hunk)
            if key is not None:
                removed.append(key)
            else:
                out.extend(lines[i:j])
            i = j
            continue

        out.append(line)
        i += 1

    if len(removed) != len(set(removed)):
        fail(f"duplicate known compatibility hunks found: {removed}")

    removed_set = set(removed)
    if removed_set != EXPECTED_DROPPED_HUNKS:
        missing = sorted(EXPECTED_DROPPED_HUNKS - removed_set)
        extra = sorted(removed_set - EXPECTED_DROPPED_HUNKS)
        fail(
            "upstream SUSFS patch layout changed; "
            f"missing_known={missing} unexpected={extra}"
        )

    destination.write_text("".join(out))
    print(
        f"[xiaomi-sm8850] prepared {COMPAT_ID} filtered upstream patch; "
        f"dropped={','.join(sorted(removed_set))}"
    )


def kernel_version(common: Path) -> tuple[int, int, int]:
    makefile = (common / "Makefile").read_text()
    values: dict[str, int] = {}
    for key in ("VERSION", "PATCHLEVEL", "SUBLEVEL"):
        match = re.search(rf"^{key}\s*=\s*(\d+)\s*$", makefile, re.MULTILINE)
        if not match:
            fail(f"unable to read {key} from {common / 'Makefile'}")
        values[key] = int(match.group(1))
    return values["VERSION"], values["PATCHLEVEL"], values["SUBLEVEL"]


def replace_once(text: str, old: str, new: str, description: str) -> str:
    count = text.count(old)
    if count != 1:
        fail(f"{description}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_source(common: Path) -> None:
    if kernel_version(common) != (6, 12, 23):
        fail("compatibility layer is restricted to Linux 6.12.23")

    exec_path = common / "fs/exec.c"
    task_path = common / "fs/proc/task_mmu.c"
    if not exec_path.is_file() or not task_path.is_file():
        fail("expected fs/exec.c and fs/proc/task_mmu.c")

    exec_text = exec_path.read_text()
    if "susfs_is_current_proc_no_su()" not in exec_text:
        fail("filtered upstream patch did not add the expected execve SUSFS hook")

    include_block = (
        "#ifdef CONFIG_KSU_SUSFS\n"
        "#include <linux/susfs_def.h>\n"
        "#endif\n"
    )
    if include_block not in exec_text:
        anchor = "#include <linux/ksm.h>\n"
        if exec_text.count(anchor) != 1:
            fail("exec.c ksm include anchor changed")
        exec_text = exec_text.replace(anchor, anchor + include_block, 1)
    exec_path.write_text(exec_text)

    task_text = task_path.read_text()
    if "#include <linux/susfs_def.h>" not in task_text:
        fail("filtered upstream patch did not add task_mmu SUSFS definitions")

    show_smap_block = (
        "#ifdef CONFIG_KSU_SUSFS_SUS_MAP\n"
        "\tif (vma->vm_file) {\n"
        "\t\tif (SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file)))\n"
        "\t\t\treturn 0;\n"
        "\t}\n"
        "#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MAP\n\n"
    )
    if show_smap_block not in task_text:
        match = re.search(
            r"(static int show_smap\(struct seq_file \*m, void \*v\)\n"
            r"\{\n"
            r"\tstruct vm_area_struct \*vma = v;\n"
            r"\tstruct mem_size_stats mss = \{\};\n\n)"
            r"(\tif \(!vma_(?:data_)?pages\(vma\)\))",
            task_text,
        )
        if not match:
            fail("task_mmu show_smap layout changed")
        task_text = (
            task_text[: match.end(1)]
            + show_smap_block
            + task_text[match.start(2) :]
        )

    rollup_head_old = (
        "\tvma_start = vma->vm_start;\n"
        "\tdo {\n"
        "\t\tsmap_gather_stats(vma, &mss, 0);\n"
        "\t\tlast_vma_end = vma->vm_end;\n"
    )
    rollup_head_new = (
        "\tvma_start = vma->vm_start;\n"
        "\tdo {\n"
        "#ifdef CONFIG_KSU_SUSFS_SUS_MAP\n"
        "\t\tif (vma->vm_file && SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file)))\n"
        "\t\t\tgoto susfs_bypass_rollup_vma;\n"
        "#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MAP\n"
        "\t\tsmap_gather_stats(vma, &mss, 0);\n"
        "#ifdef CONFIG_KSU_SUSFS_SUS_MAP\n"
        "susfs_bypass_rollup_vma:\n"
        "#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MAP\n"
        "\t\tlast_vma_end = vma->vm_end;\n"
    )
    if "susfs_bypass_rollup_vma:" not in task_text:
        task_text = replace_once(
            task_text,
            rollup_head_old,
            rollup_head_new,
            "task_mmu rollup main-loop layout",
        )

    contended_old = (
        "\t\t\tvma = vma_next(&vmi);\n"
        "\t\t\t/* Case 3 above */\n"
        "\t\t\tif (!vma)\n"
        "\t\t\t\tbreak;\n\n"
        "\t\t\t/* Case 1 and 2 above */\n"
    )
    contended_new = (
        "\t\t\tvma = vma_next(&vmi);\n"
        "\t\t\t/* Case 3 above */\n"
        "\t\t\tif (!vma)\n"
        "\t\t\t\tbreak;\n\n"
        "#ifdef CONFIG_KSU_SUSFS_SUS_MAP\n"
        "\t\t\t/* 6.12.23 consumes the resumed VMA inside this loop. */\n"
        "\t\t\tif (vma->vm_file && SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file))) {\n"
        "\t\t\t\tlast_vma_end = vma->vm_end;\n"
        "\t\t\t\tcontinue;\n"
        "\t\t\t}\n"
        "#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MAP\n\n"
        "\t\t\t/* Case 1 and 2 above */\n"
    )
    if "6.12.23 consumes the resumed VMA inside this loop." not in task_text:
        task_text = replace_once(
            task_text,
            contended_old,
            contended_new,
            "task_mmu rollup resumed-VMA layout",
        )

    for marker in (
        "SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file))",
        "susfs_bypass_rollup_vma:",
        "6.12.23 consumes the resumed VMA inside this loop.",
    ):
        if marker not in task_text:
            fail(f"task_mmu compatibility marker missing: {marker}")

    task_path.write_text(task_text)

    marker = common.parent / ".xiaomi-susfs-integration-mode"
    marker.write_text(COMPAT_ID + "\n")
    print(f"[xiaomi-sm8850] applied {COMPAT_ID} source compatibility")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p_filter = sub.add_parser("filter-patch")
    p_filter.add_argument("source", type=Path)
    p_filter.add_argument("destination", type=Path)

    p_source = sub.add_parser("patch-source")
    p_source.add_argument("common", type=Path)

    args = parser.parse_args()
    if args.command == "filter-patch":
        filter_patch(args.source, args.destination)
    elif args.command == "patch-source":
        patch_source(args.common)


if __name__ == "__main__":
    main()

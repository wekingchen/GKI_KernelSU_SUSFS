#!/usr/bin/env python3
"""Fail closed when a successful K50 Pro CI run skipped compatibility checks.

This reads actual GitHub job logs, not a CLI summary or the source YAML itself.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def normalized(log: str) -> list[str]:
    # Job logs can be timestamped or plain. Strip ANSI and the log prefix.
    lines = []
    for raw in log.splitlines():
        raw = re.sub(r"\x1b\[[0-9;]*m", "", raw)
        raw = re.sub(r"^20[0-9]{2}-[0-9]{2}-[0-9]{2}T[^ ]+Z ", "", raw)
        lines.append(raw.strip())
    return lines


def verify(log: str) -> None:
    lines = normalized(log)
    if not lines:
        raise ValueError("内核构建日志为空")
    # Only completed commands count. Inlined bash source contains many echo
    # statements and should never be mistaken for successful execution.
    required = {
        "Stock Config 源": lambda s: s.startswith((
            "使用通用 stock_defconfig:", "使用版本专用 stock config:",
            "已从官方预编译内核提取库存配置")),
        "Stock Config 已复制": lambda s: s.startswith("已复制库存配置 ->"),
        "config_data 映射已生效": lambda s: s.startswith((
            "已替换 config_data 规则:", "config_data 规则已是 stock_defconfig")),
        "BBG 配置及 LSM 检查": lambda s: s.startswith(
            "-- Baseband-guard: Okay, Baseband_guard was found in CONFIG_LSM"),
        "BBG SELinux 头文件可用": lambda s: s.startswith(
            "-- Baseband-guard: flask.h found, skip generation"),
        "FULL LTO": lambda s: s == "CONFIG_LTO_CLANG_FULL=y",
    }
    missing = [name for name, pred in required.items() if not any(map(pred, lines))]
    if missing:
        raise ValueError("关键构建证据缺失: " + ", ".join(missing))
    forbidden = [
        'Executable "ld" doesn\'t exist!',
        "genheaders: No such file or directory",
        "mv: bad './flask.h'",
        "mv: bad './av_permissions.h'",
        "Please wait susfs update",
    ]
    for line in lines:
        # Do not flag the echoed bash source, only actual error output.
        if line.startswith(("echo ", "grep ", "if ", "#")):
            continue
        if any(marker in line for marker in forbidden):
            raise ValueError("检测到 BBG/SUSFS 兼容性软失败: " + line[:240])


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: verify_fork_build_log.py <kernel-job-log>", file=sys.stderr)
        return 2
    try:
        verify(Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError) as exc:
        print("::error::K50 Pro 隔离版构建门禁未通过: " + str(exc), file=sys.stderr)
        return 1
    print("[K50Pro] Stock Config / BBG / FULL LTO 构建日志门禁通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

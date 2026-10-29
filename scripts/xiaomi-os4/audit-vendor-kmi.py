#!/usr/bin/env python3
"""只读比较 OS4 原厂 .ko 的模块 CRC 与候选 R62 Module.symvers。永不宣布可刷机。"""
from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from pathlib import Path
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection

EXAMPLES = 25


def symvers_load(path: Path) -> dict:
    exports = {}
    for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        cols = line.split()
        if not cols:
            continue
        if len(cols) < 3 or not re.fullmatch(r"0x[0-9a-fA-F]{8,16}", cols[0]):
            raise ValueError(f"Module.symvers 第 {n} 行格式异常")
        symbol, entry = cols[1], (int(cols[0], 16) & 0xffffffff, cols[2])
        if symbol in exports and exports[symbol] != entry:
            raise ValueError(f"重复且冲突的符号导出：{symbol}")
        exports[symbol] = entry
    if not exports:
        raise ValueError("Module.symvers 为空")
    return exports


def versions_read(elf) -> tuple[dict, str]:
    short = elf.get_section_by_name("__versions")
    names = elf.get_section_by_name("__version_ext_names")
    crcs = elf.get_section_by_name("__version_ext_crcs")
    if (names is None) != (crcs is None) or (short is not None and names is not None):
        raise ValueError("模块的符号版本 section 结构冲突或不完整")
    order = "<" if elf.little_endian else ">"
    results = {}
    if names is not None:
        raw_names, raw_crcs = names.data(), crcs.data()
        if not raw_names.endswith(b"\0") or len(raw_crcs) % 4:
            raise ValueError("扩展版本表格式异常")
        symbols = [p.decode("utf-8", "replace") for p in raw_names.split(b"\0")[:-1]]
        if len(symbols) != len(raw_crcs) // 4 or not all(symbols):
            raise ValueError("扩展 CRC 与符号名称数量不一致")
        for i, symbol in enumerate(symbols):
            crc = struct.unpack_from(order + "I", raw_crcs, 4 * i)[0]
            if symbol in results and results[symbol] != crc:
                raise ValueError(f"扩展版本的符号 CRC 冲突：{symbol}")
            results[symbol] = crc
        return results, "extended"
    if short is not None:
        raw = short.data()
        # 6.12 struct modversion_info: unsigned long CRC + char name[MAX_PARAM_PREFIX_LEN].
        # 64 位 (8 + 56) 与 32 位 (4 + 60) 每项均为 64 字节。
        width = 8 if elf.elfclass == 64 else 4
        if len(raw) % 64:
            raise ValueError("经典 __versions 表长度不是 64 的整数倍")
        for start in range(0, len(raw), 64):
            crc = struct.unpack_from(order + ("Q" if width == 8 else "I"), raw, start)[0] & 0xffffffff
            symbol = raw[start + width:start + 64].split(b"\0", 1)[0].decode("utf-8", "replace")
            if not symbol or (symbol in results and results[symbol] != crc):
                raise ValueError("经典 __versions 表存在空名称或 CRC 冲突")
            results[symbol] = crc
        return results, "classic"
    return {}, "absent"


def analyze_ko(file: Path, exports: dict) -> dict:
    with file.open("rb") as stream:
        elf = ELFFile(stream)
        if elf["e_type"] != "ET_REL" or elf["e_machine"] != "EM_AARCH64":
            raise ValueError(f"不是 ARM64 可重定位内核模块：{elf['e_machine']}")
        version, fmt = versions_read(elf)
        sections = elf.get_section_by_name(".modinfo")
        modinfo = {}
        if sections is not None:
            for entry in sections.data().split(b"\0"):
                if b"=" in entry:
                    k, v = entry.split(b"=", 1)
                    modinfo[k.decode("ascii", "replace")] = v.decode("utf-8", "replace")
        imports = set()
        for section in elf.iter_sections():
            if isinstance(section, SymbolTableSection):
                imports.update(s.name for s in section.iter_symbols()
                               if s["st_shndx"] == "SHN_UNDEF" and s.name)
        matching = 0
        mismatch, external, no_crc = [], [], []
        for symbol in sorted(imports | set(version)):
            dest = exports.get(symbol)
            if dest is None or dest[1] != "vmlinux":
                external.append(symbol)
            elif symbol not in version:
                no_crc.append(symbol)
            elif version[symbol] != dest[0]:
                mismatch.append({"symbol": symbol,
                                 "oem": f"0x{version[symbol]:08x}",
                                 "candidate": f"0x{dest[0]:08x}"})
            else:
                matching += 1
        return {"path": str(file), "elf_machine": str(elf["e_machine"]),
                "vermagic": modinfo.get("vermagic"), "format": fmt,
                "crc_entries": len(version), "undefined_symbols": len(imports),
                "matched": matching, "mismatch_count": len(mismatch),
                "mismatches": mismatch[:EXAMPLES],
                "unknown_provider_count": len(external), "unknown_provider_examples": external[:EXAMPLES],
                "missing_expected_crc_count": len(no_crc), "missing_expected_crc_examples": no_crc[:EXAMPLES]}


def audit(symvers: Path, modules: Path) -> tuple[dict, int]:
    if not modules.is_dir():
        raise ValueError("请提供已解压的原厂模块目录")
    zipped = [p for ext in ("*.ko.zst", "*.ko.xz", "*.ko.gz")
              for p in modules.rglob(ext) if p.is_file()]
    if zipped:
        raise ValueError(f"发现 {len(zipped)} 个压缩模块，必须先解压，不允许漏检")
    files = sorted(p for p in modules.rglob("*.ko") if p.is_file() and not p.is_symlink())
    if not files or len(files) > 3000:
        raise ValueError(f".ko 数量异常：{len(files)}")
    if any(p.stat().st_size > 200 * 1024 * 1024 for p in files):
        raise ValueError("单个 .ko 超过 200 MiB，停止分析")
    exports = symvers_load(symvers)
    results, errors = [], []
    for path in files:
        try:
            result = analyze_ko(path, exports)
            result["path"] = str(path.relative_to(modules))
            results.append(result)
        except Exception as exc:
            errors.append({"module": str(path.relative_to(modules)), "error": str(exc)})
    count = sum(item["mismatch_count"] for item in results)
    matched = sum(item["matched"] for item in results)
    total_versioned = sum(bool(item["crc_entries"]) for item in results)
    incomplete = bool(errors or matched + count == 0 or total_versioned != len(results)
                      or any(i["unknown_provider_count"] or i["missing_expected_crc_count"] for i in results))
    verdict = ("CRC_CONFLICT_DETECTED" if count else
               "INCOMPLETE_EVIDENCE" if incomplete else
               "NO_CRC_CONFLICT_IN_CHECKED_SYMBOLS_ONLY")
    code = 1 if count else 2 if incomplete else 0
    return {
        "verdict": verdict, "safe_to_flash": False,
        "checked_modules": len(results), "total_module_files": len(files),
        "modules_with_crc": total_versioned,
        "matched_vmlinux_crc": matched, "mismatched_vmlinux_crc": count,
        "unknown_provider_count": sum(i["unknown_provider_count"] for i in results),
        "errors_count": len(errors), "errors": errors[:EXAMPLES], "modules": results,
        "limitations": [
            "此检查不证明可启动/可刷机；没有验证 OEM boot、KMI symbol namespace、DT、签名或驱动行为。",
            "缺失于公共 GKI 的符号可能由厂商其它模块导出，不可仅据此判断模块缺失。",
            "原厂模块 vermagic 与故意使用 analysis localversion 的候选 R62 不同。",
            "蜂窝数据、IMS/通话、相机、Wi-Fi 等功能必须后续真机独立验证。"
        ]}, code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symvers", type=Path, required=True, help="#5 产物 Module.symvers")
    parser.add_argument("--modules", type=Path, required=True, help="解包后的原厂 .ko 目录")
    parser.add_argument("--output", type=Path, required=True, help="JSON 报告路径")
    args = parser.parse_args()
    try:
        report, code = audit(args.symvers, args.modules)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"ABI 静态审计：{report['verdict']}；相同 CRC {report['matched_vmlinux_crc']}；冲突 CRC {report['mismatched_vmlinux_crc']}；模块 {report['checked_modules']}")
    print("注意：任何结果都不意味着可以刷机。")
    return code


if __name__ == "__main__":
    sys.exit(main())

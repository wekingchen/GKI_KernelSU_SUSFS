#!/usr/bin/env python3
"""Evidence-bound OTA V2 follow-up plan based on the OS4.0.5/OS4.0.6 lessons.

This is a *diagnosis planner*, never a repair executor. No commands, ABI waivers,
boot images or workflow dispatches are emitted. Unknown signals stay unknown.
"""
import argparse
import hashlib
import json
from pathlib import Path

REVIEW = "pandora-ota-diagnostic-review-v1"
EVIDENCE = "pandora-ota-diagnostic-evidence-v1"


def check(test, reason):
    if not test:
        raise ValueError(reason)


def plan(task, report, evidence, review):
    check(task.get("schema") == "pandora-ota-diagnostic-task-v1"
          and evidence.get("schema") == EVIDENCE
          and review.get("schema") == REVIEW
          and review.get("review") == "REVIEW_REQUIRED", "Unverified OTA diagnostic input")
    identity = ("source_run_id", "stock_build", "stock_input_sha256")
    check(all(task.get(key) == evidence.get(key) == review.get(key)
              for key in identity), "Mixed source/OTA evidence")
    check(task.get("candidate_commit") == evidence.get("candidate_commit")
          and task.get("source_head_sha") == evidence.get("source_head_sha"), "Mixed GKI candidate")
    check(review.get("payload_sha256") and
          all(review.get(key) is False for key in ("safe_to_flash", "oem_gate_unlocked",
                                                  "lkg_promotion")), "Review unlocked original gate")
    check(report.get("gate") == "BLOCKED" and
          report.get("eligible_for_fastboot_boot") is False and
          report.get("flashable") is False and
          report.get("stock_input_sha256") == task.get("stock_input_sha256") and
          report.get("stock_build") == task.get("stock_build") and
          report.get("candidate_commit") == task.get("candidate_commit"),
          "Original OEM gate is not the same blocked candidate")
    codes = [x["code"] for x in task["issues"]]
    obs = evidence["observations"]
    actions = []

    def add(code, title, detail, owner="developer", prerequisite="MANUAL_EVIDENCE_REVIEW"):
        actions.append({
            "code": code, "title": title, "detail": detail,
            "owner": owner, "prerequisite": prerequisite,
            "automated_patch": False, "requires_same_ota_proof": True,
        })

    if evidence["status"] == "PARTIAL_READ_ONLY":
        add("RECOLLECT_MISSING_ONLY", "先核对缺失证据",
            "手机只取得部分只读数据。确认 Root 授权与 /proc/modules、sysfs 可读性；保留 UNKNOWN，不凭缺失值推断模块未加载。",
            owner="device", prerequisite="NEW_READ_ONLY_OBSERVATION")

    if "OEM_MODULE_PARSE_OR_IDENTITY_FAILURE" in codes:
        add("STOCK_INPUT_INTEGRITY", "重新核对 OEM 模块原件",
            "先验证同 OTA stock ZIP、boot/vendor_boot 和 vendor/system_dlkm 模块的 SHA、ELF 格式与 vermagic。解析失败应先修解析器，不修改 ABI 门禁。")
    if "OTHER_UNRESOLVED_IMPORTS" in codes:
        add("VENDOR_BOOT_PROVIDER_GRAPH", "补全早期模块提供者依赖图",
            "重查本固件 vendor_boot ramdisk 的早期 .ko 和它们的真实导出 CRC，再与 vendor_dlkm / system_dlkm 一起做闭环依赖图。OS4.0.6 曾凭此补齐 923 条缺口中的 852 条；不能假设每个 OTA 数量相同。")
    if "AMBIGUOUS_MODULE_PROVIDERS" in codes or "MODULE_CRC_MISMATCH" in codes:
        modules = obs.get("loaded_module_identity", {})
        hashes = {name: modules.get(name, {}).get("gnu_note_sha256")
                  for name in ("node_cache", "zram", "zsmalloc")}
        known = sum(isinstance(x, str) and len(x) == 64 for x in hashes.values())
        add("SPLIT_VENDOR_SYSTEM_CRC", "分开核对 vendor / system 模块",
            "对同名 .ko 分别计算实际导出 CRC，保留各自独立来源；不能仅凭同名、模块已加载或 CRC 数量一致而选一方。" +
            (" 已拿到 %d/3 项活动模块 GNU Note 摘要，需与本 OTA 的两套原件比对。" % known),
            prerequisite="EXACT_OEM_PROVIDER_PROVENANCE")
    if "STOCK_RUST_BINDER_ABI_UNRESOLVED" in codes:
        binder = obs.get("binder_runtime", {})
        impl = binder.get("active_impl", "UNKNOWN")
        loaded = binder.get("rust_binder_loaded")
        blacklist = binder.get("module_blacklist_kernelsu")
        eexist = binder.get("eexist_parameter")
        detail = ("独立确认本机使用的 Binder 活动实现、Rust 模块是否真实加载，及候选 GKI 的 Rust 工具链/符号 CRC。"
                  "OS4.0.6 的 71 条 Rust 导入不能通过忽略符号消除。")
        if impl == "c" and loaded is False:
            detail += " 本次观察为 C Binder 且 rust_binder 未加载；只能提示人工复核运行时选择，不能把该事实当成 OEM ABI 通用豁免。"
        elif loaded is True:
            detail += " 本次 Rust Binder 已加载，必须核对实际二进制与所选候选的 Rust ABI，不可套用 C Binder 方案。"
        else:
            detail += " 当前活动实现或加载状态不完整，先补采，不猜测使用了 C Binder。"
        if blacklist is not True:
            detail += " KernelSU LKM 黑名单状态未确认；OS4.0.5/4.0.6 需确保 Built-in 与 LKM 不混用。"
        if eexist is not True:
            detail += " EEXIST 启动参数未确认，必须核查但不能盲目写入或替换其他 OTA 的命令行。"
        add("RUST_BINDER_RUNTIME_ROUTE", "复核 Binder 与 Rust ABI 分支", detail)
    if not actions:
        add("BLOCKED_INPUT_REVIEW", "先检查原始 OEM 阻断",
            "即使没有已分类的模块原因，只要原始 OEM gate=BLOCKED，均不得编出待测 boot。")
    add("POST_FIX_RUNTIME_GATES", "保留功能级真机验收",
        "仅在修复代码和同 OTA OEM CRC/KMI 再次检查都通过后，才由用户 fastboot boot 验证；检查 Built-in Root/SUSFS/NoMount、BBG LSM、Re-Kernel、DroidSpaces 的 pids / 网络与模块来源，然后再讨论持久化及 LKG。",
        owner="device", prerequisite="NEW_CANDIDATE_STATIC_PASS_AND_USER_TEST")
    return {
        "schema": "pandora-ota-v2-recovery-plan-v1",
        "repository": "wekingchen/GKI_KernelSU_SUSFS",
        "device": "pandora",
        "source_run_id": task["source_run_id"],
        "stock_build": task["stock_build"],
        "stock_input_sha256": task["stock_input_sha256"],
        "candidate_commit": task["candidate_commit"],
        "evidence_sha256": review["payload_sha256"],
        "evidence_status": evidence["status"],
        "oem_gate": "BLOCKED",
        "review": "REVIEW_REQUIRED",
        "requires_new_candidate_after_fix": True,
        "rerun_without_change_will_not_resolve_abi": True,
        "automatic_patch_allowed": False,
        "automatic_rebuild_authorized": False,
        "fastboot_boot_authorized": False,
        "persistent_install_authorized": False,
        "lkg_promotion_authorized": False,
        "actions": actions,
        "note": "Human review of exact stock/GKI binaries and a corrected code or provider graph must precede a fresh candidate; this plan never changes the original gate.",
    }


def main():
    p = argparse.ArgumentParser()
    for name in ("task", "oem-report", "evidence", "review", "output", "markdown"):
        p.add_argument("--" + name, type=Path, required=True)
    args = p.parse_args()
    read = lambda path: json.loads(path.read_text(encoding="utf-8"))
    task, report, evidence, review = (
        read(args.task), read(args.oem_report), read(args.evidence), read(args.review))
    raw = args.evidence.read_bytes()
    check(hashlib.sha256(raw).hexdigest() == review["payload_sha256"],
          "Review does not bind exact uploaded evidence bytes")
    result = plan(task, report, evidence, review)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                      sort_keys=True) + "\n", encoding="utf-8")
    lines = ["## OTA V2 · 兼容性下一步处理建议", "",
             "- 只读补采已核验，但 OEM ABI 仍为 BLOCKED；不会自动修补、重编、刷写或晋升 LKG。",
             "- 固件：" + result["stock_build"],
             "- 证据状态：" + result["evidence_status"], ""]
    for idx, action in enumerate(result["actions"], 1):
        lines.append("%d. %s：%s" % (idx, action["title"], action["detail"]))
    lines += ["", "## 再次生成候选的前置条件", "",
              "必须先由开发者校正解析器、精准模块来源或内核补丁，并取得同 OTA 新的静态 OEM ABI 门禁通过；不能仅重新运行相同已归档 GKI 来假装问题已解决。",
              "静态通过后仍须人工临时启动和逐项功能验证。"]
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("PANDORA_OTA_V2_RECOVERY=REVIEW_REQUIRED_NO_AUTO_REBUILD")


if __name__ == "__main__":
    main()

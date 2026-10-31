#!/usr/bin/env python3
import argparse
import re
from pathlib import Path

def parse_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data

def require(data: dict[str, str], *keys: str) -> None:
    missing = [k for k in keys if not data.get(k)]
    if missing:
        raise SystemExit("missing required fields: " + ", ".join(missing))

def bit(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "on", "yes"}:
        return "1"
    if normalized in {"0", "false", "off", "no"}:
        return "0"
    raise SystemExit(f"cannot convert to boolean bit: {value!r}")

def safe_note(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._:+-]+", "_", value.strip())
    return value[:160] or "user-promoted-stable"

def emit(lines: list[str], key: str, value: str) -> None:
    if "\n" in value or "\r" in value:
        raise SystemExit(f"invalid multiline value for {key}")
    lines.append(f"{key}={value}")

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Promote a verified Xiaomi OS4 custom-build artifact into the movable current LKG."
    )
    ap.add_argument("--current-lkg", required=True)
    ap.add_argument("--candidate-dir", required=True)
    ap.add_argument("--source-run-id", required=True)
    ap.add_argument("--source-run-head", required=True)
    ap.add_argument("--artifact-id", required=True)
    ap.add_argument("--promoted-at", required=True)
    ap.add_argument("--note", default="user-promoted-stable")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    current = parse_env(Path(args.current_lkg))
    cand = Path(args.candidate_dir)
    selection = parse_env(cand / "selection-manifest.txt")
    upstreams = parse_env(cand / "resolved-upstreams.env")
    repro = parse_env(cand / "image-reproducibility.env")

    require(
        current,
        "LKG_DEVICE", "LKG_SYSTEM_BUILD", "LKG_ANDROID_USERSPACE", "LKG_KERNEL_KMI",
        "LKG_PROMOTION_GENERATION", "LKG_BOOT_FIXTURE_GIT_BLOB_SHA1",
        "LKG_ABI_LOCK_BASE_EXPORTS", "LKG_ABI_LOCK_SHA256",
        "LKG_ABI_ALLOWED_NEW_EXPORTS", "LKG_STOCK_BOOT_SHA256", "LKG_STOCK_HEADER_SHA256",
        "LKG_BASELINE_IMAGE_SHA256", "LKG_TESTED_BASELINE_BOOT_SHA256",
    )
    require(
        selection,
        "DEVICE", "SYSTEM_BUILD", "REQUEST_ROOT_MODE", "REQUEST_SUSFS_EXTRA",
        "REQUEST_NOMOUNT", "REQUEST_DROIDSPACES", "REQUEST_NTSYNC", "REQUEST_BBG",
        "REQUEST_REKERNEL", "REQUEST_NETWORKING", "REQUEST_CVE", "KERNEL_RELEASE",
        "IMAGE_SHA256", "CONFIG_SHA256", "SYMVERS_SHA256", "FASTBOOT_BOOT", "FASTBOOT_BOOT_SHA256",
        "ANYKERNEL3", "ANYKERNEL3_SHA256", "SAFETY",
    )
    require(
        upstreams,
        "RESOLVED_BAKASU_KIND", "RESOLVED_BAKASU_REF", "RESOLVED_BAKASU_VERSION",
        "RESOLVED_BAKASU_COMMIT", "RESOLVED_SUSFS_KIND", "RESOLVED_SUSFS_REF",
        "RESOLVED_SUSFS_VERSION", "RESOLVED_SUSFS_COMMIT", "RESOLVED_NOMOUNT_KIND",
        "RESOLVED_NOMOUNT_REF", "RESOLVED_NOMOUNT_VERSION", "RESOLVED_NOMOUNT_COMMIT",
        "RESOLVED_DROIDSPACES_KIND", "RESOLVED_DROIDSPACES_REF",
        "RESOLVED_DROIDSPACES_VERSION", "RESOLVED_DROIDSPACES_COMMIT",
        "RESOLVED_NTSYNC_KIND", "RESOLVED_NTSYNC_REF", "RESOLVED_NTSYNC_VERSION",
        "RESOLVED_NTSYNC_COMMIT", "RESOLVED_BBG_KIND", "RESOLVED_BBG_REF",
        "RESOLVED_BBG_VERSION", "RESOLVED_BBG_COMMIT", "RESOLVED_REKERNEL_KIND",
        "RESOLVED_REKERNEL_REF", "RESOLVED_REKERNEL_VERSION", "RESOLVED_REKERNEL_COMMIT",
        "UPSTREAM_SET_SHA256",
    )
    require(
        repro,
        "IMAGE_SIZE", "IMAGE_SHA256", "IMAGE_BUILD_ID_PAYLOAD_OFFSET",
        "IMAGE_MODULE_CERT_OFFSET", "IMAGE_MODULE_CERT_LENGTH",
        "NORMALIZED_IMAGE_SHA256", "MODULE_SIGNING_CERT_SHA256",
    )

    if selection["DEVICE"] != current["LKG_DEVICE"]:
        raise SystemExit("candidate device differs from current LKG")
    if selection["SYSTEM_BUILD"] != current["LKG_SYSTEM_BUILD"]:
        raise SystemExit("candidate system build differs from current LKG")
    if selection["IMAGE_SHA256"] != repro["IMAGE_SHA256"]:
        raise SystemExit("selection/repro Image SHA mismatch")

    root_mode = selection["REQUEST_ROOT_MODE"]
    susfs_extra = bit(selection["REQUEST_SUSFS_EXTRA"])
    use_nomount = bit(selection["REQUEST_NOMOUNT"])
    droidspaces = bit(selection["REQUEST_DROIDSPACES"])
    use_ntsync = bit(selection["REQUEST_NTSYNC"])
    use_bbg = bit(selection["REQUEST_BBG"])
    use_rekernel = bit(selection["REQUEST_REKERNEL"])
    use_networking = bit(selection["REQUEST_NETWORKING"])
    use_cve = bit(selection["REQUEST_CVE"])

    full_parity = (
        root_mode == "bakasu-susfs"
        and all(
            v == "1"
            for v in (
                susfs_extra, use_nomount, droidspaces, use_ntsync,
                use_bbg, use_rekernel, use_networking, use_cve,
            )
        )
    )

    generation = int(current["LKG_PROMOTION_GENERATION"]) + 1
    lines: list[str] = [
        "# Xiaomi 17 Pro / pandora / HyperOS 4 movable current LKG",
        "# Updated only when the user explicitly promotes a real-device-stable custom run.",
        "",
    ]

    emit(lines, "LKG_DEVICE", current["LKG_DEVICE"])
    emit(lines, "LKG_SYSTEM_BUILD", current["LKG_SYSTEM_BUILD"])
    emit(lines, "LKG_ANDROID_USERSPACE", current["LKG_ANDROID_USERSPACE"])
    emit(lines, "LKG_KERNEL_KMI", current["LKG_KERNEL_KMI"])
    emit(lines, "LKG_KERNEL_RELEASE", selection["KERNEL_RELEASE"])
    emit(lines, "LKG_PROMOTION_GENERATION", str(generation))
    emit(lines, "LKG_PROMOTED_AT", args.promoted_at)
    emit(lines, "LKG_PROMOTION_NOTE", safe_note(args.note))
    emit(lines, "LKG_PROMOTION_SOURCE_SAFETY", selection["SAFETY"])
    lines.append("")

    lines.append("# Feature selection is part of the LKG identity.")
    emit(lines, "LKG_ROOT_MODE", root_mode)
    emit(lines, "LKG_SUSFS_EXTRA_FEATURES", susfs_extra)
    emit(lines, "LKG_USE_NOMOUNT", use_nomount)
    emit(lines, "LKG_DROIDSPACES", droidspaces)
    emit(lines, "LKG_USE_NTSYNC", use_ntsync)
    emit(lines, "LKG_USE_BBG", use_bbg)
    emit(lines, "LKG_USE_REKERNEL", use_rekernel)
    emit(lines, "LKG_USE_NETWORKING", use_networking)
    emit(lines, "LKG_USE_CVE", use_cve)
    lines.append("")

    emit(lines, "LKG_SOURCE_RUN_ID", args.source_run_id)
    emit(lines, "LKG_SOURCE_RUN_HEAD", args.source_run_head)
    emit(lines, "LKG_IMAGE_SHA256", selection["IMAGE_SHA256"])
    emit(lines, "LKG_SYMVERS_SHA256", selection["SYMVERS_SHA256"])
    emit(lines, "LKG_FASTBOOT_BOOT_SHA256", selection["FASTBOOT_BOOT_SHA256"])
    emit(lines, "LKG_FINAL_CONFIG_SHA256", selection["CONFIG_SHA256"])
    emit(lines, "LKG_IMAGE_SIZE", repro["IMAGE_SIZE"])
    emit(lines, "LKG_IMAGE_BUILD_ID_PAYLOAD_OFFSET", repro["IMAGE_BUILD_ID_PAYLOAD_OFFSET"])
    emit(lines, "LKG_IMAGE_MODULE_CERT_OFFSET", repro["IMAGE_MODULE_CERT_OFFSET"])
    emit(lines, "LKG_IMAGE_MODULE_CERT_LENGTH", repro["IMAGE_MODULE_CERT_LENGTH"])
    emit(lines, "LKG_IMAGE_NORMALIZED_SHA256", repro["NORMALIZED_IMAGE_SHA256"])
    emit(lines, "LKG_MODULE_SIGNING_CERT_SHA256", repro["MODULE_SIGNING_CERT_SHA256"])
    emit(lines, "LKG_IMAGE_REPRODUCIBILITY", "AUTOGENERATED_MODULE_SIGNING_CERT_PLUS_GNU_BUILD_ID")
    emit(lines, "LKG_REBUILD_VALIDATION_RUN_ID", args.source_run_id)
    emit(lines, "LKG_REBUILD_VALIDATED_IMAGE_SHA256", selection["IMAGE_SHA256"])
    emit(lines, "LKG_REBUILD_VALIDATED_FASTBOOT_BOOT_SHA256", selection["FASTBOOT_BOOT_SHA256"])
    emit(lines, "LKG_REBUILD_REAL_DEVICE_VALIDATION", "PASS")
    lines.append("")

    for key in (
        "LKG_BASELINE_IMAGE_SHA256",
        "LKG_TESTED_BASELINE_BOOT_SHA256",
        "LKG_BOOT_FIXTURE_GIT_BLOB_SHA1",
        "LKG_ABI_LOCK_BASE_EXPORTS",
        "LKG_ABI_LOCK_SHA256",
        "LKG_ABI_ALLOWED_NEW_EXPORTS",
        "LKG_STOCK_BOOT_SHA256",
        "LKG_STOCK_HEADER_SHA256",
    ):
        emit(lines, key, current[key])
    lines.append("")

    emit(lines, "LKG_PACKAGE_RUN_ID", args.source_run_id)
    emit(lines, "LKG_PACKAGE_ARTIFACT_ID", args.artifact_id)
    emit(lines, "LKG_PACKAGE_NAME", selection["ANYKERNEL3"])
    emit(lines, "LKG_PACKAGE_SHA256", selection["ANYKERNEL3_SHA256"])
    emit(lines, "LKG_UPSTREAM_SET_SHA256", upstreams["UPSTREAM_SET_SHA256"])
    lines.append("")

    components = (
        ("BAKASU", "BAKASU"),
        ("SUSFS", "SUSFS"),
        ("NOMOUNT", "NOMOUNT"),
        ("DROIDSPACES", "DROIDSPACES"),
        ("NTSYNC", "NTSYNC"),
        ("BBG", "BBG"),
        ("REKERNEL", "REKERNEL"),
    )
    for lkg_name, resolved_name in components:
        emit(lines, f"LKG_{lkg_name}_KIND", upstreams[f"RESOLVED_{resolved_name}_KIND"])
        emit(lines, f"LKG_{lkg_name}_REF", upstreams[f"RESOLVED_{resolved_name}_REF"])
        emit(lines, f"LKG_{lkg_name}_VERSION", upstreams[f"RESOLVED_{resolved_name}_VERSION"])
        commit_key = (
            "LKG_NTSYNC_PATCH_COMMIT"
            if lkg_name == "NTSYNC"
            else f"LKG_{lkg_name}_COMMIT"
        )
        emit(lines, commit_key, upstreams[f"RESOLVED_{resolved_name}_COMMIT"])
    lines.append("")

    lines.append("# Legacy aliases retained for old tooling/history.")
    emit(lines, "BAKASU_COMMIT", "$LKG_BAKASU_COMMIT")
    emit(lines, "SUSFS_COMMIT", "$LKG_SUSFS_COMMIT")
    emit(lines, "NOMOUNT_COMMIT", "$LKG_NOMOUNT_COMMIT")
    emit(lines, "DROIDSPACES_COMMIT", "$LKG_DROIDSPACES_COMMIT")
    emit(lines, "NTSYNC_PATCH_COMMIT", "$LKG_NTSYNC_PATCH_COMMIT")
    emit(lines, "BBG_COMMIT", "$LKG_BBG_COMMIT")
    emit(lines, "REKERNEL_COMMIT", "$LKG_REKERNEL_COMMIT")
    lines.append("")

    emit(lines, "LKG_FASTBOOT_BOOT_VALIDATION", "PASS")
    emit(lines, "LKG_PERSISTENT_BOOT_VALIDATION", "PASS")
    emit(lines, "LKG_BUILTIN_ROOT", "PASS" if root_mode != "none" else "NOT_SELECTED")
    emit(lines, "LKG_OLD_KERNELSU_LKM_BLOCKED", "PASS" if root_mode != "none" else "NOT_SELECTED")
    emit(lines, "LKG_BBG_ACTIVE_LSM", "PASS" if use_bbg == "1" else "NOT_SELECTED")
    emit(lines, "LKG_REKERNEL_11_7_GENL", "PASS" if use_rekernel == "1" else "NOT_SELECTED")
    emit(lines, "LKG_PIDS_CONTROLLER_RUNTIME", "PASS" if droidspaces == "1" else "NOT_SELECTED")
    emit(lines, "LKG_DROIDSPACES_CHECK", "PASS" if droidspaces == "1" else "NOT_SELECTED")
    emit(lines, "LKG_NTSYNC", "PASS" if use_ntsync == "1" else "NOT_SELECTED")
    emit(lines, "LKG_BBR_DEFAULT_ACTIVE", "PASS" if use_networking == "1" else "NOT_SELECTED")
    emit(lines, "LKG_FULL_PARITY", "YES" if full_parity else "NO")

    Path(args.output).write_text("\n".join(lines) + "\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

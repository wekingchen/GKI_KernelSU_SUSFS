#!/usr/bin/env python3
"""Zero-trust validation for a *review-only* Pandora OTA diagnostic evidence payload."""
import argparse
import hashlib
import json
import re
from pathlib import Path

HEX=re.compile(r"[a-f0-9]{64}\Z")
HEAD=re.compile(r"[a-f0-9]{40}\Z")
BUILD=re.compile(r"OS[0-9]+\.[0-9.]+[A-Z0-9]+\Z")
MODULES={"node_cache","zram","zsmalloc"}


def check(ok, message):
    if not ok:
        raise ValueError(message)


def keys(obj, expected, name):
    check(isinstance(obj, dict) and set(obj)==set(expected), "Unexpected fields in "+name)


def null_or_bool(item):
    return item is None or type(item) is bool


def verify(task, report, evidence, raw, digest):
    check(len(raw)<=32768 and hashlib.sha256(raw).hexdigest()==digest, "Evidence SHA/size mismatch")
    check(task.get("schema")=="pandora-ota-diagnostic-task-v1", "Unsupported task")
    check(task.get("source_run_id")==evidence.get("source_run_id") and
          task.get("source_head_sha")==evidence.get("source_head_sha") and
          task.get("stock_build")==evidence.get("stock_build") and
          task.get("stock_input_sha256")==evidence.get("stock_input_sha256") and
          task.get("candidate_commit")==evidence.get("candidate_commit"),
          "Evidence does not match exact source run / OTA identity")
    check(report.get("gate")=="BLOCKED" and report.get("eligible_for_fastboot_boot") is False
          and report.get("stock_input_sha256")==task.get("stock_input_sha256")
          and report.get("stock_build")==task.get("stock_build")
          and report.get("candidate_commit")==task.get("candidate_commit"),
          "Original OEM gate/source does not match task")
    keys(evidence, ("schema","repository","source_run_id","source_head_sha",
                    "stock_build","stock_input_sha256","candidate_commit",
                    "checks","status","captured_at_ms","observations",
                    "attestation","device_write_allowed","safe_to_flash",
                    "lkg_promotion"),"evidence")
    check(evidence["schema"]=="pandora-ota-diagnostic-evidence-v1"
          and evidence["repository"]=="wekingchen/GKI_KernelSU_SUSFS"
          and evidence["attestation"]=="DEVICE_READ_ONLY_OBSERVATION_NOT_KERNEL_COMPATIBILITY_PROOF"
          and evidence["device_write_allowed"] is False
          and evidence["safe_to_flash"] is False
          and evidence["lkg_promotion"] is False
          and evidence["status"] in ("CAPTURED_READ_ONLY","PARTIAL_READ_ONLY")
          and type(evidence["captured_at_ms"]) is int and evidence["captured_at_ms"]>0,
          "Evidence cannot authorize a boot, kernel flash or LKG")
    checks=[item["id"] for item in task["checks"]]
    check(evidence["checks"]==checks and set(checks).issubset({"binder_runtime","loaded_module_identity"})
          and len(set(checks))==len(checks), "Evidence task check types drift")
    obs=evidence["observations"]
    keys(obs,["identity"]+checks,"observations")
    identity=obs["identity"]
    keys(identity,("device","build","boot_completed","slot","uname"),"identity")
    check(identity["device"]=="pandora" and identity["build"]==task["stock_build"]
          and identity["boot_completed"]=="1" and identity["slot"] in ("_a","_b")
          and isinstance(identity["uname"],str)
          and re.fullmatch(r"[A-Za-z0-9_.+-]{8,160}",identity["uname"]),
          "Observed device/build/slot does not match task")
    if "binder_runtime" in checks:
        binder=obs["binder_runtime"]
        keys(binder,("impl","active_impl","rust_binder_loaded","kernelsu_lkm_loaded",
                     "module_blacklist_kernelsu","eexist_parameter"),"binder")
        check(binder["impl"] in ("c","rust","UNKNOWN")
              and binder["active_impl"] in ("c","rust","UNKNOWN")
              and all(null_or_bool(binder[x]) for x in
                      ("rust_binder_loaded","kernelsu_lkm_loaded",
                       "module_blacklist_kernelsu","eexist_parameter")),
              "Unrecognized Binder observation")
    if "loaded_module_identity" in checks:
        source=obs["loaded_module_identity"]
        keys(source,MODULES,"module_identity")
        for name, item in source.items():
            keys(item,("loaded","gnu_note_sha256"),"module_"+name)
            check(null_or_bool(item["loaded"]) and
                  (item["gnu_note_sha256"] is None or
                   isinstance(item["gnu_note_sha256"],str) and
                   HEX.fullmatch(item["gnu_note_sha256"])),
                  "Unexpected module digest/loaded status")
    return {
        "schema":"pandora-ota-diagnostic-review-v1",
        "review":"REVIEW_REQUIRED",
        "source_run_id":task["source_run_id"],
        "stock_build":task["stock_build"],
        "stock_input_sha256":task["stock_input_sha256"],
        "payload_sha256":digest,
        "evidence_status":evidence["status"],
        "checks":checks,
        "safe_to_flash":False,
        "oem_gate_unlocked":False,
        "lkg_promotion":False,
        "note":"Uploaded phone observations require independent analysis; this does not attest runtime source hashes or ABI compatibility."
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--task",type=Path,required=True)
    p.add_argument("--oem-report",type=Path,required=True)
    p.add_argument("--evidence",type=Path,required=True)
    p.add_argument("--expected-sha",required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    check(bool(HEX.fullmatch(a.expected_sha)),"Invalid expected SHA")
    raw=a.evidence.read_bytes()
    result=verify(json.loads(a.task.read_text(encoding="utf-8")),
                  json.loads(a.oem_report.read_text(encoding="utf-8")),
                  json.loads(raw),raw,a.expected_sha)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("PANDORA_OTA_DIAGNOSTIC_EVIDENCE=REVIEW_REQUIRED")


if __name__=="__main__":
    main()

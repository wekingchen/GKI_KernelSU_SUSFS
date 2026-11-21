#!/usr/bin/env python3
"""Offline fail-closed reviewer for pandora OS4.0.6 EEXIST testboot evidence."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path

RELEASE="6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k"
EXPECTED_NOTES={
    "zsmalloc":"531fad7a1fd7fa95976ea97c2cd9c402e63f578d6b0d19266b1545f547a62035",
    "zram":"e6c5c0c4c3cfa4ad9f5ea4828391459b3c556dc80a77fd9bd005df2699dc0280",
    "node_cache":"24755a08ebe111a8c8b0bbf30e25a6b32c2a0527654efb68109265bd36ef2b02",
}
NOTE_PATHS={m:f"/sys/module/{m}/notes/.note.gnu.build-id" for m in EXPECTED_NOTES}

def read(folder:Path,name:str,limit:int=100000)->str:
    p=folder/name
    if not p.is_file() or p.is_symlink():
        return ""
    if p.stat().st_size>limit:
        raise ValueError("oversized evidence: "+name)
    return p.read_text(encoding="utf-8-sig",errors="replace").replace("\r","").strip()

def module_names(text:str)->set[str]:
    out=set()
    for line in text.splitlines():
        if re.fullmatch(r"[A-Za-z0-9_-]+\s+size=\d+\s+users=\d+",line.strip()):
            out.add(line.split()[0])
    return out

def note_state(folder:Path,module:str)->dict:
    raw=read(folder,f"loaded-{module.replace('_','-')}-note-sha.txt",512)
    m=re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?(/\S+)",raw)
    if not m:
        return {"state":"UNAVAILABLE","match":False}
    digest=m.group(1).lower()
    path=m.group(2)
    if path!=NOTE_PATHS[module]:
        return {"state":"WRONG_PATH","match":False,"observed_sha256":digest,"path":path}
    return {
        "state":"MATCH_VENDOR_STOCK" if digest==EXPECTED_NOTES[module] else "MISMATCH",
        "match":digest==EXPECTED_NOTES[module],
        "observed_sha256":digest,
        "expected_sha256":EXPECTED_NOTES[module],
        "path":path,
    }

def evaluate(folder:Path)->dict:
    r={
        "schema":1,
        "experiment":"PANDORA_RUST_BINDER_EEXIST_SHIM",
        "verdict":"FAIL_CLOSED",
        "temporary_boot_pass":False,
        "persistent_flash":False,
        "lkg_promotion":False,
        "formal_oem_gate":"BLOCKED",
        "reason":"unverified evidence",
    }
    try:
        device=read(folder,"device.txt")
        build=read(folder,"build.txt")
        slot=read(folder,"slot.txt")
        uname=read(folder,"uname.txt")
        boot=read(folder,"boot-completed.txt")
        r["identity"]={"device":device,"build":build,"slot":slot,"uname":uname,"boot_completed":boot}
        if device!="pandora" or build!="OS4.0.6.0.XBLCNXM":
            raise ValueError("wrong device/build")
        if slot not in ("_a","_b") or uname!=RELEASE or boot!="1":
            raise ValueError("slot/uname/boot-completed mismatch")

        params=set(read(folder,"filtered-kernel-params.txt").splitlines())
        r["filtered_kernel_params"]=sorted(x for x in params if x)
        if "pandora_rust_binder_eexist=1" not in params:
            raise ValueError("EEXIST shim kernel parameter missing")
        blacklist=[x for x in params if x.startswith("module_blacklist=")]
        if len(blacklist)!=1 or "kernelsu" not in blacklist[0].split("=",1)[1].split(","):
            raise ValueError("kernelsu LKM guard missing")
        if "rust_binder" in blacklist[0].split("=",1)[1].split(","):
            raise ValueError("rust_binder must not be blacklisted")

        impl=read(folder,"binder-impl.txt")
        active=read(folder,"binder-active-impl.txt")
        r["binder"]={"impl":impl or "UNKNOWN","active_impl":active or "UNKNOWN"}
        if impl!="c":
            raise ValueError("Binder requested implementation is not c")
        if active not in ("","c"):
            raise ValueError("Binder active_impl is not c")
        if active=="c":
            r["binder"]["active_impl_directly_verified"]=True
        else:
            r["binder"]["active_impl_directly_verified"]=False

        loaded=module_names(read(folder,"loaded-modules-redacted.txt"))
        r["loaded_selected_modules"]=sorted(loaded)
        required={"zsmalloc","zram","node_cache"}
        if not required.issubset(loaded):
            raise ValueError("vendor memory-stack module missing")
        if "rust_binder" in loaded:
            raise ValueError("OEM rust_binder unexpectedly loaded despite EEXIST shim")
        if "kernelsu" in loaded:
            raise ValueError("KernelSU LKM unexpectedly loaded despite guard")
        initstate=read(folder,"rust-binder-initstate.txt")
        r["rust_binder_initstate"]=initstate or "UNKNOWN"
        if initstate!="ABSENT":
            raise ValueError("rust_binder sysfs module state is not ABSENT")

        activity=read(folder,"binder-service-activity.txt")
        package=read(folder,"binder-service-package.txt")
        r["binder_service_checks"]={"activity":activity,"package":package}
        if not re.search(r"Service\s+activity:\s+found",activity,re.I):
            raise ValueError("activity Binder service check failed")
        if not re.search(r"Service\s+package:\s+found",package,re.I):
            raise ValueError("package Binder service check failed")

        notes={m:note_state(folder,m) for m in EXPECTED_NOTES}
        r["runtime_vendor_note_evidence"]=notes
        available=[v for v in notes.values() if v["state"]!="UNAVAILABLE"]
        if any(not v["match"] for v in available):
            raise ValueError("runtime vendor GNU Note mismatch")
        r["runtime_vendor_note_matches"]=sum(1 for v in notes.values() if v["match"])
        r["runtime_vendor_notes_complete"]=all(v["match"] for v in notes.values())

        shimlog=read(folder,"shim-kernel-log.txt",4096)
        r["shim_kernel_log_observed"]=bool(shimlog)
        r["shim_kernel_log"]=shimlog
        # Kernel log visibility can be restricted to shell; it is corroborative,
        # not required when the cmdline token is present and rust_binder is absent.

        r["verdict"]="PASS_EXPERIMENTAL_FASTBOOT_BOOT_ONLY"
        r["temporary_boot_pass"]=True
        r["reason"]=(
            "C Binder is live, rust_binder insertion is suppressed, selected vendor "
            "memory-stack remains loaded, and Binder service checks respond. "
            "Formal OEM ABI gate remains BLOCKED."
        )
    except Exception as exc:
        r["reason"]=str(exc)[:300]
    return r

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--evidence-dir",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    result=evaluate(a.evidence_dir)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n")
    print(result["verdict"]+" / FORMAL OEM ABI "+result["formal_oem_gate"])
    return 0 if result["temporary_boot_pass"] else 1

if __name__=="__main__":
    raise SystemExit(main())

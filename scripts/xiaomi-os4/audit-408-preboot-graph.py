#!/usr/bin/env python3
"""Read-only conditional graph audit. Never changes production OEM gate or authorizes boot."""
import argparse, collections, hashlib, importlib.util, json
from pathlib import Path

spec=importlib.util.spec_from_file_location("delta",Path(__file__).with_name("compare-stock-abi-inventory.py"))
delta=importlib.util.module_from_spec(spec)
spec.loader.exec_module(delta)
abi=delta.abi
STOCK="957ea67209374ce18465859bd5088bcb382b7518fd809cb30cfdfb3b636541a9"
SYMVERS="242f6b3668e6f895c894bfbd35096c2f408a1b546b3cd0649bae4ed1d99dce25"
RUST="ea5a84225ce1af3c8af7effed891aa91ed879a9d85780d40a31aa79d3fbcd34c"
EVIDENCE="6330868f3c2f834e525ed4112dced3bc2aed1b55ccca09f41f312a4c34069c61"
SELECTED={"node_cache":"bc78bab29b624743419e5a3d7f7f8586dc9f30d682cf3a65608c79601b7ddefd",
          "zram":"6737e77c46b0a5a998adf552c42191e97068c393c506d83679d24c320f13d166",
          "zsmalloc":"350f7127f0a8cda912eea8dfe6d93dbf30e5b31832969aa44ee6161424eaed3e"}

def require(value,message):
    if not value: raise ValueError(message)

def main():
    p=argparse.ArgumentParser()
    for k in ("stock","symvers","evidence","raw-report","output"):
        p.add_argument("--"+k,required=True,type=Path)
    a=p.parse_args()
    require(delta.digest(a.symvers.read_bytes())==SYMVERS,"candidate symvers mismatch")
    require(delta.digest(a.evidence.read_bytes())==EVIDENCE,"evidence mismatch")
    e=json.loads(a.evidence.read_text())
    require(e["stock_input_sha256"]==STOCK and e["stock_build"]=="OS4.0.8.0.XBLCNXM" and e["source_run_id"]==46148429897,"evidence provenance")
    raw=json.loads(a.raw_report.read_text())
    require(raw["stock_input_sha256"]==STOCK and raw["gate"]=="BLOCKED" and raw["eligible_for_fastboot_boot"] is False and raw["stock_rust_binder_sha256"]==RUST and not raw["failed_modules"] and not raw["crc_mismatches"],"original gate drift")
    rows,_=delta.inventory(a.stock,STOCK)
    dlkm={r["sha256"] for k,r in rows.items() if not k.startswith("vendor_boot/")}
    records=[r for k,r in rows.items() if not (k.startswith("vendor_boot/") and r["sha256"] in dlkm)]
    require(len(records)==673 and sum(len(r["imports"]) for r in records)==39001,"full inventory drift")
    notes=e["observations"]["loaded_module_identity"]
    for name,digest in SELECTED.items():
        matches=[r for r in records if r["module_name"]==name and r["sha256"]==digest]
        require(len(matches)==1 and notes[name]["loaded"] is True and notes[name]["gnu_note_sha256"]==matches[0]["note_sha256"],"runtime note identity mismatch: "+name)
    rust=[r for r in records if r["module_name"]=="rust_binder"]
    require(len(rust)==1 and rust[0]["sha256"]==RUST,"Rust Binder identity drift")
    # Conditional model only: if the experiment retains the observed vendor
    # memory stack and C Binder remains active with the exact EEXIST route.
    # This does not attest the future runtime or grant any boot permission.
    active=[r for r in records if r["module_name"]!="rust_binder" and (r["module_name"] not in SELECTED or r["sha256"]==SELECTED[r["module_name"]])]
    exports=abi.symvers(a.symvers)
    providers=collections.defaultdict(list)
    for r in active:
        for name,crc in r["exports"].items(): providers[name].append((r["path"],crc))
    unresolved=[]; mismatch=[]; ambiguous=[]; count=0
    for r in active:
        for name,crc in r["imports"].items():
            count+=1
            sources=providers.get(name,[])
            if name in exports: sources=[("vmlinux",exports[name])]+sources
            item={"consumer":r["path"],"symbol":name,"expected_crc":crc,"providers":sources}
            if not sources: unresolved.append(item)
            elif len(sources)!=1 or sources[0][0]==r["path"]: ambiguous.append(item)
            elif sources[0][1]!=crc: mismatch.append(item)
    out={"schema":"pandora-408-conditional-preboot-graph-v1","stock_input_sha256":STOCK,"evidence_sha256":EVIDENCE,
         "candidate_symvers_sha256":SYMVERS,"raw_gate":"BLOCKED","hypothesis":"C_BINDER_EEXIST_AND_CURRENT_VENDOR_MEMORY_STACK_RETAINED",
         "inventory_imports":39001,"conditional_imports_checked":count,"unresolved":unresolved,"crc_mismatches":mismatch,
         "ambiguous":ambiguous,"excluded_paths":[r["path"] for r in records if r not in active],
         "formal_oem_gate_unlocked":False,"eligible_for_fastboot_boot":False,"safe_to_flash":False,"lkg_promotion":False}
    out["conditional_result"]="MATCH_UNDER_UNVERIFIED_RUNTIME_ASSUMPTIONS" if not (unresolved or mismatch or ambiguous) else "REVIEW_REQUIRED"
    a.output.write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps(out,indent=2))
if __name__=="__main__": main()

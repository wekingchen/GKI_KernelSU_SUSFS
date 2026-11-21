#!/usr/bin/env python3
"""Packaging-only probe using exact stock + official r74 Image.

This deliberately does NOT create a user-deliverable boot artifact. It supplies
an explicit synthetic shadow-gate object only to exercise the boot layout
packager against the pinned real stock partition image, then deletes the output.
"""
from __future__ import annotations
import argparse, hashlib, json, struct, subprocess, sys, tempfile
from pathlib import Path

EXACT_STOCK_ZIP="bebb8754c16dd30c724fdba3687694e615e03342d6f5f55918cd06f1dca8cbb8"
EXACT_COMMIT="b1d12d482d767c50cb792d988e4479d3f75c342a"

def sha(p: Path)->str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--stock-zip",type=Path,required=True)
    ap.add_argument("--stock-report",type=Path,required=True)
    ap.add_argument("--candidate-image",type=Path,required=True)
    ap.add_argument("--build-metadata",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    if sha(a.stock_zip)!=EXACT_STOCK_ZIP:
        raise SystemExit("ERROR: stock ZIP drift")
    stock=json.loads(a.stock_report.read_text())
    meta=dict(line.split("=",1) for line in a.build_metadata.read_text().splitlines() if "=" in line)
    if meta.get("SOURCE_GKI_COMMIT")!=EXACT_COMMIT:
        raise SystemExit("ERROR: candidate commit drift")
    if sha(a.candidate_image)!=meta.get("IMAGE_SHA256"):
        raise SystemExit("ERROR: candidate Image SHA drift")
    base=Path(__file__).resolve().parent
    pack=base/"package-pandora-406-eexist-testboot-v4.py"
    with tempfile.TemporaryDirectory() as td:
        d=Path(td)
        gate=d/"shadow.json"
        gate.write_text(json.dumps({
            "formal_oem_gate":"BLOCKED",
            "formal_oem_gate_unchanged":True,
            "experimental_gate":"RUNTIME_SELECTED_EEXIST_SHIM_TEST_ELIGIBLE",
            "eligible_for_fastboot_boot_experiment":True,
            "flashable":False,
            "lkg_promotion":False,
        }))
        em=d/"meta.txt"
        em.write_text(a.build_metadata.read_text()+
                      "\nEXPERIMENT=PANDORA_RUST_BINDER_EEXIST_SHIM\n"
                      "FORMAL_OEM_GATE=BLOCKED\nFLASHABLE=NO\n")
        out=d/"layout-only.img"
        p=subprocess.run([
            sys.executable,str(pack),
            "--stock-zip",str(a.stock_zip),
            "--stock-report",str(a.stock_report),
            "--shadow-gate",str(gate),
            "--metadata",str(em),
            "--candidate-image",str(a.candidate_image),
            "--output",str(out),
        ],capture_output=True,text=True)
        if p.returncode:
            raise SystemExit(p.stderr+p.stdout)
        if "STOCK_PARTITION_AVB_FOOTER=PRESENT_STRIPPED" not in p.stdout:
            raise SystemExit("ERROR: outer AVB strip marker missing")
        if "STOCK_INNER_GKI_AVB=PRESENT_VERIFIED_STRIPPED" not in p.stdout:
            raise SystemExit("ERROR: inner GKI AVB strip marker missing")
        b=out.read_bytes()
        image=a.candidate_image.read_bytes()
        page=4096
        expected=page+((len(image)+page-1)//page)*page
        if len(b)!=expected or b[:8]!=b"ANDROID!" or b[-64:-60]==b"AVBf":
            raise SystemExit("ERROR: logical fastboot boot layout invalid")
        if struct.unpack_from("<I",b,8)[0]!=len(image):
            raise SystemExit("ERROR: embedded kernel size mismatch")
        lines=[
            "REAL_STOCK_LOGICAL_PACKAGING=PASS",
            "DELIVERABLE_BOOT=NO",
            "PURPOSE=LAYOUT_ONLY",
            f"output_logical_size={len(b)}",
            f"candidate_image_sha256={sha(a.candidate_image)}",
        ]+p.stdout.strip().splitlines()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text("\n".join(lines)+"\n")
    print("\n".join(lines))

if __name__=="__main__":
    main()

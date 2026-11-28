#!/usr/bin/env python3
"""Create a NONFLASH boot-v4 fixture from the exact same-OTA stock boot.

This fixture is intentionally *not* human-tested. It exists only so an
isolated compatibility Image can be wrapped for a reversible `fastboot boot`
experiment without borrowing a previous OTA's boot header or claiming an ABI
gate pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import zipfile
from pathlib import Path

PAGE=4096
CMD=44
CMD_LEN=1536
MAX_BOOT=200*1024*1024
BOOT_RE=re.compile(r"boot(?:_[^/]*)?\.img$",re.I)
PARAM_RE=re.compile(r"^[A-Za-z0-9_.-]+=[A-Za-z0-9_.-]+$")


def sha(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()


def fail(msg:str):
    raise SystemExit("ERROR: "+msg)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--stock-zip",type=Path,required=True)
    ap.add_argument("--stock-report",type=Path,required=True)
    ap.add_argument("--expected-build",required=True)
    ap.add_argument("--expected-stock-sha256",required=True)
    ap.add_argument("--compatibility-parameter",required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    if not PARAM_RE.fullmatch(a.compatibility_parameter):
        fail("invalid compatibility parameter")
    report=json.loads(a.stock_report.read_text(encoding="utf-8"))
    stock_bytes=a.stock_zip.read_bytes()
    if sha(stock_bytes)!=a.expected_stock_sha256 or report.get("ota_source_id")!=a.expected_stock_sha256:
        fail("stock input SHA mismatch")
    if report.get("build")!=a.expected_build or report.get("kernel_marker_verified") is not True:
        fail("stock report identity not verified")
    with zipfile.ZipFile(a.stock_zip) as z:
        boots=[x for x in z.infolist() if not x.is_dir() and BOOT_RE.fullmatch(x.filename.rsplit("/",1)[-1])]
        if len(boots)!=1 or boots[0].file_size>MAX_BOOT:
            fail("requires exactly one bounded stock boot image")
        boot=z.read(boots[0])
    if sha(boot)!=report.get("stock_boot_sha256"):
        fail("stock boot SHA mismatch")
    if len(boot)<PAGE or boot[:8]!=b"ANDROID!":
        fail("stock boot magic invalid")
    kernel_size,ramdisk_size,os_version,header_size=struct.unpack_from("<IIII",boot,8)
    reserved=list(struct.unpack_from("<4I",boot,24))
    header_version=struct.unpack_from("<I",boot,40)[0]
    signature_size=struct.unpack_from("<I",boot,1580)[0]
    if header_version!=4 or header_size!=1584 or ramdisk_size!=0 or signature_size!=0:
        fail("unsupported stock boot-v4 layout")
    aligned=(kernel_size+PAGE-1)//PAGE*PAGE
    structural_size=PAGE+aligned
    if kernel_size<=0 or structural_size>len(boot):
        fail("stock kernel range invalid")
    suffix=boot[structural_size:]
    boot_payload_size=structural_size
    avb={"stock_structural_size":structural_size}
    if suffix.strip(b"\0"):
        if len(boot)<64 or boot[-64:-60]!=b"AVBf":
            fail("stock boot has unexplained nonzero suffix")
        try:
            magic,major,minor,original_size,vbmeta_offset,vbmeta_size,reserved=struct.unpack(">4sIIQQQ28s",boot[-64:])
        except struct.error:
            fail("stock AVB footer cannot be parsed")
        if magic!=b"AVBf" or major!=1 or original_size<structural_size:
            fail("stock AVB footer identity/original size mismatch: "+
                 f"major={major} minor={minor} original_size={original_size} "+
                 f"structural_size={structural_size} vbmeta_offset={vbmeta_offset} "+
                 f"vbmeta_size={vbmeta_size} partition_size={len(boot)}")
        if not (original_size<=vbmeta_offset<=len(boot)-64 and
                0<vbmeta_size<=len(boot)-64-vbmeta_offset):
            fail("stock AVB vbmeta range invalid")
        if boot[vbmeta_offset:vbmeta_offset+4]!=b"AVB0":
            fail("stock AVB vbmeta magic missing")
        pre=boot[structural_size:original_size]
        gap=boot[original_size:vbmeta_offset]
        post=boot[vbmeta_offset+vbmeta_size:-64]
        if pre.strip(b"\0") or gap.strip(b"\0") or post.strip(b"\0"):
            def desc(data):
                nz=sum(1 for x in data if x)
                first=next((i for i,x in enumerate(data) if x),-1)
                sample=(data[first:first+16].hex() if first>=0 else "")
                return f"len={len(data)},nonzero={nz},first={first},sample={sample}"
            fail("unexpected nonzero data outside stock AVB metadata: "+
                 "pre["+desc(pre)+"] gap["+desc(gap)+"] post["+desc(post)+"]")
        boot_payload_size=original_size
        avb.update({"stock_had_avb_footer":True,
                    "stock_partition_size":len(boot),
                    "stock_avb_original_image_size":original_size,
                    "stock_avb_footer_sha256":sha(boot[-64:]),
                    "stock_vbmeta_sha256":sha(boot[vbmeta_offset:vbmeta_offset+vbmeta_size]),
                    "stock_avb_version":f"{major}.{minor}"})
    else:
        avb.update({"stock_had_avb_footer":False,"stock_partition_size":len(boot)})
    raw=boot[CMD:CMD+CMD_LEN]
    if b"\0" not in raw:
        fail("stock boot cmdline is not NUL-terminated")
    original=raw.split(b"\0",1)[0]
    tokens=original.split()
    key=a.compatibility_parameter.split("=",1)[0].encode()
    conflicting=[x for x in tokens if x.startswith(key+b"=")]
    wanted=a.compatibility_parameter.encode()
    if conflicting and conflicting!=[wanted]:
        fail("stock cmdline contains conflicting compatibility parameter")
    if not conflicting:
        tokens.append(wanted)
    cmdline=b" ".join(tokens)
    if len(cmdline)+1>CMD_LEN:
        fail("stock cmdline has no room for compatibility parameter")
    kernel=boot[PAGE:PAGE+kernel_size]
    fixture={
        "schema":2,
        "source":"same-OTA stock-derived UNVERIFIED compatibility FASTBOOT-BOOT-ONLY",
        "human_tested":False,
        "safe_to_flash":False,
        "formal_oem_gate":"BLOCKED_PREBOOT_COMPAT_EXPERIMENT",
        "stock_build":a.expected_build,
        "stock_input_sha256":a.expected_stock_sha256,
        "stock_boot_sha256":sha(boot),
        "baseline_kernel_sha256":sha(kernel),
        # fastboot boot uses the unsigned structural boot image.  If the
        # partition capture carries an AVB footer, never copy the now-invalid
        # footer after replacing the kernel.
        "boot_size":boot_payload_size,
        "header_version":4,
        "header_size":1584,
        "kernel_size":kernel_size,
        "ramdisk_size":0,
        "signature_size":0,
        "header_v4":{"cmdline":cmdline.decode("ascii"),"os_version":os_version,"reserved":reserved},
        "ramdisk_region_b64":"",
        "suffix_b64":"",
        "compatibility_kind":"PANDORA_RUST_BINDER_EEXIST_SHIM",
        "compatibility_parameter":a.compatibility_parameter,
        **avb,
    }
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(fixture,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print("STOCK_DERIVED_FIXTURE=PASS_UNVERIFIED_NONFLASH")
    print("stock_boot_sha256="+fixture["stock_boot_sha256"])
    print("stock_kernel_sha256="+fixture["baseline_kernel_sha256"])
    print("boot_size="+str(fixture["boot_size"]))
    print("stock_partition_size="+str(fixture["stock_partition_size"]))
    print("stock_had_avb_footer="+str(fixture["stock_had_avb_footer"]).lower())
    print("safe_to_flash=false")


if __name__=="__main__":
    main()

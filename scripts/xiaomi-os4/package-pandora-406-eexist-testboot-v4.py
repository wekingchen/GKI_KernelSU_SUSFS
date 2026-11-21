#!/usr/bin/env python3
"""Package one pandora OS4.0.6 EEXIST-shim experiment for fastboot boot only."""
from __future__ import annotations
import argparse, hashlib, json, re, struct, zipfile
from pathlib import Path

PAGE=4096
CMD=44
CMD_LEN=1536
MAX_BOOT=200*1024*1024
BOOT_RE=re.compile(r"boot(?:_[^/]*)?\.img$",re.I)
FLAG=b"pandora_rust_binder_eexist=1"

def sha(b: bytes)->str: return hashlib.sha256(b).hexdigest()
def fail(s): raise SystemExit("ERROR: "+s)

def add_token(cmdline: bytes, token: bytes)->bytes:
    toks=cmdline.split()
    key=token.split(b"=",1)[0]+b"="
    existing=[x for x in toks if x.startswith(key)]
    if existing and existing != [token]:
        fail("conflicting kernel parameter: "+key.decode())
    if not existing: toks.append(token)
    return b" ".join(toks)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--stock-zip",type=Path,required=True)
    ap.add_argument("--stock-report",type=Path,required=True)
    ap.add_argument("--shadow-gate",type=Path,required=True)
    ap.add_argument("--metadata",type=Path,required=True)
    ap.add_argument("--candidate-image",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    stock=json.loads(a.stock_report.read_text())
    gate=json.loads(a.shadow_gate.read_text())
    meta=dict(line.split("=",1) for line in a.metadata.read_text().splitlines() if "=" in line)
    if not (gate.get("formal_oem_gate")=="BLOCKED" and
            gate.get("formal_oem_gate_unchanged") is True and
            gate.get("experimental_gate")=="RUNTIME_SELECTED_EEXIST_SHIM_TEST_ELIGIBLE" and
            gate.get("eligible_for_fastboot_boot_experiment") is True and
            gate.get("flashable") is False and gate.get("lkg_promotion") is False):
        fail("experimental shadow gate not eligible")
    if meta.get("SOURCE_GKI_COMMIT")!="b1d12d482d767c50cb792d988e4479d3f75c342a":
        fail("not exact r74 source")
    if meta.get("EXPERIMENT")!="PANDORA_RUST_BINDER_EEXIST_SHIM":
        fail("wrong experiment metadata")
    if meta.get("FORMAL_OEM_GATE")!="BLOCKED" or meta.get("FLASHABLE")!="NO":
        fail("metadata tried to relax formal safety")
    if meta.get("KERNEL_RELEASE")!=stock.get("uname"):
        fail("candidate release differs from stock")
    if sha(a.stock_zip.read_bytes())!=stock.get("ota_source_id"):
        fail("stock input SHA drift")
    with zipfile.ZipFile(a.stock_zip) as z:
        items=[i for i in z.infolist() if not i.is_dir() and BOOT_RE.fullmatch(i.filename.rsplit("/",1)[-1])]
        if len(items)!=1 or items[0].file_size>MAX_BOOT: fail("requires exactly one stock boot")
        boot=z.read(items[0])
    if sha(boot)!=stock.get("stock_boot_sha256"): fail("stock boot hash drift")
    if len(boot)<PAGE or boot[:8]!=b"ANDROID!": fail("bad boot image")
    ks,rs,_,hs=struct.unpack_from("<IIII",boot,8)
    hv=struct.unpack_from("<I",boot,40)[0]
    sig=struct.unpack_from("<I",boot,1580)[0]
    if hv!=4 or hs!=1584 or rs!=0 or sig!=0: fail("unsupported boot-v4 layout")
    stock_has_avb_footer=(len(boot)>=AVB_FOOTER_SIZE and
                          boot[-AVB_FOOTER_SIZE:-AVB_FOOTER_SIZE+4]==b"AVBf")
    if stock_has_avb_footer:
        magic,major,minor,original_size,vbmeta_offset,vbmeta_size=struct.unpack(
            ">4sIIQQQ",boot[-AVB_FOOTER_SIZE:-AVB_FOOTER_SIZE+36])
        if magic!=b"AVBf" or major!=1 or minor>0:
            fail("unsupported AVB footer version")
        if not (PAGE<=original_size<=vbmeta_offset<len(boot)-AVB_FOOTER_SIZE):
            fail("invalid AVB footer offsets")
        if vbmeta_size<=0 or vbmeta_offset+vbmeta_size>len(boot)-AVB_FOOTER_SIZE:
            fail("invalid AVB vbmeta bounds")
        stock_payload=boot[:original_size]
    else:
        original_size=len(boot)
        vbmeta_offset=0
        vbmeta_size=0
        stock_payload=boot
    stock_kernel_end=PAGE+((ks+PAGE-1)//PAGE)*PAGE
    if stock_kernel_end>len(stock_payload):
        fail("stock kernel exceeds original boot payload")
    # For boot-v4 with no ramdisk/signature, bytes after the aligned kernel in
    # the pre-AVB image must be padding only. AVB vbmeta/footer are partition
    # metadata and are intentionally not copied into a temporary fastboot boot.
    if stock_payload[stock_kernel_end:].strip(b"\0"):
        fail("pre-AVB stock boot trailing data is nonzero")
    image=a.candidate_image.read_bytes()
    if sha(image)!=meta.get("IMAGE_SHA256"): fail("experimental Image hash mismatch")
    release=stock["uname"].encode()
    if release not in image: fail("stock release marker absent from Image")
    candidate_payload_size=PAGE+((len(image)+PAGE-1)//PAGE)*PAGE
    if candidate_payload_size>len(boot)-AVB_FOOTER_SIZE:
        fail("Image too large for stock boot partition envelope")
    header=bytearray(boot[:PAGE])
    raw=bytes(header[CMD:CMD+CMD_LEN])
    if b"\0" not in raw: fail("cmdline field not terminated")
    cmd=raw.split(b"\0",1)[0]
    if b"module_blacklist=rust_binder" in cmd:
        fail("EPERM rust_binder blacklist is forbidden for EEXIST experiment")
    # Preserve existing module_blacklist and only ensure kernelsu is excluded.
    toks=cmd.split()
    mb=[x for x in toks if x.startswith(b"module_blacklist=")]
    if len(mb)>1: fail("ambiguous module_blacklist")
    if mb:
        vals=mb[0].split(b"=",1)[1].split(b",")
        if b"kernelsu" not in vals:
            toks=[x+b",kernelsu" if x==mb[0] else x for x in toks]
        cmd=b" ".join(toks)
    else:
        cmd=add_token(cmd,b"module_blacklist=kernelsu")
    cmd=add_token(cmd,FLAG)
    if len(cmd)>=CMD_LEN: fail("cmdline overflow")
    header[CMD:CMD+CMD_LEN]=b"\0"*CMD_LEN
    header[CMD:CMD+len(cmd)]=cmd
    struct.pack_into("<I",header,8,len(image))
    out=bytearray(header)
    out+=image
    out+=b"\0"*(candidate_payload_size-len(out))
    if len(out)!=candidate_payload_size:
        fail("logical fastboot boot size mismatch")
    if len(out)>=AVB_FOOTER_SIZE and out[-AVB_FOOTER_SIZE:-AVB_FOOTER_SIZE+4]==b"AVBf":
        fail("output unexpectedly retained AVB footer")
    outcmd=bytes(out[CMD:CMD+CMD_LEN]).split(b"\0",1)[0].split()
    if FLAG not in outcmd: fail("shim enable flag missing")
    if not any(x.startswith(b"module_blacklist=") and b"kernelsu" in x.split(b"=",1)[1].split(b",") for x in outcmd):
        fail("kernelsu LKM guard missing")
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_bytes(out)
    print("EXPERIMENTAL_TESTBOOT=PASS")
    print("FORMAL_OEM_GATE=BLOCKED")
    print("STOCK_PARTITION_AVB_FOOTER="+("PRESENT_STRIPPED" if stock_has_avb_footer else "ABSENT"))
    print("FLASHABLE=NO")
    print("USE=fastboot boot ONLY")
    print("BOOT_SHA256="+sha(out))
    print("CMDLINE="+cmd.decode("ascii","replace"))

if __name__=="__main__": main()

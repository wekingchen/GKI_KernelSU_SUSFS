#!/usr/bin/env python3
"""Package one pandora OS4.0.6 EEXIST-shim experiment for fastboot boot only."""
from __future__ import annotations
import argparse, hashlib, json, re, struct, zipfile
from pathlib import Path

PAGE=4096
CMD=44
CMD_LEN=1536
MAX_BOOT=200*1024*1024
AVB_FOOTER_SIZE=64
EXACT_STOCK_ZIP_SHA256="bebb8754c16dd30c724fdba3687694e615e03342d6f5f55918cd06f1dca8cbb8"
EXACT_STOCK_BOOT_SHA256="a75b2dd5596f75474fad2da8e8e64bb0a6398864d4b7f593d1f0dd1c9328979b"
EXACT_STOCK_INNER_GKI_AVB_LEN=16384
EXACT_STOCK_INNER_GKI_AVB_SHA256="824bf63be36ecd15c0f049d73c4a925efc6fda85dd6901e0f38c9a91ed740d77"
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
    # Exact OS4.0.6 stock has a 16K GKI boot signature immediately after
    # the aligned kernel. Its AVB hash descriptor signs the STOCK kernel, so it
    # must never be copied onto a replacement Image. Accept only the pinned
    # exact signature blob; any other nonzero pre-outer-AVB tail fails closed.
    inner_tail=stock_payload[stock_kernel_end:]
    exact_stock=(stock.get("ota_source_id")==EXACT_STOCK_ZIP_SHA256)
    stock_inner_gki_avb="ABSENT"
    if exact_stock:
        if sha(boot)!=EXACT_STOCK_BOOT_SHA256:
            fail("exact stock boot SHA mismatch")
        if not stock_has_avb_footer:
            fail("exact stock boot lost outer AVB footer")
        if (len(inner_tail)!=EXACT_STOCK_INNER_GKI_AVB_LEN or
                not inner_tail.startswith(b"AVB0") or
                sha(inner_tail)!=EXACT_STOCK_INNER_GKI_AVB_SHA256):
            fail("exact stock inner GKI AVB signature drift")
        stock_inner_gki_avb="PRESENT_VERIFIED_STRIPPED"
    elif inner_tail.strip(b"\0"):
        fail("pre-AVB stock boot trailing data is nonzero")
    image=a.candidate_image.read_bytes()
    if sha(image)!=meta.get("IMAGE_SHA256"): fail("experimental Image hash mismatch")
    release=stock["uname"].encode()
    if release not in image: fail("stock release marker absent from Image")
    candidate_payload_size=PAGE+((len(image)+PAGE-1)//PAGE)*PAGE
    # This artifact is for fastboot boot only and deliberately carries no old
    # AVB metadata. A replacement Image may be larger than the stock signed
    # payload/vbmeta offset; it only has to fit the known boot partition size.
    # Persistent flashing remains forbidden by the surrounding shadow gate.
    payload_capacity=len(boot)
    if candidate_payload_size>payload_capacity:
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
    print("STOCK_PARTITION_SIZE="+str(len(boot)))
    print("STOCK_ORIGINAL_BOOT_SIZE="+str(original_size))
    print("STOCK_AVB_VBMETA_OFFSET="+str(vbmeta_offset))
    print("STOCK_AVB_VBMETA_SIZE="+str(vbmeta_size))
    print("STOCK_INNER_GKI_AVB="+stock_inner_gki_avb)
    print("FASTBOOT_BOOT_LOGICAL_SIZE="+str(len(out)))
    print("FLASHABLE=NO")
    print("USE=fastboot boot ONLY")
    print("BOOT_SHA256="+sha(out))
    print("CMDLINE="+cmd.decode("ascii","replace"))

if __name__=="__main__": main()

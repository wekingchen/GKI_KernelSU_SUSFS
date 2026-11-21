#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, struct, zipfile
from pathlib import Path

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--stock-zip",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    with zipfile.ZipFile(a.stock_zip) as z:
        items=[i for i in z.infolist() if not i.is_dir() and i.filename.rsplit("/",1)[-1]=="boot.img"]
        if len(items)!=1:
            raise SystemExit("ERROR: expected exactly one boot.img")
        b=z.read(items[0])
    if len(b)<4096 or b[:8]!=b"ANDROID!":
        raise SystemExit("ERROR: invalid Android boot image")
    ks,rs,osv,hs=struct.unpack_from("<IIII",b,8)
    hv=struct.unpack_from("<I",b,40)[0]
    sig=struct.unpack_from("<I",b,1580)[0]
    page=4096
    kernel_end=page+((ks+page-1)//page)*page
    if len(b)<64:
        raise SystemExit("ERROR: partition image too small")
    magic,major,minor,orig,vbo,vbs=struct.unpack(">4sIIQQQ28x",b[-64:])
    region=b[kernel_end:orig] if kernel_end<=orig<=len(b) else b""
    nz=[i for i,x in enumerate(region) if x]
    def hx(x: bytes, n=64): return x[:n].hex()
    lines=[
        f"partition_size={len(b)}",
        f"boot_sha256={hashlib.sha256(b).hexdigest()}",
        f"header_version={hv}",
        f"header_size={hs}",
        f"kernel_size={ks}",
        f"ramdisk_size={rs}",
        f"signature_size={sig}",
        f"kernel_aligned_end={kernel_end}",
        f"footer_magic={magic.decode(errors='replace')}",
        f"footer_version={major}.{minor}",
        f"avb_original_image_size={orig}",
        f"avb_vbmeta_offset={vbo}",
        f"avb_vbmeta_size={vbs}",
        f"post_kernel_pre_original_len={len(region)}",
        f"post_kernel_pre_original_nonzero_bytes={len(nz)}",
        f"post_kernel_first_nonzero_offset={kernel_end+nz[0] if nz else 'NONE'}",
        f"post_kernel_last_nonzero_offset={kernel_end+nz[-1] if nz else 'NONE'}",
        f"post_kernel_region_sha256={hashlib.sha256(region).hexdigest()}",
        f"post_kernel_head64_hex={hx(region)}",
        f"post_kernel_tail64_hex={region[-64:].hex() if region else ''}",
        f"vbmeta_magic_at_offset={b[vbo:vbo+4].decode(errors='replace') if vbo+4<=len(b) else 'OOB'}",
        f"vbmeta_sha256={hashlib.sha256(b[vbo:vbo+vbs]).hexdigest() if vbo+vbs<=len(b) else 'OOB'}",
    ]
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text("\n".join(lines)+"\n")
    print("\n".join(lines))
if __name__=="__main__":
    main()

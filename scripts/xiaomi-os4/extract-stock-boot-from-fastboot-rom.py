#!/usr/bin/env python3
"""Stream a Xiaomi fastboot .tgz and stop after extracting images/boot.img."""
from __future__ import annotations
import argparse, hashlib, os, tarfile, urllib.request
from pathlib import Path

def sha256_file(p: Path) -> str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024), b""): h.update(b)
    return h.hexdigest()

ap=argparse.ArgumentParser()
ap.add_argument("url")
ap.add_argument("output", type=Path)
ap.add_argument("--expected-sha256", required=True)
args=ap.parse_args()

req=urllib.request.Request(args.url, headers={"User-Agent":"pandora-os4-ci/1.0"})
with urllib.request.urlopen(req, timeout=120) as resp:
    with tarfile.open(fileobj=resp, mode="r|gz") as tf:
        found=False
        for m in tf:
            name=m.name.replace("\\","/")
            if m.isfile() and (name.endswith("/images/boot.img") or name=="images/boot.img" or name.endswith("/boot.img")):
                src=tf.extractfile(m)
                if src is None: continue
                args.output.parent.mkdir(parents=True, exist_ok=True)
                with args.output.open("wb") as out:
                    while True:
                        chunk=src.read(1024*1024)
                        if not chunk: break
                        out.write(chunk)
                print(f"extracted_member={name}")
                found=True
                break
        if not found:
            raise SystemExit("ERROR: boot.img not found before stream ended")

got=sha256_file(args.output)
print(f"stock_boot_sha256={got}")
print(f"stock_boot_size={args.output.stat().st_size}")
if got.lower()!=args.expected_sha256.lower():
    raise SystemExit(f"ERROR: stock boot SHA256 mismatch: {got}")
print("stock_boot_verified=YES")

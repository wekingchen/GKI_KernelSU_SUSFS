#!/usr/bin/env python3
"""Small candidate sidecar for the mobile form; never replaces the server's IMG/ABI checks."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def create(stock, abi, boot, run, head, repository):
    build = stock.get('build', '')
    uname = stock.get('uname', '')
    if (repository != 'wekingchen/GKI_KernelSU_SUSFS' or not re.fullmatch(r'[1-9][0-9]*', str(run))
        or not re.fullmatch(r'[a-f0-9]{40}', head)
        or not re.fullmatch(r'OS[0-9]+\.[0-9.]+[A-Z0-9]+', build)
        or not re.fullmatch(r'6\.12\.[0-9]+-android16-6-[A-Za-z0-9_.-]+', uname)
        or stock.get('device') != 'pandora' or stock.get('status') != 'NEW_OTA_CANDIDATE'
        or stock.get('kernel_marker_verified') is not True
        or abi.get('eligible_for_fastboot_boot') is not True
        or abi.get('gate') != 'CRC_AND_VERMAGIC_MATCH_CANDIDATE'
        or abi.get('stock_build') != build or abi.get('kernel_release') != uname
        or abi.get('stock_input_sha256') != stock.get('ota_source_id')
        or not re.fullmatch(r'[a-f0-9]{64}', stock.get('ota_source_id', ''))):
        raise ValueError('candidate provenance / ABI evidence mismatch')
    if boot.name != f'pandora-{build}-UNVERIFIED-FASTBOOT-BOOT-ONLY.img' or not boot.is_file():
        raise ValueError('missing exact test boot filename')
    size = boot.stat().st_size
    if not 0 < size <= 200 * 1024 * 1024:
        raise ValueError('invalid test boot size')
    with boot.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    return dict(schema='pandora-mobile-feedback-v1', repository=repository, source_run_id=int(run),
                source_head_sha=head, device='pandora', build=build, expected_uname=uname,
                tested_boot_sha256=digest, filename=boot.name, eligible_for_fastboot_boot=True,
                verification_mode='USER_ATTESTATION_NOT_REMOTE_HARDWARE_PROOF')


def main():
    p = argparse.ArgumentParser()
    for name in ('stock-report', 'abi-report', 'boot', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    for name in ('run', 'head', 'repository'):
        p.add_argument('--' + name, required=True)
    a = p.parse_args()
    result = create(json.loads(a.stock_report.read_text()), json.loads(a.abi_report.read_text()),
                    a.boot, a.run, a.head, a.repository)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()

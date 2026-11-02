#!/usr/bin/env python3
"""Restore immutable GKI bytes, never select or compile a newer source."""
import argparse
import hashlib
import json
from pathlib import Path
import re

REQUIRED = {'Image', 'Module.symvers', 'final.config', 'build-metadata.txt', 'STATUS.txt',
            'SHA256SUMS.txt', 'locked-candidate.env', 'stock-report.json', 'gki-candidate.json'}

def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def verify(root, manifest_sha, build, input_sha, asset):
    root = Path(root)
    manifest = root / 'RELEASE-SHA256SUMS.txt'
    if not re.fullmatch('[a-f0-9]{64}', manifest_sha) or digest(manifest) != manifest_sha:
        raise ValueError('archive manifest SHA mismatch')
    records = {}
    for line in manifest.read_text().splitlines():
        m = re.fullmatch(r'([a-f0-9]{64})  ([A-Za-z0-9_.-]+)', line)
        if not m or m[2] in records or m[2] == manifest.name:
            raise ValueError('unsafe or duplicate archive entry')
        records[m[2]] = m[1]
    if not REQUIRED <= records.keys():
        raise ValueError('incomplete permanent candidate')
    for name, sha in records.items():
        path = root / name
        if path.is_symlink() or not path.is_file() or digest(path) != sha:
            raise ValueError('archive bytes changed: ' + name)
    stock = json.loads((root / 'stock-report.json').read_text())
    candidate = json.loads((root / 'gki-candidate.json').read_text())
    for report in (stock, candidate):
        if report.get('build') != build or report.get('ota_source_id') != input_sha or report.get('safe_to_flash') is not False:
            raise ValueError('archive input provenance mismatch')
    if str(stock.get('github_asset_id')) != str(asset):
        raise ValueError('current stock asset differs from locked archive')
    def env(name):
        return dict(line.split('=', 1) for line in (root / name).read_text().splitlines()
                    if '=' in line and not line.startswith('#'))
    locked, meta = env('locked-candidate.env'), env('build-metadata.txt')
    if locked.get('OTA_BUILD') != build or locked.get('OTA_INPUT_SHA256') != input_sha:
        raise ValueError('locked candidate differs')
    if (meta.get('STOCK_BUILD') != build or meta.get('STOCK_INPUT_SHA256') != input_sha
        or meta.get('IMAGE_SHA256') != digest(root / 'Image')
        or meta.get('SYMVERS_SHA256') != digest(root / 'Module.symvers')
        or meta.get('FLASHABLE') != 'NO' or meta.get('FASTBOOT_BOOT') != 'NOT_BUILT'
        or meta.get('SOURCE_GKI_COMMIT') != locked.get('OTA_GKI_COMMIT')
        or not re.fullmatch('[a-f0-9]{40}', meta.get('SOURCE_GKI_COMMIT', ''))):
        raise ValueError('locked metadata mismatch')
    return {'archive_manifest_sha256': manifest_sha, 'build': build, 'input_sha256': input_sha,
            'github_asset_id': str(asset), 'image_sha256': digest(root / 'Image'),
            'source_commit': meta['SOURCE_GKI_COMMIT'], 'recompiled': False}

def main():
    p = argparse.ArgumentParser()
    for key in ('directory', 'manifest-sha', 'build', 'input-sha', 'asset'):
        p.add_argument('--' + key, required=True)
    a = p.parse_args()
    print(json.dumps(verify(a.directory, a.manifest_sha, a.build, a.input_sha, a.asset), indent=2))

if __name__ == '__main__':
    main()

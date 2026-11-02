#!/usr/bin/env python3
"""Durable fixed-input switch. All recovery mutations are scoped to a pinned journal."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

REPO = 'wekingchen/GKI_KernelSU_SUSFS'
TAG = 'pandora-os4-stock-input'

def sha(data):
    return hashlib.sha256(data).hexdigest()

class GitHub:
    def api(self, path, method='GET', **fields):
        cmd = ['gh', 'api', '-X', method, f'repos/{REPO}/{path}']
        for k, v in fields.items():
            cmd += ['-f', f'{k}={v}']
        raw = subprocess.check_output(cmd)
        return json.loads(raw) if raw.strip() else None

    def download(self, asset):
        return subprocess.check_output(['gh', 'api', '-H', 'Accept: application/octet-stream',
                                        f'repos/{REPO}/releases/assets/{int(asset)}'])

    def upload(self, release, name, data):
        with tempfile.NamedTemporaryFile() as f:
            f.write(data); f.flush()
            raw = subprocess.check_output(['gh', 'api', '--hostname', 'uploads.github.com', '-X', 'POST',
                f'repos/{REPO}/releases/{int(release)}/assets?name={name}',
                '-H', 'Content-Type: application/octet-stream', '--input', f.name])
        asset = json.loads(raw)
        if sha(self.download(asset['id'])) != sha(data):
            raise ValueError('uploaded backup/journal/asset failed download verification')
        return asset

class Transaction:
    def __init__(self, api, journal, journal_sha, new_id=None):
        self.api, self.j, self.journal_sha, self.new_id = api, journal, journal_sha, new_id
        j = journal
        if (j.get('schema') != 'pandora-stock-transaction-v1' or j.get('repository') != REPO
            or not re.fullmatch('[1-9][0-9]*', str(j.get('run_id')))
            or not all(re.fullmatch('[a-f0-9]{64}', j.get(k, '')) for k in ('old_sha', 'new_sha', 'source_sha'))
            or not all(isinstance(j.get(k), int) and j[k] > 0 for k in
                       ('fixed_release_id', 'source_release_id', 'source_asset_id', 'old_id', 'backup_id'))
            or not re.fullmatch(r'OS[0-9]+\.[0-9.]+[A-Z0-9]+', j.get('build', ''))
            or not re.fullmatch(r'[A-Za-z0-9_.-]*xm\.zip', j.get('old_name', ''))
            or not re.fullmatch(r'[A-Za-z0-9_.-]*xm\.zip', j.get('new_name', ''))
            or j.get('pending_name') != f'pandora-mobile-pending-{j["run_id"]}.upload'
            or j['old_name'] == j['new_name']):
            raise ValueError('invalid transaction journal')

    def snapshot(self):
        j = self.j
        fixed = self.api.api(f'releases/{j["fixed_release_id"]}')
        if fixed['tag_name'] != TAG or fixed['draft']:
            raise ValueError('fixed Release identity changed')
        possible = [a for a in fixed['assets'] if a['name'] in (j['pending_name'], j['new_name'])]
        if len(possible) > 1:
            raise ValueError('ambiguous new asset; manual investigation required')
        new = possible[0] if possible else None
        if new:
            if self.new_id is not None and new['id'] != self.new_id:
                raise ValueError('new asset ID differs from durable staging record')
            if self.new_id is None and new['name'] != j['pending_name']:
                raise ValueError('renamed asset without durable ID record')
        old = next((a for a in fixed['assets'] if a['id'] == j['old_id']), None)
        allowed = {j['old_id']} | ({new['id']} if new else set())
        if any(a['name'].endswith('xm.zip') and a['id'] not in allowed for a in fixed['assets']):
            raise ValueError('unrelated fixed input; refusing any mutation')
        for asset, name, expected in ((old, j['old_name'], j['old_sha']),
                                      (new, None, j['new_sha'])):
            if asset and ((name and asset['name'] != name) or sha(self.api.download(asset['id'])) != expected):
                raise ValueError('live asset SHA/name differs from journal')
        return old, new

    def audit(self):
        old, new = self.snapshot()
        return dict(journal_sha256=self.journal_sha, old_present=bool(old),
                    new_id=new['id'] if new else None, new_name=new['name'] if new else None,
                    recovery_required=not (new and not old and new['name'] == self.j['new_name']))

    def receipt(self, state):
        j = self.j
        body = (f'MOBILE_OTA_INTAKE={state}\nMOBILE_ASSET_ID={j["source_asset_id"]}\n'
                f'MOBILE_SOURCE_SHA256={j["source_sha"]}\nMOBILE_BUILD={j["build"]}\n'
                f'MOBILE_INTAKE_RUN={j["run_id"]}\nMOBILE_TRANSACTION_SHA256={self.journal_sha}\n'
                'SOURCE_PROVENANCE=ACTIVE_DEVICE_SNAPSHOT_NOT_VERIFIED_STOCK\n')
        self.api.api(f'releases/{j["source_release_id"]}', 'PATCH',
                     tag_name=f'pandora-ota-capture-{j["source_release_id"]}', body=body)

    def complete(self):
        old, new = self.snapshot()
        if not new:
            raise ValueError('no staged new asset; rollback this transaction instead')
        j = self.j
        if self.new_id is None:
            raw = json.dumps(dict(journal_sha256=self.journal_sha, new_id=new['id'],
                                  new_sha=j['new_sha']), sort_keys=True).encode()
            self.api.upload(j['source_release_id'], f'stock-staged-{j["run_id"]}.json', raw)
            self.new_id = new['id']
        if new['name'] == j['pending_name']:
            self.api.api(f'releases/assets/{new["id"]}', 'PATCH', name=j['new_name'])
        # If interrupted here, the next audit safely recognizes the double-xm state.
        self.snapshot()
        if old:
            self.api.api(f'releases/assets/{old["id"]}', 'DELETE')
        old, new = self.snapshot()
        if old or not new or new['name'] != j['new_name']:
            raise ValueError('switch not committed')
        self.api.api(f'releases/{j["fixed_release_id"]}', 'PATCH',
                     body=f'pandora current OTA stock-input: {j["build"]}; active device capture (NOT factory-original proof); asset {new["id"]}; transaction {self.journal_sha}')
        self.receipt('ACCEPTED')

    def rollback(self):
        old, new = self.snapshot()
        # Once deletion committed, rollback would replace a successfully committed input.
        # Use complete to reconcile its missing receipt; never silently roll it back.
        if not old:
            raise ValueError('old asset already deleted: complete receipt reconciliation only')
        if new:
            self.api.api(f'releases/assets/{new["id"]}', 'DELETE')
        self.receipt('REJECTED')


def prepare(api, fixed, staged_release, source_asset, source_sha, run, build, new_name, new_data, old_data):
    olds = [a for a in fixed['assets'] if a['name'].endswith('xm.zip')]
    if len(olds) != 1:
        raise ValueError('fixed input not singular')
    old = olds[0]
    # No fixed mutation happens until BOTH backup bytes and journal have been downloaded/verified.
    backup = api.upload(staged_release, f'stock-backup-{run}.zip', old_data)
    j = dict(schema='pandora-stock-transaction-v1', repository=REPO, run_id=str(run),
             fixed_release_id=fixed['id'], source_release_id=int(staged_release),
             source_asset_id=int(source_asset), source_sha=source_sha, build=build,
             old_id=old['id'], old_name=old['name'], old_sha=sha(old_data), backup_id=backup['id'],
             old_release_body=fixed.get('body') or '', new_name=new_name, new_sha=sha(new_data),
             pending_name=f'pandora-mobile-pending-{run}.upload')
    if sha(api.download(old['id'])) != j['old_sha']:
        raise ValueError('old input changed before journal preparation')
    raw = (json.dumps(j, sort_keys=True, indent=2) + '\n').encode()
    tx = Transaction(api, j, sha(raw))
    api.upload(staged_release, f'stock-transaction-{run}.json', raw)
    tx.receipt('PENDING')
    api.upload(fixed['id'], j['pending_name'], new_data)
    return tx


def load(api, release, run, expected):
    if not re.fullmatch('[a-f0-9]{64}', expected):
        raise ValueError('pin journal SHA from original intake log')
    source = api.api(f'releases/{int(release)}')
    if not source['draft']:
        raise ValueError('recovery journal must remain in source draft')
    matches = [a for a in source['assets'] if a['name'] == f'stock-transaction-{int(run)}.json']
    if len(matches) != 1:
        raise ValueError('missing/duplicate durable journal')
    raw = api.download(matches[0]['id'])
    if sha(raw) != expected:
        raise ValueError('journal SHA mismatch')
    staged = [a for a in source['assets'] if a['name'] == f'stock-staged-{int(run)}.json']
    if len(staged) > 1:
        raise ValueError('ambiguous staging ID record')
    new_id = None
    if staged:
        record = json.loads(api.download(staged[0]['id']))
        if record.get('journal_sha256') != expected or not isinstance(record.get('new_id'), int) or record['new_id'] <= 0:
            raise ValueError('invalid staging ID record')
        new_id = record['new_id']
    tx = Transaction(api, json.loads(raw), expected, new_id)
    if staged and record.get('new_sha') != tx.j['new_sha']:
        raise ValueError('staging ID SHA mismatch')
    if int(tx.j['run_id']) != int(run) or tx.j['source_release_id'] != int(release):
        raise ValueError('journal identity mismatch')
    backup = next((a for a in source['assets'] if a['id'] == tx.j['backup_id']), None)
    if not backup or backup['name'] != f'stock-backup-{int(run)}.zip' or sha(api.download(backup['id'])) != tx.j['old_sha']:
        raise ValueError('old backup missing or corrupt')
    return tx


def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['switch', 'audit', 'complete', 'rollback'])
    p.add_argument('--source-release', type=int, required=True)
    p.add_argument('--run', type=int, required=True)
    p.add_argument('--journal-sha')
    p.add_argument('--new', type=Path)
    p.add_argument('--old', type=Path)
    p.add_argument('--build')
    p.add_argument('--source-asset', type=int)
    p.add_argument('--source-sha')
    a = p.parse_args()
    api = GitHub()
    if a.mode == 'switch':
        tx = prepare(api, api.api('releases/tags/' + TAG), a.source_release, a.source_asset,
                     a.source_sha, a.run, a.build, a.new.name, a.new.read_bytes(), a.old.read_bytes())
        # Print the anchor before fixed-input mutations; also persisted in draft receipt.
        print('MOBILE_TRANSACTION_SHA256=' + tx.journal_sha, flush=True)
        tx.complete()
    else:
        tx = load(api, a.source_release, a.run, a.journal_sha)
        print(json.dumps(tx.audit(), indent=2), flush=True)
        if a.mode != 'audit':
            getattr(tx, a.mode)()

if __name__ == '__main__':
    main()

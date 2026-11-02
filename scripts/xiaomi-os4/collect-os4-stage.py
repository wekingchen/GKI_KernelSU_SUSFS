#!/usr/bin/env python3
"""Read-only, provenance-bound stage snapshot. Workflow success is never a stage."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

REPO = 'wekingchen/GKI_KernelSU_SUSFS'
CANDIDATE = 'xiaomi-sm8850-os4-ota-auto-candidate.yml'
STAGES = ('NO_NEW_OTA', 'GKI_BUILT', 'ABI_BLOCKED', 'TESTBOOT_READY', 'WAITING_HUMAN',
          'BASELINE_VERIFIED', 'CUSTOM_UNVERIFIED', 'LKG_ARCHIVED')

def require(ok, message):
    if not ok:
        raise ValueError(message)

def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', f'repos/{REPO}/{path}']))

def env(path):
    return dict(l.split('=', 1) for l in Path(path).read_text().splitlines() if '=' in l and not l.startswith('#'))

def file_sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def asset_sha(asset):
    value = asset.get('digest', '')
    require(bool(re.fullmatch('sha256:[a-f0-9]{64}', value)), 'GitHub asset digest unavailable; cannot validate stage')
    return value[7:]

def get_asset(release, name):
    matches = [a for a in release['assets'] if a['name'] == name]
    require(len(matches) == 1, 'missing/duplicate release asset: ' + name)
    return matches[0]

def download_asset(asset, path):
    with Path(path).open('wb') as out:
        subprocess.run(['gh', 'api', '-H', 'Accept: application/octet-stream',
                        f'repos/{REPO}/releases/assets/{asset["id"]}'], stdout=out, check=True)
    require(file_sha(path) == asset_sha(asset), 'release asset digest mismatch')

def artifact(run, name, root):
    matches = [a for a in api(f'actions/runs/{run}/artifacts?per_page=100')['artifacts']
               if a['name'] == name and not a['expired']]
    if not matches:
        return None
    require(len(matches) == 1, 'ambiguous run artifact')
    folder = Path(root) / f'{run}-{matches[0]["id"]}'
    folder.mkdir()
    subprocess.run(['gh', 'run', 'download', str(run), '--repo', REPO, '--name', name,
                    '--dir', str(folder)], check=True)
    return folder

def valid_run(run, workflow):
    return (run.get('head_branch') == 'dev' and run.get('status') == 'completed'
            and run.get('path') == '.github/workflows/' + workflow
            and run.get('event') in ('workflow_dispatch', 'schedule', 'release', 'workflow_run')
            and bool(re.fullmatch('[a-f0-9]{40}', run.get('head_sha', ''))))

def binding(report, source, pinned_legacy_boot=None):
    legacy = (pinned_legacy_boot is not None and report.get('status') == 'SAME_PINNED_BUILD'
              and report.get('source_provenance') == 'LEGACY_PINNED_BOOT_SHA256_ONLY'
              and report.get('stock_boot_sha256') == pinned_legacy_boot
              and bool(re.fullmatch('[a-f0-9]{64}', pinned_legacy_boot)))
    require(report.get('device') == 'pandora' and (report.get('kernel_marker_verified') is True or legacy),
            'unverified stock identity')
    require(str(report.get('github_asset_id')) == str(source['id'])
            and report.get('ota_source_id') == asset_sha(source), 'stock input changed')
    require(bool(re.fullmatch(r'OS[0-9]+\.[0-9.]+[A-Z0-9]+', report.get('build', ''))), 'invalid build')

def baseline_matches(rec, stock, image, symvers):
    return (rec.get('status') == 'HUMAN_ATTESTED_BASELINE_BOOTED'
            and rec.get('device') == 'pandora' and rec.get('stock_build') == stock['build']
            and rec.get('stock_input_sha256') == stock['ota_source_id']
            and str(rec.get('stock_release_asset_id')) == str(stock['github_asset_id'])
            and rec.get('candidate_image_sha256') == image
            and rec.get('module_symvers_sha256') == symvers
            and rec.get('observed_boot_completed') == '1'
            and rec.get('modules_basic_check') == 'PASS_HUMAN_ATTESTED')

def collect(root):
    require(os.environ['GITHUB_REPOSITORY'] == REPO and os.environ['GITHUB_REF_NAME'] == 'dev', 'trusted dev only')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    require(head == os.environ['GITHUB_SHA'], 'checkout differs from producer run')
    fixed = api('releases/tags/pandora-os4-stock-input')
    inputs = [a for a in fixed['assets'] if a['name'].endswith('xm.zip')]
    require(not fixed['draft'] and len(inputs) == 1, 'fixed input transaction unresolved')
    source = inputs[0]
    source_digest = asset_sha(source)
    runs = api(f'actions/workflows/{CANDIDATE}/runs?branch=dev&per_page=30')['workflow_runs']
    report, origin = None, None
    # Audit report, not the overall conclusion, binds the current input/build.
    for run in runs:
        if not valid_run(run, CANDIDATE):
            continue
        folder = artifact(run['id'], f'pandora-ota-input-audit-{run["id"]}', root)
        if not folder or not (folder / 'stock-report.json').is_file():
            continue
        trial = json.loads((folder / 'stock-report.json').read_text())
        if str(trial.get('github_asset_id')) == str(source['id']) and trial.get('ota_source_id') == source_digest:
            pinned = None
            if trial.get('source_provenance') == 'LEGACY_PINNED_BOOT_SHA256_ONLY':
                config = env('.github/config/pandora-os4-stock-input.env')
                require(trial.get('build') == config.get('OS4_STOCK_INPUT_BUILD'), 'legacy build differs from pin')
                pinned = config.get('OS4_STOCK_BOOT_SHA256')
            binding(trial, source, pinned)
            report, origin = trial, run
            break
    require(report is not None, 'no retained input audit for current asset; run candidate inspection/recovery first')
    build = report['build']
    result = dict(schema='pandora-os4-stage-v1', repository=REPO, device='pandora',
                  producer_run_id=int(os.environ['GITHUB_RUN_ID']), producer_head_sha=head,
                  build=build, stock_asset_id=source['id'], stock_input_sha256=source_digest,
                  source_run_id=origin['id'], source_head_sha=origin['head_sha'],
                  stage='NO_NEW_OTA', milestones=[], release_assets=[],
                  safe_to_flash=False, detail='', baseline_record_sha256='', tested_boot_sha256='')
    # The current legacy LKG is described independently of an OTA NOOP run.
    lkg = env('.github/config/pandora-os4-full-parity-lkg.env')
    if (build == lkg['LKG_SYSTEM_BUILD'] and report.get('stock_boot_sha256') == lkg['LKG_STOCK_BOOT_SHA256']):
        tag = 'pandora-os4-lkg-gen' + lkg['LKG_PROMOTION_GENERATION']
        release = api('releases/tags/' + tag)
        require(not release['draft'] and not release['prerelease'], 'LKG archive not published')
        for key in ('LKG_FASTBOOT_BOOT_SHA256', 'LKG_PACKAGE_SHA256'):
            matches = [a for a in release['assets'] if a.get('digest') == 'sha256:' + lkg[key]]
            require(len(matches) == 1, 'LKG archive SHA differs from locked configuration')
            a = matches[0]
            result['release_assets'].append(dict(tag=tag, id=a['id'], name=a['name'], sha256=asset_sha(a)))
        a = get_asset(release, f'Xiaomi17Pro-pandora-OS4-Gen{lkg["LKG_PROMOTION_GENERATION"]}-locked-lkg.env')
        require(asset_sha(a) == file_sha('.github/config/pandora-os4-full-parity-lkg.env'), 'LKG locked snapshot differs')
        result['release_assets'].append(dict(tag=tag, id=a['id'], name=a['name'], sha256=asset_sha(a)))
        result.update(stage='LKG_ARCHIVED', source_run_id=int(lkg['LKG_SOURCE_RUN_ID']),
                      source_head_sha=lkg['LKG_SOURCE_RUN_HEAD'], detail='同版本已有人确认稳定并长期归档；本次 OTA 检测可能仅为 NOOP。')
        return result
    if report.get('status') == 'SAME_PINNED_BUILD':
        result['detail'] = '未发现新的 OTA；没有生成新的待测包。'
        return result
    require(report.get('status') == 'NEW_OTA_CANDIDATE', 'input audit blocked')
    tag = 'pandora-os4-ota-candidate-' + build
    release = api('releases/tags/' + tag)
    require(not release['draft'] and release['prerelease'], 'candidate is not permanently archived')
    for name in ('stock-report.json', 'build-metadata.txt', 'gki-candidate.json'):
        download_asset(get_asset(release, name), Path(root) / name)
    archived = json.loads((Path(root) / 'stock-report.json').read_text())
    binding(archived, source)
    require(archived['build'] == build, 'candidate build mismatch')
    meta = env(Path(root) / 'build-metadata.txt')
    require(meta.get('STOCK_INPUT_SHA256') == source_digest and meta.get('STOCK_BUILD') == build
            and meta.get('FLASHABLE') == 'NO', 'candidate provenance mismatch')
    for name, key in (('Image', 'IMAGE_SHA256'), ('Module.symvers', 'SYMVERS_SHA256')):
        a = get_asset(release, name)
        require(asset_sha(a) == meta.get(key), 'candidate SHA mismatch')
        result['release_assets'].append(dict(tag=tag, id=a['id'], name=name, sha256=asset_sha(a)))
    result.update(stage='GKI_BUILT', milestones=['GKI_BUILT'], detail='GKI 已永久归档；待测附件缺失或过期时需显式恢复。')
    # Search retained runs of exactly this input; never infer readiness from a NOOP success.
    for run in runs:
        if not valid_run(run, CANDIDATE) or run.get('conclusion') != 'success':
            continue
        mobile = artifact(run['id'], f'pandora-OTA-MOBILE-FEEDBACK-{build}-{run["id"]}', root)
        if not mobile:
            blocked = artifact(run['id'], f'pandora-OTA-OEM-ABI-TESTBOOT-{build}-{run["id"]}', root)
            if blocked and (blocked / 'ota-abi-report.json').is_file():
                abi = json.loads((blocked / 'ota-abi-report.json').read_text())
                if abi.get('stock_input_sha256') == source_digest and abi.get('stock_build') == build and abi.get('eligible_for_fastboot_boot') is False:
                    result.update(stage='ABI_BLOCKED', detail=str(abi.get('reason', 'OEM ABI 未通过'))[:500],
                                  source_run_id=run['id'], source_head_sha=run['head_sha'])
                    break
            continue
        j = json.loads((mobile / 'mobile-test-feedback.json').read_text())
        require(j.get('schema') == 'pandora-mobile-feedback-v1' and j.get('source_run_id') == run['id']
                and j.get('source_head_sha') == run['head_sha'] and j.get('repository') == REPO
                and j.get('build') == build and j.get('eligible_for_fastboot_boot') is True
                and bool(re.fullmatch('[a-f0-9]{64}', j.get('tested_boot_sha256', ''))), 'invalid mobile provenance')
        # The feedback workflow independently requires both exact unexpired artifacts too.
        arts = api(f'actions/runs/{run["id"]}/artifacts?per_page=100')['artifacts']
        for prefix in ('pandora-OTA-UNVERIFIED-GKI-', 'pandora-OTA-OEM-ABI-TESTBOOT-'):
            require(sum(not a['expired'] and a['name'] == f'{prefix}{build}-{run["id"]}' for a in arts) == 1,
                    'test candidate expired; recover it first')
        result.update(stage='WAITING_HUMAN', milestones=['GKI_BUILT', 'TESTBOOT_READY', 'WAITING_HUMAN'],
                      source_run_id=run['id'], source_head_sha=run['head_sha'],
                      tested_boot_sha256=j['tested_boot_sha256'], detail='静态门禁通过，等待电脑临时启动与手机人工测试。')
        break
    record_path = Path(f'.github/config/ota-verified/{build}/verification.json')
    if record_path.is_file():
        rec = json.loads(record_path.read_text())
        require(baseline_matches(rec, report, meta['IMAGE_SHA256'], meta['SYMVERS_SHA256']), 'baseline record differs from current input')
        result.update(stage='BASELINE_VERIFIED', source_run_id=rec['source_ota_run_id'],
                      source_head_sha=rec['source_ota_head_sha'], baseline_record_sha256=file_sha(record_path),
                      detail='同版本开发基线已由人工反馈确认；自定义内核仍需另行测试。')
        result['milestones'].append('BASELINE_VERIFIED')
        custom_runs = api('actions/workflows/xiaomi-sm8850-os4-custom.yml/runs?branch=dev&status=success&per_page=10')['workflow_runs']
        for run in custom_runs:
            if not valid_run(run, 'xiaomi-sm8850-os4-custom.yml'):
                continue
            custom = artifact(run['id'], f'pandora-OTA-CUSTOM-{build}-run-{run["id"]}', root)
            if not custom:
                continue
            # Reuse the existing bytes/fixture/provenance verifier.
            subprocess.run(['python3', 'scripts/xiaomi-os4/cross-ota-lkg.py', 'verify', '--artifact-dir', str(custom),
                            '--run-id', str(run['id']), '--head-sha', run['head_sha']], check=True)
            bound = json.loads((custom / 'verified-baseline.json').read_text())
            require(bound == rec, 'custom kernel uses a different baseline')
            result.update(stage='CUSTOM_UNVERIFIED', custom_run_id=run['id'], custom_head_sha=run['head_sha'],
                          detail='自定义 IMG/实验性 AnyKernel3 已生成，尚未确认为稳定 LKG。')
            result['milestones'].append('CUSTOM_UNVERIFIED')
            break
        pointer = Path('.github/config/ota-lkg-current.json')
        if pointer.is_file():
            stable = json.loads(pointer.read_text())
            if stable.get('stock_build') == build and stable.get('stock_input_sha256') == source_digest and stable.get('stock_release_asset_id') == source['id']:
                tag = stable['archive_tag']
                release = api('releases/tags/' + tag)
                require(not release['draft'] and not release['prerelease'], 'LKG pointer archive still pending')
                for key in ('image_sha256', 'boot_sha256', 'anykernel_sha256'):
                    matches = [a for a in release['assets'] if a.get('digest') == 'sha256:' + stable[key]]
                    require(len(matches) == 1, 'LKG public archive digest mismatch')
                    a = matches[0]
                    result['release_assets'].append(dict(tag=tag, id=a['id'], name=a['name'], sha256=asset_sha(a)))
                result.update(stage='LKG_ARCHIVED', detail='人工确认稳定、严格复现并长期归档已完成。')
                result['milestones'].append('LKG_ARCHIVED')
    return result

def main():
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True); a = p.parse_args()
    with tempfile.TemporaryDirectory() as root:
        result = collect(root)
    require(result['stage'] in STAGES, 'unknown stage')
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()

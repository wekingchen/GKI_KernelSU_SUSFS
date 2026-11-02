import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('stage',Path(__file__).with_name('collect-os4-stage.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Stage(unittest.TestCase):
    def test_run_success_never_substitutes_for_required_provenance(self):
        run=dict(head_branch='dev',status='completed',conclusion='success',path='.github/workflows/'+m.CANDIDATE,event='schedule',head_sha='a'*40)
        self.assertTrue(m.valid_run(run,m.CANDIDATE))
        for field,value in (('head_branch','fix/test'),('path','.github/workflows/other.yml'),('head_sha','bad'),('status','queued'),('event','pull_request')):
            bad=dict(run);bad[field]=value;self.assertFalse(m.valid_run(bad,m.CANDIDATE))
    def test_input_identity_sha_and_device_must_match(self):
        asset=dict(id=123,digest='sha256:'+'a'*64)
        report=dict(device='pandora',kernel_marker_verified=True,github_asset_id=123,ota_source_id='a'*64,build='OS4.0.6.0.XBLCNXM')
        m.binding(report,asset)
        for key,value in (('github_asset_id',124),('ota_source_id','b'*64),('device','other'),('kernel_marker_verified',False),('build','malformed')):
            wrong=dict(report);wrong[key]=value
            with self.assertRaises(ValueError):m.binding(wrong,asset)
        with self.assertRaises(ValueError):m.asset_sha(dict(id=123))
    def test_human_baseline_needs_same_input_hashes_and_attestation(self):
        stock=dict(build='OS4.0.6.0.XBLCNXM',ota_source_id='a'*64,github_asset_id=123)
        rec=dict(status='HUMAN_ATTESTED_BASELINE_BOOTED',device='pandora',stock_build=stock['build'],stock_input_sha256='a'*64,stock_release_asset_id=123,candidate_image_sha256='b'*64,module_symvers_sha256='c'*64,observed_boot_completed='1',modules_basic_check='PASS_HUMAN_ATTESTED',source_ota_run_id=100,source_ota_head_sha='d'*40)
        self.assertTrue(m.baseline_matches(rec,stock,'b'*64,'c'*64))
        for key in set(rec)-{'source_ota_run_id','source_ota_head_sha'}:
            bad=dict(rec);bad[key]='wrong';self.assertFalse(m.baseline_matches(bad,stock,'b'*64,'c'*64),key)


class StageSnapshots(unittest.TestCase):
    """Synthetic orchestration, not real OTA/device acceptance."""
    def test_stage_precedence_and_expired_testboot(self):
        import contextlib,json,os,tempfile
        from unittest.mock import patch
        digest='a'*64;image='b'*64;symvers='c'*64;head='d'*40;build='OS4.0.6.0.XBLCNXM'
        source=dict(id=123,name='new-xm.zip',digest='sha256:'+digest)
        report=dict(device='pandora',kernel_marker_verified=True,github_asset_id=123,ota_source_id=digest,build=build,status='NEW_OTA_CANDIDATE')
        run=dict(id=100,head_branch='dev',status='completed',conclusion='success',event='workflow_dispatch',path='.github/workflows/'+m.CANDIDATE,head_sha=head)
        candidate_assets=[dict(id=5,name='Image',digest='sha256:'+image),dict(id=6,name='Module.symvers',digest='sha256:'+symvers)]
        for index,name in enumerate(('stock-report.json','build-metadata.txt','gki-candidate.json'),10):candidate_assets.append(dict(id=index,name=name,digest='sha256:'+'e'*64))
        rec=dict(status='HUMAN_ATTESTED_BASELINE_BOOTED',device='pandora',stock_build=build,stock_input_sha256=digest,stock_release_asset_id=123,candidate_image_sha256=image,module_symvers_sha256=symvers,observed_boot_completed='1',modules_basic_check='PASS_HUMAN_ATTESTED',source_ota_run_id=100,source_ota_head_sha='d'*40)
        for mode,expected in (('noop','NO_NEW_OTA'),('expired31','GKI_BUILT'),('blocked','ABI_BLOCKED'),('ready','WAITING_HUMAN'),('baseline','BASELINE_VERIFIED'),('custom','CUSTOM_UNVERIFIED'),('stable','LKG_ARCHIVED')):
            with tempfile.TemporaryDirectory() as d,contextlib.ExitStack() as stack:
                root=Path(d);(root/'.github/config').mkdir(parents=True)
                (root/'.github/config/pandora-os4-full-parity-lkg.env').write_text('LKG_SYSTEM_BUILD=OS4.0.5.0.XBLCNXM\n')
                old=Path.cwd();os.chdir(root);stack.callback(os.chdir,old)
                trial=dict(report,status='SAME_PINNED_BUILD' if mode=='noop' else 'NEW_OTA_CANDIDATE')
                def fake_api(path):
                    if path=='releases/tags/pandora-os4-stock-input':return dict(draft=False,assets=[source])
                    if path.startswith('actions/workflows/'+m.CANDIDATE):return dict(workflow_runs=[run])
                    if path.startswith('releases/tags/pandora-os4-ota-candidate-'):return dict(draft=False,prerelease=True,assets=candidate_assets)
                    if path.startswith('actions/runs/100/artifacts'):
                        return dict(artifacts=[dict(name=f'{prefix}{build}-100',expired=False) for prefix in ('pandora-OTA-UNVERIFIED-GKI-','pandora-OTA-OEM-ABI-TESTBOOT-')])
                    if path.startswith('actions/workflows/xiaomi-sm8850-os4-custom.yml'):
                        custom=dict(run,id=200,path='.github/workflows/xiaomi-sm8850-os4-custom.yml')
                        return dict(workflow_runs=[custom] if mode in ('custom','stable') else [])
                    if path=='releases/tags/pandora-os4-lkg-gen5':
                        return dict(draft=False,prerelease=False,assets=[dict(id=i,name=str(i),digest='sha256:'+sha) for i,sha in enumerate(('1'*64,'2'*64,'3'*64),20)])
                    raise AssertionError(path)
                def fake_artifact(id,name,where):
                    folder=root/name;folder.mkdir(exist_ok=True)
                    if name=='pandora-ota-input-audit-100':(folder/'stock-report.json').write_text(json.dumps(trial));return folder
                    if 'MOBILE-FEEDBACK' in name and mode in ('ready','baseline','custom','stable'):
                        (folder/'mobile-test-feedback.json').write_text(json.dumps(dict(schema='pandora-mobile-feedback-v1',source_run_id=100,source_head_sha=head,repository=m.REPO,build=build,eligible_for_fastboot_boot=True,tested_boot_sha256='f'*64)));return folder
                    if 'OEM-ABI' in name and mode=='blocked':
                        (folder/'ota-abi-report.json').write_text(json.dumps(dict(stock_input_sha256=digest,stock_build=build,eligible_for_fastboot_boot=False,reason='CRC mismatch')));return folder
                    if 'OTA-CUSTOM' in name and mode in ('custom','stable'):
                        (folder/'verified-baseline.json').write_text(json.dumps(rec));return folder
                    return None
                def fake_download(asset,path):
                    if asset['name']=='stock-report.json':Path(path).write_text(json.dumps(report))
                    elif asset['name']=='build-metadata.txt':Path(path).write_text(f'STOCK_BUILD={build}\nSTOCK_INPUT_SHA256={digest}\nIMAGE_SHA256={image}\nSYMVERS_SHA256={symvers}\nFLASHABLE=NO\n')
                    else:Path(path).write_text('{}')
                if mode in ('baseline','custom','stable'):
                    path=root/f'.github/config/ota-verified/{build}';path.mkdir(parents=True);(path/'verification.json').write_text(json.dumps(rec))
                if mode=='stable':(root/'.github/config/ota-lkg-current.json').write_text(json.dumps(dict(stock_build=build,stock_input_sha256=digest,stock_release_asset_id=123,archive_tag='pandora-os4-lkg-gen5',image_sha256='1'*64,boot_sha256='2'*64,anykernel_sha256='3'*64)))
                stack.enter_context(patch.dict(os.environ,GITHUB_REPOSITORY=m.REPO,GITHUB_REF_NAME='dev',GITHUB_SHA=head,GITHUB_RUN_ID='300'))
                stack.enter_context(patch.object(m.subprocess,'check_output',return_value=head))
                stack.enter_context(patch.object(m.subprocess,'run'))
                stack.enter_context(patch.object(m,'api',side_effect=fake_api));stack.enter_context(patch.object(m,'artifact',side_effect=fake_artifact));stack.enter_context(patch.object(m,'download_asset',side_effect=fake_download))
                result=m.collect(root)
                self.assertEqual(result['stage'],expected,mode)
                self.assertFalse(result['safe_to_flash'])
                if mode=='ready':self.assertIn('TESTBOOT_READY',result['milestones'])

class LegacyInputAudit(unittest.TestCase):
    def test_actual_legacy_report_requires_explicit_pinned_boot_sha(self):
        report = dict(device='pandora',status='SAME_PINNED_BUILD',github_asset_id='689533830',
                      ota_source_id='504ed11e280fb0f566a73492ee9633e561292c6bf3779c9b95449348cc6f556a',
                      source_provenance='LEGACY_PINNED_BOOT_SHA256_ONLY',build='OS4.0.5.0.XBLCNXM',
                      stock_boot_sha256='4f873abec68220c0028c11c8833e7ec8b9652f263e850f1ddb76d19913374653')
        source=dict(id=689533830,digest='sha256:'+report['ota_source_id'])
        with self.assertRaises(ValueError):m.binding(report,source)
        with self.assertRaises(ValueError):m.binding(report,source,'b'*64)
        m.binding(report,source,report['stock_boot_sha256'])

if __name__=='__main__':unittest.main()

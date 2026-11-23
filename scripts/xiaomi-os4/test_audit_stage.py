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
                    if path=='actions/runs/200':
                        return dict(id=200,head_branch='dev',status='completed',
                                    conclusion='success',event='workflow_dispatch',
                                    path='.github/workflows/xiaomi-sm8850-os4-custom.yml',head_sha=head)
                    if path=='releases/tags/pandora-os4-lkg-gen7':
                        pointer=root/'.github/config/ota-lkg-current.json'
                        return dict(tag_name='pandora-os4-lkg-gen7',draft=False,prerelease=False,assets=[
                            dict(id=20,name=f'{build}-Gen7-ORIGINAL-USER-ATTESTED-boot.img',digest='sha256:'+'1'*64),
                            dict(id=21,name=f'{build}-Gen7-ORIGINAL-USER-ATTESTED-AnyKernel3.zip',digest='sha256:'+'2'*64),
                            dict(id=22,name='ota-lkg-promotion-record.json',digest='sha256:'+m.file_sha(pointer))])
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
                    elif asset['name']=='ota-lkg-promotion-record.json':
                        Path(path).write_bytes((root/'.github/config/ota-lkg-current.json').read_bytes())
                    else:Path(path).write_text('{}')
                if mode in ('baseline','custom'):
                    path=root/f'.github/config/ota-verified/{build}';path.mkdir(parents=True);(path/'verification.json').write_text(json.dumps(rec))
                if mode=='stable':
                    (root/'.github/config/ota-lkg-current.json').write_text(json.dumps(dict(
                        schema=1,device='pandora',status='USER_PROMOTED_OTA_LKG',
                        attestation='USER_CONFIRMED_BOOT_AND_PERSISTENT_STABILITY_NOT_REMOTE_HARDWARE_PROOF',
                        stock_build=build,stock_input_sha256=digest,stock_release_asset_id=123,
                        generation=7,archive_tag='pandora-os4-lkg-gen7',
                        source_run_id=200,source_head_sha=head,
                        image_sha256='3'*64,boot_sha256='1'*64,anykernel_sha256='2'*64,
                        reproduction=dict(rebuild_verification='NORMALIZED_IMAGE_AND_EXACT_SYMVERS_CONFIG_PASS'))))
                stack.enter_context(patch.dict(os.environ,GITHUB_REPOSITORY=m.REPO,GITHUB_REF_NAME='dev',GITHUB_SHA=head,GITHUB_RUN_ID='300'))
                stack.enter_context(patch.object(m.subprocess,'check_output',return_value=head))
                stack.enter_context(patch.object(m.subprocess,'run'))
                stack.enter_context(patch.object(m,'api',side_effect=fake_api));stack.enter_context(patch.object(m,'artifact',side_effect=fake_artifact));stack.enter_context(patch.object(m,'download_asset',side_effect=fake_download))
                result=m.collect(root)
                self.assertEqual(result['stage'],expected,mode)
                self.assertFalse(result['safe_to_flash'])
                if mode=='ready':self.assertIn('TESTBOOT_READY',result['milestones'])
                if mode=='stable':
                    # No verification.json exists and the original static ABI can
                    # still be BLOCKED. The exact, separately verified Gen7
                    # publication must be the status shown to the phone.
                    self.assertFalse((root/f'.github/config/ota-verified/{build}/verification.json').exists())
                    self.assertEqual(result['source_run_id'],200)
                    self.assertEqual(len(result['release_assets']),3)
                    self.assertIn('LKG_ARCHIVED',result['milestones'])


    def test_old_gen7_pointer_cannot_shadow_a_future_new_ota(self):
        import contextlib,json,os,tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d,contextlib.ExitStack() as stack:
            root=Path(d);(root/'.github/config').mkdir(parents=True)
            pointer=root/'.github/config/ota-lkg-current.json'
            pointer.write_text(json.dumps(dict(
                schema=1,device='pandora',status='USER_PROMOTED_OTA_LKG',
                stock_build='OS4.0.6.0.XBLCNXM',stock_input_sha256='a'*64,
                stock_release_asset_id=123,generation=7,archive_tag='pandora-os4-lkg-gen7')))
            old=Path.cwd();os.chdir(root);stack.callback(os.chdir,old)
            stack.enter_context(patch.object(m,'api',side_effect=AssertionError(
                'previous OTA LKG must not trigger a remote lookup')))
            result=dict(stage='ABI_BLOCKED',release_assets=[],safe_to_flash=False)
            self.assertFalse(m.versioned_lkg_snapshot(
                result,'OS4.0.7.0.XBLCNXM',dict(id=124), 'b'*64, root))
            self.assertEqual(result['stage'],'ABI_BLOCKED')
            self.assertFalse(result['safe_to_flash'])

    def test_exact_stock_but_corrupt_gen7_archive_stays_fail_closed(self):
        import contextlib,json,os,tempfile
        from unittest.mock import patch
        build='OS4.0.6.0.XBLCNXM';sha='a'*64;head='b'*40
        with tempfile.TemporaryDirectory() as d,contextlib.ExitStack() as stack:
            root=Path(d);(root/'.github/config').mkdir(parents=True)
            pointer=root/'.github/config/ota-lkg-current.json'
            pointer.write_text(json.dumps(dict(
                schema=1,device='pandora',status='USER_PROMOTED_OTA_LKG',
                attestation='USER_CONFIRMED_BOOT_AND_PERSISTENT_STABILITY_NOT_REMOTE_HARDWARE_PROOF',
                stock_build=build,stock_input_sha256=sha,
                stock_release_asset_id=123,generation=7,archive_tag='pandora-os4-lkg-gen7',
                source_run_id=200,source_head_sha=head,boot_sha256='1'*64,anykernel_sha256='2'*64,
                reproduction=dict(rebuild_verification='NORMALIZED_IMAGE_AND_EXACT_SYMVERS_CONFIG_PASS'))))
            old=Path.cwd();os.chdir(root);stack.callback(os.chdir,old)
            def fake_api(path):
                if path=='actions/runs/200':
                    return dict(id=200,head_branch='dev',status='completed',conclusion='success',
                                event='workflow_dispatch',head_sha=head,
                                path='.github/workflows/xiaomi-sm8850-os4-custom.yml')
                if path=='releases/tags/pandora-os4-lkg-gen7':
                    return dict(tag_name='pandora-os4-lkg-gen7',draft=False,prerelease=False,
                                assets=[dict(id=20,name=f'{build}-Gen7-ORIGINAL-USER-ATTESTED-boot.img',
                                             digest='sha256:'+'f'*64)])
                raise AssertionError(path)
            stack.enter_context(patch.object(m,'api',side_effect=fake_api))
            result=dict(stage='ABI_BLOCKED',release_assets=[],safe_to_flash=False)
            with self.assertRaises(ValueError):
                m.versioned_lkg_snapshot(result,build,dict(id=123),sha,root)
            self.assertEqual(result['stage'],'ABI_BLOCKED')
            self.assertFalse(result['safe_to_flash'])


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

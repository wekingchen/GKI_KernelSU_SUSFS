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
        rec=dict(status='HUMAN_ATTESTED_BASELINE_BOOTED',device='pandora',stock_build=stock['build'],stock_input_sha256='a'*64,stock_release_asset_id=123,candidate_image_sha256='b'*64,module_symvers_sha256='c'*64,observed_boot_completed='1',modules_basic_check='PASS_HUMAN_ATTESTED')
        self.assertTrue(m.baseline_matches(rec,stock,'b'*64,'c'*64))
        for key in rec:
            bad=dict(rec);bad[key]='wrong';self.assertFalse(m.baseline_matches(bad,stock,'b'*64,'c'*64),key)

if __name__=='__main__':unittest.main()

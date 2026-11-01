import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from create_test_feedback_manifest import create

class FeedbackManifest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.boot = Path(self.tmp.name) / 'pandora-OS4.0.6.0.XBLCNXM-UNVERIFIED-FASTBOOT-BOOT-ONLY.img'
        self.boot.write_bytes(b'synthetic-ci-payload')
        self.stock = dict(device='pandora', build='OS4.0.6.0.XBLCNXM', status='NEW_OTA_CANDIDATE',
                          kernel_marker_verified=True, uname='6.12.80-android16-6-test-4k', ota_source_id='a'*64)
        self.abi = dict(eligible_for_fastboot_boot=True, gate='CRC_AND_VERMAGIC_MATCH_CANDIDATE',
                        stock_build=self.stock['build'], kernel_release=self.stock['uname'], stock_input_sha256='a'*64)
    def make(self):
        return create(self.stock, self.abi, self.boot, '123', 'b'*40, 'wekingchen/GKI_KernelSU_SUSFS')
    def test_exact_digest_and_provenance(self):
        j=self.make(); self.assertEqual(j['tested_boot_sha256'],hashlib.sha256(self.boot.read_bytes()).hexdigest())
        self.assertEqual(j['source_run_id'],123)
    def test_each_provenance_mismatch_fails(self):
        for target,key,value in [('stock','device','other'),('stock','kernel_marker_verified',False),
          ('stock','status','CURRENT'),('abi','eligible_for_fastboot_boot',False),('abi','stock_build','OS4.0.7.0.XBLCNXM'),
          ('abi','stock_input_sha256','c'*64),('abi','kernel_release','other'),('abi','gate','FAILED')]:
            obj=getattr(self,target);old=obj[key];obj[key]=value
            with self.subTest(key=key), self.assertRaises(ValueError):self.make()
            obj[key]=old
    def test_wrong_or_empty_image_fails(self):
        self.boot.write_bytes(b'')
        with self.assertRaises(ValueError):self.make()
    def test_invalid_run_head_or_repository_fails(self):
        for run,head,repo in [('0','b'*40,'wekingchen/GKI_KernelSU_SUSFS'),('123','bad','wekingchen/GKI_KernelSU_SUSFS'),('123','b'*40,'other/repo')]:
            with self.assertRaises(ValueError):create(self.stock,self.abi,self.boot,run,head,repo)


class FeedbackRequestDeduplication(unittest.TestCase):
    def test_same_request_only_earliest_run_can_mutate(self):
        from check_feedback_request import previous_run, WORKFLOW
        run=dict(id=101, head_branch='dev', event='workflow_dispatch', path=WORKFLOW,
                 display_title='Pandora OTA feedback / '+'a'*32)
        self.assertEqual(previous_run([dict(workflow_runs=[run])], 'a'*32, 102),101)
        self.assertIsNone(previous_run([dict(workflow_runs=[run])], 'a'*32, 101))
        self.assertIsNone(previous_run([dict(workflow_runs=[run])], 'b'*32, 102))
        run['head_branch']='other'
        self.assertIsNone(previous_run([dict(workflow_runs=[run])], 'a'*32, 102))

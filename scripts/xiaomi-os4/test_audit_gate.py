import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
class Gate(unittest.TestCase):
    def test_fix_docs_lkg_branches_all_reject_upstream_edits_and_allow_owned_files(self):
        def git(root,*args):return subprocess.check_output(['git','-C',str(root),*args],stderr=subprocess.DEVNULL,text=True).strip()
        with tempfile.TemporaryDirectory() as d:
            up=Path(d)/'up';up.mkdir();git(up,'init','-b','dev');git(up,'config','user.email','test@example.com');git(up,'config','user.name','Test')
            (up/'shared').write_text('upstream');git(up,'add','.');git(up,'commit','-m','upstream')
            work=Path(d)/'work';git(Path(d),'clone',str(up),str(work));git(work,'config','user.email','test@example.com');git(work,'config','user.name','Test')
            base=git(work,'rev-parse','HEAD')
            for branch in ('fix/test','docs/test','lkg/test'):
                git(work,'checkout','-B',branch,base)
                (work/'pandora-owned').write_text('allowed');git(work,'add','.');git(work,'commit','-m','allowed')
                env=dict(os.environ,XIAOMI_UPSTREAM_REPO=str(up),XIAOMI_UPSTREAM_REF='dev')
                run=lambda:subprocess.run(['bash',str(ROOT/'scripts/xiaomi-os4/check-upstream-isolation.sh'),base],cwd=work,env=env,capture_output=True,text=True)
                self.assertEqual(run().returncode,0,branch)
                (work/'shared').write_text('bad');git(work,'add','.');git(work,'commit','-m','bad')
                result=run();self.assertNotEqual(result.returncode,0,branch);self.assertIn('shared',result.stdout)
    def test_bot_merge_routes_wait_for_real_exact_head_check(self):
        for file in ('.github/workflows/xiaomi-sm8850-os4-promote-lkg.yml','.github/workflows/xiaomi-sm8850-os4-ota-test-feedback.yml','scripts/xiaomi-os4/run-cross-ota-lkg.sh'):
            text=(ROOT/file).read_text()
            self.assertIn('await-pr-isolation.sh "$BRANCH" "$HEAD_SHA"',text)
        workflow=(ROOT/'.github/workflows/xiaomi-upstream-isolation-guard.yml').read_text()
        self.assertNotIn('paths-ignore:',workflow)
        self.assertNotIn('startsWith(github.head_ref',workflow)

if __name__=='__main__':unittest.main()

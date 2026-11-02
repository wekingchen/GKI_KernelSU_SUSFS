import copy
import importlib.util
import json
from pathlib import Path
import unittest

def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
m = module('stock-input-transaction')

class FakeGitHub:
    def __init__(self):
        self.releases = {1: dict(id=1,tag_name=m.TAG,draft=False,body='old',assets=[]),
                         2: dict(id=2,tag_name='capture',draft=True,body='',assets=[])}
        self.data={}; self.next=10; self.crash=None
        self.upload(1,'old-xm.zip',b'OLD')
    def download(self, asset):return self.data[asset]
    def upload(self, release, name, data):
        if any(a['name']==name for a in self.releases[release]['assets']):raise ValueError('duplicate upload')
        a=dict(id=self.next,name=name);self.next+=1;self.data[a['id']]=data
        self.releases[release]['assets'].append(a)
        if self.crash=='upload:'+name:raise RuntimeError('process killed after upload')
        return copy.deepcopy(a)
    def api(self,path,method='GET',**fields):
        if path=='releases/tags/'+m.TAG:return copy.deepcopy(self.releases[1])
        if path.startswith('releases/assets/'):
            id=int(path.rsplit('/',1)[1]); rel=next(r for r in self.releases.values() if any(a['id']==id for a in r['assets']))
            a=next(a for a in rel['assets'] if a['id']==id)
            if method=='PATCH':a.update(fields)
            elif method=='DELETE':rel['assets'].remove(a)
            if self.crash==method:raise RuntimeError('process killed after '+method)
            return copy.deepcopy(a)
        id=int(path.rsplit('/',1)[1])
        if method=='PATCH':
            self.releases[id].update(fields)
            if self.crash=='receipt':raise RuntimeError('receipt response lost')
        return copy.deepcopy(self.releases[id])

class Transactions(unittest.TestCase):
    def prepare(self,api):
        return m.prepare(api,api.api('releases/tags/'+m.TAG),2,42,'a'*64,123,'OS4.0.6.0.XBLCNXM',
                         'new-xm.zip',b'NEW',b'OLD')
    def test_happy_switch_backup_and_receipt(self):
        a=FakeGitHub();t=self.prepare(a);t.complete()
        self.assertEqual([x['name'] for x in a.releases[1]['assets']],['new-xm.zip'])
        self.assertIn('MOBILE_OTA_INTAKE=ACCEPTED',a.releases[2]['body'])
        self.assertEqual(a.download(t.j['backup_id']),b'OLD')
        self.assertEqual(m.load(a,2,123,t.journal_sha).audit()['recovery_required'],False)
    def test_crash_after_rename_double_input_recovers_by_pinned_ids(self):
        a=FakeGitHub();t=self.prepare(a);a.crash='PATCH'
        with self.assertRaises(RuntimeError):t.complete()
        self.assertEqual(len(a.releases[1]['assets']),2)
        a.crash=None;t=m.load(a,2,123,t.journal_sha)
        self.assertTrue(t.audit()['old_present']);t.complete();self.assertFalse(t.audit()['old_present'])
    def test_crash_after_delete_only_receipt_can_be_completed(self):
        a=FakeGitHub();t=self.prepare(a);a.crash='DELETE'
        with self.assertRaises(RuntimeError):t.complete()
        a.crash=None;t=m.load(a,2,123,t.journal_sha)
        with self.assertRaises(ValueError):t.rollback()
        t.complete();self.assertIn('ACCEPTED',a.releases[2]['body'])
    def test_pending_before_rename_can_be_rolled_back(self):
        a=FakeGitHub();t=self.prepare(a);m.load(a,2,123,t.journal_sha).rollback()
        self.assertEqual([x['name'] for x in a.releases[1]['assets']],['old-xm.zip'])
    def test_journal_uploaded_staging_record_lost_then_resume(self):
        a=FakeGitHub();t=self.prepare(a);a.crash='upload:stock-staged-123.json'
        with self.assertRaises(RuntimeError):t.complete()
        a.crash=None;m.load(a,2,123,t.journal_sha).complete()
        self.assertEqual(len(a.releases[1]['assets']),1)
    def test_crash_after_pending_upload_can_resume_without_touching_old(self):
        a=FakeGitHub();a.crash='upload:pandora-mobile-pending-123.upload'
        with self.assertRaises(RuntimeError):self.prepare(a)
        raw=next(a.data[x['id']] for x in a.releases[2]['assets'] if x['name']=='stock-transaction-123.json')
        a.crash=None;m.load(a,2,123,m.sha(raw)).complete()
    def test_backup_or_journal_failure_leaves_fixed_input_unchanged(self):
        for point in ('upload:stock-backup-123.zip','upload:stock-transaction-123.json'):
            a=FakeGitHub();a.crash=point
            with self.assertRaises(RuntimeError):self.prepare(a)
            self.assertEqual([x['name'] for x in a.releases[1]['assets']],['old-xm.zip'])
    def test_unrelated_current_asset_and_corrupt_journal_fail_closed(self):
        a=FakeGitHub();t=self.prepare(a)
        with self.assertRaises(ValueError):m.load(a,2,123,'b'*64)
        a.upload(1,'unrelated-xm.zip',b'OTHER')
        before=copy.deepcopy(a.releases)
        with self.assertRaises(ValueError):t.complete()
        with self.assertRaises(ValueError):t.rollback()
        self.assertEqual(before,a.releases)
    def test_mutated_old_or_new_bytes_never_deleted(self):
        for old in (True,False):
            a=FakeGitHub();t=self.prepare(a)
            id=t.j['old_id'] if old else next(x['id'] for x in a.releases[1]['assets'] if x['name'].endswith('.upload'))
            a.data[id]=b'TAMPERED'
            before=copy.deepcopy(a.releases)
            with self.assertRaises(ValueError):t.complete()
            self.assertEqual(before,a.releases)
    def test_replaced_new_asset_id_is_not_deleted_even_with_same_name_sha(self):
        a=FakeGitHub();t=self.prepare(a);t.complete()
        id=t.new_id;a.api('releases/assets/'+str(id),'DELETE');a.upload(1,'new-xm.zip',b'NEW')
        t=m.load(a,2,123,t.journal_sha)
        with self.assertRaises(ValueError):t.complete()
        with self.assertRaises(ValueError):t.rollback()
    def test_missing_receipt_is_idempotently_reconciled(self):
        a=FakeGitHub();t=self.prepare(a);t.complete();a.releases[2]['body']='PENDING'
        m.load(a,2,123,t.journal_sha).complete();self.assertIn('ACCEPTED',a.releases[2]['body'])
    def test_read_only_audit_does_not_mutate(self):
        a=FakeGitHub();t=self.prepare(a);before=copy.deepcopy(a.releases);t.audit();self.assertEqual(before,a.releases)

if __name__=='__main__':unittest.main()

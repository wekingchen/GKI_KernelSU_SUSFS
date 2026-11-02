import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('recovery',Path(__file__).with_name('verify-archived-candidate.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
B='OS4.0.6.0.XBLCNXM';S='a'*64;COMMIT='b'*40

class ArchiveRecovery(unittest.TestCase):
    def create(self,p):
        for name in m.REQUIRED:(p/name).write_text('original bytes '+name)
        for name in ('stock-report.json','gki-candidate.json'):
            (p/name).write_text(json.dumps(dict(build=B,ota_source_id=S,safe_to_flash=False,github_asset_id=123)))
        (p/'locked-candidate.env').write_text(f'OTA_BUILD={B}\nOTA_INPUT_SHA256={S}\nOTA_GKI_COMMIT={COMMIT}\n')
        (p/'build-metadata.txt').write_text(f'STOCK_BUILD={B}\nSTOCK_INPUT_SHA256={S}\nIMAGE_SHA256={m.digest(p/"Image")}\nSYMVERS_SHA256={m.digest(p/"Module.symvers")}\nFLASHABLE=NO\nFASTBOOT_BOOT=NOT_BUILT\nSOURCE_GKI_COMMIT={COMMIT}\n')
        self.manifest(p)
        return m.digest(p/'RELEASE-SHA256SUMS.txt')
    def manifest(self,p):
        (p/'RELEASE-SHA256SUMS.txt').write_text(''.join(f'{m.digest(p/n)}  {n}\n' for n in sorted(m.REQUIRED)))
    def test_day31_uses_permanent_bytes_without_any_artifact_or_new_source(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);pin=self.create(p)
            result=m.verify(p,pin,B,S,123)
            self.assertFalse(result['recompiled']);self.assertEqual(result['source_commit'],COMMIT)
    def test_wrong_manifest_sha_and_archive_bytes_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);pin=self.create(p)
            with self.assertRaises(ValueError):m.verify(p,'f'*64,B,S,123)
            (p/'Image').write_text('tampered')
            with self.assertRaises(ValueError):m.verify(p,pin,B,S,123)
    def test_changed_input_asset_sha_build_or_source_commit_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);pin=self.create(p)
            for build,sha,asset in ((B,'c'*64,123),(B,S,124),('OS4.0.7.0.XBLCNXM',S,123)):
                with self.assertRaises(ValueError):m.verify(p,pin,build,sha,asset)
            (p/'locked-candidate.env').write_text(f'OTA_BUILD={B}\nOTA_INPUT_SHA256={S}\nOTA_GKI_COMMIT={"c"*40}\n')
            self.manifest(p)
            with self.assertRaises(ValueError):m.verify(p,m.digest(p/'RELEASE-SHA256SUMS.txt'),B,S,123)
    def test_traversal_duplicate_and_missing_manifest_entries_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);self.create(p);manifest=p/'RELEASE-SHA256SUMS.txt';original=manifest.read_text()
            for text in (original+f'{S}  ../Image\n',original+original,original.replace(next(l for l in original.splitlines(True) if l.endswith('  Image\n')),'')):
                manifest.write_text(text)
                with self.assertRaises(ValueError):m.verify(p,m.digest(manifest),B,S,123)

if __name__=='__main__':unittest.main()

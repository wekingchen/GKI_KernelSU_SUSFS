import importlib.util,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('version',Path(__file__).with_name('kernel-version.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class VersionTests(unittest.TestCase):
 def test_threshold_matrix(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'Makefile'
   for n in (69,94,95,96,120):
    p.write_text(f'VERSION = 6\nPATCHLEVEL = 12\nSUBLEVEL = {n}\n')
    self.assertEqual(m.resolve(p,f'6.12.{n}'),[6,12,n])
    with self.assertRaises(ValueError):m.resolve(p,'6.12.1')
 def test_duplicate_missing_or_wrong_series_is_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'Makefile'
   for text in ('VERSION = 6\nPATCHLEVEL = 12\nSUBLEVEL = 69\nSUBLEVEL = 69\n','VERSION = 6\nPATCHLEVEL = 12\n','VERSION = 6\nPATCHLEVEL = 6\nSUBLEVEL = 69\n'):
    p.write_text(text)
    with self.assertRaises(ValueError):m.resolve(p,'6.12.69')
 def test_actual_shared_helper_threshold_without_modifying_upstream(self):
  import subprocess
  helper=Path(__file__).resolve().parents[2]/'security_patch/apply_cve_2026_43499.sh'
  text=helper.read_text();function='patch_chain_is_required() {'+text.split('patch_chain_is_required() {',1)[1].split('\n}\n',1)[0]+'\n}'
  for n in (69,94,95,96,120):
   result=subprocess.run(['bash','-c',function+f'\nkernel_version=6.12;kernel_sublevel={n};patch_chain_is_required'])
   self.assertEqual(result.returncode,0 if n<95 else 1)

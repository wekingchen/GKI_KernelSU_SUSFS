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

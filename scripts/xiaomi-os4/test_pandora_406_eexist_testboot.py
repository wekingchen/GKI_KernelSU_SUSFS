#!/usr/bin/env python3
import hashlib, importlib.util, json, struct, subprocess, sys, tempfile, unittest, zipfile
from pathlib import Path

BASE=Path(__file__).resolve().parent
SCRIPT=BASE/"package-pandora-406-eexist-testboot-v4.py"
RELEASE="6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k"

def h(b): return hashlib.sha256(b).hexdigest()

class Packager(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(); self.addCleanup(self.t.cleanup)
        self.d=Path(self.t.name)
        image=(b"X"*5000)+RELEASE.encode()+b"Y"*1000
        self.image=self.d/"Image"; self.image.write_bytes(image)
        header=bytearray(4096); header[:8]=b"ANDROID!"
        struct.pack_into("<IIII",header,8,8192,0,0,1584)
        struct.pack_into("<I",header,40,4); struct.pack_into("<I",header,1580,0)
        boot=bytes(header)+b"K"*8192
        self.zip=self.d/"stock.zip"
        with zipfile.ZipFile(self.zip,"w") as z: z.writestr("boot.img",boot)
        self.stock=self.d/"stock.json"
        self.stock.write_text(json.dumps({
            "uname":RELEASE,"ota_source_id":h(self.zip.read_bytes()),
            "stock_boot_sha256":h(boot)
        }))
        self.gate=self.d/"gate.json"
        self.gate.write_text(json.dumps({
            "formal_oem_gate":"BLOCKED","formal_oem_gate_unchanged":True,
            "experimental_gate":"RUNTIME_SELECTED_EEXIST_SHIM_TEST_ELIGIBLE",
            "eligible_for_fastboot_boot_experiment":True,"flashable":False,"lkg_promotion":False
        }))
        self.meta=self.d/"meta.txt"
        self.meta.write_text(
            "SOURCE_GKI_COMMIT=b1d12d482d767c50cb792d988e4479d3f75c342a\n"
            "EXPERIMENT=PANDORA_RUST_BINDER_EEXIST_SHIM\n"
            "FORMAL_OEM_GATE=BLOCKED\nFLASHABLE=NO\n"
            f"KERNEL_RELEASE={RELEASE}\nIMAGE_SHA256={h(image)}\n")
        self.out=self.d/"out.img"

    def run(self,*extra):
        return subprocess.run([sys.executable,str(SCRIPT),"--stock-zip",str(self.zip),
            "--stock-report",str(self.stock),"--shadow-gate",str(self.gate),
            "--metadata",str(self.meta),"--candidate-image",str(self.image),
            "--output",str(self.out),*extra],capture_output=True,text=True)

    def test_output_contains_only_expected_boot_flags(self):
        p=self.run(); self.assertEqual(p.returncode,0,p.stderr+p.stdout)
        data=self.out.read_bytes()
        cmd=data[44:44+1536].split(b"\0",1)[0]
        self.assertIn(b"pandora_rust_binder_eexist=1",cmd.split())
        self.assertIn(b"module_blacklist=kernelsu",cmd.split())
        self.assertNotIn(b"module_blacklist=rust_binder",cmd)
        self.assertEqual(len(data),12288)

    def test_formal_gate_pass_is_rejected(self):
        g=json.loads(self.gate.read_text()); g["formal_oem_gate"]="CRC_AND_VERMAGIC_MATCH_CANDIDATE"
        self.gate.write_text(json.dumps(g))
        self.assertNotEqual(self.run().returncode,0)

    def test_conflicting_shim_flag_is_rejected(self):
        with zipfile.ZipFile(self.zip) as z: boot=bytearray(z.read("boot.img"))
        cmd=b"pandora_rust_binder_eexist=0"
        boot[44:44+len(cmd)]=cmd
        with zipfile.ZipFile(self.zip,"w") as z: z.writestr("boot.img",boot)
        s=json.loads(self.stock.read_text()); s["ota_source_id"]=h(self.zip.read_bytes()); s["stock_boot_sha256"]=h(boot)
        self.stock.write_text(json.dumps(s))
        self.assertNotEqual(self.run().returncode,0)

if __name__=="__main__": unittest.main()

#!/usr/bin/env python3
"""Read-only: cross-check missing stock OEM imports against vendor_boot ramdisk providers."""
import argparse, collections, hashlib, importlib.util, io, json, struct, subprocess, zipfile
from pathlib import Path
p=Path(__file__).resolve().with_name("check-ota-oem-abi.py")
spec=importlib.util.spec_from_file_location("abi",p)
abi=importlib.util.module_from_spec(spec);spec.loader.exec_module(abi)

def cpio_modules(data):
    pos=0
    while pos+110<=len(data) and data[pos:pos+6] in (b"070701", b"070702"):
        fields=[int(data[pos+6+i*8:pos+14+i*8],16) for i in range(13)]
        sz, namesz, mode=fields[6],fields[11],fields[1]
        if namesz<2 or namesz>2048 or sz>40*1024*1024:raise ValueError("unsafe CPIO entry")
        end=pos+110+namesz
        if end>len(data):raise ValueError("truncated CPIO name")
        name=data[pos+110:end-1].decode("utf8","strict")
        if not name or name.startswith("/") or ".." in name.split("/"):raise ValueError("unsafe CPIO path")
        if name=="TRAILER!!!":return
        at=(end+3)//4*4
        if at+sz>len(data):raise ValueError("truncated CPIO data")
        if (mode & 0o170000)==0o100000 and name.endswith(".ko"):
            yield name,data[at:at+sz]
        pos=(at+sz+3)//4*4

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--stock",type=Path,required=True)
    ap.add_argument("--abi-report",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    rep=json.loads(a.abi_report.read_text())
    if (rep.get("gate")!="BLOCKED" or rep.get("eligible_for_fastboot_boot") is not False
            or len(rep.get("unresolved_kernel_imports",[]))!=923):
        raise ValueError("expected the pinned blocked report")
    with zipfile.ZipFile(a.stock) as z:
        stockmods=zipfile.ZipFile(io.BytesIO(z.read("oem-modules.zip")))
        stock_files=[i.filename for i in stockmods.infolist() if abi.KO_NAME.search(i.filename)]
        vb=z.read("vendor_boot.img")
    if vb[:8]!=b"VNDRBOOT" or struct.unpack_from("<I",vb,8)[0]!=4:
        raise ValueError("stock vendor_boot is not v4")
    page=struct.unpack_from("<I",vb,12)[0]
    size=struct.unpack_from("<I",vb,24)[0]
    head=struct.unpack_from("<I",vb,2096)[0]
    if page!=4096 or head!=2128 or not 0<size<64*1024*1024:
        raise ValueError("invalid vendor_boot layout")
    start=((head+page-1)//page)*page
    payload=vb[start:start+size]
    raw=subprocess.run(["lz4","-dc"],input=payload,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90,check=True).stdout
    if len(raw)>160*1024*1024:raise ValueError("oversized decompressed vendor ramdisk")
    before={x.rsplit("/",1)[-1] for x in stock_files}
    boot_names=[]
    providers={}
    fails=[]
    versions=collections.Counter()
    boot_crc_count=0
    for name,data in cpio_modules(raw):
        boot_names.append(name)
        try:
            sections=abi.elf_sections(data)
            vm=abi.module_vermagic(sections)
            versions[vm.split(" ")[0]]+=1
            crcs=abi.module_export_crcs(data)
            boot_crc_count+=len(crcs)
            for sym,crc in crcs.items():
                providers.setdefault(sym,[]).append({"module":name,"crc":crc})
        except Exception as e:
            fails.append({"module":name,"error":str(e)[:110]})
    exact=collections.Counter()
    unique_matched=[]
    missing=[]
    conflicts=[]
    multi=[]
    for import_id in rep["unresolved_kernel_imports"]:
        source,symbol=import_id.rsplit(":",1)
        blob=stockmods.read(source)
        sec=abi.elf_sections(abi.unpack_module(blob,source))
        want=abi.imported_versions(sec)[symbol]
        options=providers.get(symbol,[])
        same=[opt for opt in options if opt["crc"]==want]
        if len(options)==0:
            missing.append(import_id)
        elif len(options)==1 and len(same)==1:
            exact["single_provider_correct_crc"]+=1
            unique_matched.append({"consumer":source,"symbol":symbol,
              "provider":options[0]["module"],"crc":f"{want:08x}"})
        elif len(same)==0:
            conflicts.append({"consumer":source,"symbol":symbol,"expected_crc":f"{want:08x}",
                               "providers":[{"module":o["module"],"crc":f'{o["crc"]:08x}'} for o in options]})
        else:
            multi.append({"consumer":source,"symbol":symbol,"expected_crc":f"{want:08x}",
                          "providers":[{"module":o["module"],"crc":f'{o["crc"]:08x}'} for o in options]})
    result={
      "kind":"READ_ONLY_NOT_ABI_GATE", "vendor_boot_sha256":hashlib.sha256(vb).hexdigest(),
      "vendor_cpio_modules":len(boot_names),"vendor_cpio_exports":boot_crc_count,
      "vendor_boot_unique_basename_extra":len(set(p.rsplit("/",1)[-1] for p in boot_names)-before),
      "vendor_boot_additional_module_examples":sorted(set(p.rsplit("/",1)[-1] for p in boot_names)-before)[:80],
      "version_counts":versions,"parse_errors":fails[:25],"parse_error_count":len(fails),
      "previous_unresolved":923,"single_provider_correct_crc":len(unique_matched),
      "still_missing":len(missing),"wrong_crc_provider":len(conflicts),"multiple_crc_matching_providers":len(multi),
      "examples_confirmed":unique_matched[:40],"examples_still_missing":missing[:60],
      "examples_wrong_crc":conflicts[:20],"examples_multi":multi[:12],
      "qcom_scm_filenames":[x for x in boot_names if "scm" in x.lower()],
      "name_lookups":{n:[x for x in boot_names if x.rsplit("/",1)[-1]==n]
                       for n in ("smem.ko","qcom_scm.ko","qcom_ipc_logging.ko","rust_binder.ko","qcom_aoss.ko")}
    }
    a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False,default=dict)+"\n")
    public={k:v for k,v in result.items() if not k.startswith("examples_") and k not in ("vendor_boot_additional_module_examples",)}
    print(json.dumps(public,indent=2,ensure_ascii=False,default=dict))
    print("SAMPLES_CORRECT",unique_matched[:10])
    print("SAMPLES_MISSING",missing[:15])
    print("SAMPLES_MISMATCH",conflicts[:6])
    print("SAMPLES_MULTI",multi[:6])
    print("DIAGNOSTIC_ONLY_NO_BOOT_NO_GATE_CHANGE")

if __name__=="__main__":
    main()

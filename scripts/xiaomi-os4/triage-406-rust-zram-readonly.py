#!/usr/bin/env python3
"""Read-only evidence-only analysis of locked 4.0.6.0 Rust Binder and zsmalloc."""
import collections
import hashlib
import importlib.util
import io
import json
import os
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

DIR=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('abi',DIR/'check-ota-oem-abi.py')
abi=importlib.util.module_from_spec(spec); spec.loader.exec_module(abi)


def read_cpio_entries(raw: bytes):
    p=0
    while p+110<=len(raw) and raw[p:p+6] in (b"070701",b"070702"):
        fields=[int(raw[p+6+i*8:p+14+i*8],16) for i in range(13)]
        size,namelen=fields[6],fields[11]
        if namelen<2 or namelen>2048 or size>64*1024*1024:raise ValueError("invalid CPIO member")
        end=p+110+namelen
        if end>len(raw) or raw[end-1]!=0:raise ValueError("invalid CPIO filename")
        name=raw[p+110:end-1].decode("utf8","strict")
        if name=="TRAILER!!!":return
        if name.startswith("/") or ".." in name.split("/"):raise ValueError("unsafe path")
        off=(end+3)//4*4
        if off+size>len(raw):raise ValueError("truncated CPIO")
        yield name,raw[off:off+size]
        p=(off+size+3)//4*4


def vendor_ramdisk_entries(vb: bytes):
    if vb[:8]!=b"VNDRBOOT" or struct.unpack_from('<I',vb,8)[0]!=4:
        raise ValueError("expected vendor_boot v4")
    page,sz=struct.unpack_from('<I',vb,12)[0],struct.unpack_from('<I',vb,24)[0]
    head=struct.unpack_from('<I',vb,2096)[0]
    start=(head+page-1)//page*page
    buf=vb[start:start+sz]
    if buf[:4]!=b"\x02\x21\x4c\x18":raise ValueError("not LZ4 legacy")
    decoded=subprocess.run(['lz4','-dc'],input=buf,stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE,check=True,timeout=80).stdout
    return list(read_cpio_entries(decoded))


def module_data(data: bytes, name: str):
    elf=abi.unpack_module(data,name)
    sections=abi.elf_sections(elf)
    modinfo={}
    for item in sections.get('.modinfo',b'').split(b'\0'):
        if b'=' in item:
            k,v=item.split(b'=',1)
            if k in (b'depends',b'name',b'vermagic'):
                modinfo[k.decode()]=v.decode('utf8','replace')
    exported=abi.module_export_crcs(elf)
    imports=abi.imported_versions(sections)
    return {'sha256':hashlib.sha256(elf).hexdigest(),
            'bytes':len(elf),
            'name':modinfo.get('name'),
            'depends':modinfo.get('depends'),
            'vermagic':modinfo.get('vermagic','').split(' ')[0],
            'export_crc_zs_malloc':f"0x{exported['zs_malloc']:08x}" if 'zs_malloc' in exported else None,
            'import_crc_zs_malloc':f"0x{imports['zs_malloc']:08x}" if 'zs_malloc' in imports else None,
            'imports':len(imports),'exports':len(exported)}


def main():
    probe=Path(os.environ["RUNNER_TEMP"])/"rust-zram"
    zip_path=probe/"stock/pandora-stock-OS4.0.6.0.XBLCNXM-_b-xm.zip"
    gki=probe/"gki"
    conf=(gki/'final.config').read_text()
    cs={line.split('=',1)[0]:line.split('=',1)[1] for line in conf.splitlines() if '=' in line and not line.startswith('#')}
    wanted=['CONFIG_RUST','CONFIG_RUST_IS_AVAILABLE','CONFIG_RUST_BINDER',
            'CONFIG_ANDROID_BINDER_IPC','CONFIG_ANDROID_BINDERFS',
            'CONFIG_RUSTC_VERSION_TEXT','CONFIG_MODVERSIONS','CONFIG_EXTENDED_MODVERSIONS','CONFIG_RUSTC']
    config={c:cs.get(c,'NOT_ENABLED_OR_UNSET') for c in wanted}
    export_rows=(gki/'Module.symvers').read_text().splitlines()
    sym_ks=[x.split()[1] for x in export_rows if len(x.split())>=3 and x.split()[2]=='vmlinux']
    rust_exports=[x for x in sym_ks if x.startswith('_R')]
    abi_report=json.loads((probe/'existing/ota-abi-report-with-early.json').read_text())
    missing=abi_report['unresolved_kernel_imports']
    from_rust=[s for s in missing if 'rust_binder.ko:' in s]
    if len(missing)!=71 or len(from_rust)!=71:raise ValueError('expected 71 unresolved binder imports')
    with zipfile.ZipFile(zip_path) as stock:
        vb=stock.read('vendor_boot.img')
        oem=zipfile.ZipFile(io.BytesIO(stock.read('oem-modules.zip')))
        oem_index={x.filename:x for x in oem.infolist() if x.filename.endswith('.ko')}
        ramdisk=vendor_ramdisk_entries(vb)
        rammods={name:raw for name,raw in ramdisk if name.endswith('.ko')}
        non_modules=[name for name,raw in ramdisk if not name.endswith('.ko')]
        module_load={}
        for name,raw in ramdisk:
            if 'modules.' in name and not name.endswith('.ko') and len(raw)<2*1024*1024:
                lines=raw.decode('utf8','replace').splitlines()
                module_load[name]={'total_lines':len(lines),
                    'zram_family':[s for s in lines if any(k in s for k in ('zram','zsmalloc','node_cache','rust_binder'))],
                    'first_nonblank':next((s for s in lines if s.strip()),'')}
        modules={}
        for path,raw in rammods.items():
            if path.rsplit('/',1)[-1] in ('zram.ko','zsmalloc.ko','node_cache.ko','rust_binder.ko'):
                modules['vendor_boot/'+path]=module_data(raw,path)
        for path,entry in oem_index.items():
            if path.rsplit('/',1)[-1] in ('zram.ko','zsmalloc.ko','node_cache.ko','rust_binder.ko'):
                modules[path]=module_data(oem.read(entry),path)
        rustpaths=[n for n in oem_index if n.endswith('/rust_binder.ko')]
        if len(rustpaths)!=1: raise ValueError('unexpected Rust binder module count')
        rust_data=abi.unpack_module(oem.read(rustpaths[0]),rustpaths[0])
        rust_imports=abi.imported_versions(abi.elf_sections(rust_data))
    count=collections.Counter('rust_mangled' if s.rsplit(':',1)[-1].startswith('_R') else 'other' for s in from_rust)
    result={'kind':'READ_ONLY_NO_ABI_ACCEPTANCE',
        'candidate_gki_tag':'android16-6.12-2026-03_r74',
        'candidate_config':config,
        'candidate_vmlinux_export_count':len(sym_ks),
        'candidate_rust_mangled_export_count':len(rust_exports),
        'candidate_rust_mangled_export_examples':rust_exports[:12],
        'unresolved_rust_binder':len(from_rust),
        'unresolved_kind':count,
        'rust_binder_imports_total':len(rust_imports),
        'rust_binder_example_missing':[s.rsplit(':',1)[-1] for s in from_rust[:20]],
        'vendor_boot_non_module_cpio_files':non_modules,
        'vendor_boot_module_load_files':module_load,
        'zram_family_module_variants':modules}
    out=probe/'rust-zram-report.json'
    out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({k:v for k,v in result.items()
       if k not in ('rust_binder_example_missing','zram_family_module_variants')},
        indent=2,ensure_ascii=False,default=list))
    print('ZRAM_MODULES',json.dumps(modules,ensure_ascii=False))
    print('ALL_EVIDENCE_READ_ONLY',flush=True)


if __name__=='__main__':
    main()

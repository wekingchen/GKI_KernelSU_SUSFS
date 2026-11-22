#!/usr/bin/env python3
"""Apply one exact, opt-in r74 module-loader shim for pandora fastboot-boot testing.

When enabled by pandora_rust_binder_eexist=1, a userspace request to insert
rust_binder receives -EEXIST after the normal module_blacklist policy check but
before modinfo/modversion/symbol resolution. No other module is affected.
"""
from __future__ import annotations
import argparse, subprocess
from pathlib import Path

COMMIT="b1d12d482d767c50cb792d988e4479d3f75c342a"
PARAM_BLOCK="""static bool pandora_rust_binder_eexist;
core_param(pandora_rust_binder_eexist, pandora_rust_binder_eexist, bool, 0400);
"""
BLACKLIST_BLOCK='''	if (blacklisted(info->name)) {
		pr_err("Module %s is blacklisted\\n", info->name);
		return -EPERM;
	}
'''
SHIM='''
	/*
	 * pandora OS4.0.6 fastboot-boot experiment only:
	 * the stock runtime uses C Binder but requests an inert rust_binder.ko
	 * whose old Rust ABI is not provided by the r74 GKI. Android libmodprobe
	 * treats -EEXIST as an already-loaded success. Disabled by default.
	 */
	if (unlikely(pandora_rust_binder_eexist &&
		   !strcmp(info->name, "rust_binder"))) {
		pr_warn_once("pandora: rust_binder load request satisfied as EEXIST for C-Binder experiment\\n");
		return -EEXIST;
	}
'''

def patch(source: Path) -> None:
    head=subprocess.check_output(["git","-C",str(source),"rev-parse","HEAD"],text=True).strip()
    if head != COMMIT:
        raise SystemExit("ERROR: exact r74 commit required")
    p=source/"kernel/module/main.c"
    text=p.read_text()
    if "pandora_rust_binder_eexist" in text:
        raise SystemExit("ERROR: shim already present")
    param_anchor="core_param(module_blacklist, module_blacklist, charp, 0400);\n"
    if text.count(param_anchor)!=1 or text.count(BLACKLIST_BLOCK)!=1:
        raise SystemExit("ERROR: r74 module-loader anchor drift")
    text=text.replace(param_anchor,param_anchor+PARAM_BLOCK,1)
    text=text.replace(BLACKLIST_BLOCK,BLACKLIST_BLOCK+SHIM,1)
    # Strong ordering invariants: policy blacklist first, experiment EEXIST next,
    # module metadata and symbol/version work only after the shim.
    pos_black=text.index("if (blacklisted(info->name))")
    pos_shim=text.index("pandora_rust_binder_eexist &&",pos_black)
    pos_rewrite=text.index("rewrite_section_headers(info, flags)",pos_shim)
    pos_modinfo=text.index("check_modinfo(info->mod, info, flags)",pos_shim)
    if not (pos_black < pos_shim < pos_rewrite < pos_modinfo):
        raise SystemExit("ERROR: unsafe shim ordering")
    p.write_text(text)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--source",type=Path,required=True)
    a=ap.parse_args(); patch(a.source)
    print("PANDORA_RUST_BINDER_EEXIST_SHIM=APPLIED_EXACT_R74_ONLY")

if __name__=="__main__":
    main()

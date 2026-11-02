#!/usr/bin/env python3
import argparse,re
from pathlib import Path

def resolve(makefile, expected):
    text=Path(makefile).read_text()
    parts=[]
    for key in ('VERSION','PATCHLEVEL','SUBLEVEL'):
        values=re.findall(r'^'+key+r'\s*=\s*([0-9]+)\s*$',text,re.M)
        if len(values)!=1: raise ValueError('ambiguous kernel Makefile '+key)
        parts.append(int(values[0]))
    actual='.'.join(map(str,parts))
    if actual!=expected or parts[:2]!=[6,12]:raise ValueError('kernel version mismatch: '+actual+' != '+expected)
    return parts

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('makefile');p.add_argument('expected');a=p.parse_args()
    v=resolve(a.makefile,a.expected);print(str(v[0])+'.'+str(v[1]),v[2])

#!/usr/bin/env python3
import re,glob,os
rows=[]
for vt in sorted(glob.glob('out/*.validate.txt')):
    name=os.path.basename(vt).replace('.validate.txt','')
    t=open(vt).read()
    def g(pat,d='?'):
        m=re.search(pat,t); return m.group(1) if m else d
    dwt=g(r'DWARF coverage : (\d+) functions'); usr=g(r'mapped \((\d+) user')
    cpred=g(r'certain\s+(\d+) predicted'); ctp=g(r'TP=\s*(\d+)\s+FP=\s*\d+\s+unknown=\s*\d+\s+precision', )
    m=re.search(r'certain\s+(\d+) predicted\s+TP=\s*(\d+)\s+FP=\s*(\d+)\s+unknown=\s*(\d+)\s+precision=([\d.]+|n/?a)',t)
    cprec=g(r'Certain precision : ([\d.]+%|n/a[^\n]*)')
    crec=g(r'Certain recall\s+: ([\d.]+%)')
    orec=g(r'Overall recall\s+: ([\d.]+%)')
    prof=''
    rf='out/%s.result'%name
    if os.path.exists(rf):
        pm=re.search(r'PROFILE=(.*)',open(rf).read())
        if pm: prof=pm.group(1).strip()
    if m:
        pred,tp,fp,unk,pr=m.groups()
    else:
        pred=tp=fp=unk=pr='?'
    rows.append(dict(name=name,dwarf=dwt,user=usr,cpred=pred,tp=tp,fp=fp,unk=unk,
                     cprec=cprec,crec=crec,orec=orec,prof=prof))
hdr=f"{'binary':10} {'dwarfFns':8} {'userFns':7} {'certain':7} {'TP':4} {'FP':4} {'unk':4} {'c-prec':8} {'c-rec':7} {'o-rec':7}  profile"
print(hdr); print('-'*len(hdr))
for r in rows:
    print(f"{r['name']:10} {r['dwarf']:>8} {r['user']:>7} {r['cpred']:>7} {r['tp']:>4} {r['fp']:>4} {r['unk']:>4} {r['cprec']:>8} {r['crec']:>7} {r['orec']:>7}  {r['prof']}")
# distribution
precs=[float(r['cprec'].rstrip('%')) for r in rows if r['cprec'] and r['cprec'][0].isdigit()]
print("\nN with certain predictions:",len(precs))
print("100%% precision:",sum(1 for p in precs if p>=99.95))
print("<100%%:",sum(1 for p in precs if p<99.95))
recs=[float(r['crec'].rstrip('%')) for r in rows if r['crec'] and r['crec'][0].isdigit()]
import statistics
if recs: print("cert recall range %.1f-%.1f median %.1f"%(min(recs),max(recs),statistics.median(recs)))

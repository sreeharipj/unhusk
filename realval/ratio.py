#!/usr/bin/env python3
"""Location-provenance separation analysis. Reads out2/*.edges.tsv (unhusk's own
edge dump + DWARF label + decl_file). No re-derivation of Locations."""
import glob,os,re,statistics as st

def subcat(label, path):
    if label=='TP': return 'tp'
    if label=='UNK': return 'unk'
    # FP: classify by DWARF decl_file
    if 'core/src/ops/function.rs' in path: return 'fnonce_shim'
    if '/registry/' in path or '/.cargo/' in path: return 'dep'
    if 'core/src/' in path: return 'core_other'   # core generics (slice/iter/sync/...)
    if '/library/' in path: return 'lib_generic'  # alloc/std generics
    return 'lib_generic'

rows=[]  # dict per certain function
for f in sorted(glob.glob('out2/*.edges.tsv')):
    name=os.path.basename(f).replace('.edges.tsv','')
    for line in open(f):
        p=line.rstrip('\n').split('\t')
        if not p or p[0]!='EDGEDUMP': continue
        d={}
        addr=p[1]
        for kv in p[2:]:
            k,_,v=kv.partition('='); d[k]=v
        nu=int(d['user']); ns=int(d['std']); nd=int(d['dep']); nk=int(d['unk'])
        nlib=ns+nd+nk                # lib = std+dep (+unknown-origin Locations)
        denom=nu+nlib
        uf=nu/denom if denom else 0.0
        lbl=d['dwarf']; path=d.get('path','')
        cat=subcat(lbl,path)
        rows.append(dict(bin=name,addr=addr,nu=nu,nlib=nlib,uf=uf,label=lbl,cat=cat,path=path))

def dist(name, sel):
    v=[r['uf'] for r in rows if sel(r)]
    if not v:
        print(f"  {name:14} n=0"); return
    q=statistics_quartiles(v)
    print(f"  {name:14} n={len(v):4}  median={st.median(v):.3f}  IQR=[{q[0]:.3f},{q[1]:.3f}]  min={min(v):.3f}  max={max(v):.3f}")

def statistics_quartiles(v):
    s=sorted(v); n=len(s)
    def pct(p):
        if n==1: return s[0]
        i=p*(n-1); lo=int(i); fr=i-lo
        return s[lo]+(s[min(lo+1,n-1)]-s[lo])*fr
    return (pct(0.25),pct(0.75))

print("="*78)
print("USER_FRACTION DISTRIBUTIONS by category (lib = std+dep+unknown Locations)")
print("="*78)
dist('TP',            lambda r:r['cat']=='tp')
dist('fnonce_shim',   lambda r:r['cat']=='fnonce_shim')
dist('lib_generic',   lambda r:r['cat']=='lib_generic')
dist('core_other',    lambda r:r['cat']=='core_other')
dist('dep',           lambda r:r['cat']=='dep')
dist('  [reject=lib_generic+core_other+dep]', lambda r:r['cat'] in('lib_generic','core_other','dep'))
dist('  [keep=tp+fnonce_shim]', lambda r:r['cat'] in('tp','fnonce_shim'))
dist('UNK(no gt)',    lambda r:r['cat']=='unk')

from collections import Counter
print("\ncategory counts (pooled, all 13):")
c=Counter(r['cat'] for r in rows)
for k in ['tp','fnonce_shim','lib_generic','core_other','dep','unk']:
    print(f"  {k:12} {c.get(k,0)}")
print(f"  TOTAL certain {len(rows)}")

# ---- Rule evaluation ----
# keep-target (should keep): tp, fnonce_shim ; reject-target (should reject): lib_generic, core_other, dep
KEEP={'tp','fnonce_shim'}; REJECT={'lib_generic','core_other','dep'}
def rule_nuser(k): return lambda r: r['nu']>=k
def rule_uf(t):    return lambda r: r['uf']>=t
def rule_gt():     return lambda r: r['nu']>r['nlib']

rules=[('R1 n_user>=1 (current)',rule_nuser(1)),
       ('R2 n_user>n_lib',rule_gt()),
       ('R3 uf>=0.5',rule_uf(0.5)),
       ('n_user>=2',rule_nuser(2)),
       ('n_user>=3',rule_nuser(3)),
       ('uf>=0.3',rule_uf(0.3)),
       ('uf>=0.4',rule_uf(0.4)),
       ('uf>=0.5',rule_uf(0.5)),
       ('uf>=0.6',rule_uf(0.6)),
       ('uf>=0.7',rule_uf(0.7)),
       ('uf>=0.8',rule_uf(0.8))]

# consider only ground-truth-labelled functions (exclude UNK) for precision/sep
gt=[r for r in rows if r['cat']!='unk']
tot_tp=sum(1 for r in gt if r['cat']=='tp')
tot_shim=sum(1 for r in gt if r['cat']=='fnonce_shim')
tot_realfp=sum(1 for r in gt if r['cat'] in REJECT)
print(f"\nground-truth-labelled certain: TP={tot_tp} fnonce_shim={tot_shim} real_FP(lib+core+dep)={tot_realfp}  (UNK excluded={sum(1 for r in rows if r['cat']=='unk')})")

print("\n"+"="*78)
print("RULE TRADEOFF over pooled ground-truth-labelled certain set")
print("realFP_rejected / realFP_total | shim_rejected/shim_total | TP_lost/TP_total")
print("="*78)
print(f"{'rule':24} {'realFP rej':>12} {'shim rej':>12} {'TP lost':>12}   prec[shim=TP]  prec[shim=FP]")
for nm,fn in rules:
    kept=[r for r in gt if fn(r)]
    realfp_rej=tot_realfp-sum(1 for r in kept if r['cat'] in REJECT)
    shim_rej=tot_shim-sum(1 for r in kept if r['cat']=='fnonce_shim')
    tp_lost=tot_tp-sum(1 for r in kept if r['cat']=='tp')
    kept_tp=sum(1 for r in kept if r['cat']=='tp')
    kept_shim=sum(1 for r in kept if r['cat']=='fnonce_shim')
    kept_fp=sum(1 for r in kept if r['cat'] in REJECT)
    # shim=TP reading
    den1=kept_tp+kept_shim+kept_fp; p1=(kept_tp+kept_shim)/den1*100 if den1 else 0
    # shim=FP reading
    den2=kept_tp+kept_shim+kept_fp; p2=(kept_tp)/den2*100 if den2 else 0
    print(f"{nm:24} {realfp_rej:>5}/{tot_realfp:<5} {shim_rej:>5}/{tot_shim:<5} {tp_lost:>5}/{tot_tp:<5}   {p1:8.1f}%      {p2:8.1f}%")

# ---- per-binary precision for bat,fd,grex + aggregate under each rule ----
def prec_under(binset, fn, shim_as):
    sel=[r for r in gt if (r['bin'] in binset if binset else True)]
    kept=[r for r in sel if fn(r)]
    tp=sum(1 for r in kept if r['cat']=='tp')
    shim=sum(1 for r in kept if r['cat']=='fnonce_shim')
    fp=sum(1 for r in kept if r['cat'] in REJECT)
    den=tp+shim+fp
    if den==0: return None,0
    if shim_as=='TP': return (tp+shim)/den*100, den
    else: return tp/den*100, den

print("\n"+"="*78)
print("PRECISION per rule  (shim=TP / shim=FP brackets)  [denominator]")
print("="*78)
targets=[('bat',{'bat'}),('fd',{'fd'}),('grex',{'grex'}),('AGGREGATE',None)]
hdr_rules=[('R1',rule_nuser(1)),('R2 nu>nlib',rule_gt()),('uf>=0.5',rule_uf(0.5)),('uf>=0.7',rule_uf(0.7)),('n_user>=2',rule_nuser(2))]
print(f"{'target':10} "+" | ".join(f"{n:>16}" for n,_ in hdr_rules))
for tname,bs in targets:
    cells=[]
    for n,fn in hdr_rules:
        p1,d=prec_under(bs,fn,'TP'); p2,_=prec_under(bs,fn,'FP')
        cells.append(f"{(p1 or 0):4.0f}/{(p2 or 0):<4.0f}[{d}]")
    print(f"{tname:10} "+" | ".join(f"{c:>16}" for c in cells))

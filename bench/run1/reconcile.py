#!/usr/bin/env python3
"""Reconciliation numbers for the outline claim-pins: ceiling levers, RS90
clause breakdown on the sealed test crates, R3-vs-A@2 paired bootstrap.
Run AFTER mine1.py (heavy; don't run both at once)."""
import glob, json, sys
import numpy as np, pandas as pd
sys.path.insert(0, 'bench/rulemine/lib'); import mining, protocol as P  # noqa

df = pd.concat((pd.read_parquet(f) for f in sorted(glob.glob('bench/run1/fde/*.parquet'))), ignore_index=True)
for c in ('crate', 'config', 'label'):
    df[c] = df[c].astype(str)
df = df[~df.label.isin(['NONE', 'UNKNOWN'])].reset_index(drop=True)
y = P.target(df, 'ws')
anch = df['M_rel_structs'].to_numpy() >= 1
cfg = df.config.to_numpy()
crate = df.crate.to_numpy()


def ceiling(mask):
    a = y[mask]; c = anch[mask]
    return (a & c).sum() / a.sum()


print("=== ceiling (anchored/author) by config ===")
for cf in ['c1', 'c2', 'c3', 'c4']:
    m = cfg == cf
    print(f"  {cf}: {ceiling(m):.2%}  author={y[m].sum():,}")

print("\n=== matched-crate lever deltas ===")
for a, b, lab in [('c3', 'c1', 'cgu 1->16'), ('c1', 'c2', 'opt-3->opt-z'),
                  ('c1', 'c4', 'normal->inline-supp'), ('c3', 'c4', 'cgu1->inline-supp')]:
    common = set(crate[cfg == a]) & set(crate[cfg == b])
    sel = np.isin(crate, list(common))
    ca, cb = ceiling((cfg == a) & sel), ceiling((cfg == b) & sel)
    print(f"  {lab:22s} {a}={ca:.2%} {b}={cb:.2%} delta={100*(cb-ca):+.2f}pp (n={len(common)})")

split = json.load(open('bench/run1/split.json')); tc = set(split['test'])
te = np.isin(crate, list(tc)) & np.isin(cfg, ['c1', 'c2', 'c3'])
dte = df[te].reset_index(drop=True); yte = P.target(dte, 'ws')
RS90 = ["G_loc_per_kb <= 4.27 AND N_win_rel >= 1",
        "N_win_rel >= 1 AND N_win_rel_frac >= 0.6",
        "M_rel_frac >= 1 AND G_n_ref_rodata >= 1"]
print("\n=== RS90 on TEST (36 sealed crates, c1-3) ===")
full = np.zeros(len(dte), bool)
for i, cl in enumerate(RS90):
    p = mining.eval_expr(dte, cl); full |= p
    tp = int((yte & p).sum()); fp = int((~yte & p).sum())
    print(f"  clause{i} {cl:44s} P={tp/(tp+fp):.1%} fires={tp+fp}")
tp = int((yte & full).sum()); fp = int((~yte & full).sum())
print(f"  UNION P={tp/(tp+fp):.1%} recall={tp/yte.sum():.1%}")
p2 = mining.eval_expr(dte, RS90[2])
s2 = P.score_binary(yte, p2, dte.crate.to_numpy(), bootstrap=True, iters=2000)
print(f"  clause2 alone P={s2['precision']:.1%} CI{[round(x,3) for x in s2['precision_cluster_boot']]} recall={s2['recall']:.1%}")

print("\n=== R3 vs A@2 on TEST — paired crate bootstrap ===")
a2 = mining.eval_expr(dte, 'C_user >= 2 AND P_nonrel <= 0')
r3 = mining.eval_expr(dte, 'M_rel_structs >= 1 AND N_win_rel >= 5')
sa = P.score_binary(yte, a2, dte.crate.to_numpy(), bootstrap=False)
sr = P.score_binary(yte, r3, dte.crate.to_numpy(), bootstrap=False)
d, lo, hi = P.paired_crate_bootstrap(sr['per_crate'], sa['per_crate'], 'precision', iters=3000)
dr, rl, rh = P.paired_crate_bootstrap(sr['per_crate'], sa['per_crate'], 'recall', iters=3000)
pv = P.paired_crate_bootstrap_p(sr['per_crate'], sa['per_crate'], 'precision', iters=4000)
print(f"  A@2 P={sa['precision']:.1%} r={sa['recall']:.2%} | R3 P={sr['precision']:.1%} r={sr['recall']:.2%}")
print(f"  R3-A@2 precision {d:+.2f}pp [{lo:+.2f},{hi:+.2f}] p={pv:.3f} | recall {dr:+.2f}pp [{rl:+.2f},{rh:+.2f}]")

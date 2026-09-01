#!/usr/bin/env python3
"""
frontier_test.py — the c1 x test_crates held-out cell.

rules_all.json pools all 168 crates in its config sections and all 4 configs in
its split sections; there is no c1-only, test-only number anywhere. The abstract
needs one it can call held out. This computes it for the frontier rules, on c1,
ws, restricted to the sealed test crates in split.json. Expect wider CIs.
"""
import glob, json, os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "rulemine", "lib"))
import mining, protocol as P  # noqa: E402
from oracle import cluster_bootstrap  # noqa: E402

SEED, ITERS = 20260901, 5000
split = json.load(open(os.path.join(HERE, "split.json")))
TEST = set(split["test"])

files = [f for f in sorted(glob.glob(os.path.join(HERE, "fde", "*__c1.parquet")))]
df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
for c in ("crate", "config", "label"):
    df[c] = df[c].astype(str)
df = df[~df.label.isin(["NONE", "UNKNOWN"])].reset_index(drop=True)
df = df[df.crate.isin(TEST)].reset_index(drop=True)

y = np.asarray(P.target(df, "ws"), bool)
sz = df["G_size"].to_numpy().astype(float)
crate = df["crate"].to_numpy()
npos, totB = int(y.sum()), float(sz[y].sum())
cu, pt = df["C_user"].to_numpy(), df["P_total"].to_numpy()
rg = df["C_registry"].to_numpy() + df["C_git"].to_numpy()
with np.errstate(all="ignore"):
    ratio = np.where(pt > 0, cu / np.maximum(pt, 1), 0.0)

rules = {
    "B@1": (cu >= 1) & (rg == 0),
    "B@2": (cu >= 2) & (rg == 0),
    "B@3": (cu >= 3) & (rg == 0),
    "A@2": (cu >= 2) & ((pt - cu) == 0),
    "C@0.70": (pt > 0) & (ratio >= 0.70),
    "C@0.80": (pt > 0) & (ratio >= 0.80),
    "R3": mining.eval_expr(df, "M_rel_structs >= 1 AND N_win_rel >= 5"),
    "any_anchor": mining.eval_expr(df, "M_rel_structs >= 1"),
}

n_test_crates = df.crate.nunique()
print(f"c1 x test | {n_test_crates} sealed crates present | {len(df):,} fns | "
      f"{npos:,} author fns / {totB/1e6:.2f} MB | base {y.mean():.4f}\n")
print(f"{'rule':11s} {'prec':>7s} {'cluster-boot CI':>18s} {'rec_fn':>7s} {'rec_byte':>9s} {'crates':>6s} {'fires':>7s}")
out = {"config": "c1", "target": "ws", "slice": "test_crates", "seed": SEED,
       "boot_iters": ITERS, "split_sha": split["sha256"],
       "n_test_crates_present": int(n_test_crates), "author_fns": npos,
       "author_MB": round(totB / 1e6, 3), "rules": {}}
for name, m in rules.items():
    m = np.asarray(m, bool)
    tp = m & y
    ntp, nm = int(tp.sum()), int(m.sum())
    prec = ntp / nm if nm else float("nan")
    per = []
    for c in sorted(set(crate)):
        ci_ = crate == c
        t = int((m[ci_] & y[ci_]).sum()); f = int((m[ci_] & ~y[ci_]).sum())
        if t + f:
            per.append((t, f))
    _, lo, hi = cluster_bootstrap(per, iters=ITERS, seed=SEED)
    out["rules"][name] = {
        "precision": round(prec, 4), "ci": [round(lo / 100, 4), round(hi / 100, 4)],
        "recall_fn": round(ntp / npos, 4), "recall_byte": round(float(sz[tp].sum()) / totB, 4),
        "crates_firing": len(per), "fires": nm,
    }
    print(f"{name:11s} {prec:7.3f}   [{lo/100:6.3f}, {hi/100:6.3f}]  {ntp/npos:7.2%} "
          f"{float(sz[tp].sum())/totB:9.2%} {len(per):6d} {nm:7d}")

json.dump(out, open(os.path.join(HERE, "results", "frontier_c1_test.json"), "w"), indent=1)
print("\nwrote results/frontier_c1_test.json")

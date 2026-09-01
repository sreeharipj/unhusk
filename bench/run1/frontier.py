#!/usr/bin/env python3
"""
frontier.py — the c1 ws discrete-rule Pareto table, one canonical artifact.

For every fixed rule in the three families

    count   A@n = (C_user >= n) AND (P_total - C_user == 0)          [strict count]
            B@n = (C_user >= n) AND (C_registry + C_git == 0)        [loose count]
    purity  C@r = (P_total > 0) AND (C_user / P_total >= r)          [anchor purity]
    composite  R1 = M_rel_structs>=2 AND N_win_rel>=3
               R2 = M_rel_structs>=2 AND X_caller_rel>=1
               R3 = M_rel_structs>=1 AND N_win_rel>=5
    reference  any_anchor = M_rel_structs >= 1

report, on c1 (the shipped `cargo build --release` default) with the ws target:

    precision + 95% crate cluster-bootstrap CI
    function-recall  (tp fns / all author fns)
    byte-recall      (tp bytes / all author bytes)  + its own cluster-boot CI
    crate coverage   (# crates the rule fires in)
    fires, mean TP size

Nothing is fitted or selected. This file supersedes the ad-hoc script that made
the first frontier_c1.json; SEED / ITERS below are the canonical ones.
"""
import glob, json, os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "rulemine", "lib"))
import mining, protocol as P  # noqa: E402
from oracle import cluster_bootstrap  # noqa: E402

CFG = "c1"
TARGET = "ws"
SEED = 20260901
ITERS = 5000
CRATIOS = (0.50, 0.60, 0.70, 0.80, 0.90)


def byte_recall_ci(tp_mask, y, sz, crate, iters=ITERS, seed=SEED):
    """Cluster bootstrap of byte-recall: resample whole crates, recompute
    sum(TP bytes) / sum(author bytes). Returns (point, lo, hi) as fractions."""
    crates = sorted(set(crate))
    num = {c: float(sz[tp_mask & (crate == c)].sum()) for c in crates}
    den = {c: float(sz[y & (crate == c)].sum()) for c in crates}
    tot_n, tot_d = sum(num.values()), sum(den.values())
    point = tot_n / tot_d if tot_d else float("nan")
    rng = np.random.default_rng(seed)
    n = len(crates)
    xs = []
    for _ in range(iters):
        pick = rng.integers(0, n, n)
        s = sum(num[crates[i]] for i in pick)
        d = sum(den[crates[i]] for i in pick)
        if d:
            xs.append(s / d)
    xs.sort()
    lo = xs[int(0.025 * len(xs))]
    hi = xs[min(len(xs) - 1, int(0.975 * len(xs)))]
    return point, lo, hi


def main():
    files = [f for f in sorted(glob.glob(os.path.join(HERE, "fde", "*.parquet")))
             if f.endswith(f"__{CFG}.parquet")]
    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
    for c in ("crate", "config", "label"):
        df[c] = df[c].astype(str)
    df = df[~df.label.isin(["NONE", "UNKNOWN"])].reset_index(drop=True)

    y = np.asarray(P.target(df, TARGET), bool)
    sz = df["G_size"].to_numpy().astype(float)
    crate = df["crate"].to_numpy()
    npos = int(y.sum())
    totB = float(sz[y].sum())
    cu = df["C_user"].to_numpy()
    pt = df["P_total"].to_numpy()
    rg = df["C_registry"].to_numpy() + df["C_git"].to_numpy()
    with np.errstate(all="ignore"):
        ratio = np.where(pt > 0, cu / np.maximum(pt, 1), 0.0)

    rules = {}
    for n in (1, 2, 3):
        rules[f"A@{n}"] = (cu >= n) & ((pt - cu) == 0)
    for n in (1, 2, 3):
        rules[f"B@{n}"] = (cu >= n) & (rg == 0)
    for r in CRATIOS:
        rules[f"C@{r:.2f}"] = (pt > 0) & (ratio >= r)
    rules["R1"] = mining.eval_expr(df, "M_rel_structs >= 2 AND N_win_rel >= 3")
    rules["R2"] = mining.eval_expr(df, "M_rel_structs >= 2 AND X_caller_rel >= 1")
    rules["R3"] = mining.eval_expr(df, "M_rel_structs >= 1 AND N_win_rel >= 5")
    rules["any_anchor"] = mining.eval_expr(df, "M_rel_structs >= 1")

    out = {"config": CFG, "target": TARGET, "seed": SEED, "boot_iters": ITERS,
           "author_fns": npos, "author_MB": round(totB / 1e6, 3),
           "n_crates": int(df.crate.nunique()),
           "note": "canonical; supersedes the ad-hoc frontier_c1.json. "
                   "count(A/B) vs purity(C) vs composite(R).",
           "rules": {}}

    hdr = f"{'rule':11s} {'prec':>7s} {'ci':>16s}  {'rec_fn':>7s} {'rec_byte':>9s}" \
          f" {'byteCI':>16s} {'crates':>6s} {'fires':>7s}"
    print(f"c1 ws | {npos:,} author fns / {totB/1e6:.2f} MB / {df.crate.nunique()} crates\n")
    print(hdr)
    for name, m in rules.items():
        m = np.asarray(m, bool)
        tp = m & y
        ntp, nm = int(tp.sum()), int(m.sum())
        prec = ntp / nm if nm else float("nan")
        # precision CI: crate cluster bootstrap of (tp, fp)
        per = []
        for c in sorted(set(crate)):
            ci_ = crate == c
            t = int((m[ci_] & y[ci_]).sum())
            f = int((m[ci_] & ~y[ci_]).sum())
            if t + f:
                per.append((t, f))
        _, plo, phi = cluster_bootstrap(per, iters=ITERS, seed=SEED)
        bpt, blo, bhi = byte_recall_ci(tp, y, sz, crate)
        rec_fn = ntp / npos
        rec_byte = float(sz[tp].sum()) / totB
        mean_tp = float(sz[tp].sum()) / max(ntp, 1)
        out["rules"][name] = {
            "precision": round(prec, 4),
            "ci": [round(plo / 100, 4), round(phi / 100, 4)],
            "recall_fn": round(rec_fn, 4),
            "recall_byte": round(rec_byte, 4),
            "recall_byte_ci": [round(blo, 4), round(bhi, 4)],
            "crates_firing": len(per),
            "fires": nm,
            "mean_tp_bytes": round(mean_tp, 0),
        }
        print(f"{name:11s} {prec:7.3f} [{plo/100:6.3f},{phi/100:6.3f}]  "
              f"{rec_fn:7.2%} {rec_byte:9.2%} [{blo:6.3f},{bhi:6.3f}] "
              f"{len(per):6d} {nm:7d}")

    json.dump(out, open(os.path.join(HERE, "results", "frontier_c1.json"), "w"), indent=1)
    print("\nwrote results/frontier_c1.json")


if __name__ == "__main__":
    main()

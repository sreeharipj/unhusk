#!/usr/bin/env python3
"""
boot_diag.py -- the few-clusters diagnostic Cameron & Miller (2015, VI.C.4)
prescribe for a pairs cluster bootstrap.

With G = 36 sealed crates we are inside the regime they call "few" (they put it
at anywhere from <20 to <50), where the pairs cluster bootstrap is known not to
eliminate overrejection.  Their recommended check is to look at the bootstrap
distribution itself: a mass that sits apart from the rest means one cluster is
driving the interval.  This reports the four things they ask for -- summary
statistics, replicate count, the extreme values, and the shape of the
distribution -- plus a leave-one-crate-out sweep, which is the direct test of
"are the results sensitive to the inclusion of that cluster".

Run from the repo root:  python3 bench/run1/boot_diag.py
"""
import glob, json, os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "rulemine", "lib"))
import mining, protocol as P  # noqa: E402

SEED, ITERS = 20260901, 5000
split = json.load(open(os.path.join(HERE, "split.json")))
TEST = set(split["test"])

files = sorted(glob.glob(os.path.join(HERE, "fde", "*__c1.parquet")))
df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
for c in ("crate", "config", "label"):
    df[c] = df[c].astype(str)
df = df[~df.label.isin(["NONE", "UNKNOWN"])].reset_index(drop=True)


def clusters_for(sub, mask):
    """(tp, fp) per crate, keeping only crates where the rule fires."""
    y = np.asarray(P.target(sub, "ws"), bool)
    crate = sub["crate"].to_numpy()
    m = np.asarray(mask, bool)
    out = []
    for c in sorted(set(crate)):
        i = crate == c
        t = int((m[i] & y[i]).sum())
        f = int((m[i] & ~y[i]).sum())
        if t + f:
            out.append((c, t, f))
    return out


def boot(cl, iters=ITERS, seed=SEED):
    """Pairs cluster bootstrap over whole crates. Returns the replicates."""
    rng = np.random.default_rng(seed)
    n = len(cl)
    s = np.array([t for _, t, _ in cl], float)
    f = np.array([x for _, _, x in cl], float)
    xs = []
    for _ in range(iters):
        p = rng.integers(0, n, n)
        num, den = s[p].sum(), s[p].sum() + f[p].sum()
        if den:
            xs.append(100.0 * num / den)
    return np.array(sorted(xs))


def rules_for(sub):
    cu, pt = sub["C_user"].to_numpy(), sub["P_total"].to_numpy()
    rg = sub["C_registry"].to_numpy() + sub["C_git"].to_numpy()
    with np.errstate(all="ignore"):
        ratio = np.where(pt > 0, cu / np.maximum(pt, 1), 0.0)
    return {
        "B@2":    (cu >= 2) & (rg == 0),
        "C@0.70": (pt > 0) & (ratio >= 0.70),
        "A@2":    (cu >= 2) & ((pt - cu) == 0),
        "R3":     np.asarray(mining.eval_expr(sub, "M_rel_structs >= 1 AND N_win_rel >= 5"), bool),
    }


def report(tag, sub):
    print(f"\n{'='*72}\n{tag}   ({sub.crate.nunique()} crates, {len(sub):,} fns)\n{'='*72}")
    R = rules_for(sub)
    res = {}
    for name, mask in R.items():
        cl = clusters_for(sub, mask)
        G = len(cl)
        tot_t = sum(t for _, t, _ in cl)
        tot_f = sum(f for _, _, f in cl)
        point = 100.0 * tot_t / (tot_t + tot_f)
        xs = boot(cl)
        lo, hi = np.percentile(xs, [2.5, 97.5])

        # (1) summary stats  (2) replicate count  (3) extremes  (4) shape
        gaps = np.diff(xs)
        gi = int(np.argmax(gaps))
        biggest_gap = gaps[gi]
        gap_at = xs[gi]
        below = (gi + 1) / len(xs)

        # share of all firings held by the single largest crate
        fires = sorted(((t + f, c, t, f) for c, t, f in cl), reverse=True)
        top_share = 100.0 * fires[0][0] / (tot_t + tot_f)

        # leave-one-crate-out: how far can dropping ONE crate move the point?
        loo = []
        for c, t, f in cl:
            nt, nf = tot_t - t, tot_f - f
            if nt + nf:
                loo.append((100.0 * nt / (nt + nf), c))
        loo.sort()
        lo_c, hi_c = loo[0], loo[-1]

        print(f"\n  {name}   G = {G} crates, {tot_t + tot_f:,} firings")
        print(f"    point            {point:6.2f}%   CI [{lo:.2f}, {hi:.2f}]  "
              f"(width {hi-lo:.2f} pp)")
        print(f"    replicates       {len(xs):,} of {ITERS} requested")
        print(f"    boot mean/sd     {xs.mean():6.2f}% / {xs.std(ddof=1):.2f} pp")
        print(f"    5 lowest         {np.round(xs[:5], 2).tolist()}")
        print(f"    5 highest        {np.round(xs[-5:], 2).tolist()}")
        print(f"    largest gap      {biggest_gap:.3f} pp at {gap_at:.2f}% "
              f"({below:.1%} of mass below it)")
        print(f"    biggest crate    {fires[0][1]} = {fires[0][0]:,} firings "
              f"({top_share:.1f}% of all)")
        print(f"    leave-one-out    {lo_c[0]:.2f}% (drop {lo_c[1]}) .. "
              f"{hi_c[0]:.2f}% (drop {hi_c[1]})  span {hi_c[0]-lo_c[0]:.2f} pp")

        # coarse histogram
        cnt, edge = np.histogram(xs, bins=24)
        top = cnt.max()
        print("    shape")
        for k in range(24):
            bar = "#" * int(round(40 * cnt[k] / top))
            print(f"      {edge[k]:6.2f} {bar}")
        res[name] = dict(G=G, point=round(point, 2), lo=round(lo, 2), hi=round(hi, 2),
                         width=round(hi - lo, 2), boot_sd=round(float(xs.std(ddof=1)), 3),
                         largest_gap_pp=round(float(biggest_gap), 3),
                         mass_below_gap=round(float(below), 4),
                         top_crate=fires[0][1], top_crate_share=round(top_share, 2),
                         loo_min=round(lo_c[0], 2), loo_min_crate=lo_c[1],
                         loo_max=round(hi_c[0], 2), loo_max_crate=hi_c[1],
                         loo_span=round(hi_c[0] - lo_c[0], 2))
    return res


out = {"seed": SEED, "iters": ITERS,
       "test": report("SEALED TEST CRATES (the held-out read)",
                      df[df.crate.isin(TEST)].reset_index(drop=True)),
       "all": report("ALL CRATES (the descriptive read)", df)}
json.dump(out, open(os.path.join(HERE, "results", "boot_diag.json"), "w"), indent=1)
print("\nwrote results/boot_diag.json")

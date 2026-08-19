#!/usr/bin/env python3
"""
D02 — how good can this search make a rule look on pure noise?

The question behind "should we add twenty more features" is really "how much of
what the search finds is signal, and how much can a search of this shape
manufacture from a space this large?" That is measurable, not a matter of
judgement.

Method. Labels are shuffled WITHIN each crate, which destroys the relationship
between features and authorship while preserving every crate's base rate and the
cluster structure the bootstrap relies on. The entire conjunction search then runs
on that noise, under exactly the protocol used for the real result. Whatever it
returns is the noise floor: the best rule a search over this feature space can
produce when there is nothing to find.

Repeated at several feature-set sizes, the noise floor as a function of feature
count answers the actual question — if going from 20 features to 91 lifts the
noise floor substantially, then going from 91 to 112 will lift it again, and any
apparent gain from new features has to clear that bar before it means anything.

Note on what this does and does not control. It measures inflation from the SIZE
of the search space. It does not measure inflation from a human choosing which
features to build, which is why the study's defence there is the pre-registered
ordering and the sealed split, not this script.
"""
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDY, "lib"))
import mining  # noqa: E402
import protocol as P  # noqa: E402

N_PERM = 8
SIZES = [10, 25, 45, 91]
TAU = 0.95
MIN_CRATES = 8


def shuffle_within_crate(y, crates, rng):
    """Permute labels inside each crate. Preserves per-crate base rate exactly."""
    out = y.copy()
    order = np.argsort(crates, kind="stable")
    bounds = np.flatnonzero(np.r_[True, crates[order][1:] != crates[order][:-1]])
    bounds = np.r_[bounds, len(order)]
    for a, b in zip(bounds[:-1], bounds[1:]):
        idx = order[a:b]
        out[idx] = rng.permutation(y[idx])
    return out


def best_rule(df, y, cols, tau=TAU, min_crates=MIN_CRATES):
    space = mining.Bitspace(y, df["crate"].to_numpy())
    atoms = mining.dedupe_atoms(mining.make_atoms(df, cols, max_thresholds=8), space)
    res, _ = mining.search_pairs(atoms, space, tau=tau, min_crates=min_crates,
                                 max_len=2, top_k=1)
    if not res:
        return {"n_atoms": len(atoms), "found": False, "recall": 0.0,
                "precision": float("nan"), "expr": None}
    r = res[0]
    return {"n_atoms": len(atoms), "found": True, "recall": r["recall"],
            "precision": r["precision"], "expr": r["expr"],
            "crates_firing": r["crates_firing"]}


def main():
    df = P.load("dev")
    y = P.target(df, "ws")
    all_cols = P.feature_cols(df)
    crates = df["crate"].to_numpy()
    rng = np.random.default_rng(P.SEED)

    print(f"dev {len(df):,} rows, {len(all_cols)} features, base {y.mean():.3%}")
    print(f"precision floor {TAU:.0%}, must fire in >= {MIN_CRATES} crates, "
          f"{N_PERM} permutations per size\n")

    out = {"n_perm": N_PERM, "tau": TAU, "min_crates": MIN_CRATES, "sizes": {}}
    for size in SIZES:
        # A fixed random subset per size, so real and permuted runs see the same
        # features and the only difference is the labels.
        cols = (all_cols if size >= len(all_cols)
                else list(rng.choice(all_cols, size=size, replace=False)))
        t0 = time.time()
        real = best_rule(df, y, cols)
        print(f"── {size} features ({real['n_atoms']} atoms)")
        print(f"   REAL   recall {real['recall']:>7.2%}  precision "
              f"{real['precision']:>6.1%}   {real['expr']}")

        nulls = []
        for i in range(N_PERM):
            yp = shuffle_within_crate(y, crates, rng)
            n = best_rule(df, yp, cols)
            nulls.append(n)
            print(f"   null {i+1}/{N_PERM}  recall {n['recall']:>7.2%}  "
                  f"precision {n['precision']:>6.1%}"
                  + ("" if n["found"] else "   (nothing qualified)"), flush=True)
        rec = np.array([n["recall"] for n in nulls])
        found = sum(1 for n in nulls if n["found"])
        # One-sided permutation p: how often does noise match or beat the real rule?
        pval = (1 + int((rec >= real["recall"]).sum())) / (1 + len(rec))
        print(f"   noise floor: {found}/{N_PERM} permutations produced any qualifying "
              f"rule; best-recall mean {rec.mean():.3%}, max {rec.max():.3%}")
        print(f"   real / noise-max ratio {real['recall']/max(rec.max(),1e-9):>6.1f}x"
              f"   permutation p = {pval:.3f}   ({time.time()-t0:.0f}s)\n")
        out["sizes"][str(size)] = {
            "n_features": len(cols), "n_atoms": real["n_atoms"],
            "real": real,
            "null_found": found,
            "null_recall_mean": float(rec.mean()), "null_recall_max": float(rec.max()),
            "null_recall_all": [float(v) for v in rec],
            "permutation_p": pval,
            "features": list(cols) if size < len(all_cols) else "all",
        }

    print("── summary: does a bigger space inflate what noise can produce?")
    print(f"   {'features':>9}{'atoms':>8}{'real recall':>13}{'noise max':>11}"
          f"{'noise mean':>12}{'ratio':>8}{'perm p':>9}")
    for size in SIZES:
        s = out["sizes"][str(size)]
        print(f"   {s['n_features']:>9}{s['n_atoms']:>8}{s['real']['recall']:>12.2%}"
              f"{s['null_recall_max']:>11.3%}{s['null_recall_mean']:>12.3%}"
              f"{s['real']['recall']/max(s['null_recall_max'],1e-9):>7.1f}x"
              f"{s['permutation_p']:>9.3f}")
    json.dump(out, open(os.path.join(STUDY, "results", "d02_permutation.json"), "w"),
              indent=1, default=float)
    print("\nwrote results/d02_permutation.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

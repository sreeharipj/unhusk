#!/usr/bin/env python3
"""
D03 — is the invisible population even separable, in principle, from these
observables?

D01 asks how well a model does on the functions that carry no author `Location`.
This asks something stronger and cheaper: how much of that population is
*information-theoretically* out of reach, no matter what model or rule is used.

Method. Two functions with identical feature vectors cannot be told apart by any
predictor over those features. So: bucket the invisible population by its exact
feature vector (discretised, since floats are effectively unique otherwise) and
look at buckets containing both author and non-author functions. Within such a
bucket, the best any predictor can do is call the whole bucket by its majority
class, and the minority members are irreducible error. Summed over buckets, that
is a lower bound on the error rate of ANY rule or model built from these
features — a Bayes-error estimate.

Reported two ways:
  - over the CURRENT 91 features, discretised
  - over each feature family alone, to show which channel carries separating
    information at all in this population

Then the practical version of the same question: among invisible author
functions, how many share their exact discretised vector with at least one
non-author function? Those are the ones a new feature would have to break apart,
and their count bounds what any expansion of the feature set could win.

Cheap, exact, and it does not involve fitting anything.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDY, "lib"))
import protocol as P  # noqa: E402


def discretise(df, cols):
    """Integer features kept as-is (capped, since tails are sparse); continuous
    features cut into deciles. Discretisation only ever MERGES rows, so the
    resulting collision count is a lower bound on true collisions and therefore
    a conservative (optimistic-for-the-features) estimate of Bayes error."""
    out = {}
    for c in cols:
        v = df[c].to_numpy()
        if v.dtype.kind in "iu" or np.allclose(v, np.round(v)):
            out[c] = np.clip(v, -1, 32).astype(np.int16)
        else:
            try:
                out[c] = pd.qcut(v, 10, labels=False, duplicates="drop").astype(np.int16)
            except ValueError:
                out[c] = np.zeros(len(v), np.int16)
    return pd.DataFrame(out)


def bayes_bound(D, y):
    """Minimum achievable error over these features: sum over collision buckets of
    the minority-class count, divided by n. Also returns the achievable precision
    at full recall on the majority-author buckets."""
    key = pd.util.hash_pandas_object(D, index=False)
    g = pd.DataFrame({"k": key.to_numpy(), "y": y})
    agg = g.groupby("k").y.agg(["sum", "count"])
    pos, n = agg["sum"].to_numpy(), agg["count"].to_numpy()
    neg = n - pos
    minority = np.minimum(pos, neg)
    n_buckets = len(agg)
    mixed = int(((pos > 0) & (neg > 0)).sum())
    pos_in_mixed = int(pos[(pos > 0) & (neg > 0)].sum())
    return {
        "n_rows": int(len(y)), "n_positive": int(y.sum()),
        "n_buckets": n_buckets,
        "n_mixed_buckets": mixed,
        "bayes_error_lower_bound": float(minority.sum() / len(y)),
        "positives_in_mixed_buckets": pos_in_mixed,
        "frac_positives_contaminated": float(pos_in_mixed / max(int(y.sum()), 1)),
        # Purely-positive buckets: the part reachable at 100% precision in principle.
        "positives_in_pure_buckets": int(pos[(neg == 0)].sum()),
        "frac_positives_pure": float(pos[(neg == 0)].sum() / max(int(y.sum()), 1)),
    }


def main():
    df = P.load("dev")
    y = P.target(df, "ws")
    cols = P.feature_cols(df)
    inv = (df["M_rel_structs"].to_numpy() == 0)

    out = {}
    print(f"dev {len(df):,} rows, {len(cols)} features\n")

    for name, sel in (("whole population", np.ones(len(df), bool)),
                      ("invisible (no author Location)", inv),
                      ("anchor-bearing", ~inv)):
        sub = df[sel]
        D = discretise(sub, cols)
        r = bayes_bound(D, y[sel])
        out[name] = r
        print(f"── {name}: {r['n_rows']:,} rows, {r['n_positive']:,} author")
        print(f"     distinct feature vectors      {r['n_buckets']:,}")
        print(f"     vectors holding both classes  {r['n_mixed_buckets']:,}")
        print(f"     author functions sharing a vector with a non-author: "
              f"{r['positives_in_mixed_buckets']:,} ({r['frac_positives_contaminated']:.1%})")
        print(f"     author functions in a PURE vector (reachable at 100% precision): "
              f"{r['positives_in_pure_buckets']:,} ({r['frac_positives_pure']:.1%})")
        print(f"     Bayes error lower bound        {r['bayes_error_lower_bound']:.4%}\n")

    print("── which family carries separating information in the invisible population")
    print(f"   {'family':<8}{'n feat':>8}{'pure positives':>16}{'% of invisible authors':>24}")
    fam_res = {}
    sub = df[inv]
    yy = y[inv]
    for fam in sorted(P.FEATURE_FAMILIES):
        fc = [c for c in cols if c.startswith(fam + "_")]
        if not fc:
            continue
        r = bayes_bound(discretise(sub, fc), yy)
        fam_res[fam] = r
        print(f"   {fam:<8}{len(fc):>8}{r['positives_in_pure_buckets']:>16,}"
              f"{r['frac_positives_pure']:>23.1%}")
    out["invisible_by_family"] = fam_res

    # ── The bound above is VACUOUS in high dimensions, and saying so is the point.
    # With 91 features over 1.6M rows almost every row has a unique vector
    # (1,122,298 distinct vectors for 1,620,673 rows), so "no non-author function
    # shares this vector" means the row is MEMORISABLE, not that it is separable
    # by anything that generalises. The family breakdown above tracks feature
    # cardinality, not information. The honest version restricts to a handful of
    # coarsely binned features, where collisions are forced and the bound means
    # something; and the generalising answer is D01's held-out model, not this.
    print("\n── the same bound at low dimension, where it is not vacuous")
    print(f"   {'features':<44}{'cells':>8}{'mixed':>8}{'Bayes err':>11}{'pure pos':>10}")
    low = {}
    PROBES = [
        ("N_win_rel, N_dist_rel (3 bins each)", ["N_win_rel", "N_dist_rel"], 3),
        ("+ X_caller_rel", ["N_win_rel", "N_dist_rel", "X_caller_rel"], 3),
        ("+ G_n_insn, G_size", ["N_win_rel", "N_dist_rel", "X_caller_rel",
                                "G_n_insn", "G_size"], 3),
        ("5 features, 5 bins each", ["N_win_rel", "N_dist_rel", "X_caller_rel",
                                     "G_n_insn", "G_size"], 5),
    ]
    subv = df[inv]
    yv = y[inv]
    for label, fc, nb in PROBES:
        fc = [c for c in fc if c in cols]
        Dl = pd.DataFrame({c: pd.qcut(subv[c].rank(method="first"), nb,
                                      labels=False, duplicates="drop").astype(np.int16)
                           for c in fc})
        r = bayes_bound(Dl, yv)
        low[label] = r
        print(f"   {label:<44}{r['n_buckets']:>8,}{r['n_mixed_buckets']:>8,}"
              f"{r['bayes_error_lower_bound']:>10.2%}{r['frac_positives_pure']:>9.1%}")
    out["low_dimensional_probes"] = low
    out["_caveat"] = ("The high-dimensional bound is vacuous: with 91 features "
                      "nearly every row is unique, so the 'pure vector' fraction "
                      "measures cardinality rather than separability. Use D01's "
                      "held-out model for the generalising answer, and the "
                      "low-dimensional probes here for a meaningful bound.")

    inv_all = out["invisible (no author Location)"]
    print(f"\n── what a new feature would have to do (read with the caveat above)")
    print(f"   Invisible author functions: {inv_all['n_positive']:,}")
    print(f"   Already in a pure feature vector: {inv_all['positives_in_pure_buckets']:,} "
          f"({inv_all['frac_positives_pure']:.1%}) — separable in principle today")
    print(f"   Sharing a vector with a non-author: "
          f"{inv_all['positives_in_mixed_buckets']:,} "
          f"({inv_all['frac_positives_contaminated']:.1%}) — a new feature must split these")
    print(f"   Those {inv_all['positives_in_mixed_buckets']:,} functions are "
          f"{100*inv_all['positives_in_mixed_buckets']/int(y.sum()):.1f}% of all author "
          f"functions in the development set,")
    print(f"   which is the ceiling on what ANY new feature could add to overall recall.")

    json.dump(out, open(os.path.join(STUDY, "results", "d03_separability.json"), "w"),
              indent=1, default=float)
    print("\nwrote results/d03_separability.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

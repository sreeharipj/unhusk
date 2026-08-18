#!/usr/bin/env python3
"""
E19 — the composite rule the scope condition implies. POST-HOC. Not validated.

§5.10 found that R3 wins by a wide margin on programs with many anchor-bearing
functions and loses on programs with few. The obvious move is a composite: pick
the rule per binary, using a quantity computable without any ground truth —
the number of functions in that binary referencing at least one relative-path
`Location`.

**This is post-hoc and must be read as such.** The threshold was chosen after
seeing V4's result, on the same data. It has no held-out validation of any kind
and it is NOT one of the three pre-registered proposals. It is computed here so
that the idea is on the record with numbers attached, as a hypothesis for a
future study with its own sealed split — not as a result.

Reported on every corpus, including the ones that motivated it, with that
contamination stated per row.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDY, "lib"))
import mining  # noqa: E402
import protocol as P  # noqa: E402

R3 = "M_rel_structs >= 1 AND N_win_rel >= 5"
A2 = "C_user >= 2 AND P_nonrel <= 0"
R1 = "M_rel_structs >= 2 AND N_win_rel >= 3"
THRESHOLDS = [10, 20, 30, 40, 60, 80]


def anchors_per_build(full):
    key = (full["crate"].astype(str) + "|" + full["config"].astype(str))
    return key.map(full.assign(k=key, a=full["M_rel_structs"] >= 1).groupby("k").a.sum())


def load_aux(d):
    files = sorted(f for f in os.listdir(d) if f.endswith(".parquet"))
    df = pd.concat((pd.read_parquet(os.path.join(d, f)) for f in files),
                   ignore_index=True, copy=False)
    for c in ("crate", "config", "label"):
        df[c] = df[c].astype(str)
    return df


def evaluate(name, full, contamination):
    keep = (~full["label"].isin(["NONE", "UNKNOWN"])).to_numpy()
    anch = anchors_per_build(full).to_numpy()
    df = full[keep].reset_index(drop=True)
    a = anch[keep]
    y = P.target(df, "ws")
    m_r3, m_a2, m_r1 = (mining.eval_expr(df, e) for e in (R3, A2, R1))

    print(f"\n=== {name}  ({len(df):,} functions, {df.crate.nunique()} crates)  "
          f"[{contamination}]")
    print(f"    {'strategy':<34}{'fires':>8}{'prec':>8}{'recall':>9}")
    rows = {}
    for label, mask in (("always A@2 (incumbent)", m_a2), ("always R1", m_r1),
                        ("always R3", m_r3)):
        s = P.score_binary(y, mask, df["crate"], bootstrap=False)
        print(f"    {label:<34}{s['predicted']:>8,}{s['precision']:>8.1%}{s['recall']:>9.2%}")
        rows[label] = {k: v for k, v in s.items() if k != "per_crate"}
    for t in THRESHOLDS:
        mask = np.where(a > t, m_r3, m_a2)
        s = P.score_binary(y, mask, df["crate"], bootstrap=False)
        label = f"R3 if anchors > {t}, else A@2"
        print(f"    {label:<34}{s['predicted']:>8,}{s['precision']:>8.1%}{s['recall']:>9.2%}")
        rows[label] = {k: v for k, v in s.items() if k != "per_crate"}
    return rows


def main():
    out = {"WARNING": "post-hoc; threshold chosen after seeing the V4 result; "
                      "no held-out validation; not a pre-registered proposal"}
    main_all = P.load("all", labeled_only=False)
    out["main: held-out crates"] = evaluate(
        "main corpus, held-out crates",
        main_all[main_all["crate"].isin(P.SPLIT["test"])].reset_index(drop=True),
        "lockbox already read once; this is a second, post-hoc use")
    out["main: development crates"] = evaluate(
        "main corpus, development crates",
        main_all[main_all["crate"].isin(P.SPLIT["dev"])].reset_index(drop=True),
        "in-sample")
    for name, d in (("V3 (codegen-units)", os.path.join(STUDY, "v3", "fde")),
                    ("V4 (fresh programs)", os.path.join(STUDY, "v4", "fde"))):
        if os.path.isdir(d) and os.listdir(d):
            out[name] = evaluate(name, load_aux(d),
                                 "MOTIVATED the threshold" if name.startswith("V4")
                                 else "not used to choose the threshold")
    json.dump(out, open(os.path.join(STUDY, "results", "e19_scope_rule.json"), "w"),
              indent=1, default=float)
    print("\nPOST-HOC. No held-out validation. Recorded as a hypothesis, not a result.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

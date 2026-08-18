#!/usr/bin/env python3
"""
E16 — the auxiliary corpora: a different build recipe, the codegen-units axis,
and programs this study never chose.

The rules are already frozen (`results/picks.json`, pre-registered before the
lockbox). Nothing here selects anything; these are the same fixed expressions
evaluated on more binaries, which is why running it after the lockbox is not a
second bite at the apple.

  V2  the same crates via realval's own build script (default release profile)
  V3  codegen-units 16 and 4, lto off and thin -- the axis the 344-build matrix
      pinned at 1, and the configuration `cargo build --release` actually
      produces. This is the experiment most able to falsify the neighbourhood
      finding, because address-order locality IS a codegen-unit effect.
  V4  20 programs from winnow's pinned manifest that appear in no part of the
      43-crate corpus -- a sample fixed by someone else, for another purpose,
      before this study existed.

V2 and V3 overlap the development crates, so each is reported split into its
lockbox half and its development half and never pooled. V4 shares no crate with
anything, so it is reported whole.
"""
import json
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDY, "lib"))
import mining  # noqa: E402
import protocol as P  # noqa: E402


def load_dir(d):
    files = sorted(f for f in os.listdir(d) if f.endswith(".parquet"))
    if not files:
        return None
    df = pd.concat((pd.read_parquet(os.path.join(d, f)) for f in files),
                   ignore_index=True, copy=False)
    for c in ("crate", "config", "label", "gt_crate"):
        df[c] = df[c].astype(str)
    return df[~df["label"].isin(["NONE", "UNKNOWN"])].reset_index(drop=True)


def main():
    picks = json.load(open(os.path.join(STUDY, "results", "picks.json")))
    rules = [(r["short"], r["expr"]) for r in picks["rules"]]
    rules += [("A@2", b["expr"]) for b in picks["baselines"] if b.get("is_incumbent")]
    rules += [("bare>=2", "M_rel_structs >= 2"), ("any", "M_rel_structs >= 1")]

    corpora = {}
    for name, d in (("V2", os.path.join(STUDY, "v2", "fde")),
                    ("V3", os.path.join(STUDY, "v3", "fde")),
                    ("V4", os.path.join(STUDY, "v4", "fde"))):
        if os.path.isdir(d):
            df = load_dir(d)
            if df is not None and len(df):
                corpora[name] = df

    out = {}
    for name, df in corpora.items():
        y = P.target(df, "ws")
        print(f"\n=== {name}: {len(df):,} labelled functions, {df.crate.nunique()} crates, "
              f"{df.config.nunique()} configs, base rate {y.mean():.3%}")
        print(f"    configs: {', '.join(sorted(df.config.unique()))}")
        slices = {"all": df.index.to_numpy()}
        if name in ("V2", "V3"):
            lock = df["crate"].isin(P.SPLIT["test"]).to_numpy()
            dev = df["crate"].isin(P.SPLIT["dev"]).to_numpy()
            slices = {}
            if lock.any():
                slices["lockbox crates"] = lock.nonzero()[0]
            if dev.any():
                slices["dev crates (seen)"] = dev.nonzero()[0]
        out[name] = {"n": int(len(df)), "n_crates": int(df.crate.nunique()),
                     "configs": sorted(df.config.unique()), "base_rate": float(y.mean()),
                     "slices": {}}
        for sname, idx in slices.items():
            sub = df.iloc[idx]
            yy = y[idx]
            print(f"\n    -- {sname}: {len(sub):,} functions, {sub.crate.nunique()} crates, "
                  f"base rate {yy.mean():.3%}")
            print(f"       {'rule':<10}{'fires':>9}{'prec':>8}{'   prec 95% CI':>18}{'recall':>9}{'crates':>9}")
            rows = {}
            for short, expr in rules:
                pred = mining.eval_expr(sub, expr)
                s = P.score_binary(yy, pred, sub["crate"], bootstrap=True, iters=3000)
                lo, hi = s["precision_cluster_boot"]
                print(f"       {short:<10}{s['predicted']:>9,}{s['precision']:>8.1%}"
                      f"   [{lo:>5.1%},{hi:>6.1%}]{s['recall']:>9.2%}"
                      f"{s['n_crates_firing']:>5}/{sub.crate.nunique():<4}")
                rows[short] = {k: v for k, v in s.items() if k != "per_crate"}
                rows[short]["expr"] = expr
            out[name]["slices"][sname] = rows

        # For V3, the whole point is the per-config breakdown.
        if name == "V3" and df.config.nunique() > 1:
            print(f"\n    -- per codegen-units configuration")
            print(f"       {'config':<38}" + "".join(f"{s:>17}" for s, _ in rules[:4]))
            per = {}
            for cfg in sorted(df.config.unique()):
                sel = (df["config"] == cfg).to_numpy()
                cells, rec = [], {}
                for short, expr in rules[:4]:
                    pred = mining.eval_expr(df[sel], expr)
                    yy = y[sel]
                    tp, f = int((pred & yy).sum()), int(pred.sum())
                    p = tp / f if f else float("nan")
                    r = tp / int(yy.sum()) if yy.sum() else float("nan")
                    cells.append(f"{p:>8.1%}/{r:>7.2%}")
                    rec[short] = {"precision": p, "recall": r, "fires": f}
                print(f"       {cfg:<38}" + "".join(f"{c:>17}" for c in cells))
                per[cfg] = rec
            out[name]["per_config"] = per

    json.dump(out, open(os.path.join(STUDY, "results", "e16_aux_corpora.json"), "w"),
              indent=1, default=float)
    print(f"\nwrote results/e16_aux_corpora.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

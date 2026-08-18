#!/usr/bin/env python3
"""
mine.py — the rule search, parameterised by feature family so the same code and
the same protocol run over the incumbent's feature space and over this study's
wider one. Called by e02 (incumbent features) and e03 (everything).

Two stages, and the second is the one that matters:

  Stage 1  DISCOVERY. Exhaustive (or beam) search over the 28 development
           crates pooled, maximising recall subject to a precision floor.
           Produces the candidate rules a human then reads.

  Stage 2  NESTED VALIDATION OF THE PROCEDURE. For each development crate in
           turn, re-run the *entire* search on the other 27 and evaluate its
           winner on the held-out crate. This does not validate any particular
           rule; it estimates what a search of this shape yields on a program it
           has never seen, which is the number a reader should believe. The gap
           between stage 1 and stage 2 is the selection bias of the search
           itself, measured rather than assumed.

Neither stage touches the 15 lockbox crates.
"""
import argparse
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


def run_search(df, y, families, tau, min_crates, max_len, beam, max_thresholds,
               top_k=60, verbose=False):
    cols = P.feature_cols(df, families)
    space = mining.Bitspace(y, df["crate"].to_numpy())
    atoms = mining.make_atoms(df, cols, max_thresholds=max_thresholds)
    atoms = mining.dedupe_atoms(atoms, space)
    if verbose:
        print(f"    {len(cols)} features -> {len(atoms)} distinct atoms", flush=True)
    if beam:
        res = mining.beam_search(atoms, space, tau=tau, min_crates=min_crates,
                                 max_len=max_len, beam=beam, top_k=top_k, verbose=verbose)
    else:
        res, _ = mining.search_pairs(atoms, space, tau=tau, min_crates=min_crates,
                                     max_len=max_len, top_k=top_k,
                                     progress=(200 if verbose else None))
    return res, atoms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--families", default="C,P")
    ap.add_argument("--variant", default="ws")
    ap.add_argument("--tau", type=float, nargs="+", default=[0.90, 0.95, 0.99])
    ap.add_argument("--min-crates", type=int, default=8)
    ap.add_argument("--max-len", type=int, default=3)
    ap.add_argument("--beam", type=int, default=0)
    ap.add_argument("--max-thresholds", type=int, default=8)
    ap.add_argument("--nested", action="store_true")
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()

    families = args.families.split(",")
    df = P.load("dev")
    y = P.target(df, args.variant)
    print(f"{args.tag}: dev {len(df):,} rows, {df.crate.nunique()} crates, "
          f"families={families}, target={args.variant} (base {y.mean():.3%})\n")

    out = {"tag": args.tag, "families": families, "variant": args.variant,
           "max_len": args.max_len, "beam": args.beam, "min_crates": args.min_crates,
           "n_rows": int(len(df)), "n_crates": int(df.crate.nunique()), "stage1": {},
           "stage2": {}}

    for tau in args.tau:
        t0 = time.time()
        res, atoms = run_search(df, y, families, tau, args.min_crates, args.max_len,
                                args.beam, args.max_thresholds, verbose=True)
        print(f"  ── precision floor {tau:.0%}: {len(res)} qualifying rules "
              f"({time.time()-t0:.0f}s)")
        print(f"     {'recall':>7}{'prec':>8}{'fires':>9}{'crates':>7}  rule")
        for r in res[:args.top]:
            print(f"     {r['recall']:>7.2%}{r['precision']:>8.1%}{r['predicted']:>9,}"
                  f"{r['crates_firing']:>7}  {r['expr']}")
        out["stage1"][f"{tau}"] = res[:args.top * 2]
        print()

    if args.nested:
        print("  ── stage 2: nested leave-one-crate-out validation of the search itself")
        for tau in args.tau:
            rows = []
            for crate, tr, te in P.loco_folds(df):
                dtr, ytr = df[tr], y[tr]
                res, atoms = run_search(dtr, ytr, families, tau, max(args.min_crates - 1, 2),
                                        args.max_len, args.beam, args.max_thresholds, top_k=1)
                if not res:
                    rows.append({"crate": crate, "rule": None, "tp": 0, "predicted": 0,
                                 "n_pos": int(y[te].sum())})
                    continue
                expr = res[0]["expr"]
                pred = mining.eval_expr(df[te], expr)
                yy = y[te]
                rows.append({"crate": crate, "rule": expr,
                             "tp": int((pred & yy).sum()), "predicted": int(pred.sum()),
                             "n_pos": int(yy.sum()),
                             "insample_recall": res[0]["recall"],
                             "insample_precision": res[0]["precision"]})
            tp = sum(r["tp"] for r in rows)
            pr = sum(r["predicted"] for r in rows)
            po = sum(r["n_pos"] for r in rows)
            print(f"     tau={tau:.0%}  out-of-fold pooled precision "
                  f"{tp/pr if pr else float('nan'):.1%}  recall {tp/po if po else float('nan'):.2%} "
                  f" (in-sample mean precision "
                  f"{np.mean([r.get('insample_precision', np.nan) for r in rows]):.1%})")
            distinct = {}
            for r in rows:
                distinct[r["rule"]] = distinct.get(r["rule"], 0) + 1
            print(f"     search picked {len(distinct)} distinct rules across 28 folds; "
                  f"most common: {sorted(distinct.items(), key=lambda kv: -kv[1])[0]}")
            out["stage2"][f"{tau}"] = {"pooled_precision": tp / pr if pr else None,
                                       "pooled_recall": tp / po if po else None,
                                       "folds": rows}
    json.dump(out, open(os.path.join(STUDY, "results", f"{args.tag}.json"), "w"),
              indent=1, default=float)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

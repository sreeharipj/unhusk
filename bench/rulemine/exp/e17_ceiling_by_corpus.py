#!/usr/bin/env python3
"""
E17 — the recall ceiling is not one number; it moves with the build.

§5.1 derived a ceiling of 18.09% on the development set: the fraction of author
functions that reference at least one author `Location`, which bounds every rule
of the incumbent's shape. That number was quoted as though it were a property of
Rust. It is not — it is a property of Rust *plus a build configuration*, and it
moved as soon as the auxiliary corpora arrived (R3 reaches 24.23% recall on V3,
which would be impossible under an 18.09% ceiling).

This measures it everywhere, because the difference is itself a finding: how much
author panic evidence survives into the binary is an inlining question, and
inlining is exactly what `lto` and `codegen-units` control.
"""
import json
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDY, "lib"))
import protocol as P  # noqa: E402


def ceiling(df):
    y = P.target(df, "ws")
    has = (df["M_rel_structs"] >= 1).to_numpy()
    return {"n_author": int(y.sum()), "n_with_anchor": int((y & has).sum()),
            "ceiling": float((y & has).sum() / y.sum()) if y.sum() else float("nan"),
            "precision_of_any": float((y & has).sum() / has.sum()) if has.sum() else float("nan")}


def load_dir(d):
    files = sorted(f for f in os.listdir(d) if f.endswith(".parquet"))
    df = pd.concat((pd.read_parquet(os.path.join(d, f)) for f in files),
                   ignore_index=True, copy=False)
    for c in ("crate", "config", "label"):
        df[c] = df[c].astype(str)
    return df[~df["label"].isin(["NONE", "UNKNOWN"])].reset_index(drop=True)


def main():
    out = {}
    print(f"{'corpus / configuration':<46}{'author fns':>12}{'with anchor':>13}"
          f"{'CEILING':>10}{'prec of any':>13}")

    main_df = P.load("all", columns=["crate", "config", "label", "M_rel_structs"])
    for side, crates in (("main: development crates", P.SPLIT["dev"]),
                         ("main: held-out crates", P.SPLIT["test"])):
        sub = main_df[main_df["crate"].isin(crates)]
        c = ceiling(sub)
        print(f"{side:<46}{c['n_author']:>12,}{c['n_with_anchor']:>13,}"
              f"{c['ceiling']:>10.2%}{c['precision_of_any']:>13.1%}")
        out[side] = c

    print(f"\n{'main corpus, by build configuration':<46}")
    for cfg in sorted(main_df["config"].unique()):
        c = ceiling(main_df[main_df["config"] == cfg])
        print(f"  {cfg:<44}{c['n_author']:>12,}{c['n_with_anchor']:>13,}"
              f"{c['ceiling']:>10.2%}{c['precision_of_any']:>13.1%}")
        out[f"main/{cfg}"] = c

    for name, d in (("V2 (realval build script)", os.path.join(STUDY, "v2", "fde")),
                    ("V3 (codegen-units axis)", os.path.join(STUDY, "v3", "fde")),
                    ("V4 (fresh programs)", os.path.join(STUDY, "v4", "fde"))):
        if not (os.path.isdir(d) and os.listdir(d)):
            continue
        df = load_dir(d)
        print()
        c = ceiling(df)
        print(f"{name:<46}{c['n_author']:>12,}{c['n_with_anchor']:>13,}"
              f"{c['ceiling']:>10.2%}{c['precision_of_any']:>13.1%}")
        out[name] = c
        if df["config"].nunique() > 1:
            for cfg in sorted(df["config"].unique()):
                c = ceiling(df[df["config"] == cfg])
                print(f"  {cfg:<44}{c['n_author']:>12,}{c['n_with_anchor']:>13,}"
                      f"{c['ceiling']:>10.2%}{c['precision_of_any']:>13.1%}")
                out[f"{name}/{cfg}"] = c

    vals = [v["ceiling"] for k, v in out.items() if "/" in k]
    if vals:
        print(f"\nacross build configurations the ceiling ranges "
              f"{min(vals):.1%} to {max(vals):.1%} — a factor of {max(vals)/min(vals):.1f}.")
        out["_range"] = {"min": min(vals), "max": max(vals)}
    json.dump(out, open(os.path.join(STUDY, "results", "e17_ceiling_by_corpus.json"), "w"),
              indent=1, default=float)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

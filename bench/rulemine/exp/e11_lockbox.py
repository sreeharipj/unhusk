#!/usr/bin/env python3
"""
E11 — the lockbox. Read once.

Everything before this point ran on the 28 development crates. This script scores
the final proposed rules on the 15 crates sealed in `data/split.json`
(SHA-256 5bdc01f3...) before any model was fit, and on two auxiliary corpora that
test different things:

  TEST  15 held-out crates x 8 configs. Different PROGRAMS. The headline.
  V2    32 crates built by realval's own pipeline (default release profile).
        Different BUILD RECIPE. Reported split into its lockbox and development
        halves, never pooled, because the development half is contaminated.
  V3    the codegen-units axis (cgu=16/4, lto=off/thin) that the main matrix
        never varied, and which is the configuration cargo actually ships by
        default. This is the experiment most able to falsify the neighbourhood
        finding, since address-order locality is a codegen-unit effect.

Whatever this prints is what the report says, including if it is worse.
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

SPLIT = P.SPLIT


def load_aux(fde_dir):
    files = sorted(f for f in os.listdir(fde_dir) if f.endswith(".parquet"))
    df = pd.concat((pd.read_parquet(os.path.join(fde_dir, f)) for f in files),
                   ignore_index=True, copy=False)
    for c in ("crate", "config", "label", "gt_crate"):
        df[c] = df[c].astype(str)
    return df[~df["label"].isin(["NONE", "UNKNOWN"])].reset_index(drop=True)


def score(df, expr, tag):
    y = P.target(df, "ws")
    pred = mining.eval_expr(df, expr)
    s = P.score_binary(y, pred, df["crate"], bootstrap=True, iters=4000)
    s["tag"] = tag
    s["n_crates"] = int(df["crate"].nunique())
    return s


def line(tag, s, extra=""):
    lo, hi = s["precision_cluster_boot"]
    print(f"   {tag:<28}{s['predicted']:>8,}{s['precision']:>8.1%}"
          f"  [{lo:>5.1%},{hi:>6.1%}]{s['recall']:>9.2%}{s['n_crates_firing']:>4}/"
          f"{s['n_crates']:<4}{extra}")


def main():
    picks = json.load(open(os.path.join(STUDY, "results", "picks.json")))
    rules = picks["rules"] + picks.get("baselines", [])

    dev = P.load("dev")
    test = P.load("test")
    print(f"dev  {len(dev):,} rows / {dev.crate.nunique()} crates   "
          f"test {len(test):,} rows / {test.crate.nunique()} crates")
    print(f"base rate  dev {P.target(dev,'ws').mean():.3%}   "
          f"test {P.target(test,'ws').mean():.3%}\n")

    aux = {}
    for name, d in (("V2", os.path.join(STUDY, "v2", "fde")),
                    ("V3", os.path.join(STUDY, "v3", "fde"))):
        if os.path.isdir(d) and os.listdir(d):
            a = load_aux(d)
            aux[name] = a
            print(f"{name}: {len(a):,} rows, {a.crate.nunique()} crates, "
                  f"{a.config.nunique()} configs, base rate {P.target(a,'ws').mean():.3%}")
    print()

    out = {"picks": picks, "results": {}}
    for r in rules:
        expr, name = r["expr"], r["name"]
        print(f"── {name}")
        print(f"   {expr}")
        print(f"   {'corpus':<28}{'fires':>8}{'prec':>8}{'  prec 95% CI':>16}"
              f"{'recall':>9}{'crates':>10}")
        res = {}
        res["dev"] = score(dev, expr, "dev")
        line("dev (28 crates, seen)", res["dev"])
        res["test"] = score(test, expr, "test")
        drop = 100 * (res["test"]["precision"] - res["dev"]["precision"])
        line("TEST (15 crates, lockbox)", res["test"], f"  {drop:+.2f} pp vs dev")
        for name_aux, a in aux.items():
            lock = a[a["crate"].isin(SPLIT["test"])]
            devh = a[a["crate"].isin(SPLIT["dev"])]
            if len(lock):
                res[f"{name_aux}_test"] = score(lock, expr, f"{name_aux}_test")
                line(f"{name_aux} lockbox crates", res[f"{name_aux}_test"])
            if len(devh):
                res[f"{name_aux}_dev"] = score(devh, expr, f"{name_aux}_dev")
                line(f"{name_aux} dev crates (seen)", res[f"{name_aux}_dev"])
        out["results"][name] = {k: {kk: vv for kk, vv in v.items() if kk != "per_crate"}
                                for k, v in res.items()}
        out["results"][name]["per_crate_test"] = res["test"]["per_crate"]
        print()

    # Paired head-to-head against the incumbent on the lockbox only.
    base = next((r for r in rules if r.get("is_incumbent")), None)
    if base:
        print("── paired comparison on the LOCKBOX, 15 crates, vs the incumbent")
        b = score(test, base["expr"], "test")
        # The pre-registered family is the three proposals. Their p-values are
        # Holm-corrected as a family of three; the extra context rules are
        # reported but excluded from the correction family, because correcting
        # over rules that were never proposed would understate the proposals.
        family = [r for r in picks["rules"]]
        others = [r for r in rules if r["name"] not in {x["name"] for x in family}
                  and r["name"] != base["name"]]
        rows_f = []
        for r in family:
            s = score(test, r["expr"], "test")
            d, lo, hi = P.paired_crate_bootstrap(s["per_crate"], b["per_crate"],
                                                 "precision", iters=8000)
            pv = P.paired_crate_bootstrap_p(s["per_crate"], b["per_crate"],
                                            "precision", iters=8000)
            rows_f.append((r, s, d, lo, hi, pv))
        adj = P.holm([x[5] for x in rows_f])
        print(f"   {'rule':<34}{'precision delta':>26}{'recall delta':>16}"
              f"{'p':>9}{'Holm p':>9}")
        for (r, s, d, lo, hi, pv), pa in zip(rows_f, adj):
            dr = 100 * (s["recall"] - b["recall"])
            print(f"   {r['name'][:33]:<34}{d:>+9.2f} pp [{lo:+5.1f},{hi:+5.1f}]"
                  f"{dr:>+13.2f} pp{pv:>9.4f}{pa:>9.4f}"
                  f"{'  *' if pa < 0.05 else ''}")
            out["results"][r["name"]]["vs_incumbent_test"] = {
                "delta_precision_pp": d, "ci": [lo, hi], "delta_recall_pp": dr,
                "p_value": pv, "holm_adjusted_p": pa}
        if others:
            print(f"\n   context rules (NOT in the pre-registered family, uncorrected):")
            for r in others:
                s = score(test, r["expr"], "test")
                d, lo, hi = P.paired_crate_bootstrap(s["per_crate"], b["per_crate"],
                                                     "precision", iters=4000)
                dr = 100 * (s["recall"] - b["recall"])
                print(f"   {r['name'][:33]:<34}{d:>+9.2f} pp [{lo:+5.1f},{hi:+5.1f}]"
                      f"{dr:>+13.2f} pp")
                out["results"][r["name"]]["vs_incumbent_test"] = {
                    "delta_precision_pp": d, "ci": [lo, hi], "delta_recall_pp": dr}

    json.dump(out, open(os.path.join(STUDY, "results", "e11_lockbox.json"), "w"),
              indent=1, default=float)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

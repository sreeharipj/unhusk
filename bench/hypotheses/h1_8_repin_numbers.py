#!/usr/bin/env python3
"""
h1_8_repin_numbers.py -- re-pin of the ceiling and base-rate numbers.

SUPERSEDES h1_7_pin_numbers.py, which wrote results/pinned_numbers.json on
2026-08-20 (commit 2196133) in the middle of Phase 1. Three things landed after
it and none was in the file:

  a67539e  Phase 2.2  suppressing inlining crashes the ceiling
  9a12e87  Phase 2.1  the codegen-units confound, on all 43 matched crates
  624f034  Phase 3.2  the ceiling on PE for the first time
  7e14cd4  v5         a sealed 38-crate held-out corpus, 76 builds

The substantive problem with the old pin is not that it is out of date. It is
that bench/rulemine/data/fde is 344 builds at codegen-units=1, so the pinned
ceiling describes a configuration cargo does not ship. Per build_v5.sh, the
shipping default is cgu=16 / lto=false ("what `cargo build --release` does").
The ceiling moves with that setting -- h2.1 measured 22.586% -> 18.596% pooled
across 43 matched crates -- so a single pinned number was never well defined.

This re-pin therefore reports the ceiling three ways:

  corpora      per corpus and convention, as before (schema-compatible), + v5
  by_config    per corpus per config, so no configuration is averaged away
  matched_cgu  cgu=1 vs cgu=16 on an IDENTICAL crate set, within v4 and within
               v5. This is the only cgu contrast that controls the population;
               pooling across corpora would compare different crate sets.

Writes: results/pinned_numbers.json          (canonical; same path as before)
        bench/hypotheses/h1_8_output.md      (human-readable rendering)
"""
import glob
import json
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
STUDY = os.path.join(ROOT, "bench", "rulemine")
RESULTS_DIR = os.path.join(ROOT, "results")
sys.path.insert(0, os.path.join(STUDY, "lib"))
import protocol as P  # noqa: E402

# Config name -> codegen-units. main/'s 8 configs carry no cgu- prefix and are
# cgu=1 (bench/origin's matrix); v2-release is cargo's default release profile,
# which is cgu=16 / lto=false.
def cgu_of(config):
    if config.startswith("cgu-16"):
        return 16
    if config.startswith("cgu-4"):
        return 4
    if config == "v2-release":
        return 16
    return 1


CORPORA = {
    "main": os.path.join(STUDY, "data", "fde"),
    "V2": os.path.join(STUDY, "v2", "fde"),
    "V3": os.path.join(STUDY, "v3", "fde"),
    "V4": os.path.join(STUDY, "v4", "fde"),
    "V5": os.path.join(STUDY, "v5", "fde"),
}
CONVENTIONS = ("ws", "strict")


def load_dir(d):
    files = sorted(glob.glob(os.path.join(d, "*.parquet")))
    if not files:
        return None
    df = pd.concat((pd.read_parquet(f, columns=["crate", "config", "label", "M_rel_structs"])
                    for f in files), ignore_index=True, copy=False)
    for c in ("crate", "config", "label"):
        df[c] = df[c].astype(str)
    df = df[~df["label"].isin(["NONE", "UNKNOWN"])].reset_index(drop=True)
    df["cgu"] = df["config"].map(cgu_of)
    return df


def stats_for(df, convention):
    y = P.target(df, convention)
    has = (df["M_rel_structs"] >= 1).to_numpy()
    n_labeled, n_author = int(len(df)), int(y.sum())
    n_anchored = int((y & has).sum())
    return {
        "n_labeled_fdes": n_labeled,
        "n_author_fns": n_author,
        "n_anchored_author_fns": n_anchored,
        "base_rate": {"numerator": n_author, "denominator": n_labeled,
                      "pct": round(100 * n_author / n_labeled, 4) if n_labeled else None},
        "ceiling": {"numerator": n_anchored, "denominator": n_author,
                    "pct": round(100 * n_anchored / n_author, 4) if n_author else None},
    }


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    loaded = {name: load_dir(d) for name, d in CORPORA.items()}

    out = {
        "_meta": {
            "generated_by": "bench/hypotheses/h1_8_repin_numbers.py",
            "supersedes": "bench/hypotheses/h1_7_pin_numbers.py (commit 2196133, 2026-08-20)",
            "source": "bench/rulemine/{data,v2,v3,v4,v5}/fde",
            "definitions": {
                "base_rate": "n_author_fns / n_labeled_fdes (label not in {NONE,UNKNOWN})",
                "ceiling": "n_anchored_author_fns / n_author_fns, anchored = M_rel_structs>=1",
                "ws": "positives = label in {AUTHOR, WORKSPACE}",
                "strict": "positives = label == AUTHOR only",
                "cgu": "codegen-units; main's 8 configs are cgu=1, v2-release is cargo's "
                       "default release profile (cgu=16/lto=false)",
            },
            "reading_rules": [
                "The ceiling is not one number: it moves with codegen-units. Quote it "
                "with its cgu, or quote the matched contrast.",
                "cgu=16/lto=false is what `cargo build --release` does (build_v5.sh), so "
                "it is the figure that describes shipped binaries.",
                "Only matched_cgu compares cgu levels on an identical crate set. Do not "
                "compare a cgu=1 row in one corpus against a cgu=16 row in another.",
                "V5 is the sealed held-out corpus (7e14cd4); it is the strongest single "
                "source for a headline.",
            ],
        },
        "corpora": {},
        "by_config": {},
        "matched_cgu": {},
    }

    # --- corpora: schema-compatible with the old pin, plus V5 -----------------
    main_df = loaded["main"]
    sides = {
        "main/development": main_df[main_df["crate"].isin(P.SPLIT["dev"])],
        "main/held-out": main_df[main_df["crate"].isin(P.SPLIT["test"])],
        "main/all": main_df,
    }
    for name, df in sides.items():
        out["corpora"][name] = {c: stats_for(df, c) for c in CONVENTIONS}
    for name in ("V2", "V3", "V4", "V5"):
        df = loaded[name]
        out["corpora"][name] = ({c: stats_for(df, c) for c in CONVENTIONS}
                                if df is not None else {"missing": True})

    # --- by_config: nothing averaged away ------------------------------------
    for name, df in loaded.items():
        if df is None:
            continue
        out["by_config"][name] = {}
        for config, g in df.groupby("config", sort=True):
            out["by_config"][name][config] = {
                "cgu": int(g["cgu"].iloc[0]),
                "n_crates": int(g["crate"].nunique()),
                **{c: stats_for(g, c) for c in CONVENTIONS},
            }

    # --- matched_cgu: identical crate set, cgu=1 vs cgu=16 -------------------
    for name in ("V4", "V5"):
        df = loaded[name]
        if df is None:
            continue
        a = df[df["cgu"] == 1]
        b = df[df["cgu"] == 16]
        if a.empty or b.empty:
            continue
        shared = sorted(set(a["crate"]) & set(b["crate"]))
        a, b = a[a["crate"].isin(shared)], b[b["crate"].isin(shared)]
        entry = {"n_crates_matched": len(shared),
                 "config_cgu1": sorted(a["config"].unique()),
                 "config_cgu16": sorted(b["config"].unique())}
        for c in CONVENTIONS:
            sa, sb = stats_for(a, c), stats_for(b, c)
            entry[c] = {
                "cgu1": sa, "cgu16": sb,
                "ceiling_delta_pp": round(sb["ceiling"]["pct"] - sa["ceiling"]["pct"], 4),
            }
        out["matched_cgu"][name] = entry

    with open(os.path.join(RESULTS_DIR, "pinned_numbers.json"), "w") as fh:
        json.dump(out, fh, indent=2)

    L = ["# h1.8 -- RE-PINNED ceiling & base-rate numbers",
         "",
         "Supersedes h1.7 (`results/pinned_numbers.json`, commit 2196133, 2026-08-20).",
         "The old pin was computed on `data/fde` only, which is 344 builds at",
         "**codegen-units=1** -- a configuration cargo does not ship. It also predates V5.",
         "",
         "## 1. Per corpus (schema-compatible with the old pin, plus V5)",
         "",
         "| corpus | conv | base rate | (num/denom) | ceiling | (num/denom) |",
         "|---|---|---:|---|---:|---|"]
    for corpus, convs in out["corpora"].items():
        if convs.get("missing"):
            L.append(f"| {corpus} | -- | missing | -- | -- | -- |")
            continue
        for conv, s in convs.items():
            br, ce = s["base_rate"], s["ceiling"]
            L.append(f"| {corpus} | {conv} | {br['pct']}% | {br['numerator']}/{br['denominator']} "
                     f"| {ce['pct']}% | {ce['numerator']}/{ce['denominator']} |")

    L += ["", "## 2. Matched cgu contrast -- identical crate set within each corpus", "",
          "The only sound way to read the codegen-units effect: same crates, same corpus,",
          "cgu=1 vs cgu=16. cgu=16/lto=false is what `cargo build --release` does.", "",
          "| corpus | crates | conv | ceiling cgu=1 | ceiling cgu=16 | delta |",
          "|---|---:|---|---:|---:|---:|"]
    for name, e in out["matched_cgu"].items():
        for conv in CONVENTIONS:
            d = e[conv]
            L.append(f"| {name} | {e['n_crates_matched']} | {conv} | "
                     f"{d['cgu1']['ceiling']['pct']}% | {d['cgu16']['ceiling']['pct']}% | "
                     f"{d['ceiling_delta_pp']:+.2f}pp |")

    L += ["", "## 3. Per config -- nothing averaged away", "",
          "| corpus | config | cgu | crates | conv | base rate | ceiling |",
          "|---|---|---:|---:|---|---:|---:|"]
    for corpus, cfgs in out["by_config"].items():
        for config, s in cfgs.items():
            for conv in CONVENTIONS:
                L.append(f"| {corpus} | `{config}` | {s['cgu']} | {s['n_crates']} | {conv} "
                         f"| {s[conv]['base_rate']['pct']}% | {s[conv]['ceiling']['pct']}% |")

    with open(os.path.join(HERE, "h1_8_output.md"), "w") as fh:
        fh.write("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

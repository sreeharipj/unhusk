#!/usr/bin/env python3
"""
apply_rules.py — run the proposed rules on any stripped x86-64 ELF Rust binary.

This is the study's rules made usable. It deliberately reuses the *same* code
path the measurements ran through (`extractor` -> `lib/features.py` ->
the rule expression), rather than reimplementing the features, so that a number
produced here cannot drift from a number in REPORT.md.

  ./apply_rules.py BINARY [--rule R1|R2|R3|all] [--json OUT]

With no ground truth available (the normal case for a real sample) it reports
what each rule fires on: how many functions, at what addresses, and which author
source files those functions reference. That is exactly the input the downstream
YARA-X rule generator consumes, so the yield number is the operationally
meaningful one.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
from features import build_rows  # noqa: E402
from mining import eval_expr  # noqa: E402
from paths import p_class  # noqa: E402

EXTRACT = os.path.join(HERE, "extractor", "target", "release", "rulemine_extract")


def load_rules():
    picks = json.load(open(os.path.join(HERE, "results", "picks.json")))
    rules = {r["short"]: r for r in picks["rules"]}
    for b in picks["baselines"]:
        if b.get("is_incumbent"):
            rules["A@2"] = {"short": "A@2", "name": b["name"], "expr": b["expr"],
                            "plain": "the incumbent shipped rule"}
    for a in picks.get("additive", []):
        rules["R4"] = {"short": "R4", "name": a["name"], "expr": a["expr"],
                       "plain": a["plain"]}
    return rules


def analyse(binary):
    if not os.path.exists(EXTRACT):
        raise SystemExit(f"extractor not built: run `cd extractor && cargo build --release`")
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as fh:
        out = fh.name
    subprocess.run([EXTRACT, binary, "--crate-name", os.path.basename(binary),
                    "--config", "adhoc", "-o", out], check=True)
    raw = json.load(open(out))
    os.unlink(out)
    rows, meta = build_rows(raw, None)   # no ground truth: label column is "NONE"
    return pd.DataFrame(rows), raw, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("binary")
    ap.add_argument("--rule", default="all")
    ap.add_argument("--json")
    ap.add_argument("--max-list", type=int, default=12)
    args = ap.parse_args()

    rules = load_rules()
    df, raw, meta = analyse(args.binary)
    loc_by_id = {l["id"]: l for l in raw["locations"]}
    fn_locs = {f["s"]: f["locs"] for f in raw["functions"]}

    print(f"{args.binary}")
    print(f"  sha256      {raw['sha256']}")
    print(f"  arch        {raw['arch']}  pie={raw['is_pie']}  fde source: {raw['fde_source']}")
    print(f"  functions   {meta['n_fdes']:,}")
    print(f"  Locations   {meta['n_locations']:,}")
    print(f"  functions referencing >=1 relative-path Location: "
          f"{int((df['M_rel_structs'] >= 1).sum()):,}\n")

    report = {"binary": args.binary, "sha256": raw["sha256"],
              "n_functions": meta["n_fdes"], "n_locations": meta["n_locations"],
              "n_functions_with_author_location": int((df["M_rel_structs"] >= 1).sum()),
              "rules": {}}
    want = list(rules) if args.rule == "all" else [args.rule]
    for key in want:
        r = rules.get(key)
        if r is None:
            print(f"  unknown rule {key}"); continue
        mask = eval_expr(df, r["expr"])
        hits = df[mask]
        files = {}
        for s in hits["fn_start"]:
            for lid in fn_locs.get(int(s), []):
                f = loc_by_id[lid]["file"]
                # Use the study's taxonomy, not a bare "is it relative" test:
                # `library/std/src/io/mod.rs` is relative but is the standard
                # library, and must not be listed as author source.
                if p_class(f) == "REL":
                    files[f] = files.get(f, 0) + 1
        print(f"  {key}: {r['expr']}")
        print(f"     fires on {int(mask.sum()):,} of {len(df):,} functions "
              f"({mask.mean():.3%})")
        if len(files):
            top = sorted(files.items(), key=lambda kv: -kv[1])[:args.max_list]
            print(f"     author source files implicated ({len(files)}):")
            for f, c in top:
                print(f"        {c:>4}  {f}")
        if int(mask.sum()):
            addrs = [f"0x{int(a):x}" for a in hits["fn_start"][:args.max_list]]
            print(f"     addresses: {' '.join(addrs)}"
                  f"{' ...' if int(mask.sum()) > args.max_list else ''}")
        print()
        report["rules"][key] = {
            "expr": r["expr"], "n_fired": int(mask.sum()),
            "fraction": float(mask.mean()),
            "addresses": [int(a) for a in hits["fn_start"]],
            "author_files": files,
        }
    if args.json:
        json.dump(report, open(args.json, "w"), indent=1)
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

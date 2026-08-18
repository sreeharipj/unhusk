#!/usr/bin/env python3
"""
make_split.py — seal the corpus split BEFORE any modelling happens.

Why a sealed lockbox and not just cross-validation. This study runs many
model families, many feature sets and many thresholds over six hours. Even with
honest leave-one-crate-out cross-validation inside the development set, the
*choice* of what to report is made by a human (me) who has seen those CV
numbers, and that choice is itself a fit to the data. The only defence is a
partition that is fixed before any number is seen and read exactly once, at the
end, for the small number of rules actually proposed.

The split is by CRATE, never by function and never by build config, because:
  - two FDEs in the same crate come from the same source and are not
    independent draws;
  - the same function compiled under 8 configs appears 8 times, so splitting on
    (crate, config) would put near-identical rows on both sides — the classic
    leak that makes a binary-analysis result look far better than it is.

It is stratified on two axes: the corpus's own workload tag (async / generics /
workspace / depfree — the axis along which the incumbent tool's precision is
already known to vary) and AUTHOR-function count (the size axis), so neither
side ends up all-large or all-async.

Ratio: 2 development : 1 held-out test.
"""
import hashlib
import json
import os
import random

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SEED = 20260819

TAGS = {}
for line in open(os.path.join(ROOT, "bench", "origin", "corpus.tsv")):
    if line.startswith("#") or not line.strip():
        continue
    parts = line.rstrip("\n").split("\t")
    if len(parts) < 4 or parts[0] == "name":
        continue
    TAGS[parts[0].replace("-", "_")] = parts[3]


def stratum(crate):
    t = TAGS.get(crate, TAGS.get(crate.replace("_", "-"), ""))
    if "async" in t:
        return "ASYNC"
    if "generics" in t:
        return "GENERICS"
    if "workspace" in t:
        return "WORKSPACE"
    return "DEPFREE"


def main():
    b = pd.read_csv(os.path.join(HERE, "data", "builds.csv"))
    per = b.groupby("crate", as_index=False).agg(
        n_rows=("n_rows", "sum"), n_labeled=("n_labeled", "sum"),
        n_author=("n_author", "sum"), n_dep=("n_dep", "sum"),
        n_configs=("config", "nunique"))
    per["stratum"] = per["crate"].map(stratum)

    rng = random.Random(SEED)
    dev, test = [], []
    for s, g in per.groupby("stratum"):
        crates = list(g.sort_values("n_author", ascending=False)["crate"])
        # Walk size-ordered triples; one of every three goes to the lockbox, its
        # position inside the triple chosen at random so the assignment is not
        # a deterministic function of rank.
        for i in range(0, len(crates), 3):
            block = crates[i:i + 3]
            if len(block) == 1:
                (dev if rng.random() < 2 / 3 else test).append(block[0])
                continue
            pick = rng.randrange(len(block))
            for j, c in enumerate(block):
                (test if j == pick else dev).append(c)

    dev, test = sorted(dev), sorted(test)
    assert not set(dev) & set(test)
    assert set(dev) | set(test) == set(per["crate"])

    payload = {"seed": SEED, "ratio": "2 dev : 1 test", "unit": "crate",
               "stratified_on": ["workload tag", "AUTHOR-function count"],
               "dev": dev, "test": test}
    digest = hashlib.sha256(
        json.dumps({"dev": dev, "test": test}, sort_keys=True).encode()).hexdigest()
    payload["sha256"] = digest

    with open(os.path.join(HERE, "data", "split.json"), "w") as fh:
        json.dump(payload, fh, indent=1)

    per["side"] = per["crate"].apply(lambda c: "test" if c in set(test) else "dev")
    per.sort_values(["side", "stratum", "n_author"], ascending=[True, True, False]) \
       .to_csv(os.path.join(HERE, "data", "split_crates.csv"), index=False)

    print(f"SPLIT SHA-256 {digest}")
    print(f"dev  {len(dev):2d} crates: {' '.join(dev)}")
    print(f"test {len(test):2d} crates: {' '.join(test)}")
    print()
    bal = per.groupby(["side", "stratum"]).agg(
        crates=("crate", "count"), author=("n_author", "sum"),
        labeled=("n_labeled", "sum")).reset_index()
    bal["author_rate_pct"] = (100 * bal.author / bal.labeled).round(2)
    print(bal.to_string(index=False))
    print()
    tot = per.groupby("side").agg(crates=("crate", "count"), author=("n_author", "sum"),
                                  labeled=("n_labeled", "sum"))
    tot["author_rate_pct"] = (100 * tot.author / tot.labeled).round(3)
    print(tot.to_string())


if __name__ == "__main__":
    raise SystemExit(main())

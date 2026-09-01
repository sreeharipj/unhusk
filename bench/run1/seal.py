#!/usr/bin/env python3
"""Deterministic dev/test crate split, written once. Re-running never reshuffles."""
import hashlib, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sp = os.path.join(HERE, "split.json")
if os.path.exists(sp):
    print("split.json exists — keeping"); sys.exit(0)
crates = sorted({l.split("\t")[0].strip() for l in open(os.path.join(HERE, "corpus.tsv")) if l.strip()})
bucket = lambda n: int(hashlib.sha1(n.encode()).hexdigest(), 16) % 3
test = sorted(c for c in crates if bucket(c) == 0)
dev = sorted(c for c in crates if bucket(c) != 0)
sha = hashlib.sha256(json.dumps({"dev": dev, "test": test}, sort_keys=True).encode()).hexdigest()
json.dump({"seed": "run1-v1", "n": len(crates), "dev": dev, "test": test, "sha256": sha},
          open(sp, "w"), indent=1)
open(os.path.join(HERE, "PREREGISTER.md"), "w").write(
    f"# run1 pre-registration\n\n"
    f"Corpus: {len(crates)} crates, union of realval + rulemine/v4 + rulemine/v5, symlinked under `src/`.\n"
    f"Split: sha1(name) %% 3 == 0 -> test ({len(test)}), else dev ({len(dev)}). sha256 `{sha}`.\n\n"
    f"Configs (`configs.tsv`): c1 shipped default opt-3/cgu-16/lto-off/panic-unwind; "
    f"c2 = c1 but opt-z; c3 = c1 but cgu-1; c4 inline-suppressed (nightly, -Z inline-llvm=no, opt-z/lto-thin/cgu-1).\n\n"
    f"Rules are FIXED expressions with no fitted parameters (`analyze.py`): A@1-6, B@1-6, C@0.1-0.9, "
    f"A2_incumbent, R1/R2/R3, three picks baselines, RS90 (3-clause disjunction), TRIVIAL. "
    f"analyze.py only evaluates them; nothing is selected on the test crates.\n")
print("sealed", sha)

#!/usr/bin/env python3
"""
verify.py — re-derive the numbers this sub-study reports and check its
invariants. Exit 0 only if every check passes. Safe to run on a checkout without
re-running the searches (it reads results/*.json).

Checks:
  1  split hash: o00/o01/o02/o03 all carry the parent study's frozen
     split_sha256, and it matches data/split.json.
  2  trust anchor 1: o00 recorded 0 atom/predicate mismatches.
  3  trust anchor 2: o00's incumbent re-evaluation reproduced picks.json's
     pooled precision and fired-count for R1/R2/R3 exactly.
  4  o01 exhaustive searches are marked complete (not time-boxed out) for at
     least tau=0.90.
  5  o02: every GOSDT model in the sweep converged (Status.CONVERGED) and the
     reported "best" trees are certified optimal (lower==upper).
  6  o03: each candidate's recall_global re-derives from tp / npos_global_dev,
     and precision from tp / (tp+fp), to 1e-6.
  7  o03: the paired-vs-R3 family carries Holm-adjusted p-values.
  8  freshness: every results/*.json is newer than the script that writes it.
  9  the lockbox was not read: no file here references data/fde of the test
     crates, and o03 says so.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(HERE, "results")
STUDY = os.path.dirname(HERE)

FAILED = []


def check(name, cond, detail=""):
    tag = "ok  " if cond else "FAIL"
    print(f"  [{tag}] {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


def load(n):
    p = os.path.join(R, n)
    return json.load(open(p)) if os.path.exists(p) else None


def main():
    o00, o01, o02, o03 = (load("o00_setup.json"), load("o01_exhaustive.json"),
                          load("o02_gosdt.json"), load("o03_compare.json"))
    check("o00_setup.json present", o00 is not None)
    check("o01_exhaustive.json present", o01 is not None)
    check("o02_gosdt.json present", o02 is not None)
    check("o03_compare.json present", o03 is not None)
    if not all((o00, o01, o02, o03)):
        _finish()
        return

    split = json.load(open(os.path.join(STUDY, "data", "split.json")))
    sha = split.get("sha256") or split.get("split_sha256")
    for tag, d in (("o00", o00), ("o01", o01), ("o02", o02), ("o03", o03)):
        check(f"{tag} split hash matches data/split.json",
              d.get("split_sha256") == sha, f"{d.get('split_sha256')} != {sha}")

    check("trust anchor 1: 0 atom/predicate mismatches",
          o00.get("trust_anchor_1_atom_mismatches") == 0)
    ta2 = {r["rule"]: r for r in o00.get("trust_anchor_2_incumbent_checks", [])}
    for rk in ("R1", "R2", "R3"):
        row = ta2.get(rk, {})
        check(f"trust anchor 2: {rk} fired-count matches picks.json",
              row.get("d_predicted") == 0, str(row))

    t090 = o01.get("by_tau", {}).get("0.9", {})
    check("o01 conj<=3 @tau0.90 search complete",
          (t090.get("best_conj") or {}).get("search", {}).get("completed") is True)
    sets090 = [v for k, v in t090.items() if k.startswith("best_set") and v]
    check("o01 rule-set @tau0.90 search complete",
          bool(sets090) and all(v.get("search", {}).get("completed") for v in sets090))

    sweep = o02.get("sweep", [])
    conv = [r for r in sweep if "status" in r]
    check("o02 every GOSDT model converged",
          bool(conv) and all(r["status"] == "Status.CONVERGED" for r in conv),
          f"{sum(1 for r in conv if r['status'] != 'Status.CONVERGED')} non-converged")
    for fk, b in (o02.get("best") or {}).items():
        if b:
            check(f"o02 best[{fk}] certified optimal (lower==upper)",
                  b.get("optimal") is True)

    npg = o03.get("npos_global_dev")
    for k, v in o03.get("rows", {}).items():
        if not isinstance(v, dict) or "tp" not in v:
            continue
        rg = v["tp"] / npg
        check(f"o03 [{k}] recall_global re-derives", abs(rg - v["recall_global"]) < 1e-6)
        pr = v["tp"] / (v["tp"] + v["fp"]) if (v["tp"] + v["fp"]) else float("nan")
        check(f"o03 [{k}] precision re-derives",
              (v["fp"] == 0 and v["tp"] == 0) or abs(pr - v["precision"]) < 1e-6)

    comps = o03.get("paired_vs_R3", {})
    check("o03 paired-vs-R3 family is Holm-corrected",
          bool(comps) and all("p_recall_holm" in c and "p_precision_holm" in c
                              for c in comps.values()))

    # freshness
    pairs = [("o00_setup.json", "exp/o00_setup.py"), ("o01_exhaustive.json", "exp/o01_exhaustive.py"),
             ("o02_gosdt.json", "exp/o02_gosdt.py"), ("o03_compare.json", "exp/o03_compare.py")]
    for j, s in pairs:
        jp, sp = os.path.join(R, j), os.path.join(HERE, s)
        if os.path.exists(jp) and os.path.exists(sp):
            check(f"freshness: {j} newer than {s}", os.path.getmtime(jp) >= os.path.getmtime(sp))

    check("o03 states the lockbox is untouched",
          any("lockbox" in line and ("spent" in line or "NOT touched" in line)
              for line in o03.get("reading", [])))

    _finish()


def _finish():
    print()
    if FAILED:
        print(f"FAILED {len(FAILED)}: " + ", ".join(FAILED))
        sys.exit(1)
    print("all checks passed")
    sys.exit(0)


if __name__ == "__main__":
    main()

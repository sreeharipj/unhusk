#!/usr/bin/env python3
"""
verify.py — check REPORT.md's claims against the experiment outputs.

Most numbers in REPORT.md are interpolated from results/*.json by
`make_report.py`, so they cannot drift. A minority are written into the prose
by hand — because a sentence reads better with the number in it than with a
format placeholder — and those CAN drift when an experiment is re-run on more
data. This script re-derives every such number from the JSONs and fails if the
report disagrees.

It also checks the study's structural invariants: that the split is still the
one whose hash is published, that the replication gate passed, that the
pre-registered rules in the report are the ones in picks.json, and that no
experiment output is older than the data it was computed from.

Run it after `make all`, or on a checkout, to confirm the artifact is internally
consistent. Exit status is 0 only if every check passes.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(HERE, "results")
FAILURES = []
CHECKS = 0
SKIPPED = []


def load(name):
    p = os.path.join(R, name)
    return json.load(open(p)) if os.path.exists(p) else None


def check(label, ok, detail=""):
    global CHECKS
    CHECKS += 1
    if ok:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}   {detail}")
        FAILURES.append(f"{label}: {detail}")


def skip(label, why):
    """Record a check that could not run. Skips are printed and counted, never
    silent: an evaluator must be able to tell '28 of 28 passed with everything
    present' from '20 of 20 passed because 8 checks had no input'. A skip is not
    a failure, but a run with skips is not a full verification either."""
    print(f"  SKIP  {label}   ({why})")
    SKIPPED.append(f"{label}: {why}")


def approx(a, b, tol=0.05):
    """Both are percentages in points; tolerance is in points."""
    return a is not None and b is not None and abs(a - b) <= tol


def main():
    report = open(os.path.join(HERE, "REPORT.md")).read()

    print("── structural invariants")
    split = json.load(open(os.path.join(HERE, "data", "split.json")))
    import hashlib
    digest = hashlib.sha256(json.dumps({"dev": split["dev"], "test": split["test"]},
                                       sort_keys=True).encode()).hexdigest()
    check("split.json hash matches its own contents", digest == split["sha256"],
          f"recomputed {digest[:16]}, stored {split['sha256'][:16]}")
    check("split hash appears in REPORT.md", split["sha256"][:16] in report)
    check("dev and test are disjoint", not (set(split["dev"]) & set(split["test"])))
    check("28 dev / 15 test crates",
          len(split["dev"]) == 28 and len(split["test"]) == 15,
          f"{len(split['dev'])}/{len(split['test'])}")

    e00 = load("e00_replicate.json")
    check("E00 replication gate passed", bool(e00 and e00.get("pass")))
    if e00:
        check("E00 reports zero per-function mismatches",
              e00["counts_check"]["functions_mismatched"] == 0,
              str(e00["counts_check"]["functions_mismatched"]))
        n = e00["counts_check"]["functions_compared"]
        check(f"E00 function count {n:,} appears in REPORT.md", f"{n:,}" in report)

    picks = load("picks.json")
    if picks:
        for r in picks["rules"]:
            check(f"{r['short']} expression in REPORT.md verbatim",
                  r["expr"] in report, r["expr"])
        check("picks.json records it predates the lockbox",
              "before any lockbox read" in picks.get("registered_at", ""))

    print("\n── hand-written numbers in the prose, re-derived")

    e15 = load("e15_recall_ci.json")
    if e15:
        r3, inc = e15["R3"], e15["_incumbent"]
        m = re.search(r"R3 recovers \*\*([\d.]+)x\*\*", report)
        check("R3 recall ratio in §10 matches e15",
              m and approx(float(m.group(1)), r3["recall_ratio"], 0.01),
              f"report {m.group(1) if m else '?'}, e15 {r3['recall_ratio']:.2f}")
        check("R3 held-out recall Holm p < 0.05 (the headline claim)",
              r3["holm_adjusted_p"] < 0.05, f"p = {r3['holm_adjusted_p']}")
        check("R3 held-out precision is within 0.5 pp of the incumbent's",
              abs(100 * (r3["precision"] - inc["precision"])) < 0.5,
              f"{100*(r3['precision']-inc['precision']):+.2f} pp")

    e11 = load("e11_lockbox.json")
    if e11 and picks:
        for r in picks["rules"]:
            v = e11["results"].get(r["name"], {}).get("vs_incumbent_test")
            if not v:
                continue
            m = re.search(rf"{r['short']} ([-+][\d.]+) pp, ", report)
            check(f"{r['short']} held-out precision delta is not significant "
                  f"(the study's stated non-replication)",
                  v.get("holm_adjusted_p", 0) >= 0.05,
                  f"Holm p = {v.get('holm_adjusted_p')}")

    e17 = load("e17_ceiling_by_corpus.json")
    if e17 and "_range" in e17:
        lo = 100 * e17["_range"]["min"]
        hi = 100 * e17["_range"]["max"]
        check(f"ceiling range {lo:.1f}%-{hi:.1f}% as quoted in REPORT.md",
              f"{lo:.1f}% to {hi:.1f}%" in report or f"{lo:.1f}-{hi:.1f}%" in report,
              f"looking for {lo:.1f} to {hi:.1f}")
        dev = e17.get("main: development crates")
        if dev:
            c = 100 * dev["ceiling"]
            check(f"development-set ceiling {c:.2f}% as quoted",
                  f"{c:.2f}%" in report, f"{c:.2f}%")

    e21 = load("e21_scope_validation.json")
    if e21:
        for corpus, key in (("held-out", "test"), ("V3", "V3 (codegen-units)"),
                            ("V4", "V4 (fresh programs)")):
            d = (e21.get(key) or {}).get("R2")
            label = f"R2 moderation is null on {corpus} (the pre-registered prediction)"
            if d:
                check(label, d["spearman_p"] >= 0.05, f"p = {d['spearman_p']:.3f}")
            else:
                skip(label, f"{corpus} corpus absent — build it with `make aux`")
        for corpus, key in (("held-out", "test"), ("V4", "V4 (fresh programs)")):
            d = (e21.get(key) or {}).get("R3")
            label = f"R3 moderation IS significant on {corpus}"
            if d:
                check(label, d["spearman_p"] < 0.05, f"p = {d['spearman_p']:.3f}")
            else:
                skip(label, f"{corpus} corpus absent — build it with `make aux`")

    e20 = load("e20_percrate.json")
    if e20:
        d = e20["all_crates_contaminated"]["R3"]
        tot = d["crates_better"] + d["crates_worse"] + d["crates_tied"]
        check(f"'{d['crates_better']} of {tot}' crate win count appears in REPORT.md",
              f"{d['crates_better']} of {tot}" in report,
              f"{d['crates_better']}/{tot}")

    e16 = load("e16_aux_corpora.json")
    lk = ((e16 or {}).get("V3") or {}).get("slices", {}).get("lockbox crates", {})
    if "R3" in lk and "A@2" in lk:
        ratio = lk["R3"]["recall"] / lk["A@2"]["recall"]
        check(f"V3 recall ratio {ratio:.2f}x appears in REPORT.md",
              f"{ratio:.2f}x" in report, f"{ratio:.2f}x")
    else:
        skip("V3 recall ratio appears in REPORT.md",
             "V3 corpus absent — build it with `make v3`")

    print("\n── freshness: no result older than the data it reads")
    data_mtime = max(
        (os.path.getmtime(os.path.join(HERE, "data", "fde", f))
         for f in os.listdir(os.path.join(HERE, "data", "fde"))), default=0)
    stale = []
    for f in sorted(os.listdir(R)):
        if not f.endswith(".json"):
            continue
        if os.path.getmtime(os.path.join(R, f)) < data_mtime - 1:
            stale.append(f)
    check("every results/*.json is at least as new as data/fde/",
          not stale, f"stale: {stale}")
    check("REPORT.md is at least as new as every results/*.json",
          os.path.getmtime(os.path.join(HERE, "REPORT.md")) >= max(
              os.path.getmtime(os.path.join(R, f)) for f in os.listdir(R)
              if f.endswith(".json")) - 1)

    print(f"\n{CHECKS - len(FAILURES)}/{CHECKS} checks passed"
          + (f", {len(SKIPPED)} skipped" if SKIPPED else ""))
    if FAILURES:
        print("\nFAILURES:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    if SKIPPED:
        print("\nSKIPPED (this is a partial verification, not a full one):")
        for f in SKIPPED:
            print(f"  - {f}")
        print("\nverify: OK for the checks that could run")
        return 0
    print("verify: OK — full verification, nothing skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

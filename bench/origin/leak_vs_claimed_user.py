#!/usr/bin/env python3
"""
leak_vs_claimed_user.py — converts the pooled-over-all-FDEs leak rate (Task 1,
`inline_leak_incidence.py`) into a precision figure over the denominator that
actually decides usability: functions unhusk's SHIPPED classifier reports as
user-authored (STRONG + SINGLE tier), not all FDEs.

No rebuild, no new unhusk invocation over the whole corpus. `src/origin.rs`'s
`profile_functions` counts *distinct* user-class Location structs referenced
per FDE (`counts["user"]`, via a HashSet of struct_vaddr — see
`src/origin.rs:210-232`) over the exact same `xref::scan` `origin_probe`
already ran for every build. `src/report.rs`'s shipped tiering
(`user_anchor_count`, `report.rs:176`) counts the identical thing — distinct
user Locations directly xref'd to a function — over the same scan. The two
are the same count under a different classifier's User definition, and on a
source-built corpus (this one; no cargo-install path promotion in play) the
origin/shipped User classifications agree on every genuine relative source
path. Empirically verified once, not assumed: `unhusk --json` run directly
against `build/ripgrep/lto-fat_opt-3_panic-unwind/rg.stripped` (an
already-built binary already on disk — not a rebuild) gives STRONG=147/
SINGLE=114; deriving from that same build's `probe.json` via
`counts["user"]>=2` / `==1` reproduces both sets exactly, 0 symmetric
difference. Default `min_anchors=2`, matching `docs/validation.md`'s and
`README.md`'s reported default.

"Claimed user" = STRONG ∪ SINGLE = counts["user"] >= 1 (this is also exactly
unhusk's shipped `Certain` set — see `architecture.md:61`, `src/classify.rs:6`).
A leak instance (Task 1) is by definition inside this set (leak requires
counts["user"]>=1 AND ground truth says DEP or STD) — so leak instances are
precisely the ground-truth false positives within the claimed-user
population. This script computes, per (crate, config) and pooled/crate-
averaged: TP (ground truth AUTHOR or WORKSPACE), FP (ground truth DEP or
STD — i.e. Task 1's leak instances), and precision = TP/(TP+FP), restricted
to STRONG-only, SINGLE-only, and STRONG+SINGLE combined.

Usage: python3 leak_vs_claimed_user.py [--pretty]
Writes leak_vs_claimed_user.json next to this script.
"""
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from rules import iterate_builds, load_build, non_user  # noqa: E402

BUILD_ROOT = os.path.join(HERE, "build")
MIN_ANCHORS = 2
TP_LABELS = {"AUTHOR", "WORKSPACE"}
FP_LABELS = {"DEP", "STD"}


def tier(counts):
    u = counts.get("user", 0)
    if u >= MIN_ANCHORS:
        return "STRONG"
    if u == 1:
        return "SINGLE"
    return None  # not claimed-user at all


def safe_div(a, b):
    return (a / b) if b else None


def main():
    per_crate = {}
    per_config = defaultdict(lambda: _blank())

    def _blank():
        return {t: {"tp": 0, "fp": 0, "fp_blind": 0} for t in ("STRONG", "SINGLE", "COMBINED")}

    covered = set()
    for crate, config_id, dest in iterate_builds(BUILD_ROOT):
        covered.add((crate, config_id))
        rows, probe, gt = load_build(dest)
        if crate not in per_crate:
            per_crate[crate] = _blank()

        for r in rows:
            t = tier(r["counts"])
            if t is None:
                continue
            actual = r["actual"]
            is_tp = actual in TP_LABELS
            is_fp = actual in FP_LABELS
            if not (is_tp or is_fp):
                continue  # UNKNOWN/CONFLICT/no-GT — excluded from precision, not silently counted as either
            blind = is_fp and non_user(r["counts"]) == 0
            for target in ({t, "COMBINED"}):
                d_c = per_crate[crate][target]
                d_g = per_config[config_id][target]
                if is_tp:
                    d_c["tp"] += 1
                    d_g["tp"] += 1
                else:
                    d_c["fp"] += 1
                    d_g["fp"] += 1
                    if blind:
                        d_c["fp_blind"] += 1
                        d_g["fp_blind"] += 1

    def summarize(d):
        out = {}
        for t in ("STRONG", "SINGLE", "COMBINED"):
            tp, fp, fp_blind = d[t]["tp"], d[t]["fp"], d[t]["fp_blind"]
            out[t] = {
                "tp": tp, "fp": fp, "fp_blind": fp_blind,
                "n": tp + fp,
                "precision": safe_div(tp, tp + fp),
                "leak_fraction": safe_div(fp, tp + fp),
                "blind_fraction_of_claimed_user": safe_div(fp_blind, tp + fp),
                "blind_fraction_of_fp": safe_div(fp_blind, fp),
            }
        return out

    per_crate_summary = {c: summarize(d) for c, d in per_crate.items()}
    per_config_summary = {cfg: summarize(d) for cfg, d in per_config.items()}

    pooled = _blank()
    for d in per_crate.values():
        for t in ("STRONG", "SINGLE", "COMBINED"):
            pooled[t]["tp"] += d[t]["tp"]
            pooled[t]["fp"] += d[t]["fp"]
            pooled[t]["fp_blind"] += d[t]["fp_blind"]
    pooled_summary = summarize(pooled)

    def crate_avg(key_t, key_metric):
        vals = [m[key_t][key_metric] for m in per_crate_summary.values() if m[key_t][key_metric] is not None]
        return sum(vals) / len(vals) if vals else None

    crate_averaged = {
        t: {
            "precision": crate_avg(t, "precision"),
            "leak_fraction": crate_avg(t, "leak_fraction"),
        }
        for t in ("STRONG", "SINGLE", "COMBINED")
    }

    out = {
        "min_anchors": MIN_ANCHORS,
        "n_crates": len(per_crate),
        "n_configs": len(per_config),
        "pooled": pooled_summary,
        "crate_averaged": crate_averaged,
        "per_crate": per_crate_summary,
        "per_config": per_config_summary,
    }

    with open(os.path.join(HERE, "leak_vs_claimed_user.json"), "w") as fh:
        if "--pretty" in sys.argv:
            json.dump(out, fh, indent=2)
        else:
            json.dump(out, fh)

    print(f"min_anchors={MIN_ANCHORS}, crates={len(per_crate)}, configs={len(per_config)}")
    for t in ("STRONG", "SINGLE", "COMBINED"):
        p = pooled_summary[t]
        print(f"\n=== {t} (pooled) ===")
        print(f"  tp={p['tp']} fp={p['fp']} n={p['n']} precision={p['precision']*100:.3f}%"
              if p['n'] else "  n=0")
        print(f"  leak_fraction={p['leak_fraction']*100:.3f}%  "
              f"blind/claimed_user={p['blind_fraction_of_claimed_user']*100:.3f}%  "
              f"blind/fp={p['blind_fraction_of_fp']*100:.3f}%" if p['n'] else "")
        ca = crate_averaged[t]
        print(f"  crate-averaged precision={ca['precision']*100:.3f}%  "
              f"crate-averaged leak_fraction={ca['leak_fraction']*100:.3f}%" if ca['precision'] is not None else "")

    print("\n=== worst 5 crates by COMBINED leak_fraction (n>=10) ===")
    ranked = sorted(
        ((c, m["COMBINED"]) for c, m in per_crate_summary.items() if m["COMBINED"]["n"] >= 10),
        key=lambda kv: -(kv[1]["leak_fraction"] or 0),
    )
    for c, m in ranked[:5]:
        print(f"  {c:16} fp={m['fp']:4}/n={m['n']:4}  leak_fraction={m['leak_fraction']*100:.2f}%  precision={m['precision']*100:.2f}%")


if __name__ == "__main__":
    main()

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
population. TP = ground truth AUTHOR or WORKSPACE (merged, matching
`realval`'s coarse authorship semantics). UNKNOWN = ground truth couldn't
resolve a label at all for this FDE (tracked separately, never folded
silently into TP or FP — see Task 5a in INLINE_LEAK_INCIDENCE.md for what
that means operationally).

Computed per (crate, config) individually (not just pooled per-crate or
per-config) so a single crate's config-by-config sensitivity is answerable
without a new script — see `per_crate_config` in the output.

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
TIERS = ("STRONG", "SINGLE", "COMBINED")


def tier(counts):
    u = counts.get("user", 0)
    if u >= MIN_ANCHORS:
        return "STRONG"
    if u == 1:
        return "SINGLE"
    return None  # not claimed-user at all


def safe_div(a, b):
    return (a / b) if b else None


def blank():
    return {t: {"tp": 0, "fp": 0, "fp_blind": 0, "unknown": 0} for t in TIERS}


def add(dst, t, key, n=1):
    dst[t][key] += n
    dst["COMBINED"][key] += n


def summarize(d):
    out = {}
    for t in TIERS:
        tp, fp, fp_blind, unk = d[t]["tp"], d[t]["fp"], d[t]["fp_blind"], d[t]["unknown"]
        n_known = tp + fp
        n_all = n_known + unk
        out[t] = {
            "tp": tp, "fp": fp, "fp_blind": fp_blind, "unknown": unk,
            "n_known": n_known, "n_all": n_all,
            "precision_known_only": safe_div(tp, n_known),
            "precision_ceiling_unknown_as_tp": safe_div(tp + unk, n_all),
            "precision_floor_unknown_as_fp": safe_div(tp, n_all),
            "leak_fraction": safe_div(fp, n_known),
            "blind_fraction_of_claimed_user": safe_div(fp_blind, n_known),
            "blind_fraction_of_fp": safe_div(fp_blind, fp),
        }
    return out


def main():
    per_crate = {}
    per_config = defaultdict(blank)
    per_crate_config = {}

    for crate, config_id, dest in iterate_builds(BUILD_ROOT):
        rows, probe, gt = load_build(dest)
        if crate not in per_crate:
            per_crate[crate] = blank()
        cc_key = f"{crate}/{config_id}"
        per_crate_config[cc_key] = blank()

        for r in rows:
            t = tier(r["counts"])
            if t is None:
                continue
            actual = r["actual"]
            is_tp = actual in TP_LABELS
            is_fp = actual in FP_LABELS
            targets = [per_crate[crate], per_config[config_id], per_crate_config[cc_key]]
            if is_tp:
                for d in targets:
                    add(d, t, "tp")
            elif is_fp:
                blind = non_user(r["counts"]) == 0
                for d in targets:
                    add(d, t, "fp")
                    if blind:
                        add(d, t, "fp_blind")
            else:
                # UNKNOWN / CONFLICT / no-GT-at-all — tracked, never dropped
                for d in targets:
                    add(d, t, "unknown")

    per_crate_summary = {c: summarize(d) for c, d in per_crate.items()}
    per_config_summary = {cfg: summarize(d) for cfg, d in per_config.items()}
    per_crate_config_summary = {k: summarize(d) for k, d in per_crate_config.items()}

    pooled = blank()
    for d in per_crate.values():
        for t in TIERS:
            for key in ("tp", "fp", "fp_blind", "unknown"):
                pooled[t][key] += d[t][key]
    pooled_summary = summarize(pooled)

    def crate_avg(key_t, key_metric):
        vals = [m[key_t][key_metric] for m in per_crate_summary.values() if m[key_t][key_metric] is not None]
        return sum(vals) / len(vals) if vals else None

    crate_averaged = {
        t: {
            "precision_known_only": crate_avg(t, "precision_known_only"),
            "leak_fraction": crate_avg(t, "leak_fraction"),
        }
        for t in TIERS
    }

    out = {
        "min_anchors": MIN_ANCHORS,
        "n_crates": len(per_crate),
        "n_configs": len(per_config),
        "pooled": pooled_summary,
        "crate_averaged": crate_averaged,
        "per_crate": per_crate_summary,
        "per_config": per_config_summary,
        "per_crate_config": per_crate_config_summary,
    }

    with open(os.path.join(HERE, "leak_vs_claimed_user.json"), "w") as fh:
        if "--pretty" in sys.argv:
            json.dump(out, fh, indent=2)
        else:
            json.dump(out, fh)

    print(f"min_anchors={MIN_ANCHORS}, crates={len(per_crate)}, configs={len(per_config)}")
    for t in TIERS:
        p = pooled_summary[t]
        print(f"\n=== {t} (pooled) ===")
        print(f"  tp={p['tp']} fp={p['fp']} unknown={p['unknown']} n_known={p['n_known']} n_all={p['n_all']}")
        print(f"  precision (known-only)   = {p['precision_known_only']*100:.3f}%")
        print(f"  precision ceiling (unk=TP) = {p['precision_ceiling_unknown_as_tp']*100:.3f}%")
        print(f"  precision floor   (unk=FP) = {p['precision_floor_unknown_as_fp']*100:.3f}%")

    print("\n=== per-config precision, COMBINED tier ===")
    for cfg, m in sorted(per_config_summary.items()):
        c = m["COMBINED"]
        print(f"  {cfg:30} tp={c['tp']:5} fp={c['fp']:4} n={c['n_known']:5} precision={c['precision_known_only']*100:.2f}%")

    print("\n=== worst 5 crates by COMBINED leak_fraction (n_known>=10) ===")
    ranked = sorted(
        ((c, m["COMBINED"]) for c, m in per_crate_summary.items() if m["COMBINED"]["n_known"] >= 10),
        key=lambda kv: -(kv[1]["leak_fraction"] or 0),
    )
    for c, m in ranked[:5]:
        print(f"  {c:16} fp={m['fp']:4}/n={m['n_known']:4}  leak_fraction={m['leak_fraction']*100:.2f}%  precision={m['precision_known_only']*100:.2f}%")


if __name__ == "__main__":
    main()

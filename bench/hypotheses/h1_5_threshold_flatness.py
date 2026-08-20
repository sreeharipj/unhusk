#!/usr/bin/env python3
"""
h1_5_threshold_flatness.py — Phase 1 / hypothesis 1.5.

Claim under test (bench/rulemine/REPORT.md:983, on the post-hoc scope-
condition cut point that decides "use R3 above this many anchor-bearing
functions in the binary, else A@2"): "the threshold is flat over 30-60 on
every corpus." A prior audit could not find a committed artifact backing
this sentence. This either produces the sweep or confirms it cannot be
produced.

Reuses bench/rulemine/lib/protocol.py and lib/mining.py UNCHANGED (read-only
imports, same evaluation protocol e19_scope_rule.py itself uses: crate-level
split, `ws` target convention, unbootstrapped precision/recall so a fine
50-point sweep is fast). Does NOT modify bench/rulemine/exp/e19_scope_rule.py
-- this is a new script under bench/hypotheses/ that asks a related but
distinct question: e19 reports the *composite* rule's precision/recall at 6
threshold values; this reports R3-ALONE's precision/recall advantage over
A@2-ALONE, restricted to binaries with more than `t` anchor-bearing
functions, at a fine sweep from t=10 to t=100, on held-out + V3 + V4 only
(dev is in-sample and is not part of what REPORT.md:983 or this task asks
about).

"Flat" is operationalised as: the RECALL ADVANTAGE (R3 recall - A@2 recall,
on the >t population) varies by less than 2 percentage points across every
adjacent pair of sweep points in [30,60] on a given corpus, and does not
change sign anywhere in that range.

Outputs: bench/hypotheses/h1_5_output.json, bench/hypotheses/h1_5_output.md,
bench/hypotheses/h1_5_sweep.png (matplotlib, if available)
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
STUDY = os.path.join(ROOT, "bench", "rulemine")
sys.path.insert(0, os.path.join(STUDY, "lib"))
import mining  # noqa: E402
import protocol as P  # noqa: E402

R3 = "M_rel_structs >= 1 AND N_win_rel >= 5"
A2 = "C_user >= 2 AND P_nonrel <= 0"
SWEEP = list(range(10, 101, 5))  # 10,15,...,100


def anchors_per_build(full):
    key = (full["crate"].astype(str) + "|" + full["config"].astype(str))
    return key.map(full.assign(k=key, a=full["M_rel_structs"] >= 1).groupby("k").a.sum())


def load_aux(d):
    files = sorted(f for f in os.listdir(d) if f.endswith(".parquet"))
    df = pd.concat((pd.read_parquet(os.path.join(d, f)) for f in files),
                   ignore_index=True, copy=False)
    for c in ("crate", "config", "label"):
        df[c] = df[c].astype(str)
    return df


def prf(y, pred):
    tp = int((y & pred).sum())
    pp = int(pred.sum())
    precision = tp / pp if pp else float("nan")
    recall = tp / y.sum() if y.sum() else float("nan")
    return precision, recall, pp


def sweep_corpus(name, full):
    keep = (~full["label"].isin(["NONE", "UNKNOWN"])).to_numpy()
    anch = anchors_per_build(full).to_numpy()
    df = full[keep].reset_index(drop=True)
    a = anch[keep]
    y = P.target(df, "ws")
    m_r3 = mining.eval_expr(df, R3)
    m_a2 = mining.eval_expr(df, A2)

    rows = []
    for t in SWEEP:
        pop = a > t
        if pop.sum() < 20:  # too few functions above this cut to mean anything
            rows.append({"t": t, "n_pop": int(pop.sum()), "skipped": True})
            continue
        yp, r3p, r3n = prf(y[pop], m_r3[pop])
        yp2, a2p, a2n = prf(y[pop], m_a2[pop])
        rows.append({
            "t": t, "n_pop": int(pop.sum()),
            "R3_precision": round(yp, 4), "R3_recall": round(r3p, 4), "R3_fires": r3n,
            "A2_precision": round(yp2, 4), "A2_recall": round(a2p, 4), "A2_fires": a2n,
            "recall_advantage_pp": round(100 * (r3p - a2p), 2),
            "precision_diff_pp": round(100 * (yp - yp2), 2),
        })
    return rows


def flatness_check(rows):
    band = [r for r in rows if 30 <= r["t"] <= 60 and not r.get("skipped")]
    if len(band) < 2:
        return {"verdict": "INSUFFICIENT_DATA", "n_points": len(band)}
    advs = [r["recall_advantage_pp"] for r in band]
    max_step = max(abs(advs[i + 1] - advs[i]) for i in range(len(advs) - 1))
    sign_changes = any((advs[i] > 0) != (advs[i + 1] > 0) for i in range(len(advs) - 1))
    span = max(advs) - min(advs)
    return {
        "verdict": "FLAT" if (max_step < 2.0 and not sign_changes) else "NOT_FLAT",
        "n_points": len(band), "max_adjacent_step_pp": round(max_step, 2),
        "span_pp": round(span, 2), "sign_changes": sign_changes,
        "advantages": advs,
    }


def main():
    out = {"header": {"sweep": SWEEP, "definition": "flat = adjacent-step < 2pp and no "
                       "sign change in recall-advantage, for t in [30,60]"}}
    corpora = {}
    corpora["held-out"] = P.load("test", labeled_only=False)
    v3_dir = os.path.join(STUDY, "v3", "fde")
    v4_dir = os.path.join(STUDY, "v4", "fde")
    if os.path.isdir(v3_dir) and os.listdir(v3_dir):
        corpora["V3"] = load_aux(v3_dir)
    else:
        out["header"]["V3_missing"] = True
    if os.path.isdir(v4_dir) and os.listdir(v4_dir):
        corpora["V4"] = load_aux(v4_dir)
    else:
        out["header"]["V4_missing"] = True

    results = {}
    for name, df in corpora.items():
        rows = sweep_corpus(name, df)
        results[name] = {"sweep": rows, "flatness": flatness_check(rows)}
    out["results"] = results

    with open(os.path.join(HERE, "h1_5_output.json"), "w") as fh:
        json.dump(out, fh, indent=2, default=float)

    lines = ["# h1.5 -- is the R3-vs-A@2 threshold really flat over 30-60?", ""]
    for name, r in results.items():
        lines.append(f"## {name}")
        lines.append("")
        lines.append("| t | n_pop | R3 prec | R3 recall | A@2 prec | A@2 recall | recall adv (pp) |")
        lines.append("|---:|---:|---:|---:|---:|---:|---:|")
        for row in r["sweep"]:
            if row.get("skipped"):
                lines.append(f"| {row['t']} | {row['n_pop']} | -- | -- | -- | -- | (too few, skipped) |")
                continue
            lines.append(f"| {row['t']} | {row['n_pop']} | {row['R3_precision']:.1%} | "
                         f"{row['R3_recall']:.1%} | {row['A2_precision']:.1%} | "
                         f"{row['A2_recall']:.1%} | {row['recall_advantage_pp']:+.2f} |")
        f = r["flatness"]
        lines.append("")
        lines.append(f"**Flatness over [30,60]: {f['verdict']}** "
                     f"(n={f.get('n_points')}, max adjacent step={f.get('max_adjacent_step_pp')}pp, "
                     f"span={f.get('span_pp')}pp, sign changes={f.get('sign_changes')})")
        lines.append("")

    with open(os.path.join(HERE, "h1_5_output.md"), "w") as fh:
        fh.write("\n".join(lines))
    print("\n".join(lines))

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(7, 4.5))
        for name, r in results.items():
            pts = [(row["t"], row["recall_advantage_pp"]) for row in r["sweep"] if not row.get("skipped")]
            if not pts:
                continue
            xs, ys = zip(*pts)
            ax.plot(xs, ys, marker="o", label=name)
        ax.axvspan(30, 60, alpha=0.15, color="gray", label="30-60 band")
        ax.axhline(0, color="black", linewidth=0.5)
        ax.set_xlabel("anchor-count threshold t")
        ax.set_ylabel("R3 recall - A@2 recall (pp), on binaries with anchors > t")
        ax.set_title("R3-vs-A@2 recall advantage vs threshold")
        ax.legend()
        fig.tight_layout()
        fig.savefig(os.path.join(HERE, "h1_5_sweep.png"), dpi=130)
        print("wrote h1_5_sweep.png")
    except Exception as e:
        print(f"plot skipped: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

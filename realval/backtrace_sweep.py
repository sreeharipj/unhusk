#!/usr/bin/env python3
"""
backtrace_sweep.py — Measure --backtrace-depth effect on the 13 real-world binaries.

Runs unhusk at backtrace depth 0 (off/baseline), 1, 2, and ∞ (9999) and
extracts precision/recall of the certain_by_backtrace bucket from DWARF
validation output.

Output: realval/BACKTRACE_SWEEP.md

Question: does backward-BFS from certain materially raise recall, at what
precision, and where should the backward walk be bounded?
"""

import subprocess, re, sys, statistics
from pathlib import Path

UNHUSK = Path(__file__).parent.parent / "target" / "release" / "unhusk"
OUT    = Path(__file__).parent / "out"
BINARIES = sorted(p.stem for p in OUT.glob("*.stripped"))

DEPTHS = [0, 1, 2, 9999]  # 0 = off/baseline; 9999 = effectively ∞


def run_validate(name: str, depth: int):
    stripped = OUT / f"{name}.stripped"
    debug    = OUT / f"{name}.debug"
    cmd = [str(UNHUSK), str(stripped), "--validate", str(debug),
           "--backtrace-depth", str(depth)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return result.stdout + result.stderr


def parse_metrics(output: str):
    """
    Returns a dict with:
      bt_n, bt_tp, bt_fp, bt_unk, bt_prec  — backtrace bucket metrics
      baseline_recall                        — certain+inferred overall recall (%)
      combined_recall                        — recall with backtrace (+backtrace line)
      recall_gain_pp                         — pp gain from backtrace
      backtrace_new_fns                      — new DWARF-user fns contributed
      certain_prec                           — certain bucket precision (%)
      certain_recall                         — certain bucket recall (%)
    """
    m = re.search(
        r'backtrace \(low-conf\)\s+(\d+) predicted\s+TP=\s*(\d+)\s+FP=\s*(\d+)'
        r'\s+unknown=\s*(\d+)\s+precision=([\d.]+)%',
        output,
    )
    if m:
        bt_n, bt_tp, bt_fp, bt_unk = int(m[1]), int(m[2]), int(m[3]), int(m[4])
        bt_prec = float(m[5])
    else:
        bt_n = bt_tp = bt_fp = bt_unk = 0
        bt_prec = float('nan')

    m2 = re.search(r'Overall recall\s*:\s*([\d.]+)%', output)
    baseline_recall = float(m2[1]) if m2 else float('nan')

    # "+backtrace     :    35  (50.0%)  (+4.3pp recall gain, 3 new fns)"
    m3 = re.search(
        r'\+backtrace\s+:\s+\d+\s+\(([\d.]+)%\)\s+\(\+([\d.]+)pp recall gain,\s+(\d+) new',
        output,
    )
    if m3:
        combined_recall   = float(m3[1])
        recall_gain_pp    = float(m3[2])
        backtrace_new_fns = int(m3[3])
    else:
        combined_recall   = baseline_recall
        recall_gain_pp    = 0.0
        backtrace_new_fns = 0

    m4 = re.search(r'Certain precision\s*:\s*([\d.]+)%', output)
    certain_prec = float(m4[1]) if m4 else float('nan')

    m5 = re.search(r'Certain recall\s*:\s*([\d.]+)%', output)
    certain_recall = float(m5[1]) if m5 else float('nan')

    return {
        "bt_n": bt_n, "bt_tp": bt_tp, "bt_fp": bt_fp, "bt_unk": bt_unk,
        "bt_prec": bt_prec,
        "baseline_recall": baseline_recall,
        "combined_recall": combined_recall,
        "recall_gain_pp": recall_gain_pp,
        "backtrace_new_fns": backtrace_new_fns,
        "certain_prec": certain_prec,
        "certain_recall": certain_recall,
    }


def depth_label(d: int) -> str:
    return "∞" if d >= 9999 else str(d)


# ── Run the sweep ─────────────────────────────────────────────────────────────

rows: dict[str, dict[str, dict]] = {}

for name in BINARIES:
    rows[name] = {}
    for depth in DEPTHS:
        label = depth_label(depth)
        sys.stderr.write(f"  {name} depth={label}...\n")
        out = run_validate(name, depth)
        rows[name][label] = parse_metrics(out)

# ── Build markdown ────────────────────────────────────────────────────────────

lines = []
lines.append("# Backward call-graph (backtrace) sweep — 13 real-world binaries")
lines.append("")
lines.append("**Question:** Does `--backtrace-depth N` materially raise recall, at what precision,")
lines.append("and where should the backward walk be bounded?")
lines.append("")
lines.append("Certain precision is constant across depths (backtrace only adds a separate bucket).")
lines.append("")
lines.append("## Per-binary results")
lines.append("")

for depth in [1, 2, 9999]:
    dl = depth_label(depth)
    lines.append(f"### depth={dl}")
    lines.append("")
    lines.append("| binary | certain | bt-n | bt-prec | bt-TP | baseline-recall | combined-recall | gain(pp) | new-fns |")
    lines.append("|--------|--------:|-----:|--------:|------:|----------------:|----------------:|---------:|--------:|")

    bt_n_sum = 0; bt_tp_sum = 0; bt_fp_sum = 0
    base_recalls = []; comb_recalls = []; gain_vals = []

    for name in BINARIES:
        d0 = rows[name]["0"]
        d  = rows[name][dl]
        cert_str = f"{d0['certain_prec']:.1f}%" if d0['certain_prec'] == d0['certain_prec'] else "n/a"
        bt_prec_str = f"{d['bt_prec']:.1f}%" if d['bt_prec'] == d['bt_prec'] else "n/a"
        base_str = f"{d['baseline_recall']:.1f}%" if d['baseline_recall'] == d['baseline_recall'] else "n/a"
        comb_str = f"{d['combined_recall']:.1f}%" if d['combined_recall'] == d['combined_recall'] else "n/a"
        gain_str = f"+{d['recall_gain_pp']:.1f}" if d['recall_gain_pp'] > 0 else "0.0"
        lines.append(
            f"| {name} | {cert_str}"
            f" | {d['bt_n']} | {bt_prec_str} | {d['bt_tp']}"
            f" | {base_str} | {comb_str} | {gain_str} | {d['backtrace_new_fns']} |"
        )
        bt_n_sum  += d['bt_n']
        bt_tp_sum += d['bt_tp']
        bt_fp_sum += d['bt_fp']
        if d['baseline_recall'] == d['baseline_recall']:
            base_recalls.append(d['baseline_recall'])
        if d['combined_recall'] == d['combined_recall']:
            comb_recalls.append(d['combined_recall'])
        gain_vals.append(d['recall_gain_pp'])

    agg_prec = 100.0 * bt_tp_sum / (bt_tp_sum + bt_fp_sum) if (bt_tp_sum + bt_fp_sum) > 0 else float('nan')
    med_base = statistics.median(base_recalls) if base_recalls else float('nan')
    med_comb = statistics.median(comb_recalls) if comb_recalls else float('nan')
    med_gain = statistics.median(gain_vals) if gain_vals else 0.0

    lines.append("")
    lines.append(
        f"**Pooled backtrace precision (depth={dl}): {agg_prec:.1f}%**"
        f"  (bt_n={bt_n_sum} total, TP={bt_tp_sum}, FP={bt_fp_sum})"
    )
    lines.append(
        f"Median baseline recall: {med_base:.1f}%  →  median combined recall: {med_comb:.1f}%"
        f"  (median gain: +{med_gain:.1f}pp)"
    )
    lines.append("")

# ── Combined summary table ─────────────────────────────────────────────────────

lines.append("## Summary: precision and recall gain by depth")
lines.append("")
lines.append("| depth | pooled-bt-prec | median-gain(pp) | median-base-recall | median-combined-recall |")
lines.append("|------:|---------------:|----------------:|-------------------:|-----------------------:|")

for depth in [1, 2, 9999]:
    dl = depth_label(depth)
    bt_tp_sum = 0; bt_fp_sum = 0
    base_recalls = []; comb_recalls = []; gain_vals = []
    for name in BINARIES:
        d = rows[name][dl]
        bt_tp_sum += d['bt_tp']; bt_fp_sum += d['bt_fp']
        if d['baseline_recall'] == d['baseline_recall']:
            base_recalls.append(d['baseline_recall'])
        if d['combined_recall'] == d['combined_recall']:
            comb_recalls.append(d['combined_recall'])
        gain_vals.append(d['recall_gain_pp'])
    agg_prec = 100.0 * bt_tp_sum / (bt_tp_sum + bt_fp_sum) if (bt_tp_sum + bt_fp_sum) > 0 else float('nan')
    med_base = statistics.median(base_recalls) if base_recalls else float('nan')
    med_comb = statistics.median(comb_recalls) if comb_recalls else float('nan')
    med_gain = statistics.median(gain_vals) if gain_vals else 0.0
    lines.append(
        f"| {dl} | {agg_prec:.1f}% | +{med_gain:.1f} | {med_base:.1f}% | {med_comb:.1f}% |"
    )

lines.append("")

# ── Bimodal split ─────────────────────────────────────────────────────────────

lines.append("## Bimodal split: which binaries gain at depth=1?")
lines.append("")
lines.append("| binary | gain(pp) | bt-prec | new-fns | verdict |")
lines.append("|--------|---------:|--------:|--------:|---------|")

GAIN_THRESHOLD_PP  = 1.0   # worth including
PREC_THRESHOLD_PCT = 30.0  # acceptable precision floor

for name in BINARIES:
    d = rows[name]["1"]
    gain = d['recall_gain_pp']
    prec = d['bt_prec']
    new  = d['backtrace_new_fns']
    prec_str = f"{prec:.1f}%" if prec == prec else "n/a"
    if gain >= GAIN_THRESHOLD_PP and (prec != prec or prec >= PREC_THRESHOLD_PCT):
        verdict = "✓ gain at acceptable prec"
    elif gain >= GAIN_THRESHOLD_PP and prec < PREC_THRESHOLD_PCT:
        verdict = "⚠ gain but low prec"
    elif gain < GAIN_THRESHOLD_PP:
        verdict = "– negligible gain"
    else:
        verdict = "?"
    lines.append(f"| {name} | +{gain:.1f} | {prec_str} | {new} | {verdict} |")

lines.append("")

# ── Skipped / failed ──────────────────────────────────────────────────────────

skipped = [n for n in BINARIES
           if rows[n]["1"]["baseline_recall"] != rows[n]["1"]["baseline_recall"]]
lines.append("## Skipped / failed builds")
lines.append("")
if skipped:
    for n in skipped:
        lines.append(f"- {n}: metrics unavailable (binary or DWARF validation failed)")
else:
    lines.append("None — all 13 binaries ran successfully.")
lines.append("")

# ── Verdict ───────────────────────────────────────────────────────────────────

lines.append("## Verdict")
lines.append("")
lines.append(
    "*(Fill in after reviewing the numbers above.)*  "
    "Key questions to answer:"
)
lines.append("")
lines.append(
    "1. Does backward-BFS materially raise recall (>1pp on median)?  "
    "At what precision?  "
    "Is the precision acceptable relative to inferred (~5%)?  "
)
lines.append(
    "2. At which depth is the precision/recall trade-off best?  "
    "Depth 1 vs. 2 vs. ∞?  "
)
lines.append(
    "3. Is there a bimodal split — some binaries get large gain, others get noise?  "
    "If so, what distinguishes the two groups (size, architecture, dep density)?  "
)

result_text = "\n".join(lines)
out_path = Path(__file__).parent / "BACKTRACE_SWEEP.md"
out_path.write_text(result_text)
print(result_text)
print(f"\nWritten to {out_path}", file=sys.stderr)

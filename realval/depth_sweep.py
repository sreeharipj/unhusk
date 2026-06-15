#!/usr/bin/env python3
"""
Measure --infer-depth effect on the 13 real-world binaries.
Runs unhusk at depth 0 (certain-only), 1, 2, and unlimited (None)
and extracts inferred precision/recall from DWARF validation output.

Output: depth_sweep_results.md in realval/
"""

import subprocess, re, sys
from pathlib import Path

UNHUSK = Path(__file__).parent.parent / "target" / "release" / "unhusk"
OUT    = Path(__file__).parent / "out"
BINARIES = sorted(p.stem for p in OUT.glob("*.stripped"))

DEPTHS = [None, 1, 2]  # None = unlimited

def run_validate(name: str, depth):
    stripped = OUT / f"{name}.stripped"
    debug    = OUT / f"{name}.debug"
    cmd = [str(UNHUSK), str(stripped), "--validate", str(debug)]
    if depth is not None:
        cmd += ["--infer-depth", str(depth)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return result.stdout + result.stderr

def parse_metrics(output: str):
    """Extract inferred TP, FP, unknown, precision; overall recall from output."""
    m = re.search(r"inferred\s+(\d+) predicted\s+TP=\s*(\d+)\s+FP=\s*(\d+)\s+unknown=\s*(\d+)\s+precision=([\d.]+)%", output)
    inf = {"n": 0, "tp": 0, "fp": 0, "unk": 0, "prec": 0.0}
    if m:
        inf = {"n": int(m[1]), "tp": int(m[2]), "fp": int(m[3]), "unk": int(m[4]), "prec": float(m[5])}

    m2 = re.search(r"Overall recall\s*:\s*([\d.]+)%", output)
    recall = float(m2[1]) if m2 else None

    m3 = re.search(r"Certain precision\s*:\s*([\d.]+)%", output)
    cert_prec = float(m3[1]) if m3 else None

    m4 = re.search(r"Certain recall\s*:\s*([\d.]+)%", output)
    cert_recall = float(m4[1]) if m4 else None

    return inf, recall, cert_prec, cert_recall

def depth_label(d):
    return f"d={d}" if d is not None else "d=∞"

rows = {}  # name -> {depth_label -> (inf, overall_recall, cert_prec)}

for name in BINARIES:
    rows[name] = {}
    for depth in DEPTHS:
        label = depth_label(depth)
        sys.stderr.write(f"  {name} {label}...\n")
        out = run_validate(name, depth)
        inf, overall_recall, cert_prec, cert_recall = parse_metrics(out)
        rows[name][label] = (inf, overall_recall, cert_prec, cert_recall)

# Print markdown table: for each binary, show (d=∞, d=1) side-by-side
lines = []
lines.append("# Depth-limit sweep on 13 real-world binaries")
lines.append("")
lines.append("**Question:** Does `--infer-depth 1` improve inferred precision on real binaries, and at what recall cost?")
lines.append("")
lines.append("Certain precision is constant across depths (depth only affects inferred BFS).")
lines.append("")
lines.append("| binary | cert-prec | inf-n(∞) | inf-prec(∞) | inf-n(1) | inf-prec(1) | delta-prec | inf-TP(∞) | inf-TP(1) | recall(∞) | recall(1) |")
lines.append("|--------|-----------|----------|-------------|----------|-------------|------------|-----------|-----------|-----------|-----------|")

inf_n_inf_sum  = 0; inf_tp_inf_sum = 0
inf_n_1_sum    = 0; inf_tp_1_sum   = 0
recall_inf_vals = []; recall_1_vals = []

for name in BINARIES:
    d_inf = rows[name]["d=∞"]
    d_1   = rows[name]["d=1"]
    inf_inf, rec_inf, cert_prec, _ = d_inf
    inf_1,   rec_1,  _,         _ = d_1

    delta = inf_1["prec"] - inf_inf["prec"]
    delta_str = f"{delta:+.1f}%"

    lines.append(
        f"| {name} | {cert_prec:.1f}% "
        f"| {inf_inf['n']} | {inf_inf['prec']:.1f}% "
        f"| {inf_1['n']} | {inf_1['prec']:.1f}% "
        f"| {delta_str} "
        f"| {inf_inf['tp']} | {inf_1['tp']} "
        f"| {rec_inf:.1f}% | {rec_1:.1f}% |"
    )
    inf_n_inf_sum  += inf_inf["n"];  inf_tp_inf_sum += inf_inf["tp"]
    inf_n_1_sum    += inf_1["n"];    inf_tp_1_sum   += inf_1["tp"]
    if rec_inf is not None: recall_inf_vals.append(rec_inf)
    if rec_1   is not None: recall_1_vals.append(rec_1)

# Aggregate precision
agg_prec_inf = 100.0 * inf_tp_inf_sum / inf_n_inf_sum if inf_n_inf_sum else 0.0
agg_prec_1   = 100.0 * inf_tp_1_sum   / inf_n_1_sum   if inf_n_1_sum   else 0.0
import statistics
med_rec_inf  = statistics.median(recall_inf_vals) if recall_inf_vals else 0
med_rec_1    = statistics.median(recall_1_vals)   if recall_1_vals   else 0

lines.append("")
lines.append(f"**Aggregate inferred precision (pooled): d=∞ {agg_prec_inf:.1f}%  →  d=1 {agg_prec_1:.1f}%**")
lines.append(f"Inferred count: d=∞ {inf_n_inf_sum} total, TP={inf_tp_inf_sum}  →  d=1 {inf_n_1_sum} total, TP={inf_tp_1_sum}")
lines.append(f"Median overall recall: d=∞ {med_rec_inf:.1f}%  →  d=1 {med_rec_1:.1f}%")
lines.append("")
lines.append("Depth 2 results:")
lines.append("")
lines.append("| binary | inf-n(2) | inf-prec(2) | inf-TP(2) | recall(2) |")
lines.append("|--------|----------|-------------|-----------|-----------|")
for name in BINARIES:
    d_2 = rows[name]["d=2"]
    inf_2, rec_2, _, _ = d_2
    lines.append(f"| {name} | {inf_2['n']} | {inf_2['prec']:.1f}% | {inf_2['tp']} | {rec_2:.1f}% |")

result_text = "\n".join(lines)
out_path = Path(__file__).parent / "DEPTH_SWEEP.md"
out_path.write_text(result_text)
print(result_text)
print(f"\nWritten to {out_path}")

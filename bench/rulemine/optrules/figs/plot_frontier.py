#!/usr/bin/env python3
"""
figs/plot_frontier.py — precision vs global-recall for the incumbent rules, the
GOSDT sweep, and the o01 rule sets, on tier-A dev. Writes frontier_light.png and
frontier_dark.png. Reads results/o02_gosdt.json and results/o03_compare.json.
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(os.path.dirname(HERE), "results")


def draw(dark):
    o02 = json.load(open(os.path.join(R, "o02_gosdt.json")))
    o03 = json.load(open(os.path.join(R, "o03_compare.json")))
    fg = "#e6e6e6" if dark else "#1a1a1a"
    bg = "#161616" if dark else "#ffffff"
    grid = "#333" if dark else "#ddd"
    acc = "#5ac8fa" if dark else "#0a7ea4"
    acc2 = "#ff9f0a" if dark else "#c85a00"

    fig, ax = plt.subplots(figsize=(7.2, 5.0))
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)

    sweep = [r for r in o02["sweep"] if r.get("recall_global") and r.get("precision")]
    tree = sorted([r for r in sweep if not r["rule_list"]], key=lambda r: r["recall_global"])
    lst = sorted([r for r in sweep if r["rule_list"]], key=lambda r: r["recall_global"])
    if tree:
        ax.plot([r["recall_global"] for r in tree], [r["precision"] for r in tree],
                "-o", ms=3, lw=1, color=acc, label="GOSDT trees (all CONVERGED)")
    if lst:
        ax.plot([r["recall_global"] for r in lst], [r["precision"] for r in lst],
                "-s", ms=3, lw=1, color=acc, alpha=0.45, label="GOSDT rule lists")

    rows = o03["rows"]
    for name, mark, col in [("R1", "^", fg), ("R2", "v", fg), ("A@2", "D", fg),
                            ("R3", "*", acc2)]:
        v = rows.get(name)
        if v:
            ax.scatter([v["recall_global"]], [v["precision"]], marker=mark, s=90,
                       color=col, zorder=5, edgecolor=bg, linewidth=0.6)
            ax.annotate(name, (v["recall_global"], v["precision"]),
                        textcoords="offset points", xytext=(6, 5), color=fg, fontsize=9)

    for name in [k for k in rows if k.startswith("o01 best_set")]:
        v = rows[name]
        ax.scatter([v["recall_global"]], [v["precision"]], marker="P", s=70,
                   color=acc2, zorder=5, edgecolor=bg, linewidth=0.6)

    nl = o02.get("nested_loco_best", {})
    b95 = (o02.get("best") or {}).get("floor_0.9067")
    if nl and b95:
        ax.annotate("", xy=(nl["held_pooled_recall_global"], nl["held_pooled_precision"]),
                    xytext=(b95["recall_global"], b95["precision"]),
                    arrowprops=dict(arrowstyle="->", color=acc2, lw=1.4))
        ax.scatter([nl["held_pooled_recall_global"]], [nl["held_pooled_precision"]],
                   marker="o", s=55, facecolor="none", edgecolor=acc2, zorder=6)
        ax.annotate("GOSDT best: dev -> nested-LOCO",
                    (nl["held_pooled_recall_global"], nl["held_pooled_precision"]),
                    textcoords="offset points", xytext=(4, -14), color=acc2, fontsize=8)

    ceil = o03.get("tierA_recall_ceiling", 0.181)
    ax.axvline(ceil, ls=":", color=grid, lw=1)
    ax.annotate(f"tier-A ceiling {ceil:.3f}", (ceil, 0.80), rotation=90,
                color=fg, fontsize=8, va="bottom", ha="right")

    ax.set_xlabel("global recall  (tp / all dev author functions)", color=fg)
    ax.set_ylabel("pooled precision", color=fg)
    ax.set_title("optrules — tier A, development set (28 crates)", color=fg, fontsize=11)
    ax.set_ylim(0.78, 1.0)
    ax.set_xlim(0, max(0.19, ceil + 0.01))
    ax.grid(True, color=grid, lw=0.5)
    for s in ax.spines.values():
        s.set_color(grid)
    ax.tick_params(colors=fg)
    leg = ax.legend(loc="lower left", fontsize=8, framealpha=0.2)
    for t in leg.get_texts():
        t.set_color(fg)
    fig.tight_layout()
    out = os.path.join(HERE, f"frontier_{'dark' if dark else 'light'}.png")
    fig.savefig(out, dpi=140, facecolor=bg)
    plt.close(fig)
    print("wrote", out)


if __name__ == "__main__":
    draw(False)
    draw(True)

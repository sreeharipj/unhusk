#!/usr/bin/env python3
"""
figs/plot_v5.py — the held-out result on one axis: R3 vs RS90 / RS925 / GOSDT_A
on dev and on v5, precision vs global recall, with the precision cluster-boot
interval drawn as a vertical bar. Reads results/o03_compare.json (dev) and
results/o04_v5_read.json (v5). Writes v5_{light,dark}.png.
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(os.path.dirname(HERE), "results")


def draw(dark):
    dev = json.load(open(os.path.join(R, "o03_compare.json")))["rows"]
    v5 = json.load(open(os.path.join(R, "o04_v5_read.json")))["rows"]
    fg = "#e6e6e6" if dark else "#1a1a1a"
    bg = "#161616" if dark else "#ffffff"
    grid = "#333" if dark else "#dcdcdc"
    cinc = "#8e8e93"
    cwin = "#5ac8fa" if dark else "#0a7ea4"

    fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.6), sharey=True)
    for ax, (title, rows, keymap) in zip(axes, [
        ("development (28 crates)", dev,
         {"R3": "R3", "RS90": "o01 best_set__clausefloor_tau @tau0.9",
          "RS925": "o01 best_set__clausefloor_tau @tau0.925",
          "GOSDT_A": "o02 GOSDT floor_0.9067"}),
        ("v5 held-out (38 crates)", v5,
         {"R3": "R3", "RS90": "RS90", "RS925": "RS925", "GOSDT_A": "GOSDT_A"}),
    ]):
        fig.patch.set_facecolor(bg)
        ax.set_facecolor(bg)
        for label, key in keymap.items():
            v = rows.get(key)
            if not v:
                continue
            x = v["recall_global"]
            p = v["precision"]
            ci = v.get("precision_cluster_boot") or [p, p]
            col = cinc if label == "R3" else cwin
            ax.plot([x, x], ci, color=col, lw=2.5, alpha=0.5, solid_capstyle="round")
            ax.scatter([x], [p], s=80, color=col, zorder=5,
                       edgecolor=bg, linewidth=0.6,
                       marker="*" if label == "R3" else ("P" if label.startswith("RS") else "o"))
            ax.annotate(label, (x, p), textcoords="offset points",
                        xytext=(7, 5), color=fg, fontsize=8.5)
        ax.set_title(title, color=fg, fontsize=10)
        ax.set_xlabel("global recall", color=fg)
        ax.grid(True, color=grid, lw=0.5)
        for s in ax.spines.values():
            s.set_color(grid)
        ax.tick_params(colors=fg)
        ax.set_xlim(0.05, 0.24)
    axes[0].set_ylabel("pooled precision  (bar = crate cluster bootstrap)", color=fg)
    axes[0].set_ylim(0.80, 0.98)
    fig.suptitle("R3 vs the certified disjunction — dev and held-out",
                 color=fg, fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    out = os.path.join(HERE, f"v5_{'dark' if dark else 'light'}.png")
    fig.savefig(out, dpi=140, facecolor=bg)
    plt.close(fig)
    print("wrote", out)


if __name__ == "__main__":
    draw(False)
    draw(True)

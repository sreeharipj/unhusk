#!/usr/bin/env python3
"""
plot_scope.py — the scope condition, which is what tells an analyst which rule to
reach for.

The frontier figure answers "which operating point"; this one answers "on which
binary". Each point is one crate: how many of its functions carry an author
`Location` at all (the anchor count, computable from a stripped binary with no
ground truth) against how much more author code the rule recovers than the
incumbent does. A rule whose advantage depends on anchor count slopes upward;
one that does not is flat.

Form: a scatter with a per-panel LOWESS-free trend summary (median in two bins)
rather than a fitted line, because the claim being made is monotone-and-ordinal
(it is tested with Spearman), and drawing an OLS line would assert a linearity
the statistics never claimed.

Colour: the same three categorical slots as the frontier figure, assigned to the
same entities — blue stays the incumbent's reference line at zero, orange is the
proposed rules. Panels are faceted by rule rather than by colour, so identity is
never colour-alone.
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDY, "lib"))

THEMES = {
    "light": dict(surface="#fcfcfb", ink="#0b0b0b", ink2="#52514e", muted="#9e9d95",
                  grid="#e6e5e0", s1="#2a78d6", s2="#eb6834", s3="#1baf7a"),
    "dark": dict(surface="#1a1a19", ink="#ffffff", ink2="#c3c2b7", muted="#6f6e66",
                 grid="#2e2e2c", s1="#3987e5", s2="#d95926", s3="#199e70"),
}

CORPORA = [("test", "held-out — 15 sealed crates"),
           ("V3 (codegen-units)", "V3 — codegen-units 4/16"),
           ("V4 (fresh programs)", "V4 — 40 fresh programs")]
RULES = ["R3", "R1", "R2"]
SUB = {"R3": "neighbourhood, threshold 1", "R1": "neighbourhood, threshold 2",
       "R2": "caller — a count, not a density"}


def main():
    e21 = json.load(open(os.path.join(STUDY, "results", "e21_scope_validation.json")))
    ranked = {r["crate"]: r for r in e21.get("held_out_ranked", [])}

    for theme, C in THEMES.items():
        fig, axes = plt.subplots(len(RULES), len(CORPORA), figsize=(13.6, 9.2),
                                 facecolor=C["surface"], sharex="col")
        for i, rule in enumerate(RULES):
            for j, (key, title) in enumerate(CORPORA):
                ax = axes[i][j]
                ax.set_facecolor(C["surface"])
                for s in ax.spines.values():
                    s.set_color(C["grid"])
                ax.tick_params(colors=C["ink2"], labelsize=8.5)
                ax.grid(True, color=C["grid"], linewidth=0.7, zorder=0)
                ax.set_axisbelow(True)
                d = (e21.get(key) or {}).get(rule)
                ax.axhline(0, color=C["s1"], lw=1.2, ls=(0, (4, 3)), zorder=2)
                ax.axvline(20, color=C["muted"], lw=1.0, ls=(0, (2, 3)), zorder=1)

                pts = (d or {}).get("points", [])
                if pts:
                    xs = np.array([q["anchors"] for q in pts], float)
                    ys = np.array([q["recall_delta_pp"] for q in pts], float)
                    ax.scatter(xs, ys, s=40, color=C["s2"], alpha=0.8, zorder=5,
                               edgecolors=C["surface"], linewidths=0.8)
                if d:
                    for side, x0, x1 in (("low", 1.4, 20), ("high", 20, 380)):
                        m = d[side]["median_pp"]
                        if m is None:
                            continue
                        ax.hlines(m, x0, x1, color=C["s3"], lw=2.8, zorder=6)
                        ax.text(x1 * 0.94 if side == "high" else x0 * 1.1, m,
                                f"{m:+.1f}", color=C["s3"], fontsize=8.4,
                                va="bottom", ha="right" if side == "high" else "left",
                                zorder=7)
                    sig = d["spearman_p"] < 0.05
                    ax.text(0.03, 0.045,
                            f"rho {d['spearman_r']:+.3f}   p {d['spearman_p']:.3f}"
                            + ("  *" if sig else ""),
                            transform=ax.transAxes, fontsize=8.6,
                            color=C["ink"] if sig else C["ink2"],
                            fontweight="bold" if sig else "normal", zorder=8)
                    ax.text(0.03, 0.915,
                            f"wins {d['low']['wins']}/{d['low']['n']}  below  |  "
                            f"{d['high']['wins']}/{d['high']['n']}  above",
                            transform=ax.transAxes, fontsize=8.2, color=C["ink2"],
                            zorder=8)
                ax.set_xscale("log")
                ax.set_xlim(1.4, 400)
                if i == 0:
                    ax.set_title(title, color=C["ink"], fontsize=10.5, loc="left", pad=7)
                if j == 0:
                    ax.set_ylabel(f"{rule} recall advantage (pp)\n{SUB[rule]}",
                                  color=C["ink2"], fontsize=9)
                if i == len(RULES) - 1:
                    ax.set_xlabel("anchor-bearing functions in the binary (log)",
                                  color=C["ink2"], fontsize=9)
        # One y-scale per row. The claim is comparative across corpora, and free
        # scales would let a +0.6 pp panel look identical to a +11 pp one.
        for i, rule in enumerate(RULES):
            vals = []
            for key, _ in CORPORA:
                for q in ((e21.get(key) or {}).get(rule) or {}).get("points", []):
                    vals.append(q["recall_delta_pp"])
            if not vals:
                continue
            lo, hi = min(vals), max(vals)
            pad = max(0.12 * (hi - lo), 0.5)
            for j in range(len(CORPORA)):
                axes[i][j].set_ylim(lo - pad, hi + pad * 1.35)
        axes[0][0].text(22, axes[0][0].get_ylim()[1] * 0.62,
                        "20 anchors —\nthe §2 threshold",
                        color=C["ink2"], fontsize=8.2, zorder=8)
        # Set x-limits last: annotations and hlines placed earlier can otherwise
        # expand them, and these panels share x by column.
        for row in axes:
            for ax in row:
                ax.set_xlim(1.4, 420)
        fig.suptitle("Which rule to use, and how to tell — rule advantage over the "
                     "incumbent against a binary's anchor count",
                     color=C["ink"], fontsize=12.5, x=0.006, ha="left", y=0.988)
        fig.text(0.006, 0.955,
                 "Each point is one crate. Green bars are the median advantage below "
                 "and above 20 anchors. Blue dashed line is the incumbent. "
                 "The two density rules slope up; the caller rule does not.",
                 color=C["ink2"], fontsize=9, ha="left")
        fig.tight_layout(rect=(0, 0, 1, 0.945))
        out = os.path.join(HERE, f"scope_{theme}.png")
        fig.savefig(out, dpi=165, facecolor=C["surface"])
        plt.close(fig)
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

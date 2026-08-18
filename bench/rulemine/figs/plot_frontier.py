#!/usr/bin/env python3
"""
plot_frontier.py — the precision/recall frontier, so the choice of rule can be
argued from a picture rather than asserted.

Three panels, in the order a reader needs them:

  a. the whole space          where the ceiling and the base rate are, and how
                              far an unconstrained model can go
  b. the deployable region    the incumbent family, every mined candidate, and
                              this study's proposals, on the DEVELOPMENT set --
                              i.e. where the search actually happened
  c. the held-out read        the same four rules on the 15 sealed crates, with
                              cluster-bootstrap intervals. This is the panel the
                              conclusion rests on, and it is separate precisely
                              because panel b is in-sample and panel c is not.

Colour: three categorical slots assigned by role and never cycled -- blue for
the incumbent family, orange for this study's proposals, aqua for the mined
rule set. The learned models are not categorical series but reference bounds,
so they are neutral ink, which also keeps them visually subordinate to the
rules. Aqua sits below 3:1 on the light surface, so it is direct-labelled
rather than legend-only.
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
                  grid="#e6e5e0", s1="#2a78d6", s2="#eb6834", s3="#1baf7a", bound="#52514e"),
    "dark": dict(surface="#1a1a19", ink="#ffffff", ink2="#c3c2b7", muted="#6f6e66",
                 grid="#2e2e2c", s1="#3987e5", s2="#d95926", s3="#199e70", bound="#c3c2b7"),
}


def pr_curve(y, score, max_points=1200):
    order = np.argsort(-score, kind="stable")
    ys = y[order]
    tp = np.cumsum(ys)
    fp = np.cumsum(~ys)
    prec = tp / np.maximum(tp + fp, 1)
    rec = tp / max(int(y.sum()), 1)
    keep = np.unique(np.linspace(0, len(prec) - 1, max_points).astype(int))
    return rec[keep], prec[keep]


def main():
    z = np.load(os.path.join(STUDY, "results", "e05_oof_scores.npz"), allow_pickle=True)
    y = z["y"].astype(bool)
    base = float(y.mean())
    e01 = json.load(open(os.path.join(STUDY, "results", "e01_baselines.json")))["ws"]
    picks = json.load(open(os.path.join(STUDY, "results", "picks.json")))
    p11 = os.path.join(STUDY, "results", "e11_lockbox.json")
    lock = json.load(open(p11)) if os.path.exists(p11) else None

    mined = []
    for tag in ("e03_full_pairs", "e02_incumbent"):
        p = os.path.join(STUDY, "results", f"{tag}.json")
        if os.path.exists(p):
            for rules in json.load(open(p))["stage1"].values():
                mined += [(r["recall"], r["precision"]) for r in rules]
    mined = np.array(mined) if mined else np.zeros((0, 2))

    for theme, C in THEMES.items():
        fig, axes = plt.subplots(1, 3, figsize=(17.4, 5.4), facecolor=C["surface"])
        for ax in axes:
            ax.set_facecolor(C["surface"])
            for s in ax.spines.values():
                s.set_color(C["grid"])
            ax.tick_params(colors=C["ink2"], labelsize=9)
            ax.grid(True, color=C["grid"], linewidth=0.7, zorder=0)
            ax.set_axisbelow(True)

        # ── a. the whole space ───────────────────────────────────────────────
        ax = axes[0]
        for name, alpha, ls in (("GB", 0.95, "-"), ("RF", 0.5, (0, (5, 2))),
                                ("CART6", 0.45, (0, (1, 2)))):
            if name in z:
                r, p = pr_curve(y, z[name])
                ax.plot(100 * r, 100 * p, color=C["bound"], alpha=alpha, ls=ls,
                        lw=2.0 if name == "GB" else 1.5, zorder=3)
        ax.axhline(100 * base, color=C["muted"], lw=1.1, ls=(0, (2, 3)), zorder=1)
        ax.text(98, 100 * base + 2.5, f"base rate {base:.1%}", color=C["ink2"],
                fontsize=8.5, ha="right")
        # The ceiling is a property of the BUILD, not of the method: it ranges
        # 15.7%-30.6% across the study's configurations (E17). Drawing it as a
        # band rather than a line keeps that visible.
        ax.axvspan(15.7, 30.6, color=C["muted"], alpha=0.16, zorder=1, lw=0)
        ax.axvline(18.09, color=C["muted"], lw=1.1, ls=(0, (4, 3)), zorder=1)
        ax.text(32, 34, "15.7-30.6%: the ceiling for any rule\nneeding the function's own author\n"
                        "Location. It is set by the build,\nnot by the method (dashed = this\n"
                        "study's development set, 18.1%).",
                color=C["ink2"], fontsize=8.3, va="center")
        if len(mined):
            ax.scatter(100 * mined[:, 0], 100 * mined[:, 1], s=8, color=C["muted"],
                       alpha=0.45, linewidths=0, zorder=2)
        ax.annotate("gradient boosting\n(headroom bound — not a rule)", (62, 62),
                    xytext=(46, 82), color=C["ink2"], fontsize=8.5,
                    arrowprops=dict(arrowstyle="-", color=C["muted"], lw=0.8))
        ax.set_xlim(0, 100); ax.set_ylim(0, 103)
        ax.set_xlabel("recall — author functions recovered (%)", color=C["ink2"], fontsize=9.5)
        ax.set_ylabel("precision (%)", color=C["ink2"], fontsize=9.5)
        ax.set_title("a. the whole space", color=C["ink"], fontsize=11.5, loc="left", pad=8)

        # ── b. the deployable region, development set ────────────────────────
        ax = axes[1]
        if "GB" in z:
            r, p = pr_curve(y, z["GB"], 4000)
            ax.plot(100 * r, 100 * p, color=C["bound"], lw=1.9, zorder=3,
                    label="gradient boosting (bound)")
        if "CART6" in z:
            r, p = pr_curve(y, z["CART6"], 4000)
            ax.plot(100 * r, 100 * p, color=C["bound"], lw=1.3, alpha=0.45,
                    ls=(0, (1, 2)), zorder=3, label="CART depth 6")
        if len(mined):
            ax.scatter(100 * mined[:, 0], 100 * mined[:, 1], s=13, color=C["muted"],
                       alpha=0.4, linewidths=0, zorder=2, label="mined candidates")
        for key, marker, lab in (("A", "o", "RULE_A@N (incumbent)"),
                                 ("B", "^", "RULE_B@N"), ("C", "s", "RULE_C@r")):
            pts = sorted((r["recall"], r["precision"]) for r in e01
                         if r["rule"].startswith(key + "@"))
            if not pts:
                continue
            pts = np.array(pts)
            ax.plot(100 * pts[:, 0], 100 * pts[:, 1], marker=marker, ms=5.5,
                    color=C["s1"], lw=1.0, alpha=0.9, zorder=4, label=lab,
                    markeredgecolor=C["surface"], markeredgewidth=0.7)
        a2 = next(r for r in e01 if r["rule"] == "A@2")
        ax.annotate("A@2 — shipped default",
                    (100 * a2["recall"], 100 * a2["precision"]),
                    textcoords="offset points", xytext=(14, -7), ha="left",
                    color=C["s1"], fontsize=8.8,
                    arrowprops=dict(arrowstyle="-", color=C["s1"], lw=0.8))
        for i, pk in enumerate(picks["rules"]):
            d = pk["dev"]
            ax.scatter([100 * d["recall"]], [100 * d["precision"]], marker="*", s=230,
                       color=C["s2"], zorder=6, edgecolors=C["surface"], linewidths=0.9,
                       label="this study's proposals" if i == 0 else None)
            ax.annotate(pk["short"], (100 * d["recall"], 100 * d["precision"]),
                        textcoords="offset points",
                        xytext=(9, 4) if pk["short"] != "R1" else (9, -3),
                        color=C["s2"], fontsize=9.5, fontweight="bold")
        for st in picks.get("rule_sets", []):
            d = st["dev"]
            ax.scatter([100 * d["recall"]], [100 * d["precision"]], marker="D", s=58,
                       color=C["s3"], zorder=6, edgecolors=C["surface"], linewidths=0.9)
            ax.annotate("mined 5-clause set", (100 * d["recall"], 100 * d["precision"]),
                        textcoords="offset points", xytext=(9, 9),
                        color=C["s3"], fontsize=8.8)
        ax.set_xlim(0, 22); ax.set_ylim(84, 100.5)
        ax.set_xlabel("recall (%)", color=C["ink2"], fontsize=9.5)
        ax.set_ylabel("precision (%)", color=C["ink2"], fontsize=9.5)
        ax.set_title("b. deployable region — development set (in-sample)",
                     color=C["ink"], fontsize=11.5, loc="left", pad=8)
        leg = ax.legend(loc="lower left", fontsize=7.8, frameon=True, framealpha=0.95,
                        facecolor=C["surface"], edgecolor=C["grid"], borderpad=0.5)
        for t in leg.get_texts():
            t.set_color(C["ink2"])

        # ── c. the held-out read ─────────────────────────────────────────────
        ax = axes[2]
        if lock:
            def get(name):
                r = lock["results"].get(name, {}).get("test")
                return r
            inc = get("A@2 (incumbent, shipped default)")
            if inc:
                ax.axhline(100 * inc["precision"], color=C["s1"], lw=1.0,
                           ls=(0, (3, 3)), zorder=1)
                ax.text(0.3, 100 * inc["precision"] + 0.45,
                        "the incumbent's precision", color=C["s1"], fontsize=8.3)
                lo, hi = inc["precision_cluster_boot"]
                ax.errorbar([100 * inc["recall"]], [100 * inc["precision"]],
                            yerr=[[100 * (inc["precision"] - lo)], [100 * (hi - inc["precision"])]],
                            fmt="o", ms=9, color=C["s1"], capsize=4, elinewidth=1.2,
                            zorder=5, label="A@2 (incumbent)")
                ax.annotate("A@2", (100 * inc["recall"], 100 * inc["precision"]),
                            textcoords="offset points", xytext=(0, -22),
                            ha="center", color=C["s1"], fontsize=9.5, fontweight="bold")
            for i, pk in enumerate(picks["rules"]):
                t = get(pk["name"])
                if not t:
                    continue
                lo, hi = t["precision_cluster_boot"]
                ax.errorbar([100 * t["recall"]], [100 * t["precision"]],
                            yerr=[[100 * (t["precision"] - lo)], [100 * (hi - t["precision"])]],
                            fmt="*", ms=17, color=C["s2"], capsize=4, elinewidth=1.2,
                            zorder=6, label="this study's proposals" if i == 0 else None)
                ax.annotate(pk["short"], (100 * t["recall"], 100 * t["precision"]),
                            textcoords="offset points", xytext=(7, 7),
                            color=C["s2"], fontsize=10, fontweight="bold")
            e15p = os.path.join(STUDY, "results", "e15_recall_ci.json")
            if os.path.exists(e15p) and inc:
                e15 = json.load(open(e15p))
                r3 = e15.get("R3")
                if r3:
                    ax.annotate(f"{r3['recall_ratio']:.2f}x the recall,\n"
                                f"{abs(100*(r3['precision']-inc['precision'])):.2f} pp of precision",
                                (100 * r3["recall"], 100 * r3["precision"]),
                                textcoords="offset points", xytext=(-16, -42),
                                ha="center", color=C["s2"], fontsize=8.6,
                                arrowprops=dict(arrowstyle="-", color=C["s2"], lw=0.8))
            ax.set_xlim(0, 20)
            ax.set_xlabel("recall (%)", color=C["ink2"], fontsize=9.5)
            ax.set_ylabel("precision (%)  — bars are 95% cluster bootstrap",
                          color=C["ink2"], fontsize=9.5)
            ax.set_title("c. the held-out read — 15 sealed crates, read once",
                         color=C["ink"], fontsize=11.5, loc="left", pad=8)
            leg = ax.legend(loc="lower left", fontsize=8, frameon=True, framealpha=0.95,
                            facecolor=C["surface"], edgecolor=C["grid"])
            for t in leg.get_texts():
                t.set_color(C["ink2"])
        else:
            ax.text(0.5, 0.5, "lockbox not yet read", ha="center", va="center",
                    color=C["ink2"], transform=ax.transAxes)
            ax.set_title("c. the held-out read", color=C["ink"], fontsize=11.5,
                         loc="left", pad=8)

        fig.suptitle("Author attribution in stripped Rust binaries — "
                     "43 crates x 8 build configurations, 2.95M functions",
                     color=C["ink"], fontsize=12.5, x=0.006, ha="left", y=0.985)
        fig.tight_layout(rect=(0, 0, 1, 0.945))
        out = os.path.join(HERE, f"frontier_{theme}.png")
        fig.savefig(out, dpi=165, facecolor=C["surface"])
        plt.close(fig)
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

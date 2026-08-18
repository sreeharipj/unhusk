"""
protocol.py — the evaluation protocol, in one place, so no experiment can
quietly use a different one.

Decisions fixed here (see JOURNAL.md 00:42 for why):

  unit of analysis   one FDE (function), as delimited by .eh_frame
  clustering         by crate; 8 build configs of a crate never split
  development set    28 crates; all search, all tuning, all model selection
  held-out set       15 crates; read once, at the end
  inner validation   leave-one-crate-out over the 28 development crates
  excluded rows      label NONE (no FDE in the symbol oracle's map) and
                     label UNKNOWN (the oracle could not attribute the symbol)
                     are dropped from SCORING but were fully present when
                     features were computed — the tool sees them at runtime
  target             AUTHOR vs everything else. Two variants, both reported:
                       strict : positives = AUTHOR
                       ws     : positives = AUTHOR or WORKSPACE (a path
                                dependency inside the same repo, which an
                                analyst would normally call author code)

Metrics are precision-first because the tool is precision-first: a false AUTHOR
call sends an analyst to read library code, which is worse than missing a
function. `coverage` is reported alongside because a rule that fires on nothing
has undefined-good precision.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(STUDY))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from oracle import cluster_bootstrap, wilson  # noqa: E402

SEED = 20260819
DATA = os.path.join(STUDY, "data", "fde")
SPLIT = json.load(open(os.path.join(STUDY, "data", "split.json")))

ID_COLS = ["crate", "config", "fn_start", "fn_end", "fde_idx", "label", "gt_crate"]

FEATURE_FAMILIES = {
    "C": "incumbent path-class counts (unhusk's 7-way taxonomy)",
    "P": "this study's 8-way path taxonomy",
    "M": "multiplicity variants (structs / lines / files, dominance, entropy)",
    "F": "Location fan-out across functions",
    "G": "geometry and instruction shape",
    "N": "address-order neighbourhood",
    "X": "call graph",
    "B": "whole-binary normalisers",
}


def feature_cols(df, families=None):
    fams = set(families or FEATURE_FAMILIES)
    return [c for c in df.columns
            if c not in ID_COLS and "_" in c and c.split("_", 1)[0] in fams]


def load(side="dev", crates=None, configs=None, columns=None, labeled_only=True):
    """Load the feature table for one side of the split."""
    want = set(crates) if crates is not None else set(
        SPLIT["dev"] if side == "dev" else SPLIT["test"] if side == "test"
        else SPLIT["dev"] + SPLIT["test"])
    files = []
    for f in sorted(os.listdir(DATA)):
        crate, config = f[:-8].split("__", 1)
        if crate not in want:
            continue
        if configs is not None and config not in configs:
            continue
        files.append(os.path.join(DATA, f))
    if not files:
        raise SystemExit(f"no parquet files matched side={side} crates={crates}")
    df = pd.concat((pd.read_parquet(p, columns=columns) for p in files),
                   ignore_index=True, copy=False)
    for c in ("crate", "config", "label", "gt_crate"):
        if c in df.columns:
            df[c] = df[c].astype(str)
    if labeled_only and "label" in df.columns:
        df = df[~df["label"].isin(["NONE", "UNKNOWN"])].reset_index(drop=True)
    return df


def target(df, variant="ws"):
    """Binary target vector. `ws` merges WORKSPACE into the positive class."""
    if variant == "strict":
        return (df["label"] == "AUTHOR").to_numpy()
    if variant == "ws":
        return df["label"].isin(["AUTHOR", "WORKSPACE"]).to_numpy()
    raise ValueError(variant)


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_binary(y, pred, groups, bootstrap=True, iters=4000):
    """Pooled and crate-averaged precision/recall/coverage for a hard 0/1 rule.

    `groups` is the per-row crate. The cluster bootstrap resamples whole crates,
    because functions inside one crate are not independent and a single large
    binary can otherwise dominate a pooled count.
    """
    y = np.asarray(y, bool)
    pred = np.asarray(pred, bool)
    tp = int((y & pred).sum())
    fp = int((~y & pred).sum())
    fn = int((y & ~pred).sum())
    n = int(len(y))

    out = {
        "n": n, "n_pos": int(y.sum()), "tp": tp, "fp": fp, "fn": fn,
        "predicted": tp + fp,
        "precision": tp / (tp + fp) if (tp + fp) else float("nan"),
        "recall": tp / (tp + fn) if (tp + fn) else float("nan"),
        "coverage": (tp + fp) / n if n else float("nan"),
        "base_rate": float(y.mean()) if n else float("nan"),
    }
    p, lo, hi = wilson(tp, tp + fp)
    out["precision_wilson"] = [lo / 100, hi / 100] if tp + fp else [float("nan")] * 2

    # Positional, not label-based: a caller may hand us a filtered frame whose
    # index no longer starts at zero, and groupby().groups returns index LABELS.
    # Using those to index the numpy arrays silently reads the wrong rows, or
    # raises if the frame is short enough. Found the hard way on the V2 subset.
    g = pd.Series(np.asarray(groups))
    per = {}
    clusters = []
    for crate, idx in g.groupby(g).indices.items():
        i = np.asarray(idx)
        yy, pp = y[i], pred[i]
        t = int((yy & pp).sum())
        f = int((~yy & pp).sum())
        m = int((yy & ~pp).sum())
        per[crate] = {
            "precision": t / (t + f) if (t + f) else float("nan"),
            "recall": t / (t + m) if (t + m) else float("nan"),
            "coverage": (t + f) / len(i),
            "predicted": t + f, "tp": t, "n_pos": int(yy.sum()),
        }
        clusters.append((t, f))
    vals = [v["precision"] for v in per.values() if not np.isnan(v["precision"])]
    out["precision_crate_avg"] = float(np.mean(vals)) if vals else float("nan")
    out["n_crates_firing"] = len(vals)
    rvals = [v["recall"] for v in per.values() if not np.isnan(v["recall"])]
    out["recall_crate_avg"] = float(np.mean(rvals)) if rvals else float("nan")
    if bootstrap and len([c for c in clusters if sum(c)]) >= 2:
        _, blo, bhi = cluster_bootstrap([c for c in clusters if sum(c)], iters=iters, seed=SEED)
        out["precision_cluster_boot"] = [blo / 100, bhi / 100]
    else:
        out["precision_cluster_boot"] = [float("nan")] * 2
    out["per_crate"] = per
    return out


def precision_at_recall(y, score, targets=(0.02, 0.05, 0.10, 0.20, 0.30)):
    """Highest precision achievable at >= each target recall, by sweeping the
    score threshold. Returns {recall_target: (precision, recall, threshold)}."""
    y = np.asarray(y, bool)
    score = np.asarray(score, float)
    order = np.argsort(-score, kind="stable")
    ys = y[order]
    ss = score[order]
    tp = np.cumsum(ys)
    fp = np.cumsum(~ys)
    prec = tp / np.maximum(tp + fp, 1)
    rec = tp / max(int(y.sum()), 1)
    out = {}
    for t in targets:
        ok = np.flatnonzero(rec >= t)
        if len(ok) == 0:
            out[t] = (float("nan"), float("nan"), float("nan"))
            continue
        # Among all thresholds meeting the recall target, the best precision.
        j = ok[0] + np.argmax(prec[ok[0]:])
        out[t] = (float(prec[j]), float(rec[j]), float(ss[j]))
    return out


def average_precision(y, score):
    y = np.asarray(y, bool)
    order = np.argsort(-np.asarray(score, float), kind="stable")
    ys = y[order]
    tp = np.cumsum(ys)
    fp = np.cumsum(~ys)
    prec = tp / np.maximum(tp + fp, 1)
    npos = max(int(y.sum()), 1)
    return float((prec * ys).sum() / npos)


def paired_crate_bootstrap(per_a, per_b, key="precision", iters=4000, seed=SEED):
    """Paired percentile bootstrap over crates of (metric_a - metric_b), in
    points. Resamples crates, recomputing each side's POOLED metric from the
    resampled crates, so a crate that fires for one rule and not the other is
    handled honestly rather than dropped."""
    rng = np.random.default_rng(seed)
    crates = sorted(set(per_a) & set(per_b))
    if len(crates) < 2:
        return float("nan"), float("nan"), float("nan")

    def pooled(pers, sel):
        if key == "precision":
            t = sum(pers[c]["tp"] for c in sel)
            p = sum(pers[c]["predicted"] for c in sel)
            return t / p if p else np.nan
        t = sum(pers[c]["tp"] for c in sel)
        n = sum(pers[c]["n_pos"] for c in sel)
        return t / n if n else np.nan

    point = pooled(per_a, crates) - pooled(per_b, crates)
    diffs = []
    idx = np.arange(len(crates))
    for _ in range(iters):
        sel = [crates[i] for i in rng.choice(idx, size=len(idx), replace=True)]
        a, b = pooled(per_a, sel), pooled(per_b, sel)
        if not (np.isnan(a) or np.isnan(b)):
            diffs.append(a - b)
    if len(diffs) < 100:
        return 100 * point, float("nan"), float("nan")
    diffs.sort()
    return (100 * point, 100 * diffs[int(0.025 * len(diffs))],
            100 * diffs[min(len(diffs) - 1, int(0.975 * len(diffs)))])


def paired_crate_bootstrap_p(per_a, per_b, key="precision", iters=8000, seed=SEED):
    """Two-sided bootstrap p-value for (metric_a - metric_b) != 0, resampling
    whole crates. Returned alongside the interval so that a family of
    pre-registered comparisons can be Holm-corrected rather than eyeballed."""
    rng = np.random.default_rng(seed + 1)
    crates = sorted(set(per_a) & set(per_b))
    if len(crates) < 2:
        return float("nan")

    def pooled(pers, sel):
        if key == "precision":
            t = sum(pers[c]["tp"] for c in sel)
            p = sum(pers[c]["predicted"] for c in sel)
            return t / p if p else np.nan
        t = sum(pers[c]["tp"] for c in sel)
        n = sum(pers[c]["n_pos"] for c in sel)
        return t / n if n else np.nan

    point = pooled(per_a, crates) - pooled(per_b, crates)
    idx = np.arange(len(crates))
    diffs = []
    for _ in range(iters):
        sel = [crates[i] for i in rng.choice(idx, size=len(idx), replace=True)]
        a, b = pooled(per_a, sel), pooled(per_b, sel)
        if not (np.isnan(a) or np.isnan(b)):
            diffs.append(a - b)
    if len(diffs) < 100:
        return float("nan")
    diffs = np.asarray(diffs)
    # Centre the bootstrap distribution on zero and ask how often it is at least
    # as extreme as the observed difference.
    centred = diffs - point
    p = float((np.abs(centred) >= abs(point)).mean())
    return min(1.0, max(p, 1.0 / (len(diffs) + 1)))


def holm(pvals):
    """Holm-Bonferroni adjusted p-values, in the input order. Used for the small
    pre-registered family of lockbox comparisons; a Bonferroni-family method is
    the right choice here because the family is tiny and the question is
    'does ANY of these survive', not 'what fraction of discoveries are false'."""
    n = len(pvals)
    order = sorted(range(n), key=lambda i: pvals[i])
    adj = [0.0] * n
    running = 0.0
    for rank, i in enumerate(order):
        val = (n - rank) * pvals[i]
        running = max(running, val)
        adj[i] = min(1.0, running)
    return adj


def loco_folds(df):
    """Leave-one-crate-out over whatever crates are present in `df`."""
    crates = sorted(df["crate"].unique())
    for c in crates:
        test = (df["crate"] == c).to_numpy()
        yield c, ~test, test


def fmt(x, pct=True, nd=1):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "  n/a"
    return f"{100*x:.{nd}f}%" if pct else f"{x:.{nd}f}"

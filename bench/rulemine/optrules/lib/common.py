"""
optrules/lib/common.py — shared machinery for the optimal-rule study.

This sub-study asks one question: D04 concluded the incumbent Boolean rule family
is near-optimal in its own space, but D04's search was *greedy* (beam search,
sequential covering). Does a search that returns an optimality *certificate*
change that answer?

Two hypothesis classes are searched, both restricted to the study's own
interpretable threshold atoms so any result is directly comparable to A@2 / R1 /
R2 / R3:

  o01  short conjunctions (<= 3 atoms) and small rule SETS (<= 3 clauses, each a
       <= 2-atom conjunction, OR'd). The atom count after de-duplication is small
       enough that both searches are *exhaustive* over the tier-A population, so
       "nothing better exists" is a proof, not a heuristic failure. This is the
       CORELS / optimal-rule-list angle without the (unbuildable) library.

  o02  sparse decision trees, via GOSDT's branch-and-bound (certifiably optimal
       for a given regularisation and depth budget). A different, richer class:
       nested if/else sharing structure, which o01 does not cover.

Populations ("tiers"), fixed here so no experiment drifts:

  A   M_rel_structs >= 1  — the function references at least one author Location
      of its own. Every incumbent readable rule (A@2, R1, R2, R3) can only fire
      here. ~19k labelled rows corpus-wide; small enough for exhaustive search
      and for GOSDT to run on the whole tier with no subsampling.

  B   M_rel_structs == 0  — the "invisible" 82% D04 already searched with beam +
      covering and found nothing at >= 90% precision. GOSDT is re-run here on a
      crate-stratified subsample only, as an independent check of that negative.

Everything reuses the parent study's protocol.py: same split, same clustered
scoring, same cluster bootstrap, same LOCO folds. The lockbox is NOT touched by
any script here.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OPTRULES = os.path.dirname(HERE)
STUDY = os.path.dirname(OPTRULES)
sys.path.insert(0, os.path.join(STUDY, "lib"))

import mining  # noqa: E402
import protocol as P  # noqa: E402

SEED = P.SEED
CACHE = os.path.join(OPTRULES, "cache")
RESULTS = os.path.join(OPTRULES, "results")

# Tier predicate -> a callable over a loaded feature frame.
TIERS = {
    "A": lambda df: df["M_rel_structs"].to_numpy() >= 1,
    "B": lambda df: df["M_rel_structs"].to_numpy() == 0,
}

# Families kept for atom generation. D01's leave-one-family-out found B and F
# contribute nothing to an unconstrained model; they are dropped to keep the
# atom set small enough for exhaustive search. M is kept despite being ~neutral
# for the model because it is the incumbent's scope variable and the tier split.
ATOM_FAMILIES = ["C", "M", "N", "X", "G", "P"]


def load_tier(tier, side="dev", variant="ws", families=None):
    """Return (df, y, groups) for one tier and one side of the split."""
    cols = None  # load all; parquet is 142 MB total, cheap
    df = P.load(side=side, columns=cols)
    keep = TIERS[tier](df)
    df = df[keep].reset_index(drop=True)
    y = P.target(df, variant=variant)
    groups = df["crate"].to_numpy()
    return df, y, groups


def full_positive_count(side="dev", variant="ws"):
    """Total positives across the WHOLE labelled population for `side` — the
    denominator for *global* recall, so a tier-restricted rule is not flattered
    by a shrunken denominator."""
    df = P.load(side=side, columns=["crate", "label"])
    return int(P.target(df, variant=variant).sum())


def build_atoms(df, families=None, max_thresholds=8, min_support=150):
    """Interpretable threshold atoms over the kept families, de-duplicated by
    packed mask against a Bitspace built on this df's crates."""
    fams = families or ATOM_FAMILIES
    cols = P.feature_cols(df, families=fams)
    space = mining.Bitspace(np.zeros(len(df), bool), df["crate"].to_numpy())
    atoms = mining.make_atoms(df, cols, max_thresholds=max_thresholds,
                              min_support=min_support)
    atoms = mining.dedupe_atoms(atoms, space)
    return atoms, space, cols


def incumbent_rules():
    """A@2 / R1 / R2 / R3 / R4 / set-4 / ceilings, from the parent study's frozen
    picks.json — the single source of truth, so this study cannot quote a stale
    rule."""
    picks = json.load(open(os.path.join(STUDY, "results", "picks.json")))
    out = {}
    for r in picks["rules"]:
        out[r["short"]] = {"kind": "conj", "expr": r["expr"], "name": r["name"]}
    for b in picks["baselines"]:
        short = "A@2" if b.get("is_incumbent") else b["name"]
        out[short] = {"kind": "conj", "expr": b["expr"], "name": b["name"]}
    for s in picks.get("rule_sets", []):
        out[s["short"]] = {"kind": "set", "clauses": s["clauses"], "name": s["name"]}
    for a in picks.get("additive", []):
        out[a.get("short", a["name"])] = {"kind": "conj", "expr": a["expr"],
                                          "name": a["name"]}
    return out, picks["split_sha256"]


def eval_conj(df, expr):
    return mining.eval_expr(df, expr)


def eval_set(df, clauses):
    """OR of AND-clauses."""
    mask = np.zeros(len(df), bool)
    for c in clauses:
        mask |= mining.eval_expr(df, c)
    return mask


def eval_rule(df, rule):
    if rule["kind"] == "conj":
        return eval_conj(df, rule["expr"])
    return eval_set(df, rule["clauses"])


def score(df, y, groups, pred, npos_global, bootstrap=True, iters=4000):
    """protocol.score_binary plus a global-recall field (tp / all positives on
    this side, not tp / positives-in-tier)."""
    s = P.score_binary(y, pred, groups, bootstrap=bootstrap, iters=iters)
    s["recall_global"] = s["tp"] / npos_global if npos_global else float("nan")
    s["npos_global"] = npos_global
    return s


def loco_pred(df, rule):
    """A fixed rule needs no refitting, but LOCO scoring still asks: pooled over
    the held-out crate only. Returns per-crate (tp, fp, n_pos) so the caller can
    pool honestly the way protocol.paired_crate_bootstrap does."""
    per = {}
    for crate, tr, te in P.loco_folds(df):
        sub = df[te]
        yy = None
        pred = eval_rule(sub, rule)
        per[crate] = pred
    return per


def summarise_rule(name, rule, df, y, groups, npos_global):
    pred = eval_rule(df, rule)
    s = score(df, y, groups, pred, npos_global)
    return {
        "name": name, "rule": rule,
        "precision": s["precision"], "precision_wilson": s["precision_wilson"],
        "precision_cluster_boot": s["precision_cluster_boot"],
        "precision_crate_avg": s["precision_crate_avg"],
        "recall_tier": s["recall"], "recall_global": s["recall_global"],
        "predicted": s["predicted"], "tp": s["tp"], "fp": s["fp"],
        "coverage": s["coverage"], "n_crates_firing": s["n_crates_firing"],
        "per_crate": s["per_crate"],
    }


def jdump(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=1, default=_default)
        fh.write("\n")


def _default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.bool_,)):
        return bool(o)
    raise TypeError(type(o))

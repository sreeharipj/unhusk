#!/usr/bin/env python3
"""
E06 — sequential covering: a rule SET rather than a single rule.

A single conjunction has to be right about every author function at once. A
disjunction of a few conjunctions does not: each clause can specialise on a
different mechanism by which author code becomes visible (its own panic sites,
its neighbours', its callers'), and the set's recall is their union while its
precision stays governed by the weakest clause.

This is the RIPPER shape, with one deliberate change of objective. RIPPER grows
each rule to maximise information gain and prunes on a validation split; here
each new clause is grown to maximise *newly covered positives* subject to the
same precision floor the rest of the study uses, and precision is always
evaluated against the full row set rather than against the not-yet-covered
remainder — because a false positive is a false positive whether or not some
earlier clause already fired on a different row.

Stopping: no clause qualifies, or the marginal clause adds under 0.3 pp of
recall, or 6 clauses. The point is a rule an analyst will actually read, so a
40-clause list would be a failure even if it scored better.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDY, "lib"))
import mining  # noqa: E402
import protocol as P  # noqa: E402


BEAM = 300


def _mask_for(atoms, idxs):
    w = atoms[idxs[0]]["words"].copy()
    for k in idxs[1:]:
        w &= atoms[k]["words"]
    return w


def grow_clause(atoms, space, uncovered_words, tau, min_crates, max_len=3):
    """Best conjunction by NEWLY covered positives, subject to global precision.

    Candidate masks are NOT retained. The first version of this function kept the
    packed mask alongside every candidate; at 916 atoms and a 400-wide beam that
    is ~366k live candidates x 205 KB = 75 GB, which on a 14 GB machine does not
    fail loudly -- it swaps until everything else on the box crawls, which is
    exactly what it did for twenty minutes before being killed. Only the
    surviving beam's masks are materialised, rebuilt from their atom indices,
    which costs one extra AND per beam member per level and nothing in memory.
    """
    best = None
    n = len(atoms)
    cur = [([], None)]
    for _ in range(max_len):
        scored = []
        for idxs, w in cur:
            start_k = (max(idxs) + 1) if idxs else 0
            for k in range(start_k, n):
                w2 = atoms[k]["words"] if w is None else (w & atoms[k]["words"])
                tp, pred, _, per_pred = space.stats(w2)
                if pred == 0:
                    continue
                prec = tp / pred
                new_tp = int(np.bitwise_count(w2 & uncovered_words & space.y_words)
                             .sum(dtype=np.int64))
                crates = int((per_pred > 0).sum())
                scored.append((idxs + [k], prec, new_tp, crates))
                if prec >= tau and crates >= min_crates:
                    if best is None or new_tp > best[2]:
                        best = (idxs + [k], prec, new_tp, crates)
        if not scored:
            break
        scored.sort(key=lambda c: (-c[2], -c[1]))
        cur = [(c[0], _mask_for(atoms, c[0])) for c in scored[:BEAM]]
    if best is None:
        return None
    idxs, prec, new_tp, crates = best
    return idxs, _mask_for(atoms, idxs), prec, new_tp, crates


def main():
    df = P.load("dev")
    y = P.target(df, "ws")
    space = mining.Bitspace(y, df["crate"].to_numpy())
    cols = P.feature_cols(df)
    atoms = mining.dedupe_atoms(mining.make_atoms(df, cols, max_thresholds=8), space)
    print(f"dev {len(df):,} rows, {len(atoms)} atoms\n")

    out = {"clauses": {}, "protocol": "sequential covering, dev only"}
    for tau in (0.95, 0.90):
        print(f"── precision floor {tau:.0%}")
        uncovered = np.full(len(space.y_words), np.uint64(0xFFFFFFFFFFFFFFFF), np.uint64)
        set_words = np.zeros(len(space.y_words), np.uint64)
        clauses = []
        for step in range(6):
            best = grow_clause(atoms, space, uncovered, tau, 8, max_len=3)
            if best is None:
                print("   (no further clause qualifies)")
                break
            idxs, w, prec, new_tp, crates = best
            expr = " AND ".join(atoms[i]["expr"] for i in idxs)
            set_words = set_words | w
            m = space.metrics(set_words)
            gain = new_tp / space.n_pos
            print(f"   +clause {step+1}: {expr}")
            print(f"      clause alone  prec {prec:.1%}  new positives {new_tp:,} "
                  f"(+{gain:.2%} recall)  crates {crates}")
            print(f"      SET so far    prec {m['precision']:.1%}  recall {m['recall']:.2%} "
                  f" fires {m['predicted']:,}  crates {m['crates_firing']}")
            clauses.append({"expr": expr, "clause_precision": prec, "new_tp": new_tp,
                            "recall_gain": gain, "set_precision": m["precision"],
                            "set_recall": m["recall"], "set_predicted": m["predicted"],
                            "set_crates": m["crates_firing"]})
            uncovered = uncovered & ~w
            if gain < 0.003:
                print("      (marginal gain below 0.3 pp — stopping)")
                break
        out["clauses"][str(tau)] = clauses
        print()
    json.dump(out, open(os.path.join(STUDY, "results", "e06_cover.json"), "w"),
              indent=1, default=float)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

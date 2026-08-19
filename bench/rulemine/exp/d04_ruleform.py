#!/usr/bin/env python3
"""
D04 — is the gap a FEATURE gap or a RULE-FORM gap?

D01 found that on the invisible population (the 81.9% of author functions that
reference no author `Location` of their own) a gradient-boosted model reaches
89.6% precision at 5% recall and 85.5% at 10%, while E04's exhaustive search over
the SAME rows and the SAME 91 features found a best two-term rule at 91.5%
precision but only 1.13% recall, and 70.7% at 10%.

Same data, same features, four to nine times the recall at matched precision. That
difference cannot be a feature gap — the features are identical. It is the cost of
insisting on a two-term conjunction.

This experiment asks how much of that cost a *richer but still readable* form
buys back, before anyone spends effort on new features:

  len 2      the current form, as a baseline
  len 3-5    longer conjunctions by beam search. Length 2 stays exhaustive, so
             the baseline everything is compared against is exact; at 735 atoms
             over 1.6M rows an exhaustive triple loop is ~66M bitwise ANDs of 25k
             words each and does not finish in a useful time.
  list-k     a decision list: k conjunctions OR'd together, grown by sequential
             covering, each clause meeting the precision floor

If a 4-term conjunction or a 4-clause list closes most of the gap, the productive
next step is a slightly richer rule form on the features that already exist. If
none of them move, the gap really is "a model can do this and a rule cannot", and
that is the finding rather than a to-do.

Runs on the 28 development crates only.
"""
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDY, "lib"))
import mining  # noqa: E402
import protocol as P  # noqa: E402

TAUS = [0.90, 0.80]


def covering(atoms, space, tau, min_crates, max_clauses=5, max_len=3, beam=250):
    """Sequential covering restricted to this population. Each clause must meet the
    precision floor on its own; clauses are grown to maximise newly covered
    positives. Masks are rebuilt from atom indices rather than retained (see
    exp/e06_cover.py for why)."""
    def mask_for(idxs):
        w = atoms[idxs[0]]["words"].copy()
        for k in idxs[1:]:
            w &= atoms[k]["words"]
        return w

    n = len(atoms)
    uncovered = np.full(len(space.y_words), np.uint64(0xFFFFFFFFFFFFFFFF), np.uint64)
    chosen, set_words = [], np.zeros(len(space.y_words), np.uint64)
    for _ in range(max_clauses):
        best = None
        cur = [([], None)]
        for _ in range(max_len):
            scored = []
            for idxs, w in cur:
                start = (max(idxs) + 1) if idxs else 0
                for k in range(start, n):
                    w2 = atoms[k]["words"] if w is None else (w & atoms[k]["words"])
                    tp, pred, _, per_pred = space.stats(w2)
                    if pred == 0:
                        continue
                    prec = tp / pred
                    new_tp = int(np.bitwise_count(w2 & uncovered & space.y_words)
                                 .sum(dtype=np.int64))
                    crates = int((per_pred > 0).sum())
                    scored.append((idxs + [k], prec, new_tp, crates))
                    if prec >= tau and crates >= min_crates and (
                            best is None or new_tp > best[2]):
                        best = (idxs + [k], prec, new_tp, crates)
            if not scored:
                break
            scored.sort(key=lambda c: (-c[2], -c[1]))
            cur = [(c[0], mask_for(c[0])) for c in scored[:beam]]
        if best is None:
            break
        idxs, prec, new_tp, crates = best
        w = mask_for(idxs)
        set_words = set_words | w
        m = space.metrics(set_words)
        chosen.append({"expr": " AND ".join(atoms[i]["expr"] for i in idxs),
                       "clause_precision": prec, "new_tp": new_tp,
                       "set_precision": m["precision"], "set_recall": m["recall"],
                       "set_predicted": m["predicted"], "set_crates": m["crates_firing"]})
        uncovered = uncovered & ~w
        if new_tp / max(space.n_pos, 1) < 0.002:
            break
    return chosen


def main():
    df_all = P.load("dev")
    y_all = P.target(df_all, "ws")
    inv = (df_all["M_rel_structs"].to_numpy() == 0)
    df = df_all[inv].reset_index(drop=True)
    y = y_all[inv]
    cols = P.feature_cols(df)
    share = float(y.sum() / y_all.sum())

    print(f"invisible population: {len(df):,} rows, {int(y.sum()):,} author "
          f"(base {y.mean():.3%}), {share:.1%} of all author functions\n")
    space = mining.Bitspace(y, df["crate"].to_numpy())
    atoms = mining.dedupe_atoms(mining.make_atoms(df, cols, max_thresholds=8), space)
    print(f"{len(cols)} features -> {len(atoms)} atoms\n")

    out = {"population": {"n": int(len(df)), "n_pos": int(y.sum()),
                          "base_rate": float(y.mean()),
                          "share_of_all_positives": share},
           "gb_reference": json.load(open(os.path.join(
               STUDY, "results", "d01_headroom.json")))["A_headroom"]["invisible"]
           if os.path.exists(os.path.join(STUDY, "results", "d01_headroom.json")) else None,
           "forms": {}}

    for tau in TAUS:
        print(f"══ precision floor {tau:.0%} ══════════════════════════════════")
        rows = {}
        for name, kw in (("len 2 (current form)", dict(max_len=2, beam=0)),
                         ("len 3 (beam)", dict(max_len=3, beam=150)),
                         ("len 4 (beam)", dict(max_len=4, beam=150)),
                         ("len 5 (beam)", dict(max_len=5, beam=150))):
            t0 = time.time()
            if kw["beam"]:
                res = mining.beam_search(atoms, space, tau=tau, min_crates=8,
                                         max_len=kw["max_len"], beam=kw["beam"], top_k=1)
            else:
                res, _ = mining.search_pairs(atoms, space, tau=tau, min_crates=8,
                                             max_len=kw["max_len"], top_k=1)
            if res:
                r = res[0]
                print(f"  {name:<22} recall {r['recall']:>6.2%}  precision "
                      f"{r['precision']:>6.1%}  (+{r['recall']*share:>5.2%} overall)  "
                      f"[{time.time()-t0:.0f}s]")
                print(f"  {'':<22} {r['expr']}")
                rows[name] = {"recall": r["recall"], "precision": r["precision"],
                              "expr": r["expr"], "overall_recall_gain": r["recall"] * share}
            else:
                print(f"  {name:<22} nothing qualifies")
                rows[name] = None

        t0 = time.time()
        cl = covering(atoms, space, tau, 8, max_clauses=5, max_len=2)
        if cl:
            last = cl[-1]
            print(f"  {'decision list ('+str(len(cl))+' clauses)':<22} recall "
                  f"{last['set_recall']:>6.2%}  precision {last['set_precision']:>6.1%}"
                  f"  (+{last['set_recall']*share:>5.2%} overall)  [{time.time()-t0:.0f}s]")
            for i, c in enumerate(cl, 1):
                print(f"  {'':<22} {i}. {c['expr']}")
            rows["decision list"] = {"recall": last["set_recall"],
                                     "precision": last["set_precision"],
                                     "clauses": [c["expr"] for c in cl],
                                     "overall_recall_gain": last["set_recall"] * share}
        else:
            rows["decision list"] = None
        out["forms"][str(tau)] = rows
        print()

    gbref = out.get("gb_reference")
    if gbref:
        print("── against the model on the same rows and the same features")
        print(f"   {'form':<26}{'recall @ ~90% precision':>26}")
        r2 = (out["forms"]["0.9"].get("len 2 (current form)") or {}).get("recall")
        best = max((v["recall"] for v in out["forms"]["0.9"].values() if v), default=0)
        gb5 = gbref["precision_at_recall"].get("0.05")
        gb10 = gbref["precision_at_recall"].get("0.1")
        print(f"   {'two-term rule':<26}{r2 or 0:>25.2%}")
        print(f"   {'best readable form':<26}{best:>25.2%}")
        print(f"   {'gradient boosting':<26}{'5% @ '+format(gb5,'.1%') if gb5 else 'n/a':>25}"
              f"   (10% @ {gb10:.1%})" if gb10 else "")
    json.dump(out, open(os.path.join(STUDY, "results", "d04_ruleform.json"), "w"),
              indent=1, default=float)
    print("\nwrote results/d04_ruleform.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

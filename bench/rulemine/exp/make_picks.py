#!/usr/bin/env python3
"""
make_picks.py — freeze the proposed rules BEFORE the lockbox is opened.

Everything this writes is a pre-registration. `exp/e11_lockbox.py` reads this
file and nothing else; whatever it reports for these expressions is what the
report says. The three proposals were chosen from E10's factor ablation -- a
pre-structured grid of ~25 hand-specified factor combinations -- rather than
from the 916-atom exhaustive search, which matters for the multiple-comparison
argument and is stated as such in the report.

Selection criteria, fixed here and not revisited:
  R1  the rule that DOMINATES the incumbent: higher precision and higher recall
      at once. This is the one that decides whether the study found anything.
  R2  the highest-precision rule that still fires in every development crate.
  R3  the highest-recall rule that holds >= 90% precision, for an analyst who
      wants coverage rather than certainty.
Plus the additive ceiling-breaker from E04, reported separately because it
operates on a disjoint population (functions with no author Location at all)
and is therefore not comparable on the same axes.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDY, "lib"))
import mining  # noqa: E402
import protocol as P  # noqa: E402

PROPOSED = [
    dict(name="R1 neighbourhood-corroborated multiplicity", short="R1",
         expr="M_rel_structs >= 2 AND N_win_rel >= 3",
         plain="at least 2 distinct author Location records in this function, AND "
               "at least 3 among its +/-5 neighbours in address order",
         why="dominates the incumbent on both axes; the neighbourhood term vetoes "
             "inline-absorption false positives, which sit in the library's region "
             "of .text",
         label_offset=(9, 5)),
    dict(name="R2 caller-corroborated multiplicity", short="R2",
         expr="M_rel_structs >= 2 AND X_caller_rel >= 1",
         plain="at least 2 distinct author Location records, AND at least one "
               "direct caller that also references author Locations",
         why="highest precision of the readable rules; a library generic that "
             "inlined an author closure is still called from library code",
         label_offset=(9, -12)),
    dict(name="R3 high-recall neighbourhood rule", short="R3",
         expr="M_rel_structs >= 1 AND N_win_rel >= 5",
         plain="at least 1 author Location record, AND at least 5 among its "
               "+/-5 neighbours",
         why="drops the multiplicity requirement to 1 and pays for it with a "
             "stronger neighbourhood demand; roughly doubles the incumbent's recall "
             "at comparable precision",
         label_offset=(-52, 8)),
]

CONTEXT = [
    dict(name="A@2 (incumbent, shipped default)", expr="C_user >= 2 AND P_nonrel <= 0",
         is_incumbent=True),
    dict(name="bare multiplicity (structs >= 2)", expr="M_rel_structs >= 2"),
    dict(name="line-span variant", expr="M_rel_line_span >= 2 AND N_win_rel >= 3"),
    dict(name="A@2 + neighbourhood", expr="C_user >= 2 AND P_nonrel <= 0 AND N_win_rel >= 3"),
    dict(name="any author Location (loosest possible)", expr="M_rel_structs >= 1"),
]

RULE_SETS = [
    dict(name="E06 sequential-covering set (4 clauses)", short="set-4",
         expr=None, label_offset=(8, -14)),
]

ADDITIVE = [
    dict(name="R4 helper rule (additive, disjoint population)",
         expr="X_callee_rel >= 3 AND X_caller_all_rel >= 1",
         plain="every direct caller references author Locations, AND this function "
               "calls at least 3 author Locations' worth of author code",
         population="functions referencing NO author Location of their own",
         why="recovers #[track_caller] helpers and private author helpers, which "
             "are structurally incapable of carrying their own Location"),
]


def main():
    dev = P.load("dev")
    y = P.target(dev, "ws")
    out = {"registered_at": "before any lockbox read",
           "split_sha256": P.SPLIT["sha256"], "rules": [], "baselines": [],
           "rule_sets": [], "additive": []}

    for r in PROPOSED:
        s = P.score_binary(y, mining.eval_expr(dev, r["expr"]), dev["crate"], bootstrap=False)
        r = dict(r)
        r["dev"] = {"precision": s["precision"], "recall": s["recall"],
                    "predicted": s["predicted"], "crates_firing": s["n_crates_firing"]}
        out["rules"].append(r)
        print(f"{r['short']}  {s['precision']:.1%} / {s['recall']:.2%}   {r['expr']}")

    for r in CONTEXT:
        s = P.score_binary(y, mining.eval_expr(dev, r["expr"]), dev["crate"], bootstrap=False)
        r = dict(r)
        r["dev"] = {"precision": s["precision"], "recall": s["recall"],
                    "predicted": s["predicted"], "crates_firing": s["n_crates_firing"]}
        out["baselines"].append(r)
        print(f"    {r['name']:<42}{s['precision']:.1%} / {s['recall']:.2%}")

    # The sequential-covering set, if E06 has produced one.
    p = os.path.join(STUDY, "results", "e06_cover.json")
    if os.path.exists(p):
        cov = json.load(open(p))
        cl = cov["clauses"].get("0.95", [])
        if cl:
            expr = " OR ".join(f"({c['expr']})" for c in cl)
            st = dict(RULE_SETS[0])
            st["clauses"] = [c["expr"] for c in cl]
            st["dev"] = {"precision": cl[-1]["set_precision"],
                         "recall": cl[-1]["set_recall"],
                         "predicted": cl[-1]["set_predicted"]}
            st["expr_or"] = expr
            out["rule_sets"].append(st)
            print(f"set-4  {st['dev']['precision']:.1%} / {st['dev']['recall']:.2%}  "
                  f"({len(cl)} clauses)")

    for r in ADDITIVE:
        out["additive"].append(r)

    json.dump(out, open(os.path.join(STUDY, "results", "picks.json"), "w"), indent=1,
              default=float)
    print("\nwrote results/picks.json — the lockbox reads only this")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

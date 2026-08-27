#!/usr/bin/env python3
"""
o00 — build the binarised search matrix for tier A, and cross-check it two ways
before any search runs.

  trust anchor 1  every atom column in the packed matrix must equal the raw
                  predicate re-evaluated on the feature frame. Catches an
                  ordering / dtype / de-dup bug that would silently corrupt every
                  downstream search.

  trust anchor 2  each incumbent readable rule (A@2, R1, R2, R3), evaluated here
                  on the tier-A development frame, must reproduce the pooled
                  precision / recall / fired-count that the parent study's frozen
                  picks.json recorded on the full development set. R1/R2/R3 fire
                  only where M_rel_structs >= 1, so the tier-A restriction must be
                  a no-op for them; A@2 keys on C_user and may differ by a
                  handful of rows, which is reported rather than asserted.

Writes cache/tierA_dev.npz and results/o00_setup.json. Touches only the
development split.
"""
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import common as C  # noqa: E402


def main():
    t0 = time.time()
    out = {"seed": C.SEED, "families": C.ATOM_FAMILIES}

    df, y_ws, groups = C.load_tier("A", side="dev", variant="ws")
    y_strict = C.load_tier("A", side="dev", variant="strict")[1]
    npos_g_ws = C.full_positive_count(side="dev", variant="ws")
    npos_g_strict = C.full_positive_count(side="dev", variant="strict")

    out["tierA"] = {
        "n_rows": int(len(df)), "n_crates": int(df["crate"].nunique()),
        "n_pos_ws_tier": int(y_ws.sum()), "n_pos_strict_tier": int(y_strict.sum()),
        "n_pos_ws_global_dev": npos_g_ws, "n_pos_strict_global_dev": npos_g_strict,
        "base_rate_ws": float(y_ws.mean()), "base_rate_strict": float(y_strict.mean()),
        "recall_ceiling_ws": float(y_ws.sum() / npos_g_ws),
        "recall_ceiling_strict": float(y_strict.sum() / npos_g_strict),
    }
    print(f"tier A dev: {len(df):,} rows, {df['crate'].nunique()} crates, "
          f"{int(y_ws.sum()):,} ws-pos in tier "
          f"(global-recall ceiling {y_ws.sum()/npos_g_ws:.3%})", flush=True)

    atoms, space, cols = C.build_atoms(df)
    print(f"atoms: {len(atoms)} over {len(cols)} columns "
          f"({time.time()-t0:.0f}s)", flush=True)

    # ── pack matrix ──────────────────────────────────────────────────────────
    X = np.zeros((len(df), len(atoms)), dtype=bool)
    exprs = []
    mism = 0
    for k, a in enumerate(atoms):
        X[:, k] = a["mask"]
        exprs.append(a["expr"])
        v = df[a["col"]].to_numpy()
        raw = (v >= a["t"]) if a["op"] == ">=" else (v <= a["t"])
        if not np.array_equal(raw, a["mask"]):
            mism += 1
    out["trust_anchor_1_atom_mismatches"] = int(mism)
    assert mism == 0, f"{mism} atom columns disagree with their raw predicate"
    print(f"trust anchor 1: {len(atoms)}/{len(atoms)} atom columns match raw "
          f"predicate", flush=True)

    # ── trust anchor 2: incumbent rules vs frozen picks.json ─────────────────
    rules, split_sha = C.incumbent_rules()
    picks_dev = {}
    import json
    picks = json.load(open(os.path.join(C.STUDY, "results", "picks.json")))
    for r in picks["rules"]:
        picks_dev[r["short"]] = r["dev"]
    for b in picks["baselines"]:
        short = "A@2" if b.get("is_incumbent") else b["name"]
        picks_dev[short] = b["dev"]

    checks = []
    for short in ["A@2", "R1", "R2", "R3", "M_rel_structs >= 1"]:
        if short not in rules:
            continue
        pred = C.eval_rule(df, rules[short])
        s = C.P.score_binary(y_ws, pred, groups, bootstrap=False)
        ref = picks_dev.get(short) or picks_dev.get(rules[short]["name"])
        row = {"rule": short, "expr": rules[short].get("expr"),
               "here_precision": s["precision"], "here_recall": s["recall"],
               "here_predicted": s["predicted"],
               "picks_precision": (ref or {}).get("precision"),
               "picks_recall": (ref or {}).get("recall"),
               "picks_predicted": (ref or {}).get("predicted")}
        if ref:
            row["d_precision"] = abs(s["precision"] - ref["precision"])
            row["d_predicted"] = int(s["predicted"] - ref["predicted"])
        checks.append(row)
        print(f"  {short:20s} here P={s['precision']:.4f} R={s['recall']:.4f} "
              f"n={s['predicted']:5d}   picks P={(ref or {}).get('precision', float('nan')):.4f} "
              f"n={(ref or {}).get('predicted', -1)}", flush=True)
    out["trust_anchor_2_incumbent_checks"] = checks
    out["split_sha256"] = split_sha

    # R1/R2/R3 must be exact under the tier-A restriction.
    for row in checks:
        if row["rule"] in ("R1", "R2", "R3") and row.get("d_predicted") is not None:
            assert row["d_predicted"] == 0, f"{row['rule']} fired-count drifted: {row}"

    # ── save ────────────────────────────────────────────────────────────────
    uniq, codes = np.unique(groups, return_inverse=True)
    os.makedirs(C.CACHE, exist_ok=True)
    np.savez_compressed(
        os.path.join(C.CACHE, "tierA_dev.npz"),
        X=np.packbits(X, axis=0), X_shape=np.array(X.shape),
        y_ws=y_ws, y_strict=y_strict,
        crate_codes=codes.astype(np.int32), crate_names=uniq,
        atom_exprs=np.array(exprs),
        npos_global_ws=np.array(npos_g_ws), npos_global_strict=np.array(npos_g_strict),
    )
    out["cache"] = "cache/tierA_dev.npz"
    out["n_atoms"] = len(atoms)
    out["atom_exprs"] = exprs
    out["elapsed_s"] = round(time.time() - t0, 1)
    C.jdump(out, os.path.join(C.RESULTS, "o00_setup.json"))
    print(f"\nwrote {C.RESULTS}/o00_setup.json  ({out['elapsed_s']}s)", flush=True)


if __name__ == "__main__":
    main()

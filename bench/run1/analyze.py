#!/usr/bin/env python3
"""
run1 analysis — evaluate ALL rules on the corpus, or apply them to one binary.

  python3 analyze.py                 # score every rule on fde/*.parquet -> REPORT.md + results/rules_all.json
  python3 analyze.py --apply BIN     # extract BIN, report which rules fire (no ground truth)

All rules are fixed expressions. Nothing is fitted or selected here.
"""
import argparse, glob, json, os, subprocess, sys, tempfile
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RULEMINE = os.path.join(os.path.dirname(HERE), "rulemine")
sys.path.insert(0, os.path.join(RULEMINE, "lib"))
import mining                     # noqa: E402
import protocol as P              # noqa: E402
EXTRACT = os.path.join(RULEMINE, "extractor", "target", "release", "rulemine_extract")

RS90 = ["G_loc_per_kb <= 4.27 AND N_win_rel >= 1",
        "N_win_rel >= 1 AND N_win_rel_frac >= 0.6",
        "M_rel_frac >= 1 AND G_n_ref_rodata >= 1"]
PICKS = {
    "R1": "M_rel_structs >= 2 AND N_win_rel >= 3",
    "R2": "M_rel_structs >= 2 AND X_caller_rel >= 1",
    "R3": "M_rel_structs >= 1 AND N_win_rel >= 5",
    "A2_incumbent": "C_user >= 2 AND P_nonrel <= 0",
    "bare_structs>=2": "M_rel_structs >= 2",
    "linespan>=2_win>=3": "M_rel_line_span >= 2 AND N_win_rel >= 3",
    "incumbent+win>=3": "C_user >= 2 AND P_nonrel <= 0 AND N_win_rel >= 3",
    "any_anchor": "M_rel_structs >= 1",
}


def all_preds(df):
    out = {}
    cu = df["C_user"].to_numpy() if "C_user" in df else None
    pt = df["P_total"].to_numpy() if "P_total" in df else None
    if cu is not None and pt is not None:
        nonuser = pt - cu
        for n in range(1, 7):
            out[f"A@{n}"] = (cu >= n) & (nonuser == 0)
        if "C_registry" in df and "C_git" in df:
            rg = df["C_registry"].to_numpy() + df["C_git"].to_numpy()
            for n in range(1, 7):
                out[f"B@{n}"] = (cu >= n) & (rg == 0)
        with np.errstate(all="ignore"):
            ratio = np.where(pt > 0, cu / np.maximum(pt, 1), 0.0)
        for r in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
            out[f"C@{r:.2f}"] = (pt > 0) & (ratio >= r)
        out["TRIVIAL:all"] = np.ones(len(df), bool)
        out["TRIVIAL:any-user-loc"] = cu >= 1
    for name, expr in PICKS.items():
        try:
            out[name] = mining.eval_expr(df, expr)
        except Exception as e:                       # noqa: BLE001
            out[name] = "ERR:" + str(e)
    try:
        m = np.zeros(len(df), bool)
        for c in RS90:
            m |= mining.eval_expr(df, c)
        out["RS90"] = m
    except Exception as e:                           # noqa: BLE001
        out["RS90"] = "ERR:" + str(e)
    return out


def _report(res):
    L = [f"# run1 — all rules", "",
         f"{res['n_rows']:,} labelled functions · {res['n_crates']} crates · "
         f"builds {res['n_builds']} · configs {', '.join(res['configs'])}",
         f"split sha `{res['split_sha']}`", ""]
    for variant, vres in res["variants"].items():
        L.append(f"\n## target = {variant}\n")
        for sname, sd in vres.items():
            L.append(f"\n### {sname} — n={sd['n']:,}, base rate {sd['base_rate']:.2%}\n")
            L.append("| rule | fires | prec | prec 95% CI (crate boot) | recall | crates |")
            L.append("|---|---:|---:|---|---:|---:|")
            for rn, r in sd["rules"].items():
                if "error" in r:
                    L.append(f"| {rn} | — | ERR | `{r['error'][:48]}` | — | — |"); continue
                lo, hi = r["precision_cluster_boot"]
                ci = "" if lo != lo else f"[{lo:.1%}, {hi:.1%}]"
                L.append(f"| {rn} | {r['predicted']:,} | {r['precision']:.1%} | {ci} | "
                         f"{r['recall']:.2%} | {r['n_crates_firing']} |")
    open(os.path.join(HERE, "REPORT.md"), "w").write("\n".join(L) + "\n")


def corpus_mode():
    files = sorted(glob.glob(os.path.join(HERE, "fde", "*.parquet")))
    if not files:
        sys.exit("no fde/*.parquet — run build.sh + build_dataset_aux.py first")
    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
    for c in ("crate", "config", "label"):
        if c in df:
            df[c] = df[c].astype(str)
    df = df[~df["label"].isin(["NONE", "UNKNOWN"])].reset_index(drop=True)
    spf = os.path.join(HERE, "split.json")
    split = json.load(open(spf)) if os.path.exists(spf) else {"dev": [], "test": [], "sha256": None}
    preds = all_preds(df)
    res = {"n_rows": len(df), "n_crates": int(df.crate.nunique()),
           "n_builds": int(df.groupby(["crate", "config"]).ngroups),
           "configs": sorted(df.config.unique()), "split_sha": split.get("sha256"), "variants": {}}
    crate_arr = df.crate.to_numpy()
    for variant in ("ws", "strict"):
        y = P.target(df, variant)
        slices = {"pooled": np.ones(len(df), bool)}
        for c in sorted(df.config.unique()):
            slices[f"cfg:{c}"] = (df.config == c).to_numpy()
        if split["dev"]:
            slices["dev_crates"] = df.crate.isin(split["dev"]).to_numpy()
        if split["test"]:
            slices["test_crates"] = df.crate.isin(split["test"]).to_numpy()
        vres = {}
        for sname, smask in slices.items():
            idx = np.where(smask)[0]
            if len(idx) == 0:
                continue
            sub_y, sub_cr = y[idx], crate_arr[idx]
            rr = {}
            for rn, pred in preds.items():
                if isinstance(pred, str):
                    rr[rn] = {"error": pred}; continue
                s = P.score_binary(sub_y, np.asarray(pred)[idx], sub_cr, bootstrap=True, iters=2000)
                rr[rn] = {k: s[k] for k in ("predicted", "tp", "fp", "precision", "recall",
                          "coverage", "base_rate", "precision_cluster_boot",
                          "precision_crate_avg", "n_crates_firing")}
            vres[sname] = {"n": int(len(idx)), "base_rate": float(sub_y.mean()), "rules": rr}
        res["variants"][variant] = vres
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    json.dump(res, open(os.path.join(HERE, "results", "rules_all.json"), "w"), indent=1, default=float)
    _report(res)
    print(f"wrote REPORT.md + results/rules_all.json  ({res['n_rows']:,} fns, {res['n_builds']} builds)")


def apply_mode(binary, outp):
    with tempfile.NamedTemporaryFile("r", suffix=".json", delete=False) as tf:
        raw = tf.name
    try:
        subprocess.run([EXTRACT, binary, "--crate-name", "sample", "--config", "adhoc", "-o", raw],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        rec = {"binary": os.path.basename(binary), "error": e.stderr.decode()[:200]}
        if outp:
            json.dump(rec, open(outp, "w"), indent=1)
        print(json.dumps(rec)); return
    from features import build_rows                  # noqa: E402
    rows, _ = build_rows(json.load(open(raw)), None)
    df = pd.DataFrame(rows)
    preds = all_preds(df)
    fired = {k: int(np.asarray(v).sum()) for k, v in preds.items() if not isinstance(v, str)}
    rec = {"binary": os.path.basename(binary), "n_functions": len(df), "fired": fired}
    if outp:
        json.dump(rec, open(outp, "w"), indent=1)
    print(json.dumps(rec))
    os.unlink(raw)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply")
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.apply:
        apply_mode(a.apply, a.out)
    else:
        corpus_mode()

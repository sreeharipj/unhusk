#!/usr/bin/env python3
"""
mine_gpu.py — the deep rule search on run1, GPU-accelerated, wrapped in an
anti-overfitting gauntlet that RS90 would not have survived.

Why RS90 collapsed (52.5% test P vs ~90% on its 38-crate selection set):
  1. selected on ONE small held-out set — the argmax chased noise
  2. no cross-validation, no stability check across resamples
  3. gated on a POINT precision estimate, not a lower bound
  4. 2 of its 3 OR-clauses fired OUT of the anchored tier (functions with no
     author Location of their own), where precision is a coin flip at scale

This search:
  * headline class is IN-TIER only (M_rel_structs >= 1). A function with no
    author Location of its own is not attributed to the author here.
  * one all-rows pass is kept purely as a pre-registered NEGATIVE control that
    reproduces the RS90 failure mode.
  * every surviving candidate must clear, in order:
      S1  GPU exhaustive pooled search (singles/pairs/triples, 3 taus)
      S2  precision lower bound on the FULL search set: crate cluster-boot
          2.5th pct >= tau - 0.02   (RS90 dies here: lb ~0.52)
      S3  5-fold crate-blocked CV: min-fold precision >= tau - 0.03, fires
          in all 5 folds
      S4  stability selection: in the top-K of >= 50% of 150 crate-bootstrap
          resamples of the search set
      S5  permutation null: held-in global recall beats the 95th pct of 25
          within-crate label-shuffled searches (selection-inflation control)
      S6  beats R3 / A@2 paired over crates (Holm across the survivor family)
      S7  pre-register survivors -> git commit -> ONE pass over the sealed test
          crates  (`mine_gpu.py --final`)

Disjunctions: capped at 2 clauses x 2 atoms; EACH clause must independently
clear S2 at tau-0.05 and not be a per-crate coin flip (CV min >= tau-0.08) —
exactly what RS90 clauses 0 and 1 failed.

GPU: torch (cupy/numba absent). The in-tier space is ~56k rows x ~1500 atoms;
the full search set is evaluated with mining.Bitspace (bit-packed, per-crate
popcount in one pass), so one evaluation per candidate yields S2+S3+S6.
"""
import argparse, glob, hashlib, json, os, subprocess, sys, time
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RULEMINE = os.path.join(os.path.dirname(HERE), "rulemine")
sys.path.insert(0, os.path.join(RULEMINE, "lib"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "scripts"))
import mining, protocol as P                      # noqa: E402
from oracle import cluster_bootstrap             # noqa: E402

os.environ.setdefault("PYTHONUNBUFFERED", "1")
import torch                                      # noqa: E402

DEV = "cuda" if torch.cuda.is_available() else "cpu"
TAUS = [0.95, 0.925, 0.90]
MIN_CRATES = 15
SEARCH_CONFIGS = ["c1", "c2", "c3"]
N_FOLDS = 5
N_STAB = int(os.environ.get("MINE_GPU_STAB", 150))
N_PERM = int(os.environ.get("MINE_GPU_PERM", 25))
STAB_TOPK = 50
KEEP_S1 = int(os.environ.get("MINE_GPU_KEEP", 120))
SEED = 20260901

BASELINES = {
    "A@2": "C_user >= 2 AND P_nonrel <= 0",
    "R1": "M_rel_structs >= 2 AND N_win_rel >= 3",
    "R2": "M_rel_structs >= 2 AND X_caller_rel >= 1",
    "R3": "M_rel_structs >= 1 AND N_win_rel >= 5",
}
RS90 = ["G_loc_per_kb <= 4.27 AND N_win_rel >= 1",
        "N_win_rel >= 1 AND N_win_rel_frac >= 0.6",
        "M_rel_frac >= 1 AND G_n_ref_rodata >= 1"]


def log(*a):
    print(*a, flush=True)


def fold_of(name, k=N_FOLDS):
    return int(hashlib.sha1(name.encode()).hexdigest(), 16) % k


# ── data ──────────────────────────────────────────────────────────────────────

def load(with_allrows=False):
    t0 = time.time()
    df = pd.concat((pd.read_parquet(f) for f in sorted(glob.glob(os.path.join(HERE, "fde", "*.parquet")))),
                   ignore_index=True)
    for c in ("crate", "config", "label"):
        df[c] = df[c].astype(str)
    df = df[~df.label.isin(["NONE", "UNKNOWN"])].reset_index(drop=True)
    split = json.load(open(os.path.join(HERE, "split.json")))
    test_crates = set(split["test"])
    in_cfg = df.config.isin(SEARCH_CONFIGS).to_numpy()
    is_test = df.crate.isin(test_crates).to_numpy()
    search = df[in_cfg & ~is_test].reset_index(drop=True)
    test = df[in_cfg & is_test].reset_index(drop=True)
    allrows = df[in_cfg].reset_index(drop=True) if with_allrows else None
    log(f"[load] {time.time()-t0:.0f}s  search {len(search):,} rows / {search.crate.nunique()} crates | "
        f"test {len(test):,} / {test.crate.nunique()}")
    return search, test, allrows


# ── full-search-set evaluator (bit-packed, one pass -> S2+S3+S6) ──────────────

class Full:
    """mining.Bitspace over the FULL search set + a per-atom packed-mask cache,
    so any conjunction/disjunction is a handful of bitwise ANDs and one popcount
    pass that already carries per-crate counts."""

    def __init__(self, df):
        self.df = df
        self.y = P.target(df, "ws").astype(bool)
        self.crates = df.crate.to_numpy()
        self.space = mining.Bitspace(self.y, self.crates)
        self.cname = list(self.space.crate_names)
        self.fold = np.array([fold_of(c) for c in self.cname])
        self.npos_global = int(self.y.sum())
        self._atom = {}

    def _atom_words(self, expr_atom):
        w = self._atom.get(expr_atom)
        if w is None:
            col, op, t = mining.parse_rule(expr_atom)[0]
            v = self.df[col].to_numpy()
            m = (v >= t) if op == ">=" else (v <= t)
            w = self.space.pack(m)
            self._atom[expr_atom] = w
        return w

    def _conj_words(self, expr):
        parts = expr.split(" AND ")
        w = self._atom_words(parts[0]).copy()
        for p in parts[1:]:
            w &= self._atom_words(p)
        return w

    def words(self, rule):
        """rule: a conjunction string, or a list of conjunction strings (OR)."""
        if isinstance(rule, str):
            return self._conj_words(rule)
        w = self._conj_words(rule[0]).copy()
        for r in rule[1:]:
            w |= self._conj_words(r)
        return w

    def evaluate(self, rule, bootstrap=True):
        w = self.words(rule)
        tp, pred, per_tp, per_pred = self.space.stats(w)
        firing = per_pred > 0
        # cluster-bootstrap lower bound (skip for cheap pre-filter passes)
        if bootstrap:
            clusters = [(int(per_tp[i]), int(per_pred[i] - per_tp[i])) for i in np.nonzero(firing)[0]]
            lb = cluster_bootstrap(clusters, iters=3000, seed=SEED)[1] / 100 if len(clusters) >= 2 else float("nan")
        else:
            lb = float("nan")
        # per-fold pooled precision
        folds = {}
        for f in range(N_FOLDS):
            ci = np.where(self.fold == f)[0]
            t = int(per_tp[ci].sum()); p = int(per_pred[ci].sum())
            folds[f] = (t / p) if p else float("nan")
        fvals = [folds[f] for f in range(N_FOLDS)]
        fires_all = all(not np.isnan(x) for x in fvals)
        # per-crate dicts for paired bootstrap (protocol shape)
        per = {}
        for i, cn in enumerate(self.cname):
            if per_pred[i] == 0 and self.space.pos_per_crate[i] == 0:
                continue
            per[cn] = {"tp": int(per_tp[i]), "predicted": int(per_pred[i]),
                       "n_pos": int(self.space.pos_per_crate[i]),
                       "precision": (per_tp[i] / per_pred[i]) if per_pred[i] else float("nan"),
                       "recall": (per_tp[i] / self.space.pos_per_crate[i]) if self.space.pos_per_crate[i] else float("nan")}
        return {"tp": int(tp), "pred": int(pred),
                "precision": (tp / pred) if pred else float("nan"),
                "recall": tp / self.npos_global,
                "recall_global": tp / self.npos_global,
                "lb": lb, "crates_firing": int(firing.sum()),
                "fold_prec": fvals, "fold_min": (np.nanmin(fvals) if any(not np.isnan(x) for x in fvals) else float("nan")),
                "fold_mean": (float(np.nanmean(fvals)) if fires_all else float("nan")),
                "fires_all_folds": fires_all, "per_crate": per,
                "out_of_tier_frac": self._oot(w)}

    def _oot(self, w):
        if not hasattr(self, "_tier_words"):
            self._tier_words = self.space.pack((self.df["M_rel_structs"].to_numpy() >= 1))
        pred = int(np.bitwise_count(w).sum())
        oot = int(np.bitwise_count(w & ~self._tier_words).sum())
        return (oot / pred) if pred else 0.0


# ── GPU tier bitspace (S1 discovery, S4/S5 resample loops) ───────────────────

class GPU:
    def __init__(self, X, y, crate_codes, n_crates):
        self.X = torch.as_tensor(X, dtype=torch.float32, device=DEV)
        self.y = torch.as_tensor(y, dtype=torch.float32, device=DEV)
        self.Xy = self.X * self.y
        oh = torch.zeros(n_crates, len(y), dtype=torch.float32, device=DEV)
        oh[torch.as_tensor(crate_codes, dtype=torch.long, device=DEV),
           torch.arange(len(y), device=DEV)] = 1.0
        self.C = oh
        self.Cy = oh * self.y
        self.n_crates = n_crates
        self.A = self.X.shape[0]

    def pairs(self):
        return self.Xy @ self.X.T, self.X @ self.X.T          # tp, pred  [A,A]

    def mask_of(self, idx):
        m = self.X[idx[0]].clone()
        for i in idx[1:]:
            m = m * self.X[i]
        return m

    def crates_firing(self, masks):                          # masks [B,n] -> [B]
        return ((torch.clamp(masks, max=1.0) @ self.C.T) > 0).sum(1)


def build_atoms(dtier):
    cols = P.feature_cols(dtier)
    atoms = mining.make_atoms(dtier, cols, max_thresholds=14, min_support=200)
    bs = mining.Bitspace(P.target(dtier, "ws"), dtier.crate.to_numpy())
    atoms = mining.dedupe_atoms(atoms, bs)
    X = np.stack([a["mask"].astype(np.float32) for a in atoms])
    return atoms, X, cols


# ── S1 ───────────────────────────────────────────────────────────────────────

def s1_search(g, atoms, npos_global, taus=TAUS, keep=KEEP_S1):
    A = g.A
    tp2, pred2 = g.pairs()
    iu = torch.triu_indices(A, A, offset=1, device=DEV)
    tp_p, pred_p = tp2[iu[0], iu[1]], pred2[iu[0], iu[1]]
    prec_p = torch.where(pred_p > 0, tp_p / pred_p.clamp(min=1), torch.zeros_like(tp_p))
    rec_p = tp_p / npos_global
    tp_s, pred_s = torch.diagonal(tp2), torch.diagonal(pred2)
    prec_s = torch.where(pred_s > 0, tp_s / pred_s.clamp(min=1), torch.zeros_like(tp_s))

    out = {}
    for tau in taus:
        cand = {}
        for i in torch.nonzero((prec_s >= tau) & (pred_s > 0)).flatten().tolist():
            cand[(i,)] = (atoms[i]["expr"], float(tp_s[i]), float(pred_s[i]))
        idxp = torch.nonzero((prec_p >= tau) & (pred_p > 0)).flatten()
        for e in idxp.tolist():
            i, j = int(iu[0][e]), int(iu[1][e])
            cand[(i, j)] = (f"{atoms[i]['expr']} AND {atoms[j]['expr']}", float(tp_p[e]), float(pred_p[e]))
        # triples: shortlist high-tp pairs, AND against every atom on-GPU
        sl = torch.nonzero((pred_p > 0) & (tp_p >= 0.01 * npos_global)).flatten()
        sl = sl[torch.argsort(tp_p[sl], descending=True)][:4000]
        if len(sl):
            pr = [(int(iu[0][e]), int(iu[1][e])) for e in sl.tolist()]
            PM = torch.stack([g.X[i] * g.X[j] for i, j in pr])
            t_pred = PM @ g.X.T
            t_tp = (PM * g.y) @ g.X.T
            t_prec = torch.where(t_pred > 0, t_tp / t_pred.clamp(min=1), torch.zeros_like(t_pred))
            okt = (t_prec >= tau) & (t_pred > 0) & (t_tp >= 0.015 * npos_global)
            si, sk = torch.nonzero(okt, as_tuple=True)
            if len(si):
                order = torch.argsort(t_tp[si, sk], descending=True)[:3000]
                si, sk = si[order].tolist(), sk[order].tolist()
                tph, pdh = t_tp.cpu().numpy(), t_pred.cpu().numpy()
                for s_, k_ in zip(si, sk):
                    i, j = pr[s_]
                    if k_ in (i, j):
                        continue
                    key = tuple(sorted((i, j, k_)))
                    if key in cand:
                        continue
                    cand[key] = (" AND ".join(atoms[x]["expr"] for x in key),
                                 float(tph[s_, k_]), float(pdh[s_, k_]))
        rows = [{"atoms": list(k), "expr": v[0], "tp": v[1], "pred": v[2],
                 "precision": v[1] / v[2] if v[2] else 0.0, "recall_global": v[1] / npos_global}
                for k, v in cand.items()]
        rows.sort(key=lambda r: (-r["recall_global"], -r["precision"]))
        top = rows[: keep * 3]
        if top:
            M = torch.stack([g.mask_of(tuple(r["atoms"])) for r in top])
            cf = g.crates_firing(M).cpu().numpy()
            top = [r for r, c in zip(top, cf) if c >= MIN_CRATES]
        out[str(tau)] = top[:keep]
        log(f"[S1] tau={tau}: {len(rows)} unique candidates -> {len(out[str(tau)])} with >= {MIN_CRATES} crates firing")
    return out


# ── S4 stability ─────────────────────────────────────────────────────────────

def s4_stability(g, npos_global, tau, n_resamp=N_STAB):
    rng = np.random.default_rng(SEED)
    K = g.n_crates
    A = g.A
    iu = torch.triu_indices(A, A, offset=1, device=DEV)
    counts = {}
    for _ in range(n_resamp):
        w = torch.bincount(torch.as_tensor(rng.integers(0, K, size=K), device=DEV), minlength=K).float()
        roww = g.C.T @ w
        Xw = g.X * roww
        pred = Xw @ g.X.T
        tp = (Xw * g.y) @ g.X.T
        pr = torch.where(pred > 0, tp / pred.clamp(min=1), torch.zeros_like(tp))
        rec = tp / max(npos_global, 1)
        pr_p, pred_p, rec_p = pr[iu[0], iu[1]], pred[iu[0], iu[1]], rec[iu[0], iu[1]]
        ok = (pr_p >= tau) & (pred_p > 0)
        if ok.sum() == 0:
            continue
        sel = torch.nonzero(ok).flatten()
        order = torch.argsort(rec_p[sel], descending=True)[:STAB_TOPK]
        for e in sel[order].tolist():
            key = (int(iu[0][e]), int(iu[1][e]))
            counts[key] = counts.get(key, 0) + 1
    return {k: v / n_resamp for k, v in counts.items()}


# ── S5 permutation null ──────────────────────────────────────────────────────

def s5_permutation(g, dtier, npos_global, tau, n_perm=N_PERM):
    rng = np.random.default_rng(SEED + 7)
    y0 = P.target(dtier, "ws").astype(np.float32)
    codes = pd.factorize(dtier.crate.to_numpy())[0]
    groups = [np.where(codes == c)[0] for c in np.unique(codes)]
    A = g.A
    iu = torch.triu_indices(A, A, offset=1, device=DEV)
    best = []
    for _ in range(n_perm):
        yp = y0.copy()
        for m in groups:
            yp[m] = y0[m][rng.permutation(len(m))]
        yt = torch.as_tensor(yp, device=DEV)
        pred = g.X @ g.X.T
        tp = (g.X * yt) @ g.X.T
        pr = torch.where(pred > 0, tp / pred.clamp(min=1), torch.zeros_like(tp))
        rec = tp / npos_global
        pr_p, pred_p, rec_p = pr[iu[0], iu[1]], pred[iu[0], iu[1]], rec[iu[0], iu[1]]
        ok = (pr_p >= tau) & (pred_p > 0)
        best.append(float(rec_p[ok].max()) if ok.any() else 0.0)
    b = np.array(best)
    return {"mean": float(b.mean()), "p95": float(np.quantile(b, 0.95)),
            "max": float(b.max()), "all": [round(x, 4) for x in b.tolist()]}


# ── S6 paired vs baselines ──────────────────────────────────────────────────

def paired(full, cand_per, bname, iters=5000):
    sb = full.evaluate(BASELINES[bname])
    dP, loP, hiP = P.paired_crate_bootstrap(cand_per, sb["per_crate"], "precision", iters)
    dR, loR, hiR = P.paired_crate_bootstrap(cand_per, sb["per_crate"], "recall", iters)
    pP = P.paired_crate_bootstrap_p(cand_per, sb["per_crate"], "precision", iters + 2000)
    return {"dP": dP, "dP_ci": [loP, hiP], "dP_p": pP, "dR": dR, "dR_ci": [loR, hiR]}


# ── disjunction search (tight cap) ─────────────────────────────────────────

def disj_search(g, atoms, full, npos_global, tau):
    A = g.A
    tp2, pred2 = g.pairs()
    iu = torch.triu_indices(A, A, offset=1, device=DEV)
    tp_s, pred_s = torch.diagonal(tp2), torch.diagonal(pred2)
    pool = []
    for i in torch.nonzero((pred_s > 0) & (tp_s / pred_s.clamp(min=1) >= tau - 0.05)).flatten().tolist():
        pool.append(atoms[i]["expr"])
    tp_p, pred_p = tp2[iu[0], iu[1]], pred2[iu[0], iu[1]]
    pr_p = torch.where(pred_p > 0, tp_p / pred_p.clamp(min=1), torch.zeros_like(tp_p))
    good = torch.nonzero((pred_p > 0) & (pr_p >= tau - 0.05) & (tp_p >= 0.02 * npos_global)).flatten()
    good = good[torch.argsort(tp_p[good], descending=True)][:150]
    for e in good.tolist():
        i, j = int(iu[0][e]), int(iu[1][e])
        pool.append(f"{atoms[i]['expr']} AND {atoms[j]['expr']}")
    log(f"[disj tau={tau}] clause pool {len(pool)}")
    keep = []
    for expr in pool:
        s = full.evaluate(expr, bootstrap=False)          # cheap pooled+CV pre-filter
        if not s["fires_all_folds"] or s["fold_min"] < tau - 0.08:
            continue
        s = full.evaluate(expr)                            # bootstrap only survivors
        if np.isnan(s["lb"]) or s["lb"] < tau - 0.05:
            continue
        keep.append({"expr": expr, "lb": s["lb"], "fold_min": s["fold_min"], "Rg": s["recall_global"]})
    keep.sort(key=lambda k: -k["lb"])
    keep = keep[:45]
    log(f"[disj tau={tau}] clauses passing S2(tau-0.05)+per-clause CV: {len(keep)}")
    res = []
    for a in range(len(keep)):
        for b in range(a + 1, len(keep)):
            rule = [keep[a]["expr"], keep[b]["expr"]]
            s = full.evaluate(rule, bootstrap=False)       # cheap gate first
            if s["precision"] < tau or s["crates_firing"] < MIN_CRATES:
                continue
            if not s["fires_all_folds"] or s["fold_min"] < tau - 0.03:
                continue
            s = full.evaluate(rule)                        # bootstrap the few that pass
            if np.isnan(s["lb"]) or s["lb"] < tau - 0.02:
                continue
            res.append({"expr": rule, "is_disj": True, "tau": tau,
                        "s2_prec": s["precision"], "s2_lb": s["lb"], "s2_recall": s["recall"],
                        "recall_global": s["recall_global"], "cv_min_prec": s["fold_min"],
                        "cv_mean_prec": s["fold_mean"], "cv_folds": [round(x, 4) for x in s["fold_prec"]],
                        "out_of_tier_frac": s["out_of_tier_frac"], "per_crate": s["per_crate"]})
    res.sort(key=lambda c: (-(c["cv_min_prec"] or 0), -c["recall_global"]))
    return res


# ── negative control ───────────────────────────────────────────────────────

def negative_control(atoms, npos_global, full):
    _, _, allrows = load(with_allrows=True)
    y = P.target(allrows, "ws").astype(np.float32)
    cols_needed = sorted({a["col"] for a in atoms})
    V = {c: allrows[c].to_numpy() for c in cols_needed}          # ~60 columns, not 1328
    n, A = len(allrows), len(atoms)
    tp = np.zeros((A, A)); pred = np.zeros((A, A))
    step = 400_000
    for s in range(0, n, step):
        sl = slice(s, s + step)
        # build the [A, tile] atom matrix for THIS tile only (never the whole n)
        xb = torch.as_tensor(
            np.stack([((V[a["col"]][sl] >= a["t"]) if a["op"] == ">=" else (V[a["col"]][sl] <= a["t"]))
                      for a in atoms]).astype(np.float32), device=DEV)
        yb = torch.as_tensor(y[sl], device=DEV)
        pred += (xb @ xb.T).cpu().numpy()
        tp += ((xb * yb) @ xb.T).cpu().numpy()
        del xb, yb
    torch.cuda.empty_cache()
    with np.errstate(invalid="ignore", divide="ignore"):
        prec = np.where(pred > 0, tp / np.maximum(pred, 1), 0.0)
    rec = tp / npos_global
    iu = np.triu_indices(A, 1)
    ok = (prec[iu] >= 0.90) & (pred[iu] > 0)
    if ok.sum() == 0:
        return {"note": "no all-rows pair reached prec >= 0.90 on all-rows pooled"}
    ci, cj, cr = iu[0][ok], iu[1][ok], rec[iu][ok]
    order = np.argsort(-cr)[:15]
    rows = []
    for e in order:
        i, j = int(ci[e]), int(cj[e])
        expr = f"{atoms[i]['expr']} AND {atoms[j]['expr']}"
        s = full.evaluate(expr)   # measured on the search set (has GT + folds)
        rows.append({"expr": expr, "allrows_pooled_prec": float(prec[i, j]),
                     "allrows_recall_global": float(rec[i, j]),
                     "search_P": s["precision"], "search_lb": s["lb"],
                     "search_out_of_tier_frac": s["out_of_tier_frac"],
                     "search_cv_min_prec": s["fold_min"],
                     "passes_cv_at_0.90": bool(s["fires_all_folds"] and s["fold_min"] >= 0.87)})
    del allrows
    return {"top_by_allrows_recall": rows,
            "summary": "high-recall all-rows rules escape the anchored tier and "
                       "fail CV — RS90's failure mode, reproduced under control"}


# ── prereg ────────────────────────────────────────────────────────────────

def write_prereg(report):
    p = os.path.join(HERE, "MINE_GPU_PREREG.md")
    L = ["# mine_gpu — pre-registration of sealed-test candidates", "",
         f"Written {time.strftime('%Y-%m-%d %H:%M:%S')} by mine_gpu.py BEFORE any test-set read.",
         f"Split sha `{json.load(open(os.path.join(HERE,'split.json'))).get('sha','?')}`; "
         "test crates read exactly once by `mine_gpu.py --final`.", "",
         "## Decision rule (fixed in advance)", "",
         "A candidate is a POSITIVE result iff, on the sealed test crates:",
         "1. test precision (pooled, ws) >= tau - 0.03, AND",
         "2. test precision cluster-bootstrap 2.5th pct >= tau - 0.05, AND",
         "3. paired crate bootstrap vs R3: recall delta > 0 with 95% CI excluding 0,",
         "   OR precision delta > 0 with 95% CI excluding 0 — no significant loss on",
         "   the other axis; Holm-corrected across the family below.", "",
         "Anything failing 1-3 is a NEGATIVE: the readable-rule class is capped at R3.", "",
         "## Pre-registered candidates", ""]
    surv = report["survivors_preregister"]
    if not surv:
        L += ["**NONE.** No candidate survived S1-S6. The negative result stands and the "
              "sealed test set is NOT consumed."]
    for i, c in enumerate(surv, 1):
        expr = c["expr"] if isinstance(c["expr"], str) else " OR ".join(c["expr"])
        L += [f"### C{i}  {'(disjunction) ' if c.get('is_disj') else ''}tau = {c['tau']}",
              "```", expr, "```",
              f"- held-in precision {c['search_P']:.3f}  lb {c['search_lb']:.3f}  global recall {c['search_Rg']:.3f}",
              f"- CV min-fold precision {c['cv_min_prec']:.3f}  mean {c['cv_mean_prec']:.3f}  folds {c['cv_folds']}",
              f"- stability {c['stab_freq']}  ·  beats permutation p95: {c['beats_perm_p95']}  ·  out-of-tier {c['out_of_tier_frac']:.3f}",
              f"- vs R3  dP {c['vs_R3']['dP']:+.2f}pp {c['vs_R3']['dP_ci']}  dR {c['vs_R3']['dR']:+.2f}pp {c['vs_R3']['dR_ci']}",
              f"- vs A@2 dP {c['vs_A@2']['dP']:+.2f}pp {c['vs_A@2']['dP_ci']}  dR {c['vs_A@2']['dR']:+.2f}pp {c['vs_A@2']['dR_ci']}",
              ""]
    open(p, "w").write("\n".join(L))
    log(f"[prereg] wrote {p}")


# ── orchestration ────────────────────────────────────────────────────────

def run(_):
    t0 = time.time()
    log(f"[env] torch {torch.__version__}  device {DEV}  "
        f"{torch.cuda.get_device_name(0) if DEV == 'cuda' else ''}")
    search, test, _ = load()
    full = Full(search)
    npos_global = full.npos_global
    log(f"[full] {len(search):,} rows / {len(full.cname)} crates | global author fns {npos_global:,} "
        f"(base {full.y.mean():.3%})")

    tier = search["M_rel_structs"].to_numpy() >= 1
    dtier = search[tier].reset_index(drop=True)
    yt = P.target(dtier, "ws").astype(np.float32)
    codes, uniq = pd.factorize(dtier.crate.to_numpy())
    log(f"[tier] {len(dtier):,} rows / {len(uniq)} crates  ({time.time()-t0:.0f}s)")

    atoms, X, cols = build_atoms(dtier)
    log(f"[atoms] {len(atoms)} atoms from {len(cols)} features  ({time.time()-t0:.0f}s)")
    g = GPU(X, yt, codes, len(uniq))

    base = {}
    for nm, ex in list(BASELINES.items()) + [("RS90", RS90)]:
        s = full.evaluate(ex)
        base[nm] = {"search_P": s["precision"], "search_lb": s["lb"], "search_r": s["recall"],
                    "search_Rg": s["recall_global"], "out_of_tier_frac": s["out_of_tier_frac"],
                    "cv_min": s["fold_min"], "per_crate": s["per_crate"]}
        log(f"[base] {nm:5} P={s['precision']:.3f} lb={s['lb']:.3f} Rg={s['recall_global']:.3f} "
            f"cvmin={s['fold_min']:.3f} oot={s['out_of_tier_frac']:.2f}")

    s1 = s1_search(g, atoms, npos_global)

    report = {"env": {"torch": torch.__version__, "gpu": torch.cuda.get_device_name(0) if DEV == "cuda" else None},
              "search_rows": int(len(search)), "search_crates": int(len(full.cname)),
              "tier_rows": int(len(dtier)), "npos_global": npos_global, "n_atoms": len(atoms),
              "n_stab": N_STAB, "n_perm": N_PERM, "baselines": {k: {kk: vv for kk, vv in v.items() if kk != "per_crate"}
                                                               for k, v in base.items()},
              "taus": {}, "disjunction": {}}
    survivors = []

    for tau in TAUS:
        tk = str(tau)
        cands = s1[tk]
        log(f"\n===== tau {tau}: {len(cands)} S1 candidates =====")
        # S2 + S3 in one evaluation each
        s23 = []
        for c in cands:
            pre = full.evaluate(c["expr"], bootstrap=False)
            if not pre["fires_all_folds"] or pre["fold_min"] < tau - 0.03:
                c.update({"s2_lb": float("nan"), "cv_min_prec": pre["fold_min"],
                          "recall_global": pre["recall_global"],
                          "out_of_tier_frac": pre["out_of_tier_frac"]})
                continue
            s = full.evaluate(c["expr"])
            c.update({"s2_prec": s["precision"], "s2_lb": s["lb"], "s2_recall": s["recall"],
                      "recall_global": s["recall_global"], "cv_folds": [round(x, 4) for x in s["fold_prec"]],
                      "cv_min_prec": s["fold_min"], "cv_mean_prec": s["fold_mean"],
                      "out_of_tier_frac": s["out_of_tier_frac"], "per_crate": s["per_crate"],
                      "crates_firing": s["crates_firing"]})
            if np.isnan(c["s2_lb"]) or c["s2_lb"] < tau - 0.02:
                continue
            if not s["fires_all_folds"] or c["cv_min_prec"] < tau - 0.03:
                continue
            s23.append(c)
        log(f"[S2+S3] lb >= {tau-0.02:.3f} AND CV-min >= {tau-0.03:.3f} in all folds: {len(s23)}/{len(cands)}")
        for c in s23:
            log(f"     {c['expr'][:64]:64s} lb={c['s2_lb']:.3f} cvmin={c['cv_min_prec']:.3f} "
                f"Rg={c['recall_global']:.3f} oot={c['out_of_tier_frac']:.2f}")
        # S4
        stab = s4_stability(g, npos_global, tau) if s23 else {}
        for c in s23:
            ai = c["atoms"]
            ps = [tuple(sorted((ai[a], ai[b]))) for a in range(len(ai)) for b in range(a + 1, len(ai))]
            c["stab_freq"] = max([stab.get(p, 0.0) for p in ps], default=0.0)
        s4 = [c for c in s23 if c["stab_freq"] >= 0.50]
        log(f"[S4] stability >= 0.50 over {N_STAB} resamples: {len(s4)}/{len(s23)}")
        # S5
        perm = s5_permutation(g, dtier, npos_global, tau) if s4 else None
        s5 = []
        if perm:
            log(f"[S5] perm best-recall  mean={perm['mean']:.3f}  p95={perm['p95']:.3f}  max={perm['max']:.3f}")
            for c in s4:
                c["beats_perm_p95"] = bool(c["recall_global"] > perm["p95"])
                c["beats_perm_max"] = bool(c["recall_global"] > perm["max"])
                if c["beats_perm_p95"]:
                    s5.append(c)
        log(f"[S5] held-in global recall > perm p95: {len(s5)}/{len(s4)}")
        # S6
        for c in s5:
            c["vs_R3"] = paired(full, c["per_crate"], "R3")
            c["vs_A@2"] = paired(full, c["per_crate"], "A@2")
            c["tau"] = tau
        report["taus"][tk] = {
            "n_s1": len(cands), "n_s23": len(s23), "n_s4": len(s4), "n_s5": len(s5), "perm": perm,
            "s1_all": [{"expr": c["expr"], "s1_prec": round(c["precision"], 4),
                        "s1_Rg": round(c["recall_global"], 4),
                        "cv_min": (None if np.isnan(c.get("cv_min_prec", np.nan)) else round(c["cv_min_prec"], 4)),
                        "oot": round(c.get("out_of_tier_frac", 0.0), 3)} for c in cands],
            "candidates": [_strip(c) for c in s23],
            "survivors": [_strip(c) for c in s5]}
        survivors += s5

    for tau in (0.95, 0.925):
        dq = disj_search(g, atoms, full, npos_global, tau)
        log(f"[disj tau={tau}] union candidates passing S2+S3: {len(dq)}")
        # S6 on the top unions; a disjunction is only pre-registered if it beats
        # R3 with a CI excluding 0 on at least one axis (the conjunction bar).
        for c in dq[:12]:
            c["stab_freq"] = None
            c["beats_perm_p95"] = None
            c["vs_R3"] = paired(full, c["per_crate"], "R3")
            c["vs_A@2"] = paired(full, c["per_crate"], "A@2")
        report["disjunction"][str(tau)] = [_strip(c) for c in dq[:12]]
        beat = [c for c in dq[:12]
                if (c["vs_R3"]["dR"] > 0 and c["vs_R3"]["dR_ci"][0] > 0)
                or (c["vs_R3"]["dP"] > 0 and c["vs_R3"]["dP_ci"][0] > 0)]
        beat.sort(key=lambda c: -c["vs_R3"]["dR"])
        log(f"[disj tau={tau}] unions beating R3 (CI excludes 0): {len(beat)}")
        survivors += beat[:3]

    # checkpoint BEFORE the negative control (it reloads 6.9M rows)
    _dump(report, survivors, t0)
    report["negative_control"] = negative_control(atoms, npos_global, full)
    _dump(report, survivors, t0)
    write_prereg(report)
    log(f"\n[done] {report.get('elapsed_s')}s — {len(survivors)} survivor(s) pre-registered.")
    log("       results/mine_gpu.json + MINE_GPU_PREREG.md.  Commit the prereg, then: mine_gpu.py --final")


def _dump(report, survivors, t0):
    report["survivors_preregister"] = [{
        "expr": c["expr"], "tau": c.get("tau"), "is_disj": c.get("is_disj", False),
        "search_P": c.get("s2_prec"), "search_lb": c.get("s2_lb"), "search_Rg": c.get("recall_global"),
        "cv_min_prec": c.get("cv_min_prec"), "cv_mean_prec": c.get("cv_mean_prec"),
        "cv_folds": c.get("cv_folds"), "stab_freq": c.get("stab_freq"),
        "beats_perm_p95": c.get("beats_perm_p95"), "out_of_tier_frac": c.get("out_of_tier_frac"),
        "vs_R3": c.get("vs_R3"), "vs_A@2": c.get("vs_A@2")} for c in survivors]
    report["elapsed_s"] = round(time.time() - t0, 1)
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    json.dump(report, open(os.path.join(HERE, "results", "mine_gpu.json"), "w"), indent=1, default=_json)


def _strip(c):
    return {k: v for k, v in c.items() if k not in ("atoms", "per_crate")}


def _json(x):
    if isinstance(x, (np.floating, np.integer)):
        return float(x)
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, (np.bool_,)):
        return bool(x)
    return str(x)


# ── S7: the single sealed-test pass ─────────────────────────────────────────

def final(_):
    prereg = os.path.join(HERE, "MINE_GPU_PREREG.md")
    if not os.path.exists(prereg):
        sys.exit("no MINE_GPU_PREREG.md — run `mine_gpu.py` first")
    r = subprocess.run(["git", "-C", HERE, "status", "--porcelain", "--", prereg],
                       capture_output=True, text=True)
    if r.stdout.strip():
        sys.exit("MINE_GPU_PREREG.md is not committed — commit it before consuming the test set.")
    rep = json.load(open(os.path.join(HERE, "results", "mine_gpu.json")))
    cands = rep["survivors_preregister"]
    if not cands:
        log("no pre-registered candidates — negative result stands, test set untouched.")
        return
    search, test, _ = load()
    ftest = Full(test)
    fsearch = Full(search)
    r3_test = ftest.evaluate(BASELINES["R3"])
    rows, fam_p = [], []
    for c in cands:
        st = ftest.evaluate(c["expr"])
        dP, loP, hiP = P.paired_crate_bootstrap(st["per_crate"], r3_test["per_crate"], "precision", 6000)
        dR, loR, hiR = P.paired_crate_bootstrap(st["per_crate"], r3_test["per_crate"], "recall", 6000)
        pP = P.paired_crate_bootstrap_p(st["per_crate"], r3_test["per_crate"], "precision", 8000)
        fam_p.append(pP)
        rows.append({"expr": c["expr"], "tau": c["tau"], "is_disj": c["is_disj"],
                     "test_P": st["precision"], "test_P_lb": st["lb"], "test_recall": st["recall"],
                     "test_Rg": st["recall_global"], "test_crates_firing": st["crates_firing"],
                     "test_out_of_tier_frac": st["out_of_tier_frac"],
                     "vs_R3_dP": dP, "vs_R3_dP_ci": [loP, hiP], "vs_R3_dP_p": pP,
                     "vs_R3_dR": dR, "vs_R3_dR_ci": [loR, hiR]})
    adj = P.holm(fam_p)
    for row, a in zip(rows, adj):
        tau = row["tau"]
        c1 = row["test_P"] >= tau - 0.03
        c2 = (not np.isnan(row["test_P_lb"])) and row["test_P_lb"] >= tau - 0.05
        c3 = ((row["vs_R3_dR"] > 0 and row["vs_R3_dR_ci"][0] > 0) or
              (row["vs_R3_dP"] > 0 and row["vs_R3_dP_ci"][0] > 0))
        row["holm_p"] = a
        row["POSITIVE"] = bool(c1 and c2 and c3)
    json.dump({"test_crates": int(test.crate.nunique()), "r3_test":
               {k: r3_test[k] for k in ("precision", "recall", "lb")}, "rows": rows},
              open(os.path.join(HERE, "results", "mine_gpu_test.json"), "w"), indent=1, default=_json)
    for row in rows:
        e = row["expr"] if isinstance(row["expr"], str) else " OR ".join(row["expr"])
        log(f"{'POS' if row['POSITIVE'] else 'neg'}  {e[:60]:60s} testP={row['test_P']:.3f} "
            f"lb={row['test_P_lb']:.3f} r={row['test_recall']:.3f} dR={row['vs_R3_dR']:+.2f} "
            f"dRci={[round(x,2) for x in row['vs_R3_dR_ci']]} holm_p={row['holm_p']:.3f}")
    npos = sum(row["POSITIVE"] for row in rows)
    log(f"\n{'POSITIVE' if npos else 'NEGATIVE'}: {npos}/{len(rows)} pre-registered candidates beat R3 on the sealed test set.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", action="store_true", help="consume the sealed test set (needs committed prereg)")
    a = ap.parse_args()
    (final if a.final else run)(a)

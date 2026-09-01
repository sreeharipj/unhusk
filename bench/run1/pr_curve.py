#!/usr/bin/env python3
"""
size_analysis.py — the nuanced version of "we catch bigger functions".

Three questions, c1 (shipped default), ws target:

  Q1  Where in the size distribution does the method work?  recall of R3 / A@2 /
      the anchored ceiling, per size decile of author functions.
  Q2  Is it JUST size?  Within each size band, does the rule's precision beat
      the band's base rate — i.e. is there author signal after size is fixed,
      or is multiplicity a size threshold in disguise?
  Q3  Function-recall vs byte-recall, once, with the caveat stated.
  +   the precision / recall frontier (OOF logistic), quoted points + linear
      slope only (no functional-form fit — that would overclaim).
"""
import glob, hashlib, json, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, "bench/rulemine/lib")
import mining, protocol as P  # noqa

CFG = "c1"
FEATS = ["M_rel_structs", "M_rel_frac", "M_rel_files", "N_win_rel", "N_win_rel_frac",
         "C_user", "X_caller_rel", "G_loc_per_kb", "F_rel_fo_mean", "B_frac_rel_fde"]
RULES = {"A@2": "C_user >= 2 AND P_nonrel <= 0",
         "R3": "M_rel_structs >= 1 AND N_win_rel >= 5",
         "any_anchor": "M_rel_structs >= 1"}


def sigmoid(z): return 1.0 / (1.0 + np.exp(-z))


def fit_logreg(X, y, iters=400, lr=0.5, l2=1e-3):
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Xs = np.c_[np.ones(len(X)), (X - mu) / sd]
    w = np.zeros(Xs.shape[1])
    for _ in range(iters):
        g = Xs.T @ (sigmoid(Xs @ w) - y) / len(y) + l2 * np.r_[0, w[1:]]
        w -= lr * g
    return w, mu, sd


def predict(w, mu, sd, X):
    return sigmoid(np.c_[np.ones(len(X)), (X - mu) / sd] @ w)


def main():
    df = pd.concat((pd.read_parquet(f) for f in sorted(glob.glob("bench/run1/fde/*.parquet"))
                    if f.endswith(f"__{CFG}.parquet")), ignore_index=True)
    for c in ("crate", "label"):
        df[c] = df[c].astype(str)
    df = df[~df.label.isin(["NONE", "UNKNOWN"])].reset_index(drop=True)
    y = P.target(df, "ws")
    size = df["G_size"].to_numpy().astype(float)
    crate = df["crate"].to_numpy()
    npos, totB = int(y.sum()), float(size[y].sum())
    print(f"c1  {len(df):,} fns / {df.crate.nunique()} crates | "
          f"author {npos:,} fns  {totB/1e6:.2f} MB  (median author fn "
          f"{np.median(size[y]):.0f} B, non-author median {np.median(size[~y]):.0f} B)\n")

    # ---- Q1: recall per size decile of AUTHOR functions ----
    aq = np.quantile(size[y], np.linspace(0, 1, 11))
    aq[-1] += 1
    band = np.digitize(size, aq) - 1          # 0..9 for author-fn size scale
    preds = {n: mining.eval_expr(df, e) for n, e in RULES.items()}
    print("Q1  recall within each author-fn size decile")
    print(f"    {'decile':22s} {'nAuthor':>8s} {'A@2':>7s} {'R3':>7s} {'ceiling':>8s}")
    for b in range(10):
        m = (band == b) & y
        lo, hi = aq[b], aq[b + 1]
        if m.sum() == 0:
            continue
        r = {n: (preds[n] & m).sum() / m.sum() for n in RULES}
        print(f"    [{lo:6.0f},{hi:7.0f})B      {m.sum():8d} "
              f"{r['A@2']:7.2%} {r['R3']:7.2%} {r['any_anchor']:8.2%}")

    # ---- Q2: is it just size?  band-controlled precision vs base rate ----
    # size bands over ALL functions (log-spaced), compare rule precision to the
    # band base rate and to a pure size cut at the same recall.
    edges = np.array([0, 128, 256, 512, 1024, 2048, 4096, 8192, 1e9])
    sb = np.digitize(size, edges) - 1
    print("\nQ2  within a size band, does the rule beat the band's base rate?")
    print(f"    {'band':16s} {'nFns':>8s} {'base%':>7s} {'R3 prec':>9s} {'R3 rec':>8s} "
          f"{'lift':>6s}")
    for b in range(len(edges) - 1):
        m = sb == b
        if m.sum() < 200:
            continue
        base = y[m].mean()
        r3 = preds["R3"] & m
        pr = (r3 & y).sum() / max(r3.sum(), 1)
        rc = (r3 & y).sum() / max(y[m].sum(), 1)
        lo, hi = edges[b], edges[b + 1]
        tag = f"{lo:.0f}-{hi:.0f}B" if hi < 1e8 else f">{lo:.0f}B"
        print(f"    {tag:16s} {m.sum():8d} {base:7.2%} "
              f"{pr:9.2%} {rc:8.2%} {pr/max(base,1e-9):6.1f}x")
    print("    (lift >> 1 in a band = author signal beyond size; lift ~1 = size proxy)")

    # ---- Q3: fn-recall vs byte-recall for the rules + the ceiling ----
    print("\nQ3  function-recall vs byte-recall  (byte-recall rewards the size bias — stated)")
    anch = df["M_rel_structs"].to_numpy() >= 1
    print(f"    ceiling      fn {(anch&y).sum()/npos:6.2%}   byte {size[anch&y].sum()/totB:6.2%}")
    for n in ("A@2", "R3"):
        tp = preds[n] & y
        print(f"    {n:12s} fn {tp.sum()/npos:6.2%}   byte {size[tp].sum()/totB:6.2%}   "
              f"(mean TP {size[tp].sum()/max(tp.sum(),1):.0f} B vs author median "
              f"{np.median(size[y]):.0f} B)")

    # ---- frontier: OOF logistic, quoted points + linear slope ----
    X = np.nan_to_num(df[[c for c in FEATS if c in df.columns]].to_numpy().astype(float))
    fold = np.array([int(hashlib.sha1(c.encode()).hexdigest(), 16) % 5 for c in crate])
    oof = np.zeros(len(df))
    for f in range(5):
        tr, te = fold != f, fold == f
        w, mu, sd = fit_logreg(X[tr], y[tr].astype(float))
        oof[te] = predict(w, mu, sd, X[te])
    order = np.argsort(-oof, kind="stable")
    ys, sz = y[order], size[order]
    tp = np.cumsum(ys); fp = np.cumsum(~ys)
    prec = tp / np.maximum(tp + fp, 1)
    rfn = tp / npos
    rby = np.cumsum(np.where(ys, sz, 0.0)) / totB
    print("\nfrontier (5-fold OOF logistic, 10 feats) — precision at fn-recall")
    pts = []
    for t in (0.02, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30):
        j = int(np.argmin(np.abs(rfn - t)))
        pts.append((rfn[j], prec[j], rby[j]))
        print(f"    r_fn={t:.0%}:  prec={prec[j]:.3f}   r_byte={rby[j]:.3f}")
    sel = (rfn >= 0.03) & (rfn <= 0.25)
    b1, a1 = np.polyfit(rfn[sel], prec[sel], 1)
    r2 = 1 - np.sum((prec[sel] - (a1 + b1 * rfn[sel]))**2) / np.sum((prec[sel] - prec[sel].mean())**2)
    print(f"    linear over 3-25%:  prec = {a1:.3f} {b1:+.3f}*r_fn   R2={r2:.2f}   "
          f"(+10pp recall  ->  {-b1*10:.1f}pp precision)")

    json.dump({"author_fns": npos, "author_MB": totB / 1e6,
               "ceiling_fn": float((anch & y).sum() / npos),
               "ceiling_byte": float(size[anch & y].sum() / totB),
               "frontier_points": [{"r_fn": float(a), "prec": float(b), "r_byte": float(c)} for a, b, c in pts],
               "frontier_linear": {"a": float(a1), "b": float(b1), "r2": float(r2)}},
              open("bench/run1/results/size_analysis.json", "w"), indent=1)
    print("\nwrote bench/run1/results/size_analysis.json")


if __name__ == "__main__":
    main()

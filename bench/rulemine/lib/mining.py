"""
mining.py — the rule search engine.

The deliverable of this study is a *white-box rule*: something an analyst can
read, argue with, and implement in fifty lines of Rust. So the search is over
conjunctions of interpretable threshold tests ("at least two distinct author
Locations AND no dependency Location"), not over model weights. Black-box models
appear elsewhere in the study only as an upper bound on what the features can
support — never as a proposed rule.

Mechanics. Every atom (`feature >= t`, `feature <= t`) is evaluated once into a
bit-packed mask over the training rows. A conjunction is then a bitwise AND and
two population counts, so an exhaustive sweep of every pair of ~1,500 atoms —
about a million candidate rules — is a matter of a minute rather than a day.
Rows are ordered by crate and each crate's block is padded to a whole number of
64-bit words, so per-crate counts come out of the same popcount pass and every
candidate gets clustered statistics for free.

Objective. Precision alone is maximised by a rule that fires once, and recall
alone by a rule that fires always, so neither is the objective. The search
maximises **recall subject to a precision floor**, with a floor on how many
distinct crates the rule must fire in — the deployment-shaped question ("what is
the most author code I can recover while being wrong less than 5% of the time,
in a way that works on more than one program?").
"""
import numpy as np

WORD = 64


def pack_by_crate(mask_bool, crate_codes, n_crates):
    """Pack a boolean row-mask into uint64 words, crate-blocked and padded so
    each crate starts on a word boundary. Returns (words, crate_word_starts)."""
    words = []
    starts = []
    for c in range(n_crates):
        sel = mask_bool[crate_codes == c]
        pad = (-len(sel)) % WORD
        if pad:
            sel = np.concatenate([sel, np.zeros(pad, bool)])
        starts.append(sum(len(w) for w in words))
        words.append(np.packbits(sel, bitorder="little").view(np.uint64))
    return np.concatenate(words) if words else np.zeros(0, np.uint64), np.array(starts, np.int64)


class Bitspace:
    """Row space for one training set: the target, the crate blocking, and the
    machinery to turn a boolean row-mask into clustered counts."""

    def __init__(self, y, crates):
        crates = np.asarray(crates)
        uniq, codes = np.unique(crates, return_inverse=True)
        self.crate_names = uniq
        self.codes = codes
        self.n_crates = len(uniq)
        self.n_rows = len(y)
        self.y_words, self.starts = pack_by_crate(np.asarray(y, bool), codes, self.n_crates)
        self.n_pos = int(np.asarray(y, bool).sum())
        self.pos_per_crate = np.array(
            [int(np.asarray(y, bool)[codes == c].sum()) for c in range(self.n_crates)], np.int64)

    def pack(self, mask_bool):
        return pack_by_crate(np.asarray(mask_bool, bool), self.codes, self.n_crates)[0]

    def stats(self, pred_words):
        """(tp, predicted, per-crate tp, per-crate predicted) for a packed mask."""
        pc_pred = np.bitwise_count(pred_words)
        pc_tp = np.bitwise_count(pred_words & self.y_words)
        return (int(pc_tp.sum(dtype=np.int64)), int(pc_pred.sum(dtype=np.int64)),
                np.add.reduceat(pc_tp, self.starts).astype(np.int64),
                np.add.reduceat(pc_pred, self.starts).astype(np.int64))

    def metrics(self, pred_words):
        tp, pred, per_tp, per_pred = self.stats(pred_words)
        firing = int((per_pred > 0).sum())
        with np.errstate(invalid="ignore", divide="ignore"):
            per_prec = np.where(per_pred > 0, per_tp / np.maximum(per_pred, 1), np.nan)
        return {
            "tp": tp, "predicted": pred,
            "precision": tp / pred if pred else float("nan"),
            "recall": tp / self.n_pos if self.n_pos else float("nan"),
            "coverage": pred / self.n_rows,
            "crates_firing": firing,
            "precision_crate_avg": float(np.nanmean(per_prec)) if firing else float("nan"),
            "crates_perfect": int(((per_pred > 0) & (per_tp == per_pred)).sum()),
            "per_crate_tp": per_tp, "per_crate_pred": per_pred,
        }


# ── Atom generation ───────────────────────────────────────────────────────────

def make_atoms(df, cols, max_thresholds=8, min_support=200):
    """Interpretable threshold atoms over `cols`.

    Integer-valued columns get integer thresholds from the low end of their
    range (1,2,3,... — where the interesting structure in count features lives)
    plus any further quantiles needed; continuous columns get quantile
    thresholds rounded to three significant figures so the printed rule is
    readable. Atoms whose support is below `min_support` rows, or above
    n - min_support, are dropped as unable to carry a usable rule.
    """
    atoms = []
    n = len(df)
    for c in cols:
        v = df[c].to_numpy()
        if v.dtype.kind in "iu" or np.allclose(v, np.round(v), equal_nan=True):
            vmax = int(np.nanmax(v)) if len(v) else 0
            cands = [t for t in (1, 2, 3, 4, 5, 6, 8, 10, 16, 32) if t <= vmax]
            if len(cands) < max_thresholds and vmax > 0:
                qs = np.unique(np.round(np.nanquantile(v, [0.5, 0.75, 0.9, 0.99])).astype(int))
                cands = sorted(set(cands) | {int(q) for q in qs if q > 0})
            cands = cands[:max_thresholds]
            fmt = "{:d}"
        else:
            qs = np.nanquantile(v, np.linspace(0.05, 0.95, max_thresholds))
            cands = sorted({float(f"{q:.3g}") for q in qs})
            fmt = "{:g}"
        for t in cands:
            for op, mask in ((">=", v >= t), ("<=", v <= t)):
                s = int(mask.sum())
                if s < min_support or s > n - min_support:
                    continue
                atoms.append({"col": c, "op": op, "t": t,
                              "expr": f"{c} {op} {fmt.format(t)}", "mask": mask})
    return atoms


def dedupe_atoms(atoms, space):
    """Drop atoms whose packed mask is bit-identical to one already kept — a
    common outcome when two thresholds fall between the same observed values."""
    seen = {}
    out = []
    for a in atoms:
        w = space.pack(a["mask"])
        key = hash(w.tobytes())
        if key in seen:
            continue
        seen[key] = True
        a["words"] = w
        out.append(a)
    return out


# ── Search ────────────────────────────────────────────────────────────────────

def _qualifies(m, tau, min_crates, min_recall):
    return (m["predicted"] > 0 and m["precision"] >= tau
            and m["crates_firing"] >= min_crates and m["recall"] >= min_recall)


def search_pairs(atoms, space, tau=0.95, min_crates=5, min_recall=0.0,
                 top_k=100, max_len=2, progress=None):
    """Exhaustive search over conjunctions of up to `max_len` atoms.

    Returns the `top_k` qualifying rules ranked by recall (the objective), each
    with its clustered statistics. `max_len=3` is only tractable for small atom
    sets; use `beam_search` above that.
    """
    results = []
    singles = []
    for i, a in enumerate(atoms):
        m = space.metrics(a["words"])
        singles.append(m)
        if _qualifies(m, tau, min_crates, min_recall):
            results.append({"atoms": [i], "expr": a["expr"], **_clean(m)})

    if max_len >= 2:
        n = len(atoms)
        for i in range(n):
            wi = atoms[i]["words"]
            # A conjunction can only lose true positives, so any atom whose own
            # tp count is already below the best qualifying recall can never
            # produce a better rule: skip it and everything under it.
            for j in range(i + 1, n):
                w = wi & atoms[j]["words"]
                m = space.metrics(w)
                if _qualifies(m, tau, min_crates, min_recall):
                    results.append({"atoms": [i, j],
                                    "expr": f"{atoms[i]['expr']} AND {atoms[j]['expr']}",
                                    **_clean(m)})
            if progress and i % progress == 0:
                print(f"    pairs {i}/{n} kept={len(results)}", flush=True)

    if max_len >= 3:
        n = len(atoms)
        for i in range(n):
            wi = atoms[i]["words"]
            for j in range(i + 1, n):
                wij = wi & atoms[j]["words"]
                if space.stats(wij)[0] == 0:
                    continue
                for k in range(j + 1, n):
                    w = wij & atoms[k]["words"]
                    m = space.metrics(w)
                    if _qualifies(m, tau, min_crates, min_recall):
                        results.append({"atoms": [i, j, k],
                                        "expr": f"{atoms[i]['expr']} AND {atoms[j]['expr']} "
                                                f"AND {atoms[k]['expr']}",
                                        **_clean(m)})
            if progress and i % progress == 0:
                print(f"    triples {i}/{n} kept={len(results)}", flush=True)

    results.sort(key=lambda r: (-r["recall"], -r["precision"]))
    return results[:top_k], singles


def beam_search(atoms, space, tau=0.95, min_crates=5, max_len=4, beam=200,
                top_k=100, verbose=False):
    """Greedy beam search for longer conjunctions than exhaustive can reach.

    The beam is scored by recall among rules that already meet the precision
    floor, and by precision among those that do not yet — so a partial rule is
    allowed to climb towards the floor before it starts trading recall away.
    """
    n = len(atoms)
    frontier = []
    for i, a in enumerate(atoms):
        m = space.metrics(a["words"])
        frontier.append(([i], a["words"], m))
    kept = [r for r in frontier if _qualifies(r[2], tau, min_crates, 0.0)]

    def rank(item):
        m = item[2]
        met = m["precision"] >= tau and m["crates_firing"] >= min_crates
        return (0 if met else 1, -m["recall"] if met else -m["precision"])

    frontier.sort(key=rank)
    frontier = frontier[:beam]
    out = {tuple(sorted(r[0])): r for r in kept}

    for depth in range(2, max_len + 1):
        nxt = []
        for idxs, w, _ in frontier:
            last = max(idxs)
            for k in range(last + 1, n):
                if k in idxs:
                    continue
                w2 = w & atoms[k]["words"]
                m2 = space.metrics(w2)
                if m2["predicted"] == 0:
                    continue
                nxt.append((idxs + [k], w2, m2))
        if not nxt:
            break
        nxt.sort(key=rank)
        frontier = nxt[:beam]
        for idxs, _, m in frontier:
            if _qualifies(m, tau, min_crates, 0.0):
                out[tuple(sorted(idxs))] = (idxs, None, m)
        if verbose:
            best = frontier[0][2]
            print(f"    depth {depth}: frontier {len(nxt)} -> {len(frontier)}, "
                  f"best prec {best['precision']:.3f} recall {best['recall']:.3f}", flush=True)

    results = []
    for idxs, _, m in out.values():
        results.append({"atoms": list(idxs),
                        "expr": " AND ".join(atoms[i]["expr"] for i in sorted(idxs)),
                        **_clean(m)})
    results.sort(key=lambda r: (-r["recall"], -r["precision"]))
    return results[:top_k]


def _clean(m):
    return {k: v for k, v in m.items() if not k.startswith("per_crate")}


def apply_rule(df, atoms, idxs):
    """Re-evaluate a mined rule on a fresh dataframe (e.g. the lockbox)."""
    mask = np.ones(len(df), bool)
    for i in idxs:
        a = atoms[i]
        v = df[a["col"]].to_numpy()
        mask &= (v >= a["t"]) if a["op"] == ">=" else (v <= a["t"])
    return mask


def parse_rule(expr):
    """'a >= 2 AND b <= 0' -> [(col, op, t), ...]; the printed form is the rule."""
    out = []
    for part in expr.split(" AND "):
        col, op, t = part.split()
        out.append((col, op, float(t)))
    return out


def eval_expr(df, expr):
    mask = np.ones(len(df), bool)
    for col, op, t in parse_rule(expr):
        v = df[col].to_numpy()
        mask &= (v >= t) if op == ">=" else (v <= t)
    return mask

"""
features.py — turn one build's raw observables into a per-function feature row.

Every feature here is computable from a *stripped* binary. Nothing reads the
symbol table, the DWARF, or the ground-truth labels: the label is joined on at
the very end, by address, and never participates in any feature. That includes
the neighbourhood and call-graph features, which aggregate other functions'
*observations* (their Location references), never other functions' *labels* —
label propagation would be leakage and is deliberately not done.

Features are grouped into named families so that ablations can add or remove a
whole channel at once:

  C  incumbent      unhusk's 7 path-class counts, exactly as RULE_A/B/C see them
  P  taxonomy       this study's 8-class counts (splits STDDEP out of registry)
  M  multiplicity   what "two locations" can mean: distinct structs vs distinct
                    (file,line) vs distinct files; dominance; entropy; line span
  F  fanout         how many *other* functions reference the same Location
  G  geometry       size, instruction mix, reference density
  N  neighbourhood  address-order context: gaps, the +/-k FDE window, run structure
  X  callgraph      direct call edges, in and out, and the callees' composition
  B  binary         whole-binary normalisers (this binary's own base rates)
"""
import math
from collections import defaultdict

import numpy as np

from paths import P_CLASSES, UNHUSK_CLASSES, p_class, unhusk_class

WINDOW = 5  # +/- this many FDEs in address order for the neighbourhood window


def _entropy(counts):
    tot = sum(counts)
    if tot <= 0:
        return 0.0
    h = 0.0
    for c in counts:
        if c > 0:
            p = c / tot
            h -= p * math.log2(p)
    return h


def build_rows(raw, gt):
    """raw: parsed rulemine.raw.v1 dict. gt: parsed ground_truth.json dict (or None).

    Returns (list-of-dict rows, meta dict).
    """
    locs = raw["locations"]
    fns = raw["functions"]
    n_fns = len(fns)

    # ── Per-Location static attributes ───────────────────────────────────────
    loc_uh = np.empty(len(locs), dtype=object)
    loc_p = np.empty(len(locs), dtype=object)
    loc_file = np.empty(len(locs), dtype=object)
    loc_line = np.zeros(len(locs), dtype=np.int32)
    loc_col = np.zeros(len(locs), dtype=np.int32)
    file_cache = {}
    for i, l in enumerate(locs):
        f = l["file"]
        cls = file_cache.get(f)
        if cls is None:
            cls = (unhusk_class(f), p_class(f))
            file_cache[f] = cls
        loc_uh[i], loc_p[i] = cls
        loc_file[i] = f
        loc_line[i] = l["line"]
        loc_col[i] = l["col"]

    # ── Fan-out: how many functions reference each Location struct ───────────
    fanout = np.zeros(len(locs), dtype=np.int32)
    for fn in fns:
        for lid in fn["locs"]:
            if lid < len(fanout):
                fanout[lid] += 1

    # ── Call graph: invert the out-edges ─────────────────────────────────────
    idx_of_start = {fn["s"]: i for i, fn in enumerate(fns)}
    callers = defaultdict(list)
    for i, fn in enumerate(fns):
        for c in fn["callees"]:
            j = idx_of_start.get(c)
            if j is not None and j != i:
                callers[j].append(i)

    # ── First pass: per-function Location aggregates ─────────────────────────
    per = []
    for fn in fns:
        ids = [i for i in fn["locs"] if i < len(locs)]
        uh_cnt = dict.fromkeys(UNHUSK_CLASSES, 0)
        p_cnt = dict.fromkeys(P_CLASSES, 0)
        rel_files, rel_lines, rel_fanouts = defaultdict(int), set(), []
        all_files = defaultdict(int)
        nonrel_files = defaultdict(int)
        rel_line_vals, rel_cols = [], set()
        for i in ids:
            uh_cnt[loc_uh[i]] += 1
            pc = loc_p[i]
            p_cnt[pc] += 1
            f = loc_file[i]
            all_files[f] += 1
            if pc == "REL":
                rel_files[f] += 1
                rel_lines.add((f, loc_line[i]))
                rel_line_vals.append(loc_line[i])
                rel_cols.add((f, loc_line[i], loc_col[i]))
                rel_fanouts.append(int(fanout[i]))
            else:
                nonrel_files[f] += 1
        per.append((ids, uh_cnt, p_cnt, rel_files, rel_lines, rel_fanouts,
                    all_files, nonrel_files, rel_line_vals, rel_cols))

    # ── Address-order neighbourhood (fns already sorted by start) ────────────
    starts = np.array([fn["s"] for fn in fns], dtype=np.int64)
    ends = np.array([fn["e"] for fn in fns], dtype=np.int64)
    order_ok = bool(np.all(np.diff(starts) > 0)) if n_fns > 1 else True

    nrel = np.array([p[2]["REL"] for p in per], dtype=np.int32)
    nreg = np.array([p[2]["REGISTRY"] + p[2]["GIT"] for p in per], dtype=np.int32)
    nstd = np.array([p[2]["RUSTC"] + p[2]["STDDEP"] for p in per], dtype=np.int32)

    def _wsum(arr):
        c = np.concatenate([[0], np.cumsum(arr, dtype=np.int64)])
        lo = np.maximum(np.arange(n_fns) - WINDOW, 0)
        hi = np.minimum(np.arange(n_fns) + WINDOW + 1, n_fns)
        return (c[hi] - c[lo] - arr).astype(np.int32)  # excludes self

    win_rel = _wsum(nrel) if n_fns else np.zeros(0, np.int32)
    win_reg = _wsum(nreg) if n_fns else np.zeros(0, np.int32)
    win_std = _wsum(nstd) if n_fns else np.zeros(0, np.int32)

    # Distance, in FDE index, to the nearest function that references any
    # relative-path Location (a pure-observation notion of "author region").
    has_rel = nrel > 0
    dist_rel = np.full(n_fns, 10_000, dtype=np.int32)
    if has_rel.any():
        idxs = np.flatnonzero(has_rel)
        pos = np.searchsorted(idxs, np.arange(n_fns))
        left = np.where(pos > 0, np.arange(n_fns) - idxs[np.clip(pos - 1, 0, len(idxs) - 1)], 10_000)
        right = np.where(pos < len(idxs), idxs[np.clip(pos, 0, len(idxs) - 1)] - np.arange(n_fns), 10_000)
        dist_rel = np.minimum(left, right).astype(np.int32)

    dominant = []
    for p in per:
        rf = p[3]
        dominant.append(max(rf.items(), key=lambda kv: kv[1])[0] if rf else None)

    # ── Ground truth join ────────────────────────────────────────────────────
    gt_label, gt_crate = {}, {}
    if gt:
        for g in gt.get("functions", []):
            a = int(g["start"], 16)
            gt_label[a] = g.get("label", "UNKNOWN")
            gt_crate[a] = g.get("crate")

    bin_n_loc = len(locs)
    bin_frac_rel_fde = float(has_rel.mean()) if n_fns else 0.0
    bin_nrel_total = int(nrel.sum())
    bin_nreg_total = int(nreg.sum())

    rows = []
    for i, fn in enumerate(fns):
        ids, uh_cnt, p_cnt, rel_files, rel_lines, rel_fanouts, all_files, nonrel_files, rel_line_vals, rel_cols = per[i]
        size = max(int(fn["e"] - fn["s"]), 1)
        n_loc = len(ids)
        n_rel = p_cnt["REL"]
        n_nonrel = n_loc - n_rel
        rel_counts = sorted(rel_files.values(), reverse=True)
        all_counts = sorted(all_files.values(), reverse=True)

        r = {
            # ── identity ────────────────────────────────────────────────────
            "crate": raw.get("crate_name"),
            "config": raw.get("config"),
            "fn_start": int(fn["s"]),
            "fn_end": int(fn["e"]),
            "fde_idx": i,

            # ── C: incumbent's inputs ───────────────────────────────────────
            **{f"C_{k}": uh_cnt[k] for k in UNHUSK_CLASSES},

            # ── P: this study's taxonomy ────────────────────────────────────
            **{f"P_{k}": p_cnt[k] for k in P_CLASSES},
            "P_total": n_loc,
            "P_nonrel": n_nonrel,

            # ── M: what "multiplicity" can mean ─────────────────────────────
            "M_rel_structs": n_rel,
            "M_rel_lines": len(rel_lines),
            "M_rel_files": len(rel_files),
            "M_rel_colsites": len(rel_cols),
            "M_rel_top_file": rel_counts[0] if rel_counts else 0,
            "M_rel_second_file": rel_counts[1] if len(rel_counts) > 1 else 0,
            "M_rel_files_ge2": sum(1 for c in rel_counts if c >= 2),
            "M_rel_line_span": (max(rel_line_vals) - min(rel_line_vals)) if rel_line_vals else 0,
            "M_rel_line_min": min(rel_line_vals) if rel_line_vals else 0,
            "M_rel_entropy": _entropy(rel_counts),
            "M_all_entropy": _entropy(all_counts),
            "M_all_files": len(all_files),
            "M_nonrel_files": len(nonrel_files),
            "M_rel_frac": n_rel / n_loc if n_loc else 0.0,
            "M_rel_file_frac": len(rel_files) / len(all_files) if all_files else 0.0,

            # ── F: fan-out ──────────────────────────────────────────────────
            "F_rel_fo_min": min(rel_fanouts) if rel_fanouts else 0,
            "F_rel_fo_max": max(rel_fanouts) if rel_fanouts else 0,
            "F_rel_fo_mean": float(np.mean(rel_fanouts)) if rel_fanouts else 0.0,
            "F_rel_excl": sum(1 for f in rel_fanouts if f == 1),
            "F_rel_excl_frac": (sum(1 for f in rel_fanouts if f == 1) / len(rel_fanouts)) if rel_fanouts else 0.0,
            "F_all_fo_mean": float(np.mean([fanout[j] for j in ids])) if ids else 0.0,

            # ── G: geometry and instruction shape ───────────────────────────
            "G_size": size,
            "G_log_size": math.log2(size),
            "G_n_insn": fn["n_insn"],
            "G_insn_per_byte": fn["n_insn"] / size,
            "G_n_call": fn["n_call"],
            "G_n_icall": fn["n_icall"],
            "G_n_cond_br": fn["n_cond_br"],
            "G_n_uncond_br": fn["n_uncond_br"],
            "G_n_ibr": fn["n_ibr"],
            "G_n_ret": fn["n_ret"],
            "G_n_exception": fn["n_exception"],
            "G_call_dens": fn["n_call"] / max(fn["n_insn"], 1),
            "G_icall_dens": fn["n_icall"] / max(fn["n_insn"], 1),
            "G_br_dens": fn["n_cond_br"] / max(fn["n_insn"], 1),
            "G_exc_dens": fn["n_exception"] / max(fn["n_insn"], 1),
            "G_n_rip_ref": fn["n_rip_ref"],
            "G_n_ref_rodata": fn["n_ref_rodata"],
            "G_n_ref_relro": fn["n_ref_relro"],
            "G_n_ref_data": fn["n_ref_data"],
            "G_n_ref_text": fn["n_ref_text"],
            "G_n_strdirect": len(fn["strs"]),
            "G_loc_per_kb": 1024.0 * n_loc / size,
            "G_rel_per_kb": 1024.0 * n_rel / size,
            "G_relro_dens": fn["n_ref_relro"] / max(fn["n_rip_ref"], 1),

            # ── N: address-order neighbourhood ──────────────────────────────
            "N_gap_prev": int(fn["s"] - ends[i - 1]) if i > 0 else -1,
            "N_gap_next": int(starts[i + 1] - fn["e"]) if i + 1 < n_fns else -1,
            "N_prev_rel": int(nrel[i - 1]) if i > 0 else 0,
            "N_next_rel": int(nrel[i + 1]) if i + 1 < n_fns else 0,
            "N_prev_reg": int(nreg[i - 1]) if i > 0 else 0,
            "N_next_reg": int(nreg[i + 1]) if i + 1 < n_fns else 0,
            "N_win_rel": int(win_rel[i]),
            "N_win_reg": int(win_reg[i]),
            "N_win_std": int(win_std[i]),
            "N_win_rel_frac": float(win_rel[i]) / max(int(win_rel[i] + win_reg[i] + win_std[i]), 1),
            "N_dist_rel": int(dist_rel[i]),
            "N_same_file_prev": int(bool(dominant[i] and i > 0 and dominant[i] == dominant[i - 1])),
            "N_same_file_next": int(bool(dominant[i] and i + 1 < n_fns and dominant[i] == dominant[i + 1])),
            "N_pos_frac": i / max(n_fns - 1, 1),

            # ── X: call graph ───────────────────────────────────────────────
            "X_out_deg": len(fn["callees"]),
            "X_in_deg": len(callers.get(i, ())),
            "X_callee_rel": int(sum(nrel[idx_of_start[c]] for c in fn["callees"] if c in idx_of_start)),
            "X_callee_reg": int(sum(nreg[idx_of_start[c]] for c in fn["callees"] if c in idx_of_start)),
            "X_callee_with_rel": int(sum(1 for c in fn["callees"] if c in idx_of_start and nrel[idx_of_start[c]] > 0)),
            "X_caller_rel": int(sum(nrel[j] for j in callers.get(i, ()))),
            "X_caller_reg": int(sum(nreg[j] for j in callers.get(i, ()))),
            "X_caller_with_rel": int(sum(1 for j in callers.get(i, ()) if nrel[j] > 0)),
            "X_caller_max_rel": int(max((nrel[j] for j in callers.get(i, ())), default=0)),
            "X_caller_all_rel": int(bool(callers.get(i)) and all(nrel[j] > 0 for j in callers[i])),

            # ── B: whole-binary normalisers ─────────────────────────────────
            "B_n_fdes": n_fns,
            "B_n_locs": bin_n_loc,
            "B_frac_rel_fde": bin_frac_rel_fde,
            "B_nrel_total": bin_nrel_total,
            "B_nreg_total": bin_nreg_total,

            # ── label (never a feature) ─────────────────────────────────────
            "label": gt_label.get(int(fn["s"]), "NONE"),
            "gt_crate": gt_crate.get(int(fn["s"])),
        }
        rows.append(r)

    meta = {
        "crate": raw.get("crate_name"), "config": raw.get("config"),
        "sha256": raw.get("sha256"), "fde_source": raw.get("fde_source"),
        "n_fdes": n_fns, "n_locations": bin_n_loc,
        "n_strings_emitted": len(raw.get("strings", [])),
        "n_relative_relocs": raw.get("n_relative_relocs"),
        "addr_order_strict": order_ok,
        "gt_present": bool(gt),
        "gt_n_functions": len(gt.get("functions", [])) if gt else 0,
        "gt_authorship_error": gt.get("authorship_error") if gt else None,
        "gt_author_crates": gt.get("author_crates") if gt else None,
        "gt_mangling": gt.get("mangling") if gt else None,
    }
    return rows, meta

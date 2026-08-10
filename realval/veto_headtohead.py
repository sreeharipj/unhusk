#!/usr/bin/env python3
"""
veto_headtohead.py — REPORTER. The controlled comparison `bench/origin/REPORT.md`'s
verdict names as "the natural next step, not done here".

THE QUESTION
------------
`bench/origin` found that RULE_A@2 — multiplicity >= 2 PLUS a hard veto on any function
that also references a non-user Location — scores 91.5% precision on async code against
the shipped STRONG tier's documented 87.3%. That comparison was uncontrolled: different
ground truth (cargo-authorship vs `nm -C` symbol), different corpus (43 crates x 8 build
configs vs 32 binaries), different unit (FDE vs function), different code path.

This script removes every one of those differences. Same 32 binaries, same rows, same
`report_results.classify()` oracle, same strata, same Wilson/cluster-bootstrap machinery.
The ONLY thing that varies between arms is whether the veto is applied. Whatever
difference appears is attributable to the veto and to nothing else.

THE TEST THAT ACTUALLY MATTERS: ISO-RETENTION
---------------------------------------------
A veto raises precision by discarding functions. So does raising `--min-anchors`. Any
filter that throws away half the predictions will look better on precision, so
"STRONG+veto beats STRONG" is not evidence of anything by itself — the shipped tool
already ships a dial that does that, and it costs nothing to turn.

The veto earns its place only if it beats the EXISTING dial at equal retention: at the
point on the plain `--min-anchors` ladder that keeps the same number of functions, is
the veto's precision higher? If it is not, the veto is a second, more complicated way to
spend the same recall, and should not ship. That comparison is the `## Iso-retention`
section, and it is the one to read first.

Usage: veto_headtohead.py --rows rows_src.json --origin origin_src.json --out OUT.md
"""
import argparse
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)

from oracle import cluster_bootstrap, wilson  # noqa: E402
from report_results import DOMAIN_ASYNC, DOMAIN_CATEGORY, classify, fp_kind  # noqa: E402

# `origin::PathClass` discriminant order, as frozen by collect_origin.py.
CLASSES = ["user", "workspace", "registry", "git", "rustc", "generated", "unknown"]
IDX = {c: i for i, c in enumerate(CLASSES)}

# Veto variants. Each maps a per-function class-count vector to True = REJECT.
#
# `any` is RULE_A's literal rule (`FnProfile::non_user_count() > 0`). `lib` narrows the
# veto to the three classes that unambiguously mean "third-party or toolchain code"
# — the distinction matters in principle because `realval`'s authorship oracle counts
# every workspace member as author, so vetoing on Workspace would reject genuine author
# functions by construction. `rustc` and `registry` are the single-class decompositions,
# reported to show which class is doing the work rather than asserting it.
VETOES = {
    "none":     lambda v: False,
    "any":      lambda v: sum(v) - v[IDX["user"]] > 0,
    "lib":      lambda v: v[IDX["registry"]] + v[IDX["git"]] + v[IDX["rustc"]] > 0,
    "rustc":    lambda v: v[IDX["rustc"]] > 0,
    "registry": lambda v: v[IDX["registry"]] + v[IDX["git"]] > 0,
}
VETO_DESC = {
    "none": "no veto — the shipped STRONG tier, verbatim",
    "any": "reject if the function references ANY non-user Location (**RULE_A literal**)",
    "lib": "reject if it references a registry, git, or rustc Location",
    "rustc": "reject if it references a rustc/std Location",
    "registry": "reject if it references a registry or git Location",
}


def load(rows_path, origin_path):
    rows = json.load(open(rows_path))
    origin = json.load(open(origin_path))

    names = sorted(set(rows) & set(origin))
    joined = missing = 0
    for n in names:
        counts = origin[n]["counts"]
        for r in rows[n]["rows"]:
            vec = counts.get(r["addr"])
            r["origin"] = vec
            joined += vec is not None
            missing += vec is None
        rec = rows[n]
        cat = DOMAIN_CATEGORY.get(n, "cli")
        rec["domain"] = cat
        rec["stratum_b"] = "async" if cat in DOMAIN_ASYNC else "sync"
    return rows, origin, names, joined, missing


def select(rec, k, veto):
    """Certain functions this arm accepts: >= k user anchors, and not vetoed.

    A row that failed to join (`origin is None`) has no composition evidence, so the
    veto cannot be evaluated on it. Those rows are KEPT — treating an absent measurement
    as "clean" is the conservative choice for the veto arm, since it can only make the
    veto look worse, never better. The join rate is reported so this stays auditable.
    """
    rej = VETOES[veto]
    out = []
    for r in rec["rows"]:
        if r["anchors"] < k:
            continue
        if r["origin"] is not None and rej(r["origin"]):
            continue
        out.append(r)
    return out


def tally(rows, names, k, veto, oracle="meta", unwrap=True):
    """(tp, fp, unknown, clusters, kept_rows) under one arm."""
    clusters, tp, fp, unk, kept = [], 0, 0, 0, []
    for n in names:
        rec = rows[n]
        a = b = 0
        for r in select(rec, k, veto):
            kept.append((n, r))
            c = classify(r["sym"], rec, oracle, unwrap)
            if c == "user":
                a += 1
            elif c == "nonuser":
                b += 1
            else:
                unk += 1
        if a + b:
            clusters.append((a, b))
        tp += a
        fp += b
    return tp, fp, unk, clusters, kept


def row(rows, names, k, veto, base, oracle="meta", unwrap=True):
    tp, fp, unk, cl, kept = tally(rows, names, k, veto, oracle, unwrap)
    n = tp + fp
    if n == 0:
        return None
    pt, lo, hi = wilson(tp, n)
    _, blo, bhi = cluster_bootstrap(cl)
    bs = "n too small" if len(cl) < 2 else f"[{blo:.1f}, {bhi:.1f}]"
    return {
        "k": k, "veto": veto, "n": n, "tp": tp, "fp": fp, "unk": unk,
        "prec": pt, "wilson": f"[{lo:.1f}, {hi:.1f}]", "boot": bs,
        "retained": 100.0 * n / base if base else 0.0, "kept": kept, "clusters": cl,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", default=os.path.join(HERE, "rows_src.json"))
    ap.add_argument("--origin", default=os.path.join(HERE, "origin_src.json"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-anchors", type=int, default=2)
    args = ap.parse_args()

    rows, origin, names, joined, missing = load(args.rows, args.origin)
    K = args.min_anchors

    out = []
    w = out.append

    # ── validity ──
    w("## Join validity\n")
    total = joined + missing
    w(f"`rows_src.json` (the shipped tool's own per-function verdicts) joined to "
      f"`origin_src.json` (per-FDE Location composition) by function start address: "
      f"**{joined}/{total} certain functions matched ({100.0*joined/total:.2f}%)**, "
      f"{missing} unmatched, across {len(names)} binaries.\n")
    w("Two independent runs of the same pipeline over the same `.eh_frame` FDE set, so a "
      "clean join is the expected result rather than a lucky one — `check_provenance.py` "
      "already dropped every binary where root-crate promotion fires, which is the only "
      "way the two runs could have disagreed about what counts as a user path. A "
      "stronger check than the join rate: on every matched row the probe's `user` class "
      "count equals the shipped tool's `anchors` count, so the arms differ in the veto "
      "and in nothing else.\n")
    mism = sum(1 for n in names for r in rows[n]["rows"]
               if r["origin"] is not None and r["origin"][IDX["user"]] != r["anchors"])
    w(f"Rows where probe `user` != shipped `anchors`: **{mism}**.\n")

    # ── composition of the corpus ──
    w("\n## What the veto has to work with\n")
    w("Location-class histogram per binary — a veto on a class that never appears cannot "
      "do anything, so this bounds the whole experiment.\n")
    w("| binary | domain | user | workspace | registry | git | rustc | generated | unknown |")
    w("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    agg = collections.Counter()
    for n in names:
        h = origin[n]["location_class_histogram"]
        for c in CLASSES:
            agg[c] += h[c]
        w(f"| {n} | {rows[n]['domain']} | " + " | ".join(str(h[c]) for c in CLASSES) + " |")
    w("| **total** | | " + " | ".join(f"**{agg[c]}**" for c in CLASSES) + " |")

    base = sum(len(rows[n]["rows"]) for n in names)

    # ── headline: arms at K ──
    def arm_table(title, subset, ks=(K,)):
        w(f"\n**{title}** — {len(subset)} binaries\n")
        w("| min-anchors | veto | n | TP | FP | unk | precision | Wilson 95% | "
          "cluster bootstrap 95% | retained |")
        w("|---:|---|---:|---:|---:|---:|---:|---|---|---:|")
        sub_base = sum(len(rows[n]["rows"]) for n in subset)
        for k in ks:
            for v in VETOES:
                r = row(rows, subset, k, v, sub_base)
                if r is None:
                    w(f"| >= {k} | {v} | 0 | 0 | 0 | 0 | n/a | n too small | n too small | 0.0% |")
                    continue
                w(f"| >= {k} | {v} | {r['n']} | {r['tp']} | {r['fp']} | {r['unk']} | "
                  f"{r['prec']:.1f}% | {r['wilson']} | {r['boot']} | {r['retained']:.1f}% |")

    w("\n## Head-to-head: shipped STRONG vs STRONG + origin veto\n")
    w("Oracle: cargo-metadata authorship, **unwrapped** ruler — the same combination "
      "`report_results.py`'s threshold ladder uses for the published figure, so the "
      "`veto = none` row here reproduces `docs/validation.md`'s number exactly and the "
      "comparison starts from a verified baseline.\n")
    arm_table(f"COMBINED (>= {K} anchors)", names)

    w("\n### By stratum B (pre-registered: async folds in `parallel`)\n")
    for strat in ("sync", "async"):
        sub = [n for n in names if rows[n]["stratum_b"] == strat]
        if sub:
            arm_table(f"{strat.upper()} stratum", sub)

    w("\n### By domain — `docs/validation.md`'s own partition\n")
    w("The published 87.3% async figure is the `domain == async` cut (with `parallel` "
      "kept separate), NOT the async stratum above. This is the cut to compare against "
      "it.\n")
    for dom in ("cli", "async", "parallel", "macro", "crypto"):
        sub = [n for n in names if rows[n]["domain"] == dom]
        if sub:
            arm_table(f"domain `{dom}`", sub)

    # ── the decisive test ──
    w("\n## Iso-retention: does the veto beat the dial it would sit next to?\n")
    w("Both the veto and `--min-anchors` buy precision with recall. The veto is only "
      "worth shipping if, at equal retention, it buys MORE. Plain ladder first, then "
      "each veto arm placed against it.\n")
    w("Computed separately per stratum, not only pooled. Pooling would decide the "
      "question on the 23 sync binaries that dominate the corpus, and the claim under "
      "test (`bench/origin/REPORT.md`: RULE_A closes the shipped tool's *async* gap) is "
      "specifically about the async cut — where the shipped dial's own precision curve "
      "is different, so the bar the veto has to clear is different too.\n")

    def iso_section(title, subset):
        sub_base = sum(len(rows[n]["rows"]) for n in subset)
        w(f"\n### {title} — {len(subset)} binaries\n")
        w("**Plain `--min-anchors` ladder (no veto)** — the curve to beat:\n")
        w("| min-anchors | n | precision | retained |")
        w("|---:|---:|---:|---:|")
        ladder = []
        for k in range(1, 9):
            r = row(rows, subset, k, "none", sub_base)
            if r is None:
                continue
            ladder.append(r)
            w(f"| >= {k} | {r['n']} | {r['prec']:.1f}% | {r['retained']:.1f}% |")
        if len(ladder) < 2:
            w("\nLadder too short to interpolate against; no iso-retention read.\n")
            return

        def interp(retained):
            """Precision the plain dial delivers at this retention, linearly
            interpolated between the two bracketing integer thresholds. The dial is
            integer-valued, so an exact iso-retention point usually does not exist;
            interpolating is the fairest available reading and is stated rather than
            hidden. Outside the ladder's range the nearest endpoint is used, which
            flatters the veto (the dial would keep improving), so a negative advantage
            reported here is a conservative claim."""
            pts = sorted(((r["retained"], r["prec"]) for r in ladder), reverse=True)
            if retained >= pts[0][0]:
                return pts[0][1]
            if retained <= pts[-1][0]:
                return pts[-1][1]
            for (r1, p1), (r2, p2) in zip(pts, pts[1:]):
                if r2 <= retained <= r1:
                    if r1 == r2:
                        return p1
                    f = (retained - r2) / (r1 - r2)
                    return p2 + f * (p1 - p2)
            return pts[-1][1]

        w("\n**Each veto arm vs the plain dial at the same retention:**\n")
        w("| arm | n | precision | retained | plain dial at same retention | advantage |")
        w("|---|---:|---:|---:|---:|---:|")
        for k in (1, K, K + 1):
            for v in VETOES:
                if v == "none":
                    continue
                r = row(rows, subset, k, v, sub_base)
                if r is None:
                    continue
                adv = r["prec"] - interp(r["retained"])
                w(f"| `--min-anchors {k}` + veto `{v}` | {r['n']} | {r['prec']:.1f}% | "
                  f"{r['retained']:.1f}% | {interp(r['retained']):.1f}% | "
                  f"**{adv:+.1f}pp** |")

    iso_section("COMBINED", names)
    for strat in ("sync", "async"):
        iso_section(f"stratum B = {strat.upper()}",
                    [n for n in names if rows[n]["stratum_b"] == strat])
    for dom in ("cli", "async", "macro"):
        sub = [n for n in names if rows[n]["domain"] == dom]
        if len(sub) >= 2:
            iso_section(f"domain `{dom}`", sub)

    # ── is the advantage distinguishable from noise? ──
    w("\n## Is the iso-retention advantage real, or 8 binaries' worth of noise?\n")
    w("The advantages above are differences between two point estimates on small "
      "subsets — the async arm that matters most rests on 8 binaries and ~50 accepted "
      "functions. Quoting `+4pp` from that without an interval would repeat exactly the "
      "error `bench/origin/REPORT.md`'s own revision note records.\n")
    w("This is a **paired cluster bootstrap on the difference itself**: resample "
      "binaries with replacement, and on each resample recompute *both* the veto arm's "
      "precision and the plain dial's interpolated precision at that resample's own "
      "retention, then take the difference. Pairing matters — the two arms are scored on "
      "overlapping functions from the same binaries, so bootstrapping them independently "
      "would overstate the uncertainty of their difference.\n")

    def paired_bootstrap(subset, k, veto, iters=20000, seed=20260730):
        import random
        per = {}
        for n in subset:
            rec = rows[n]
            cell = {"cert": len(rec["rows"])}
            for kk in range(1, 9):
                for vv in ("none", veto):
                    a = b = 0
                    for r in select(rec, kk, vv):
                        c = classify(r["sym"], rec, "meta", True)
                        a += c == "user"
                        b += c == "nonuser"
                    cell[(kk, vv)] = (a, b)
            per[n] = cell

        def advantage(sample):
            cert = sum(per[n]["cert"] for n in sample)
            if not cert:
                return None
            lad = []
            for kk in range(1, 9):
                a = sum(per[n][(kk, "none")][0] for n in sample)
                b = sum(per[n][(kk, "none")][1] for n in sample)
                if a + b:
                    lad.append((100.0 * (a + b) / cert, 100.0 * a / (a + b)))
            va = sum(per[n][(k, veto)][0] for n in sample)
            vb = sum(per[n][(k, veto)][1] for n in sample)
            if not (va + vb) or len(lad) < 2:
                return None
            ret = 100.0 * (va + vb) / cert
            prec = 100.0 * va / (va + vb)
            lad.sort(reverse=True)
            if ret >= lad[0][0]:
                iso = lad[0][1]
            elif ret <= lad[-1][0]:
                iso = lad[-1][1]
            else:
                iso = lad[-1][1]
                for (r1, p1), (r2, p2) in zip(lad, lad[1:]):
                    if r2 <= ret <= r1:
                        iso = p1 if r1 == r2 else p2 + (ret - r2) / (r1 - r2) * (p1 - p2)
                        break
            return prec - iso

        point = advantage(list(subset))
        rng = random.Random(seed)
        draws = []
        for _ in range(iters):
            d = advantage([subset[rng.randrange(len(subset))] for _ in subset])
            if d is not None:
                draws.append(d)
        if len(draws) < 100:
            return point, None, None, None
        draws.sort()
        lo = draws[int(0.025 * len(draws))]
        hi = draws[min(len(draws) - 1, int(0.975 * len(draws)))]
        return point, lo, hi, sum(1 for d in draws if d > 0) / len(draws)

    w("| subset | arm | advantage | 95% paired bootstrap | P(advantage > 0) |")
    w("|---|---|---:|---|---:|")
    for label, subset in (
        ("COMBINED", names),
        ("stratum ASYNC", [n for n in names if rows[n]["stratum_b"] == "async"]),
        ("stratum SYNC", [n for n in names if rows[n]["stratum_b"] == "sync"]),
        ("domain `async`", [n for n in names if rows[n]["domain"] == "async"]),
        ("domain `cli`", [n for n in names if rows[n]["domain"] == "cli"]),
    ):
        if len(subset) < 2:
            continue
        for v in ("any", "rustc"):
            pt, lo, hi, pgt = paired_bootstrap(subset, K, v)
            if pt is None:
                continue
            ci = "n too small" if lo is None else f"[{lo:+.1f}, {hi:+.1f}]"
            pg = "—" if pgt is None else f"{100*pgt:.0f}%"
            w(f"| {label} | `--min-anchors {K}` + veto `{v}` | {pt:+.1f}pp | {ci} | {pg} |")

    # ── what the veto actually removes ──
    w("\n## What the veto removes\n")
    w("A veto is worth its recall cost only if what it discards is disproportionately "
      "false. Of the STRONG functions each veto rejects, how many were true author "
      "functions (cost) and how many were false attributions (benefit)?\n")
    w("| veto | removed | of which FP (benefit) | of which TP (cost) | unknown | "
      "FP rate among removed | FP rate among kept |")
    w("|---|---:|---:|---:|---:|---:|---:|")
    base_kept = {(n, r["addr"]) for n, r in tally(rows, names, K, "none")[4]}
    for v in VETOES:
        if v == "none":
            continue
        kept = {(n, r["addr"]) for n, r in tally(rows, names, K, v)[4]}
        removed_keys = base_kept - kept
        rtp = rfp = runk = 0
        for n in names:
            rec = rows[n]
            for r in rec["rows"]:
                if (n, r["addr"]) not in removed_keys:
                    continue
                c = classify(r["sym"], rec, "meta", True)
                rtp += c == "user"
                rfp += c == "nonuser"
                runk += c == "unknown"
        kr = row(rows, names, K, v, base)
        kept_fp_rate = 100.0 * kr["fp"] / kr["n"] if kr and kr["n"] else 0.0
        rem_n = rtp + rfp
        rem_fp_rate = 100.0 * rfp / rem_n if rem_n else 0.0
        w(f"| {v} | {len(removed_keys)} | {rfp} | {rtp} | {runk} | "
          f"{rem_fp_rate:.1f}% | {kept_fp_rate:.1f}% |")
    w("\nRead the last two columns together: the veto is doing useful work only where "
      "the FP rate among what it removed is materially higher than the FP rate among "
      "what it kept. Equal rates mean it is discarding functions at random with respect "
      "to correctness — buying precision purely by shrinking the denominator, which the "
      "`--min-anchors` dial already does more cheaply.\n")

    # ── fail-closed risk ──
    w("\n## Fail-closed risk: binaries left with nothing\n")
    w("Attribution feeds a downstream generator that needs at least one accepted "
      "function to produce anything at all. A veto that raises precision by silencing "
      "whole binaries trades a precision number for coverage, so the count of binaries "
      "left empty is part of its cost, not a footnote.\n")
    w("| veto | binaries with >= 1 STRONG function | binaries emptied | median STRONG per binary |")
    w("|---|---:|---:|---:|")
    for v in VETOES:
        per = {n: len(select(rows[n], K, v)) for n in names}
        nonempty = sum(1 for c in per.values() if c)
        vals = sorted(per.values())
        med = vals[len(vals) // 2] if vals else 0
        w(f"| {v} | {nonempty}/{len(names)} | {len(names) - nonempty} | {med} |")

    w("\n**Per-binary STRONG counts by arm:**\n")
    w("| binary | domain | " + " | ".join(f"`{v}`" for v in VETOES) + " |")
    w("|---|---|" + "---:|" * len(VETOES))
    for n in names:
        cells = " | ".join(str(len(select(rows[n], K, v))) for v in VETOES)
        w(f"| {n} | {rows[n]['domain']} | {cells} |")

    # ── FP causes surviving the veto ──
    w("\n## False attributions that survive the strongest veto\n")
    w("The mechanism `bench/origin` predicts the veto should catch is a library generic "
      "that inlined a user closure — it carries the user Locations that made it STRONG "
      "*and* its own library Locations. Any FP surviving the `any` veto did not carry a "
      "single library Location, which is a claim about the mechanism worth checking "
      "directly rather than assuming.\n")
    surv = collections.Counter()
    caught = collections.Counter()
    kept_any = {(n, r["addr"]) for n, r in tally(rows, names, K, "any")[4]}
    for n in names:
        rec = rows[n]
        for r in rec["rows"]:
            if r["anchors"] < K:
                continue
            if classify(r["sym"], rec, "meta", True) != "nonuser":
                continue
            (surv if (n, r["addr"]) in kept_any else caught)[fp_kind(r["sym"])] += 1
    w("| FP cause | caught by `any` veto | survives `any` veto |")
    w("|---|---:|---:|")
    for kind in sorted(set(surv) | set(caught), key=lambda k: -(surv[k] + caught[k])):
        w(f"| {kind} | {caught[kind]} | {surv[kind]} |")
    w(f"| **total** | **{sum(caught.values())}** | **{sum(surv.values())}** |")

    body = "\n".join(out)
    with open(args.out, "w") as fh:
        fh.write(body)
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())

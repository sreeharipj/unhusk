#!/usr/bin/env python3
"""
report_results.py — REPORTER. Reads rows.json from collect_rows.py, applies the
authorship rulers, and emits the results markdown (tables + full false-attribution list).

Cheap and re-runnable: no unhusk, no nm. Iterate on presentation without re-measuring.

ORACLES (both reported, never merged)
  depcrate  INHERITED. non-user iff leading crate is in unhusk's DEPCRATE dump. UNSOUND:
            DEPCRATE only lists deps that HAVE panic Locations, so a dep with no panics
            of its own is scored as *user*. Kept only for continuity with
            docs/validation.md.
  meta      cargo metadata authorship map. user iff leading crate is a workspace-member
            target; non-user iff a resolved dependency target or std; else `unknown`
            (reported, never folded into either side).

RULERS
  strict     leading crate verbatim.
  unwrapped  additionally unwraps forwarding std wrappers whose body IS the user closure
             (__rust_begin_short_backtrace::<F>, LocalKey::with::<F>).

STRATA
  B (primary, pre-registered in 63d48e0): inherited domain map. async+parallel => ASYNC.
  A-prime (EXPLORATORY, post-hoc): a runtime generic monomorphized over an author crate.
          Written after Rule A failed; never used for a headline claim.

INTERVALS
  Wilson 95% over functions, plus a cluster bootstrap resampling BINARIES. Functions are
  not independent -- they cluster by binary -- so function-level Wilson is too narrow.
  The bootstrap is the honest interval.

Usage: report_results.py rows.json [rows2.json ...] --out RESULTS_BODY.md
"""
import argparse
import collections
import json
import math
import random
import re
import sys

STD_CRATES = {
    "std", "alloc", "core", "compiler_builtins", "rustc_std_workspace_alloc",
    "rustc_std_workspace_std", "rustc_std_workspace_core", "proc_macro", "unwind",
    "panic_unwind", "panic_abort", "gimli", "object", "addr2line", "miniz_oxide",
    "hashbrown", "rustc_demangle",
}

DOMAIN_CATEGORY = {
    "miniserve": "async", "dufs": "async", "mprocs": "async", "dog": "async",
    "rustscan": "async", "trip": "async", "trippy": "async", "oha": "async",
    "bandwhich": "async", "xh": "async", "gping": "async",
    "fclones": "parallel",
    "gitui": "framework", "btm": "framework", "bottom": "framework",
    "starship": "macro", "typos": "macro", "taplo": "macro", "dprint": "macro",
    "rage": "crypto", "ouch": "crypto",
}
DOMAIN_ASYNC = {"async", "parallel"}

Z = 1.959963984540054


def wilson(k, n, z=Z):
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = (z / d) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return 100 * p, 100 * max(0.0, c - h), 100 * min(1.0, c + h)


def cluster_bootstrap(clusters, iters=20000, seed=20260717):
    tp = sum(a for a, _ in clusters)
    fp = sum(b for _, b in clusters)
    if tp + fp == 0:
        return float("nan"), float("nan"), float("nan")
    pt = 100 * tp / (tp + fp)
    if len(clusters) < 2:
        return pt, float("nan"), float("nan")
    rng = random.Random(seed)
    n = len(clusters)
    s = []
    for _ in range(iters):
        a = b = 0
        for _ in range(n):
            x, y = clusters[rng.randrange(n)]
            a += x
            b += y
        if a + b:
            s.append(100 * a / (a + b))
    s.sort()
    return pt, s[int(0.025 * len(s))], s[min(len(s) - 1, int(0.975 * len(s)))]


def leading_crate(sym, unwrap):
    if not sym:
        return None
    s = sym
    if unwrap:
        m = re.search(r"__rust_begin_short_backtrace::<(.+)", s)
        if m:
            s = m.group(1)
        if "LocalKey" in s:
            m = re.search(r"::with::<(.+)", s)
            if m:
                s = m.group(1)
    # Strip angle brackets and reference/pointer sigils: `<&&trippy_packet::ipv4::
    # Ipv4Packet as core::fmt::Debug>::fmt` must read as trippy_packet, not fail the
    # identifier match and get dropped to `unknown`.
    s = re.sub(r"^[<&*\s]+", "", s)
    s = re.sub(r"^(?:mut|dyn|impl)\s+", "", s)
    m = re.match(r"([a-zA-Z_][a-zA-Z0-9_]*)(?:::|<| )", s)
    return m.group(1) if m else None


def classify(sym, rec, oracle, unwrap):
    lc = leading_crate(sym, unwrap)
    if lc is None:
        return "unknown"
    if lc in STD_CRATES:
        return "nonuser"
    if oracle == "meta":
        author = set(rec.get("author_crates", []))
        dep = set(rec.get("dep_crates", []))
        if not author:
            return "unknown"
        if lc in author:
            return "user"
        if lc in dep:
            return "nonuser"
        return "unknown"
    return "nonuser" if lc in set(rec.get("depcrate_deps", [])) else "user"


def fp_kind(sym):
    s = sym or ""
    if "__rust_begin_short_backtrace" in s:
        return "thread-trampoline (std generic over user fn)"
    if "LocalKey" in s:
        return "TLS accessor (std generic over user closure)"
    if re.search(r"rayon|ParallelIterator|bridge_producer|plumbing", s):
        return "rayon generic (data-parallel, inlines user closure)"
    if re.search(r"handler_service|Middleware|middleware|Service<|Filter<|Handler<", s):
        return "framework handler-adapter (monomorphized over user handler)"
    if re.search(r"futures|tokio|PollFn|poll_fn|Pin<|Timeout|FuturesUnordered|Future", s):
        return "futures combinator (inlines user closure)"
    if re.search(r"core::iter::adapters|core::slice::sort|core::ops::function", s):
        return "core generic (iter/sort/fn-shim over user closure)"
    if re.search(r"serde|Deserialize|Serialize", s):
        return "serde generic (derive/monomorph over user type)"
    # Fallback: no recognized adapter shape. NOT a verdict that the bytes are stock
    # library code -- author_parameterized() decides that, and disagrees with this
    # bucket often (many rows here still name an author crate in their generic args).
    return "unclassified library generic (no recognized adapter pattern)"


def author_parameterized(sym, rec):
    """
    Was this library generic monomorphized over AUTHOR code?
      True  -> yes (actix_web::handler::handler_service::<miniserve::api, ...>)
      False -> no; stock library bytes
      None  -> UNDETERMINABLE (see below)

    This is the distinction that decides what a false attribution actually COSTS. Both
    classes are "not author-written" under a leading-crate ruler, but:
      - author-parameterized: these bytes exist only because the author's code exists.
        The instantiation is specific to this binary, so as a signature seed it is still
        author-discriminative -- a rule built on it is not prone to firing on unrelated
        software.
      - stock dependency code: bytes present in anything linking that crate. A signature
        seed here is a real cross-project false-positive risk.

    THE None CASE IS LOAD-BEARING. Legacy Rust mangling does not encode generic
    ARGUMENTS -- it mangles the definition path, so a monomorphized instance still reads
    `<nom::internal::MapOpt<F,G> as nom::internal::Parser<I>>::process` with placeholder
    params. On a legacy-mangled binary the substitution is simply not in the symbol, so
    "no author crate appears" is NOT evidence of stock library code -- it is evidence of
    nothing. Returning False there would have manufactured a finding: it is exactly how
    rage's 4 FPs were briefly, wrongly, called "genuine dependency code". v0 mangling does
    encode arguments, so the test is valid there and only there.
    """
    if rec.get("mangling") != "v0":
        return None
    author = set(rec.get("author_crates", []))
    if not author or not sym:
        return None
    lead = leading_crate(sym, unwrap=False)
    inner = {m.group(1) for m in re.finditer(r"([a-zA-Z_][a-zA-Z0-9_]*)::", sym)}
    inner.discard(lead)
    return bool(inner & author)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rows", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-anchors", type=int, default=2)
    args = ap.parse_args()

    data = {}
    for path in args.rows:
        with open(path) as fh:
            data.update(json.load(fh))
    if not data:
        print("no rows", file=sys.stderr)
        return 1

    for name, rec in data.items():
        cat = DOMAIN_CATEGORY.get(name, "cli")
        rec["domain"] = cat
        rec["stratum_b"] = "async" if cat in DOMAIN_ASYNC else "sync"
        rec["stratum_ap"] = "async" if rec.get("async_mech_symbols") else "sync"

    K = args.min_anchors
    out = []
    w = out.append

    def tally(names, pred, oracle, unwrap):
        clusters, tp, fp, unk = [], 0, 0, 0
        for n in names:
            rec = data[n]
            a = b = 0
            for r in rec["rows"]:
                if not pred(r):
                    continue
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
        return tp, fp, unk, clusters

    def table(title, names, pred):
        w(f"\n**{title}** — {len(names)} binaries: "
          f"{', '.join(sorted(names)) if len(names) <= 14 else str(len(names)) + ' binaries'}\n")
        w("| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |")
        w("|---|---|---:|---:|---:|---:|---:|---|---|")
        for oracle in ("meta", "depcrate"):
            for unwrap in (False, True):
                tp, fp, unk, cl = tally(names, pred, oracle, unwrap)
                n = tp + fp
                pt, lo, hi = wilson(tp, n)
                _, blo, bhi = cluster_bootstrap(cl)
                rl = "unwrapped" if unwrap else "strict"
                if n == 0:
                    w(f"| {oracle} | {rl} | 0 | 0 | 0 | {unk} | n/a | n too small | n too small |")
                    continue
                bs = "n too small" if len(cl) < 2 else f"[{blo:.1f}, {bhi:.1f}]"
                w(f"| {oracle} | {rl} | {n} | {tp} | {fp} | {unk} | {pt:.1f}% | "
                  f"[{lo:.1f}, {hi:.1f}] | {bs} |")

    names_all = sorted(data)
    w("## Per-binary inventory\n")
    w("| binary | stratum B | domain | certain | STRONG | author crates | dep crates (metadata) | dep crates (DEPCRATE) |")
    w("|---|---|---|---:|---:|---:|---:|---:|")
    for n in names_all:
        rec = data[n]
        strong = sum(1 for r in rec["rows"] if r["anchors"] >= K)
        w(f"| {n} | {rec['stratum_b']} | {rec['domain']} | {len(rec['rows'])} | {strong} | "
          f"{len(rec.get('author_crates', []))} | {len(rec.get('dep_crates', []))} | "
          f"{len(rec.get('depcrate_deps', []))} |")

    w("\n## STRONG tier — stratified (Rule B, pre-registered)\n")
    for strat in ("sync", "async"):
        sub = [n for n in names_all if data[n]["stratum_b"] == strat]
        if sub:
            table(f"STRONG (>= {K} anchors) — {strat.upper()}", sub, lambda r: r["anchors"] >= K)
        else:
            w(f"\n**STRONG — {strat.upper()}**: n = 0 binaries. Stratum empty; no CI can be "
              f"stated. This is a gap in the corpus, not a result.\n")
    table(f"STRONG (>= {K} anchors) — COMBINED", names_all, lambda r: r["anchors"] >= K)

    w("\n## SINGLE tier — stratified (Rule B)\n")
    for strat in ("sync", "async"):
        sub = [n for n in names_all if data[n]["stratum_b"] == strat]
        if sub:
            table(f"SINGLE (1 anchor) — {strat.upper()}", sub, lambda r: r["anchors"] == 1)
    table("SINGLE (1 anchor) — COMBINED", names_all, lambda r: r["anchors"] == 1)

    w("\n## Exploratory stratification (Rule A-prime, POST-HOC — not a headline claim)\n")
    w("Rule A-prime: ASYNC iff a runtime generic is monomorphized over an author crate "
      "(i.e. the combinator actually inlines author code), not merely linked. Written "
      "after Rule A was refuted; reported for transparency only.\n")
    for strat in ("sync", "async"):
        sub = [n for n in names_all if data[n]["stratum_ap"] == strat]
        if sub:
            table(f"[exploratory] STRONG — {strat.upper()} (A-prime)", sub,
                  lambda r: r["anchors"] >= K)

    w("\n## Threshold ladder (`--min-anchors`), combined, cargo-metadata oracle / unwrapped\n")
    w("| min-anchors | n | precision | Wilson 95% | cluster bootstrap 95% | recall retained |")
    w("|---:|---:|---:|---|---|---:|")
    base = sum(len(data[n]["rows"]) for n in names_all)
    for k in (1, 2, 3, 4):
        tp, fp, unk, cl = tally(names_all, lambda r, k=k: r["anchors"] >= k, "meta", True)
        n = tp + fp
        if n == 0:
            continue
        pt, lo, hi = wilson(tp, n)
        _, blo, bhi = cluster_bootstrap(cl)
        bs = "n too small" if len(cl) < 2 else f"[{blo:.1f}, {bhi:.1f}]"
        w(f"| >= {k} | {n} | {pt:.1f}% | [{lo:.1f}, {hi:.1f}] | {bs} | {100*n/base:.1f}% |")

    # ── full false-attribution list ──
    w(f"\n## Every false attribution — STRONG tier (>= {K} anchors)\n")
    w("Ruler: cargo-metadata oracle, **strict** (no wrapper unwrapping) — the most "
      "conservative reading, so this list is a superset. Rows marked *(rescued by "
      "unwrapped)* are forwarding wrappers whose body is the author's closure; the "
      "`unwrapped` ruler counts them as user, and that is a judgment call you can audit "
      "here rather than take on trust.\n")
    w("| binary | stratum | address | anchors | author-param? | why it is not user | demangled symbol |")
    w("|---|---|---|---:|---|---|---|")
    total_fp = 0
    kinds = collections.Counter()
    ap_counts = collections.Counter()
    for n in names_all:
        rec = data[n]
        for r in rec["rows"]:
            if r["anchors"] < K:
                continue
            if classify(r["sym"], rec, "meta", False) != "nonuser":
                continue
            total_fp += 1
            kind = fp_kind(r["sym"])
            kinds[kind] += 1
            ap = author_parameterized(r["sym"], rec)
            ap_counts[ap] += 1
            ap_label = {True: "**yes**", False: "no",
                        None: "*undeterminable (legacy mangling)*"}[ap]
            rescued = classify(r["sym"], rec, "meta", True) == "user"
            note = kind + (" *(rescued by unwrapped)*" if rescued else "")
            sym = (r["sym"] or "(no symbol)").replace("|", "\\|")
            if len(sym) > 150:
                sym = sym[:150] + "…"
            w(f"| {n} | {rec['stratum_b']} | `{r['addr']}` | {r['anchors']} | "
              f"{ap_label} | {note} | `{sym}` |")
    if total_fp == 0:
        w("| — | — | — | — | — | no STRONG false attributions under this ruler | — |")
    w(f"\n**{total_fp} STRONG false attributions total.** By cause:\n")
    for k, c in kinds.most_common():
        w(f"- {c} — {k}")
    w(f"\n**By author-parameterization** (see `author_parameterized()` — this split, not "
      f"the cause split above, is what decides the *cost* of a false attribution):\n")
    w(f"- **{ap_counts[True]}** are library generics *monomorphized over author code* — "
      f"these bytes exist only because the author's code does, so the instantiation is "
      f"specific to this binary and stays author-discriminative as a signature seed.")
    w(f"- **{ap_counts[False]}** are **stock dependency code** — bytes present in "
      f"anything linking that crate. These are the ones that would put a cross-project "
      f"false positive into a generated rule.")
    w(f"- **{ap_counts[None]}** are **undeterminable**: legacy-mangled binaries do not "
      f"encode generic arguments, so whether the generic was instantiated over author "
      f"code is not recoverable from the symbol. Counted, never guessed.")

    w(f"\n## Unknown-authorship functions (excluded from both numerator and denominator)\n")
    w("| binary | count | note |")
    w("|---|---:|---|")
    for n in names_all:
        rec = data[n]
        unk = [r for r in rec["rows"]
               if r["anchors"] >= K and classify(r["sym"], rec, "meta", False) == "unknown"]
        if unk:
            nosym = sum(1 for r in unk if not r["sym"])
            w(f"| {n} | {len(unk)} | {nosym} with no symbol at all; rest: leading crate "
              f"absent from cargo metadata |")

    body = "\n".join(out)
    with open(args.out, "w") as fh:
        fh.write(body)
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())

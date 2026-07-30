#!/usr/bin/env python3
"""
scripts/oracle.py — shared Rust-authorship oracle primitives, consolidated out
of five independent copies that had already started to diverge:
`realval/report_results.py`, `realval/precision_ci.py`, `realval/tier_eval.py`
(the latter two now deleted as superseded — see git history), `src/bin/
anchor_headroom.rs`, and `bench/origin/ground_truth.py`.

Why this exists: the DWARF-oracle std-sysroot bug was independently found and
fixed TWICE on divergent branches earlier in this project's history, because
the same fact (which paths are std, which crates are never author code) was
hardcoded in more than one place and one copy got the fix while the other
didn't. `STD_CRATES` alone existed as five slowly-diverging copies before this
file existed. This is the one place that fact lives now.

Nothing here changes any published measurement's methodology — this is a
pure move-and-verify refactor. `realval/report_results.py` re-run against its
existing `rows_src.json` after migrating to this module produces
byte-identical output to the previously-committed `results_body.md`.

Two genuine (verified-zero-impact) corrections made during consolidation,
not silent behavior changes:
  - `STD_CRATES` here is the union of all five prior copies (25 entries,
    `anchor_headroom.rs`'s list was already the fullest) rather than
    `realval`'s narrower 17-entry list. Checked against the current
    `realval/rows_src.json` (2225 rows): zero rows have a leading crate in the
    8 added entries, so this does not change any existing published number.
  - `cargo_authorship()` discards `build_script_build` from every bucket
    (a build.rs's own compiled name, shared across every crate that has one —
    carries no authorship signal, per `collect_rows.py`'s original comment).
    `bench/origin/ground_truth.py`'s from-scratch reimplementation had
    dropped this discard; checked against tonight's corpus: zero FDEs were
    actually labeled with it (a build script's own binary is never linked
    into the final artifact), so this is precautionary, not an observed fix.
"""
import json
import os
import re
import subprocess

# ── STD_CRATES ────────────────────────────────────────────────────────────────

STD_CRATES = {
    "std", "alloc", "core", "compiler_builtins",
    "rustc_std_workspace_core", "rustc_std_workspace_alloc", "rustc_std_workspace_std",
    "proc_macro", "test", "unwind", "panic_unwind", "panic_abort", "std_detect",
    "rustc_demangle", "addr2line", "gimli", "object", "miniz_oxide", "hashbrown",
    "libc", "adler", "adler2", "cfg_if", "getopts", "unwinding",
}


# ── leading_crate ─────────────────────────────────────────────────────────────

def leading_crate(sym, unwrap=False):
    """First path segment of a demangled symbol, e.g. `trippy_packet` from
    `<&&trippy_packet::ipv4::Ipv4Packet as core::fmt::Debug>::fmt`.

    `unwrap=True` additionally sees through the two pure-forwarding std
    wrapper shapes whose *body* is the author's own closure/function, rather
    than counting the wrapper's own crate (`std`) as the leading one:
    `__rust_begin_short_backtrace::<F>` (thread-trampoline) and
    `LocalKey::with::<F>` (TLS accessor). This is a measurement judgment
    call, not a default — callers that want the conservative reading pass
    `unwrap=False` (the default) and get the wrapper's own crate.
    """
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
    s = re.sub(r"^[<&*\s]+", "", s)
    s = re.sub(r"^(?:mut|dyn|impl)\s+", "", s)
    m = re.match(r"([a-zA-Z_][a-zA-Z0-9_]*)(?:::|<| )", s)
    return m.group(1) if m else None


def norm(name):
    """Cargo package name -> Rust crate identifier (hyphens become underscores)."""
    return name.replace("-", "_")


# ── nm_symbol_table ───────────────────────────────────────────────────────────

def nm_symbol_table(binary, with_size=False, timeout=900):
    """
    addr -> demangled symbol name (or (name, size) if with_size), via
    `nm --defined-only | rustfilt`.

    NOT `nm -C`. binutils's demangler does not understand Rust v0
    (`_RNvCs..._3oha3run`) and chokes on legacy symbols carrying an
    `.llvm.<hash>` suffix — both come back still-mangled and silently fail
    every downstream classification. Measured impact before this was fixed:
    14% of STRONG rows on the async corpus, dropped into an excluded
    `unknown` bucket rather than counted (see `[[project_validation_harness]]`
    memory / `realval/collect_rows.py`'s `nm_table` docstring for the full
    story). rustfilt handles legacy + v0 + `.llvm` suffixes.

    Returns (table, mangling, n_v0, n_legacy) where `mangling` is
    "v0"/"legacy"/"none", from which scheme dominates the raw `nm` output —
    which matters for `author_parameterized`-style analysis: legacy mangling
    does not encode generic arguments, v0 does.
    """
    raw = subprocess.run(
        ["nm", "--defined-only", "-S", binary] if with_size else ["nm", "--defined-only", binary],
        capture_output=True, text=True, timeout=timeout,
    ).stdout
    n_v0 = len(re.findall(r"\s_R\w", raw))
    n_legacy = len(re.findall(r"\s_ZN\w", raw))
    mangling = "v0" if n_v0 > n_legacy else ("legacy" if n_legacy else "none")

    r = subprocess.run(["rustfilt"], input=raw, capture_output=True, text=True, timeout=timeout)
    table = {}
    for line in r.stdout.splitlines():
        if with_size:
            # Type-filtered (T/t/W/w only — text symbols, i.e. functions) since
            # this mode is used to bulk-scan every defined symbol for FDE
            # mapping, where a stray data symbol could collide with a function
            # FDE's address range. Address length unconstrained (nm's width
            # varies), unlike the non-with_size branch below.
            parts = line.split(None, 3)
            if len(parts) < 3:
                continue
            addr_hex, size_hex, typ = parts[0], parts[1], parts[2]
            if typ not in ("T", "t", "W", "w"):
                continue
            if not re.match(r"^[0-9a-f]+$", addr_hex):
                continue
            name = parts[3] if len(parts) > 3 else ""
            size = int(size_hex, 16) if re.match(r"^[0-9a-f]+$", size_hex) else 0
            table[int(addr_hex, 16)] = (name, size)
        else:
            # Exact-address lookup mode (realval): every defined symbol, keyed
            # by its exact 16-hex-digit address, no type filter — callers look
            # up specific known addresses (e.g. from UNHUSK_DUMP_TIERS), they
            # don't bulk-scan by type.
            parts = line.split(None, 2)
            if len(parts) != 3 or not re.match(r"^[0-9a-f]{16}$", parts[0]):
                continue
            table[int(parts[0], 16)] = parts[2]
    return table, mangling, n_v0, n_legacy


# ── cargo_authorship ──────────────────────────────────────────────────────────

CODE_KINDS = {"lib", "rlib", "dylib", "cdylib", "staticlib", "proc-macro", "bin"}


def _cargo_metadata(repo, timeout=300):
    r = subprocess.run(
        ["cargo", "metadata", "--format-version", "1", "--no-deps", "--offline"],
        cwd=repo, capture_output=True, text=True, timeout=timeout,
    )
    if r.returncode != 0:
        tail = (r.stderr.strip().splitlines() or ["?"])[-1]
        return None, f"cargo metadata --no-deps failed: {tail[:200]}"
    return json.loads(r.stdout), None


def _cargo_lock_dep_names(repo):
    """Cargo.lock packages carrying a `source` field -> normalized names.
    Offline and exact; a dep whose crate name differs from its package name
    lands in neither bucket rather than being silently folded into one."""
    path = os.path.join(repo, "Cargo.lock")
    try:
        text = open(path).read()
    except OSError:
        return set(), "Cargo.lock not found"
    dep = set()
    for block in re.split(r"\[\[package\]\]", text)[1:]:
        m = re.search(r'^name\s*=\s*"([^"]+)"', block, re.M)
        if not m:
            continue
        if re.search(r'^source\s*=\s*"', block, re.M):
            dep.add(norm(m.group(1)))
    return dep, None


def cargo_authorship(repo, bin_name=None):
    """
    (author, workspace, dep, error) — the authorship ruler.

    Uses CRATE (target) names, not package names: package `fd-find` builds a
    bin target `fd`, and the symbol table says `fd::...` — a Cargo.lock-name
    lookup for `fd_find` would find nothing and drop every one of fd's user
    functions to unknown. `--no-deps` is also what makes this work offline: a
    full resolve wants dev-dependencies, which a release build never
    downloaded.

    Two granularities, selected by whether `bin_name` is given and resolves
    to a workspace member's `bin` target:

    - `bin_name=None` (or unresolvable): **coarse** mode — every workspace
      member package's targets go into `author`, `workspace` stays empty.
      This is `realval`'s original, published-numbers behavior: `docs/
      validation.md`'s 94.4%/87.3% figures were already computed with every
      workspace sibling counted as author, not just the target package.
    - `bin_name` given and found: **fine** mode — `author` is only the
      package that owns the `bin` target named `bin_name`; every other
      workspace member's targets go into `workspace` instead. `workspace` is
      a strict refinement of what `author` would otherwise contain — for
      `realval`'s coarse semantics, a caller does `author | workspace`.

    Author membership wins over dep membership in both modes: an author
    crate published to crates.io can be pulled in as its own CLI's
    dependency (the `typos` lib under the `typos-cli` bin) — those bytes are
    still the author's.

    `build_script_build` (a build.rs's own compiled target name, shared
    across every crate that has one) is discarded from every bucket: it
    carries no authorship signal and is never linked into the final binary
    anyway.
    """
    md, err = _cargo_metadata(repo)
    if md is None:
        return set(), set(), set(), err

    dep, lock_err = _cargo_lock_dep_names(repo)
    err = err or lock_err

    def targets_of(pkg):
        names = {norm(t["name"]) for t in pkg.get("targets", []) if CODE_KINDS & set(t.get("kind", []))}
        names.add(norm(pkg["name"]))
        return names

    target_pkg = None
    if bin_name:
        for p in md.get("packages", []):
            if any("bin" in t.get("kind", []) and t["name"] == bin_name for t in p.get("targets", [])):
                target_pkg = p
                break

    if target_pkg is None:
        author = set()
        for p in md.get("packages", []):
            author |= targets_of(p)
        workspace = set()
        if bin_name and err is None:
            err = f"no workspace member has a bin target named {bin_name!r}; using coarse (all-workspace-is-author) mode"
    else:
        author = targets_of(target_pkg)
        workspace = set()
        for p in md.get("packages", []):
            if p is target_pkg:
                continue
            workspace |= targets_of(p)
        workspace -= author

    dep -= author
    dep -= workspace
    author.discard("build_script_build")
    workspace.discard("build_script_build")
    dep.discard("build_script_build")
    return author, workspace, dep, err


# ── Confidence intervals ──────────────────────────────────────────────────────

Z95 = 1.959963984540054


def wilson(k, n, z=Z95):
    """Wilson score interval for k successes in n trials. Returns (point, lo, hi)
    as percentages. `n == 0` returns (nan, nan, nan)."""
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return 100 * p, 100 * max(0.0, center - half), 100 * min(1.0, center + half)


def cluster_bootstrap(clusters, iters=20000, seed=20260717):
    """
    Percentile bootstrap CI resampling whole CLUSTERS (e.g. binaries/crates),
    not individual functions — because functions are not independent, they
    cluster by binary, and one large binary can dominate a pooled function
    count. Function-level Wilson alone is too narrow; this is the honest
    interval when it disagrees.

    `clusters`: list of (successes, failures) per cluster.
    Returns (point, lo, hi) as percentages; `nan` bounds if fewer than 2
    non-empty clusters (too small to bootstrap).
    """
    import random

    tot_s = sum(s for s, _ in clusters)
    tot_f = sum(f for _, f in clusters)
    if tot_s + tot_f == 0:
        return float("nan"), float("nan"), float("nan")
    point = 100 * tot_s / (tot_s + tot_f)
    if len(clusters) < 2:
        return point, float("nan"), float("nan")
    rng = random.Random(seed)
    n = len(clusters)
    samples = []
    for _ in range(iters):
        s = f = 0
        for _ in range(n):
            a, b = clusters[rng.randrange(n)]
            s += a
            f += b
        if s + f:
            samples.append(100 * s / (s + f))
    if not samples:
        return point, float("nan"), float("nan")
    samples.sort()
    lo = samples[int(0.025 * len(samples))]
    hi = samples[min(len(samples) - 1, int(0.975 * len(samples)))]
    return point, lo, hi

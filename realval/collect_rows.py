#!/usr/bin/env python3
"""
collect_rows.py — COLLECTOR. Runs the slow half once and freezes raw evidence to JSON.

For each provenance-PASSing binary it records, per certain function:
    addr, tier, anchor_count, demangled symbol (from the oracle twin)
plus, per binary, everything an authorship ruler could need:
    - depcrate_deps : unhusk's DEPCRATE dump (dep crates seen in panic paths)
    - lock_user     : Cargo.lock packages with NO `source` field  = workspace members,
                      i.e. crates the author wrote in this repo
    - lock_dep      : Cargo.lock packages WITH a `source` field   = registry deps
    - async_symbols : counts of runtime-crate symbols, for stratification

No classification decisions are made here. Rulers live in report_results.py so they can
be re-run without re-invoking unhusk/nm (minutes per binary).

WHY Cargo.lock MATTERS
----------------------
The inherited oracle called a symbol non-user iff its crate was in DEPCRATE. But
DEPCRATE only lists deps that HAVE panic Locations. For ripgrep it names 21 crates while
Cargo.lock has 49 registry deps -- so 28 real dependencies were invisible and their
symbols scored as *user*, inflating precision. That bites exactly the FP mode under
study (a dep generic monomorphized over a user closure). Cargo.lock closes the hole and
gives a principled ruler: authored-in-this-repo vs pulled-from-registry.

Usage: collect_rows.py --provenance <tsv> --out rows.json DIR [DIR ...]
"""
import argparse
import collections
import glob
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
UNHUSK = os.path.join(HERE, "..", "target", "release", "unhusk")

ASYNC_RUNTIMES = {
    "tokio", "tokio_util", "tokio_stream", "futures", "futures_util", "futures_core",
    "futures_executor", "futures_channel", "async_std", "smol", "async_io", "async_task",
    "rayon", "rayon_core", "actix", "actix_web", "actix_rt", "hyper", "axum", "warp",
    "reqwest", "async_channel", "crossbeam_deque",
}


def norm(n):
    return n.replace("-", "_")


def leading_crate(sym):
    if not sym:
        return None
    s = sym.lstrip("<")
    m = re.match(r"([a-zA-Z_][a-zA-Z0-9_]*)(?:::|<| )", s)
    return m.group(1) if m else None


def parse_cargo_lock(path):
    """(workspace_members, registry_deps). No `source` field => authored in this repo.

    Fallback only. Package name != crate name (package `fd-find` ships a binary whose
    symbols read `fd::`), so this misfiles such crates; authorship_map() is preferred.
    """
    user, dep = set(), set()
    try:
        text = open(path).read()
    except OSError:
        return user, dep
    for block in re.split(r"\[\[package\]\]", text)[1:]:
        m = re.search(r'^name\s*=\s*"([^"]+)"', block, re.M)
        if not m:
            continue
        has_source = re.search(r'^source\s*=\s*"', block, re.M) is not None
        (dep if has_source else user).add(norm(m.group(1)))
    return user, dep


# Target kinds that actually contribute code to a release binary. Test/bench/example
# targets are author code but never linked into it; `custom-build` (build-script-build)
# is a target name shared by every crate that has a build.rs, so it carries no
# authorship signal and must not be treated as an author crate name.
CODE_KINDS = {"lib", "rlib", "dylib", "cdylib", "staticlib", "proc-macro", "bin"}


def authorship_map(repo):
    """
    (author_crates, dep_crates) via `cargo metadata` — the authoritative ruler.

    Uses CRATE names (target names), not package names: package `fd-find` builds a bin
    target `fd`, and the symbol table says `fd::...`. Parsing Cargo.lock alone would look
    for `fd_find`, find nothing, and drop every one of fd's user functions to `unknown`.

    Author membership WINS over dep membership. That is deliberate: an author crate that
    is also published to crates.io can be pulled in as a dependency of its own CLI (the
    `typos` lib under the `typos-cli` bin). By authorship those bytes are the author's,
    which is the same correction docs/validation.md applies by hand.
    """
    r = subprocess.run(["cargo", "metadata", "--format-version", "1"],
                       cwd=repo, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        return set(), set(), f"cargo metadata failed: {r.stderr.strip().splitlines()[-1:]}"
    md = json.loads(r.stdout)
    ws = set(md.get("workspace_members", []))
    user, dep = set(), set()
    for p in md.get("packages", []):
        names = {norm(t["name"]) for t in p.get("targets", [])
                 if CODE_KINDS & set(t.get("kind", []))}
        names.add(norm(p["name"]))
        (user if p["id"] in ws else dep).update(names)
    dep -= user          # author precedence (the `typos` case)
    user.discard("build_script_build")
    dep.discard("build_script_build")
    return user, dep, None


def find_repo(repo_root, name):
    """The cloned source tree that produced this binary (holds Cargo.toml/Cargo.lock)."""
    direct = os.path.join(repo_root, name)
    if os.path.exists(os.path.join(direct, "Cargo.toml")):
        return direct
    hits = glob.glob(os.path.join(repo_root, name, "**", "Cargo.lock"), recursive=True)
    return os.path.dirname(hits[0]) if hits else None


def nm_table(debug):
    t = {}
    r = subprocess.run(["nm", "-C", debug], capture_output=True, text=True, timeout=900)
    for line in r.stdout.splitlines():
        p = line.split(None, 2)
        if len(p) == 3 and re.match(r"^[0-9a-f]{16}$", p[0]):
            t[int(p[0], 16)] = p[2]
    return t


def collect(name, strp, dbg, repo):
    env = dict(os.environ, UNHUSK_DUMP_TIERS="1", UNHUSK_DUMP_DEPS="1")
    r = subprocess.run([UNHUSK, strp], capture_output=True, text=True, env=env, timeout=2400)
    out = r.stdout
    depcrate = sorted({norm(m.group(1)) for m in re.finditer(r"DEPCRATE\t(.+)", out)})
    nm = nm_table(dbg)

    rows = []
    for line in out.splitlines():
        m = re.match(r"TIERDUMP\t0x([0-9a-f]+)\t(\w+)\t(\d+)", line)
        if not m:
            continue
        addr = int(m.group(1), 16)
        rows.append({
            "addr": f"0x{addr:x}", "tier": m.group(2),
            "anchors": int(m.group(3)), "sym": nm.get(addr),
        })

    async_syms = collections.Counter()
    for sym in nm.values():
        lc = leading_crate(sym)
        if lc in ASYNC_RUNTIMES:
            async_syms[lc] += 1

    meta_err = None
    if repo:
        author, dep, meta_err = authorship_map(repo)
        if meta_err:  # cargo metadata unavailable: fall back to the lockfile parser
            author, dep = parse_cargo_lock(os.path.join(repo, "Cargo.lock"))
    else:
        author, dep, meta_err = set(), set(), "no repo found"

    # Runtime generics monomorphized over an author crate: the actual mechanism
    # ("futures combinators / handler-adapters that inline a user closure"), as opposed
    # to merely LINKING a runtime. Recorded here; used by the exploratory Rule A'.
    mech = collections.Counter()
    if author:
        pat = re.compile(r"\b(" + "|".join(re.escape(u) for u in sorted(author)) + r")::")
        for sym in nm.values():
            lc = leading_crate(sym)
            if lc in ASYNC_RUNTIMES and pat.search(sym or ""):
                mech[lc] += 1

    return {
        "rows": rows,
        "depcrate_deps": depcrate,
        "repo": repo,
        "meta_error": meta_err,
        "author_crates": sorted(author),
        "dep_crates": sorted(dep),
        "async_symbols": dict(async_syms.most_common()),
        "async_mech_symbols": dict(mech.most_common()),
        "n_symbols": len(nm),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--provenance", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--repo-root", default=None,
                    help="dir holding cloned repos (<repo-root>/<name>/Cargo.lock)")
    args = ap.parse_args()

    allowed = set()
    with open(args.provenance) as fh:
        for line in fh:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 3 and p[2] == "PASS":
                allowed.add(p[0])

    data = {}
    for d in args.dirs:
        repo_root = args.repo_root or os.path.join(d, "src")
        for strp in sorted(glob.glob(os.path.join(d, "*.stripped"))):
            name = os.path.basename(strp)[:-9]
            dbg = os.path.join(d, name + ".debug")
            if not os.path.exists(dbg) or name not in allowed:
                continue
            repo = find_repo(repo_root, name)
            try:
                rec = collect(name, strp, dbg, repo)
            except subprocess.TimeoutExpired:
                print(f"  {name:12} TIMEOUT — skipped", file=sys.stderr)
                continue
            rec["dir"] = d
            data[name] = rec
            print(f"  {name:12} certain={len(rec['rows']):<5} "
                  f"depcrate={len(rec['depcrate_deps']):<4} "
                  f"author={len(rec['author_crates']):<3} dep={len(rec['dep_crates']):<4} "
                  f"{'META_ERR:' + str(rec['meta_error'])[:40] if rec['meta_error'] else 'ok'}",
                  file=sys.stderr)

    with open(args.out, "w") as fh:
        json.dump(data, fh, indent=1)
    print(f"\nwrote {args.out}: {len(data)} binaries, "
          f"{sum(len(v['rows']) for v in data.values())} certain functions", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

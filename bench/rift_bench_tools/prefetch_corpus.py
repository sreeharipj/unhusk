#!/usr/bin/env python3
"""prefetch_corpus.py — sequentially pre-download crate sources for the
RIFT-vs-unhusk benchmark's tail corpus.

The overnight chain is corpus-limited, not compute-limited: it exhausts
corpus_extended.txt around 05:40 and idles until its 06:45 deadline. This
fetches a *new* set of crates (disjoint from everything already run or planned)
so the run stays fed, and puts their .crate tarballs in the shared cargo
registry cache so the compile stage never blocks on network.

Sequential by design — one crate at a time, so this never competes with the
in-flight benchmark for bandwidth, and never holds the cargo package-cache
lock (raw HTTP only, no cargo invocation).

Output: TSV of verified binary crates, ready to append to a corpus file.
"""
import json
import os
import re
import subprocess
import sys
import tarfile
import time
import urllib.request

CACHE = "/home/user/.cargo/registry/cache/index.crates.io-1949cf8c6b5b557f"
OUT = "/home/user/.claude/jobs/c9691fbb/tmp/verified_corpus.tsv"
LOG = "/home/user/.claude/jobs/c9691fbb/tmp/prefetch.log"
UA = "rift-unhusk-benchmark/0.1 (author-code identification study; sreehari.nitt@gmail.com)"

# Ordered async/network first, matching the extended corpus's stated rationale:
# real Rust malware skews async (C2 clients, scanners, downloaders), and that is
# the scientifically load-bearing block. This list runs at the tail of the other
# agent's, so if the deadline closes early the valuable rows are still at front.
CANDIDATES = [
    # ── async / network / web ───────────────────────────────────────────────
    "feroxbuster", "lychee", "mqttui", "drill", "rewrk", "sfz",
    "simple-http-server", "basic-http-server", "hickory-dns", "taplo-cli",
    "dprint", "gitoxide", "ffsend", "rustypaste-cli",
    # ── TUI / event-loop heavy ──────────────────────────────────────────────
    "skim", "television", "xplr", "csvlens", "bacon", "binsider", "rhit",
    "diskonaut", "systeroid", "kmon", "ox", "kibi",
    # ── CLI / systems ballast ───────────────────────────────────────────────
    "fselect", "nomino", "tidy-viewer", "xcp", "diskus", "oxipng", "fend",
    "kalker", "numbat", "rink", "comrak", "git-cliff", "committed",
    "cargo-deny", "cargo-machete", "cargo-bloat", "cargo-cache", "cargo-sweep",
    "cargo-hack", "cargo-msrv", "cargo-sort", "cargo-watch", "cargo-edit",
    "cargo-generate", "flamegraph", "tree-sitter-cli", "stylua", "repgrep",
    "rip2", "lemmeknow", "jql", "rnr", "ruplacer", "pazi", "rusty-man", "nu",
]


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as fh:
        fh.write(line + "\n")


def get(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read() if binary else json.loads(r.read())


def bin_targets(crate_path, name, version):
    """Return binary target names by inspecting the crate's Cargo.toml.

    cargo install only accepts a crate that produces a binary, so a crate with
    no [[bin]] and no src/main.rs would fail the benchmark at build time and
    burn a slot. Filter those out here rather than at 3am.
    """
    root = f"{name}-{version}"
    try:
        with tarfile.open(crate_path, "r:gz") as tf:
            try:
                m = tf.extractfile(f"{root}/Cargo.toml")
                toml = m.read().decode("utf-8", "replace") if m else ""
            except KeyError:
                return []
            names = re.findall(
                r'\[\[bin\]\](.*?)(?=\n\[|\Z)', toml, re.S)
            bins = []
            for blk in names:
                m2 = re.search(r'^\s*name\s*=\s*"([^"]+)"', blk, re.M)
                if m2:
                    bins.append(m2.group(1))
            if bins:
                return bins
            members = tf.getnames()
            if f"{root}/src/main.rs" in members:
                return [name]
            # Workspace roots keep binaries in subcrates; cargo install resolves
            # that itself, so treat "has src/bin/*.rs" as a binary crate too.
            if any(n.startswith(f"{root}/src/bin/") and n.endswith(".rs")
                   for n in members):
                return [name]
    except (tarfile.TarError, OSError) as e:
        log(f"    tar error: {e}")
    return []


def main():
    os.makedirs(CACHE, exist_ok=True)
    excl = set()
    ex_path = "/home/user/.claude/jobs/c9691fbb/tmp/exclude.txt"
    if os.path.exists(ex_path):
        excl = {l.strip() for l in open(ex_path) if l.strip()}
    log(f"exclusion set: {len(excl)} crates; {len(CANDIDATES)} candidates")

    verified, skipped, failed = [], [], []
    for i, name in enumerate(CANDIDATES, 1):
        if name in excl:
            log(f"[{i}/{len(CANDIDATES)}] {name}: SKIP (already planned/run)")
            skipped.append(name)
            continue
        try:
            meta = get(f"https://crates.io/api/v1/crates/{name}")
        except Exception as e:
            log(f"[{i}/{len(CANDIDATES)}] {name}: API FAIL {e}")
            failed.append(name)
            continue

        ver = meta.get("crate", {}).get("max_stable_version")
        if not ver:
            log(f"[{i}/{len(CANDIDATES)}] {name}: no stable version")
            failed.append(name)
            continue

        dest = os.path.join(CACHE, f"{name}-{ver}.crate")
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            log(f"[{i}/{len(CANDIDATES)}] {name} {ver}: already cached")
        else:
            try:
                blob = get(
                    f"https://static.crates.io/crates/{name}/{name}-{ver}.crate",
                    binary=True)
            except Exception as e:
                log(f"[{i}/{len(CANDIDATES)}] {name}: DOWNLOAD FAIL {e}")
                failed.append(name)
                continue
            tmp = dest + ".partial"
            with open(tmp, "wb") as fh:
                fh.write(blob)
            os.rename(tmp, dest)
            log(f"[{i}/{len(CANDIDATES)}] {name} {ver}: "
                f"downloaded {len(blob)/1024:.0f}KB")

        bins = bin_targets(dest, name, ver)
        if not bins:
            log(f"    -> no binary target, dropping")
            failed.append(name)
            continue
        # bench harness syntax is `crate` or `crate:binname`
        spec = name if (len(bins) == 1 and bins[0] == name) else f"{name}:{bins[0]}"
        verified.append((spec, ver, len(bins)))
        log(f"    -> OK bins={bins} spec={spec}")
        time.sleep(0.4)  # be a good crates.io citizen

    with open(OUT, "w") as fh:
        for spec, ver, nb in verified:
            fh.write(f"{spec}\t{ver}\t{nb}\n")

    log(f"DONE verified={len(verified)} skipped={len(skipped)} failed={len(failed)}")
    log(f"failed: {' '.join(failed)}")
    log(f"wrote {OUT}")


if __name__ == "__main__":
    main()

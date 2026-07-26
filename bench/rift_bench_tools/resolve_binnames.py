#!/usr/bin/env python3
"""resolve_binnames.py — pin an explicit binary name to every corpus entry.

Why this is needed
------------------
run_headtohead.sh picks the binary to analyse with:

    [[ -z "$binname" ]] && binname=$(ls "$INSTALL/bin/" | head -1)
    cp  "$INSTALL/bin/$binname" "$debug"
    rm -f "$INSTALL/bin/$binname"

`cargo install --root` puts *every* executable a crate declares into that one
shared directory, but the harness removes only the one it used. A multi-binary
crate therefore leaves orphans behind, and the *next* crate's `ls | head -1`
can return an orphan that sorts earlier than its own binary — silently
analysing the wrong program under the right name.

Observed live, not hypothetical:
  pueue    -> installs `pueue` + `pueued`, orphaning `pueued`
  ast-grep -> installs `ast-grep` + `sg`,  orphaning `sg`
  topgrade -> analysed ast-grep's `sg`  (topgrade.log builds ast-grep-0.45 sigs)
  sccache  -> analysed pueue's `pueued` (sccache.debug is full of pueue-4.0)

Giving every entry an explicit `crate:binname` means the `ls | head -1` branch
never executes, so orphans cannot be inherited no matter what order things run
in. A binname that turns out wrong degrades to a clean `binary_not_found` error
row, which is recorded and harmless — the failure mode we want, versus a
plausible-looking row measured against the wrong binary.
"""
import json
import os
import re
import sys
import tarfile
import time
import urllib.request

CACHE = "/home/user/.cargo/registry/cache/index.crates.io-1949cf8c6b5b557f"
UA = "rift-unhusk-benchmark/0.1 (author-code identification study)"


def get(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read() if binary else json.loads(r.read())


def crate_file(name):
    """Return a local .crate path for `name`, downloading if not cached."""
    try:
        meta = get(f"https://crates.io/api/v1/crates/{name}")
    except Exception as e:
        return None, None, f"api:{e}"
    ver = meta.get("crate", {}).get("max_stable_version")
    if not ver:
        return None, None, "no-stable-version"
    dest = os.path.join(CACHE, f"{name}-{ver}.crate")
    if not (os.path.exists(dest) and os.path.getsize(dest) > 0):
        try:
            blob = get(f"https://static.crates.io/crates/{name}/{name}-{ver}.crate",
                       binary=True)
        except Exception as e:
            return None, ver, f"download:{e}"
        tmp = dest + ".partial"
        with open(tmp, "wb") as fh:
            fh.write(blob)
        os.rename(tmp, dest)
    return dest, ver, None


def bins_of(path, name, ver):
    root = f"{name}-{ver}"
    try:
        with tarfile.open(path, "r:gz") as tf:
            names = tf.getnames()
            try:
                f = tf.extractfile(f"{root}/Cargo.toml")
                toml = f.read().decode("utf-8", "replace") if f else ""
            except KeyError:
                toml = ""
            bins = []
            for blk in re.findall(r'\[\[bin\]\](.*?)(?=\n\s*\[|\Z)', toml, re.S):
                m = re.search(r'^\s*name\s*=\s*"([^"]+)"', blk, re.M)
                if m:
                    bins.append(m.group(1))
            if bins:
                return bins
            # No explicit [[bin]]: cargo auto-discovers. Two shapes matter —
            # src/bin/<name>.rs yields a binary called <name>, and
            # src/bin/<name>/main.rs yields one called <name> too (the
            # directory names it, not the file). Missing the second form is how
            # silicon, whose only entry point is src/bin/silicon/main.rs, got
            # read as two binaries called "config" and "main".
            if f"{root}/src/main.rs" in names:
                return [name]
            auto = set()
            prefix = f"{root}/src/bin/"
            for n in names:
                if not n.startswith(prefix) or not n.endswith(".rs"):
                    continue
                rest = n[len(prefix):]
                if "/" in rest:
                    if rest.endswith("/main.rs"):
                        auto.add(rest.split("/")[0])
                else:
                    auto.add(rest[:-3])
            return sorted(auto)
    except (tarfile.TarError, OSError):
        return []


def primary(bins, crate):
    """Pick the representative binary for a multi-binary crate.

    Exact name match wins; otherwise the longest shared prefix with the crate
    name (so `pueue` beats `pueued`, `gix` beats `ein` for gitoxide only by
    fallback); otherwise the first declared.
    """
    if not bins:
        return None
    if crate in bins:
        return crate
    # Otherwise prefer the longest shared prefix with the crate name, and break
    # ties on declaration order rather than length — declaration order is what
    # the crate author considers primary (cargo-edit declares cargo-add first),
    # whereas "shortest" is arbitrary and picked cargo-rm.
    def score(b):
        n = 0
        for x, y in zip(b, crate):
            if x != y:
                break
            n += 1
        return (-n, bins.index(b))
    return sorted(bins, key=score)[0]


def main(path):
    lines = open(path).read().splitlines()
    out, changed, multi, problems = [], 0, [], []
    for line in lines:
        body = line.split("#")[0].strip()
        if not body:
            out.append(line)
            continue
        crate = body.split(":")[0]
        had_explicit = ":" in body
        cf, ver, err = crate_file(crate)
        if err or not cf:
            problems.append(f"{crate}: {err}")
            out.append(line)          # leave untouched; harness will error cleanly
            continue
        bins = bins_of(cf, crate, ver)
        if not bins:
            problems.append(f"{crate}: no binary target")
            out.append(line)
            continue
        pick = primary(bins, crate)
        if len(bins) > 1:
            multi.append(f"{crate} -> {bins} (picked {pick})")
        new = f"{crate}:{pick}"
        if new != body:
            changed += 1
        out.append(new)
        if not had_explicit:
            time.sleep(0.25)
    print("\n".join(out))
    sys.stderr.write(
        f"[resolve] entries pinned; {changed} rewritten; "
        f"{len(multi)} multi-binary crates\n")
    for m in multi:
        sys.stderr.write(f"  MULTI  {m}\n")
    for p in problems:
        sys.stderr.write(f"  PROBLEM {p}\n")


if __name__ == "__main__":
    main(sys.argv[1])

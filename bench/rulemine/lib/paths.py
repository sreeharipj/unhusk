"""
paths.py — path-string taxonomies.

Two taxonomies are defined here and both are carried into the dataset:

`unhusk_class`  — a faithful replication of `src/origin.rs::classify_location_path`,
                  so that the incumbent rules (RULE_A/B/C) can be scored on
                  exactly the inputs they were designed for. Any divergence
                  from the Rust original is a bug in this file; `exp/e00_replicate.py`
                  checks it against 2.95M real `origin_probe` rows and fails loudly.

`p_class`       — this study's own taxonomy, derived from a census of the actual
                  path strings in the corpus rather than inherited. It differs
                  from unhusk's in exactly one deliberate place, recorded here so
                  the difference is testable rather than accidental:
                  `/rust/deps/<crate>-<ver>/...` (the vendored dependencies of the
                  *standard library's own build*: addr2line, gimli, object,
                  miniz_oxide, hashbrown) is `STDDEP` here and `Registry` under
                  unhusk. Those paths are not the user's dependencies in any
                  sense an analyst cares about — they arrive with libstd — so
                  bucketing them with crates.io packages conflates two different
                  things. Whether that matters is measured, not assumed.
"""
import re

# Verbatim from src/origin.rs::STD_LIB_DIRS. These are the PRE-2019 rustc source
# layout names (`src/libcore/`, not `library/core/`), and the trailing slash and
# `lib` prefix are load-bearing: the naive modern-looking version of this list
# ("core", "std", "alloc", ...) matches `/src/core/` inside any dependency that
# happens to have a module called `core` — e.g.
# `.cargo/registry/src/.../minus-5.7.1/src/core/init.rs` — and silently relabels
# a crates.io dependency as the standard library. That mistake was made while
# writing this file and caught by E00's per-function cross-check against
# origin_probe; it is recorded here so nobody reintroduces it.
STD_LIB_DIRS = ("libcore/", "liballoc/", "libstd/", "libpanic_abort/",
                "libpanic_unwind/", "libunwind/", "libbacktrace/", "libtest/",
                "libproc_macro/", "libcompiler_builtins/")

def _build_script_crate(path: str):
    """Replication of src/dwarf.rs::build_script_crate — the `/build/<name>-<16hex>/`
    directory shape, requiring the metadata suffix so an ordinary `src/build/`
    directory is not swallowed."""
    norm = path.replace("\\", "/")
    idx = norm.find("/build/")
    if idx < 0:
        return None
    seg = norm[idx + len("/build/"):].split("/")[0]
    name, sep, meta = seg.rpartition("-")
    if not sep or not name:
        return None
    if len(meta) == 16 and all(c in "0123456789abcdefABCDEF" for c in meta):
        return name
    return None


def unhusk_class(path: str) -> str:
    """Replication of src/origin.rs::classify_location_path (7 classes)."""
    if "\\" in path:
        path = path.replace("\\", "/")
    if path.startswith("/rustc/") or path.startswith("library/"):
        return "rustc"
    if "/lib/rustlib/src/rust/library/" in path:
        return "rustc"
    for lib in STD_LIB_DIRS:
        if path.startswith(f"src/{lib}") or f"/src/{lib}" in path:
            return "rustc"
    if _build_script_crate(path) is not None:
        return "generated"
    if "cargo/git/checkouts/" in path:
        return "git"
    if ("cargo/registry/src/" in path or "crates.io/" in path
            or path.startswith("/rust/deps/")):
        return "registry"
    if not path.endswith(".rs"):
        return "unknown"
    if path.startswith("/"):
        return "workspace"
    return "user"


def p_class(path: str) -> str:
    """This study's taxonomy, from a census of the corpus's actual path shapes.

    REL      relative .rs path                       — the tool cannot see whose
    REGISTRY /home/*/.cargo/registry/src/*           — a crates.io dependency
    GIT      /home/*/.cargo/git/checkouts/*          — a git dependency
    RUSTC    /rustc/<hash>/library/*, sysroot forms  — the standard library
    STDDEP   /rust/deps/<crate>-<ver>/*              — libstd's own vendored deps
    OUTDIR   */target/*/build/<pkg>-<hash>/out/*     — build-script generated
    ABS      any other absolute .rs path             — path dependency / workspace
    NONRS    does not end in .rs                     — not Rust source at all
    """
    if "\\" in path:
        path = path.replace("\\", "/")
    # Dependency anchors first. `cargo/registry/src/` and `cargo/git/checkouts/`
    # are structural facts about where cargo puts things, not heuristics, so
    # nothing downstream should be able to override them -- in particular no
    # std-directory-name heuristic, which is what makes a dependency module
    # called `core` or `alloc` dangerous. unhusk's own classifier orders these
    # the other way round; it is safe there only because its std-directory list
    # uses the legacy `libcore/` spelling.
    if "cargo/git/checkouts/" in path:
        return "GIT"
    if "cargo/registry/src/" in path or "crates.io/" in path:
        return "REGISTRY"
    if _build_script_crate(path) is not None:
        return "OUTDIR"
    if path.startswith("/rust/deps/"):
        return "STDDEP"
    if path.startswith("/rustc/") or path.startswith("library/") \
            or "/lib/rustlib/src/rust/library/" in path:
        return "RUSTC"
    for lib in STD_LIB_DIRS:
        if path.startswith(f"src/{lib}") or f"/src/{lib}" in path:
            return "RUSTC"
    if not path.endswith(".rs"):
        return "NONRS"
    if path.startswith("/"):
        return "ABS"
    return "REL"


UNHUSK_CLASSES = ["user", "workspace", "registry", "git", "rustc", "generated", "unknown"]
P_CLASSES = ["REL", "REGISTRY", "GIT", "RUSTC", "STDDEP", "OUTDIR", "ABS", "NONRS"]

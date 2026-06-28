# unhusk

**Recovering author-written code from stripped Rust binaries via panic metadata** — no symbols, no debug info, no signature database.

> ⚗️ **Experimental security-research project.** A single-author research vehicle, not a product.
> Validated on 34 open-source Rust binaries; **not yet tested on live malware**. x86-64 ELF only.
> Numbers and interfaces move as evidence accumulates. Expect sharp edges.

A stripped, LTO-optimized Rust release binary is a wall of anonymous machine code in which 90%+ of the functions belong to the standard library and Cargo dependencies. unhusk finds the slice the *author* actually wrote, by exploiting a structural quirk of the Rust panic machinery.

**The trick.** Rust bakes a `core::panic::Location` (source file + line + column) into the binary for every reachable `panic!` / `.unwrap()` / bounds-check, so a crash can print `panicked at src/main.rs:42`. These survive `strip` because they are *data*, not symbols. unhusk reconstructs them, classifies each path (`src/…` → author, `…/cargo/registry/…` → dependency, `/rustc/…/library/…` → std), ties them back to function bodies via `.eh_frame`, and ranks confidence by how many distinct author panic-sites each function carries.

**Why it might matter.** The primitive — *"which bytes in this stripped Rust binary are the author's?"* — feeds malware fingerprinting (YARA-seed extraction), reverse-engineering triage (label the ~3% of functions worth reading), and binary SBOM / dependency provenance. The headline target is a Rust-malware → YARA-X rule generator (a separate project); unhusk is the standalone, independently-testable backend behind a JSON contract.

## Status & scope

- **Experimental research.** Built to find out *whether* this works and *how well*, not to ship.
- **x86-64 ELF only** (PIE and non-PIE). No PE / Mach-O / aarch64.
- **Validated on benign open-source tools, not live malware** — the single largest validity gap.
- Pure Rust, no C dependencies, no network, no runtime tools.

## How it works

**Phase 1 — panic-site source attribution** (robust; needs no unwind info). Rust embeds a `Location` struct in `.data.rel.ro` for every reachable panic site; the file-pointer field is filled by a `R_X86_64_RELATIVE` relocation pointing at the source-path string in `.rodata`:

```
.rela.dyn   R_X86_64_RELATIVE { offset, addend }
   │  offset → slot in .data.rel.ro  (the file-ptr field of a Location)
   └  addend → string in .rodata      ("src/main.rs", "/rustc/…/library/…", …)

.data.rel.ro  [ ptr(reloc) | len(u64) | line(u32) | col(u32) ]
```

Path classification is deterministic — no heuristics:

| Pattern | Origin |
|---|---|
| `src/*.rs`, `tests/*.rs`, `examples/*.rs` | **User** |
| `/rustc/HASH/library/…`, `library/…` | std/core/alloc |
| `*/cargo/registry/src/*/CRATE-VER/…`, `/rust/deps/…` | dependency crate |

(For `cargo install` binaries, paths live under `~/.cargo/registry/`; pass `--crate <name>` or rely on auto-detection to promote the root crate Dep → User.)

**Phase 2 — function attribution.** `.eh_frame` FDEs give exact `[start, end)` function ranges. An x86-64 xref scan (iced-x86) finds every function that directly references a **user** `Location` → `certain`. The `certain` set is then split into confidence tiers by **user-Location multiplicity** (below). A forward call-graph BFS (`inferred`) and reverse BFS (`certain_by_backtrace`) exist but are *not* user-authored output — they measure reachability, which is the wrong signal for precision, so they are demoted to diagnostics.

## The core finding: multiplicity is the one robust precision lever

A monomorphized library generic (e.g. `core::iter::FilterMap<…, user::closure>`) inlines **exactly one** user closure → one user Location. A genuine user function carries **several** of its own panic sites. So requiring ≥ N distinct user Locations cleanly rejects the single-closure monomorphizations that are the dominant false positive — and it does so **identically at every optimization level**, because it keys on Location structure, not on inlining.

Symbol-ground-truth precision on a **34-binary** corpus (13 source-built + 8 `cargo install` + 13 deliberately-adversarial), with the key caveat that **precision is workload-dependent**:

| Tier | Rule | CLI/systems | async/web-framework | broad pooled |
|---|---|---:|---:|---:|
| **STRONG** | ≥ N distinct user Locations (`--min-anchors`, default 2) | ~98% | ~87% | **~94%** |
| **SINGLE** | exactly 1 user Location | ~90% | ~75% | ~80% |

`--min-anchors` is the precision dial — pooled **1 → ~86% (full recall) · 2 → ~94% · 3 → ~96%** (recall falls as it rises). `--precision` emits the STRONG tier only.

**The weak spot is async / web-framework code:** futures combinators (`Pin<Box<closure>>`, `PollFn`, `tokio::Timeout`) and framework handler-adapters inline a *multi-panic* user closure → a library function with ≥2 user Locations → an irreducible false positive (no in-stripped-binary signal separates it from a real user function). This is **malware-relevant** — malware skews async (C2, scanners, network) — so expect the ~87% end there and use `--min-anchors 3` (async → ~91%) when false seeds are costly.

## On rigor — how honestly these numbers were earned

This is the part worth reading. The validation methodology is deliberately adversarial toward its own conclusions:

- **Two ground-truth rulers, on purpose.** Each prediction is scored against both DWARF `decl_file` and `nm -C` symbol leading-crate. They disagree by ~30pp — because DWARF homes user `FnOnce`/`FnMut` closure shims to `core/src/ops/function.rs`, a *measurement artifact*, not a real error. Symbol is the correct ruler for authorship; using only DWARF would have understated precision and hidden the real failure mode.
- **A pre-registered stress test.** The corpus that produced the headline was *designed to break the claim* (async / parallel / framework / macro categories), with hypotheses and kill criteria fixed in writing before any data. See `realval/CORPUS_STRESS.md`.
- **The method caught its own mistakes — and they're documented, not buried.** A "source-file coherence" tier was shipped, then **retracted** when a cleaner measurement showed it was a harness artifact (the eval had been re-parsing human output and mixing in call-closure functions). A headline ~97% precision was **corrected to ~94%** when the stress corpus added async-heavy binaries the earlier corpus lacked. Two `cargo install`-specific classifier confounds (std forwarding wrappers, an author's own library crate pulled from the registry as a "dep") were identified and controlled for. Full derivations and retractions: `realval/PRECISION_TIERS.md`, `realval/CORPUS_STRESS.md`.

Rejected refinements (do not re-add without new evidence): `#[derive(Debug)]` cross-confirmation (disjoint from `certain`; type layouts aren't ABI-stable) and call-graph adjacency rescue (anti-correlated — "called by a STRONG function" *is* the monomorphized-helper pattern).

## Robustness against section stripping

The adversary picks the compiler flags, so this was tested:

- **Phase 1 is unconditionally robust** — it needs only `.rela.dyn` + `.rodata` + `.data.rel.ro`. It survives `-C force-unwind-tables=no`, `panic=abort`, and even physical removal of `.eh_frame`.
- **`.eh_frame` removed but `.eh_frame_hdr` intact** (the realistic `objcopy --remove-section .eh_frame`): unhusk parses the hdr's function-address table → **results identical to an intact binary**.
- **Both removed:** falls back to a CALL-target-derived function map (degraded; still recovers ~93% of STRONG functions).

So an adversary must strip *both* sections to degrade Phase 2 at all. Optimization-invariance verified across thin-LTO, `lto=true,cgu=1`, `opt-level=z`, `panic=abort`, `-C force-unwind-tables=no`.

## Usage

```sh
# Identify user-authored functions in a stripped binary
unhusk <stripped-elf>

# PRECISION MODE — emit only the STRONG tier (best signature seeds)
unhusk <stripped-elf> --precision

# Precision dial — STRONG requires N distinct user Locations
#   pooled  1 → ~86% (full recall) · 2 → ~94% · 3 → ~96%   (CLI ~98%, async ~87%)
unhusk <stripped-elf> --min-anchors 3

# JSON feed for downstream tooling (suppresses the human report)
#   emits {start, end, size, tier, anchor_count, anchor_files} per function
unhusk <stripped-elf> --precision --json

# Validate precision/recall against DWARF ground truth from an unstripped twin
unhusk <stripped-elf> --validate <unstripped-elf>

# Specify the root crate (cargo-install binaries; auto-detected otherwise)
unhusk <stripped-elf> --crate ripgrep

# Recover struct/field names from #[derive(Debug)] artifacts (diagnostic)
unhusk <stripped-elf> --types
```

## Limitations

- **Functions with no reachable panic site are not found.** Pure computation, getters, and code where the optimizer proved every panic unreachable have nothing to anchor on. Recall is partial by construction (~15–46% of user functions on the test set) — fine for signature generation, which needs a handful of good seeds, not every function.
- **async / generic-heavy code degrades precision** (the ~87% weak spot above) — irreducible in a stripped binary.
- **User code reached only through trait objects / function pointers / library dispatch** appears as `library`; the xref scan follows only static call edges.
- **Never validated on live malware.** Every number here is from benign open-source tools, which may not be representative.
- **x86-64 ELF only.**

## Build & test

```sh
cargo build --release      # Rust 1.70+, no C deps
cargo test                 # unit tests run without fixtures;
                           # integration tests need fixtures under /tmp/unhusk-research/
```

Docker:

```sh
docker build -t unhusk .
docker run --rm -v "$(pwd)":/work -w /work unhusk <stripped-elf>
```

## License

Dual-licensed: **AGPL-3.0** for open-source/general use, or a **commercial license** for proprietary use. See `LICENSE`.

# unhusk

Finds author-written functions in stripped Rust binaries using panic metadata. No symbols, debug info, or signature databases.

> Experimental research project, single author. Validated on 34 open-source Rust binaries and a first batch of real in-the-wild Rust malware (static analysis only, see below). x86-64 ELF only. Numbers and interfaces change as evidence accumulates.

In a stripped, LTO-optimized Rust release binary, most functions come from the standard library and Cargo dependencies. The author's own code is a small fraction, and nothing labels it. unhusk identifies that fraction by reading the panic metadata Rust embeds.

Rust stores a `core::panic::Location` (source file, line, column) for every reachable `panic!`, `.unwrap()`, and bounds-check, so a crash can print `panicked at src/main.rs:42`. These strings survive `strip` because they are data, not symbols. unhusk reconstructs them, classifies each path (`src/…` is the author, `…/cargo/registry/…` is a dependency, `/rustc/…/library/…` is std), maps them back to functions via `.eh_frame`, and ranks each function by how many distinct author panic sites it references.

The primitive question, "which bytes in this stripped Rust binary are the author's," is useful for malware fingerprinting (YARA-seed extraction), reverse-engineering triage (labelling the few functions worth reading), and dependency/SBOM recovery. The motivating use case is a Rust-malware to YARA-X rule generator, which is a separate project; unhusk is the backend behind a JSON contract.

## Status and scope

- Research code, written to find out whether this works and how well, not to ship.
- x86-64 ELF only (PIE and non-PIE). No PE, Mach-O, or aarch64.
- Most validation is on benign open-source tools; live-malware testing has only just started.
- Pure Rust, no C dependencies, no network, no runtime tools.

## How it works

Phase 1, source attribution. Rust stores a `Location` struct in `.data.rel.ro` for every reachable panic site. Its file-pointer field is filled by an `R_X86_64_RELATIVE` relocation that points at the source-path string in `.rodata`:

```
.rela.dyn   R_X86_64_RELATIVE { offset, addend }
   offset -> slot in .data.rel.ro  (the file-ptr field of a Location)
   addend -> string in .rodata      ("src/main.rs", "/rustc/.../library/...", ...)

.data.rel.ro  [ ptr(reloc) | len(u64) | line(u32) | col(u32) ]
```

Path classification is deterministic:

| Pattern | Origin |
|---|---|
| `src/*.rs`, `tests/*.rs`, `examples/*.rs` | User |
| `/rustc/HASH/library/…`, `library/…` | std/core/alloc |
| `*/cargo/registry/src/*/CRATE-VER/…`, `/rust/deps/…` | dependency crate |

(For `cargo install` binaries the paths live under `~/.cargo/registry/`; pass `--crate <name>` or rely on auto-detection to promote the root crate from Dep to User.)

Phase 2, function attribution. `.eh_frame` FDEs give exact `[start, end)` function ranges. An x86-64 xref scan (iced-x86) finds every function that references a user `Location` and marks it `certain`. The `certain` set is then split into confidence tiers by user-Location multiplicity (below). A forward call-graph BFS (`inferred`) and a reverse BFS (`certain_by_backtrace`) exist but are not treated as user code; they measure reachability, which is the wrong signal for precision, so they are kept only as diagnostics.

## Multiplicity is the precision lever

A monomorphized library generic (say `core::iter::FilterMap<…, user::closure>`) inlines exactly one user closure, so it references one user Location. A real user function references several of its own panic sites. Requiring at least N distinct user Locations rejects the single-closure monomorphizations that cause most false positives, and it behaves the same at every optimization level because it keys on Location structure rather than inlining.

Symbol-ground-truth precision on a 34-binary corpus (13 source-built, 8 `cargo install`, 13 chosen to be adversarial). Precision depends on the kind of binary:

| Tier | Rule | CLI/systems | async/web | pooled |
|---|---|---:|---:|---:|
| STRONG | >= N distinct user Locations (`--min-anchors`, default 2) | ~98% | ~87% | ~94% |
| SINGLE | exactly 1 user Location | ~90% | ~75% | ~80% |

`--min-anchors` is the precision dial: pooled 1 -> ~86% (full recall), 2 -> ~94%, 3 -> ~96%, with recall dropping as it rises. `--precision` emits the STRONG tier only.

The weak spot is async and web-framework code. Futures combinators (`Pin<Box<closure>>`, `PollFn`, `tokio::Timeout`) and framework handler-adapters inline a user closure that itself has several panic sites, producing a library function with >= 2 user Locations and no way to tell it apart from a real user function. This matters for malware, which skews async (C2, scanners, network), so expect the ~87% end there. `--min-anchors 3` raises async precision to ~91% at the cost of recall.

## How the numbers were measured

The validation tries to disprove its own conclusions:

- Two ground-truth rulers. Each prediction is scored against both DWARF `decl_file` and `nm -C` symbol leading-crate. They disagree by about 30 points, because DWARF attributes user `FnOnce`/`FnMut` closure shims to `core/src/ops/function.rs`. That is a measurement artifact, not a real error. Symbol is the correct ruler for authorship; scoring only against DWARF would have understated precision and hidden the actual failure mode.
- A pre-registered stress test. The corpus that produced the headline numbers was built to break the claim (async, parallel, framework, macro categories), with hypotheses and pass/fail criteria written down before any data. See `realval/CORPUS_STRESS.md`.
- The method has corrected itself. A "source-file coherence" tier was shipped and then removed once a cleaner measurement showed it was a harness artifact (the eval had been re-parsing human output and mixing in call-closure functions). A headline of ~97% precision was corrected to ~94% after the stress corpus added async-heavy binaries the earlier corpus lacked. Two `cargo install`-specific classifier confounds (std forwarding wrappers, and an author's own library crate pulled from the registry as a dependency) were found and controlled for. Derivations are in `realval/PRECISION_TIERS.md` and `realval/CORPUS_STRESS.md`.

Two refinements were tried and dropped: `#[derive(Debug)]` cross-confirmation (disjoint from `certain`, and type layouts are not ABI-stable) and call-graph adjacency rescue (anti-correlated, since "called by a STRONG function" is itself the monomorphized-helper pattern).

## Real Rust malware

unhusk has been run against in-the-wild Rust malware (KrustyLoader, Akira, BlackCat/ALPHV, 01flip, P2PInfect; samples from [decoderloop/rust-malware-gallery](https://github.com/decoderloop/rust-malware-gallery), static analysis only, never executed). On current samples it reads the author's source files, the module structure (Akira's `lock.rs`, `path_finder.rs`, `prng.rs`), and a dependency-derived capability profile (KrustyLoader is an async HTTP downloader with AES) off a stripped binary. Real Rust malware tends to be async-heavy, so the ~87% weak spot is the common case. Two evasions showed up, `--remap-path-prefix` (01flip) and packing (P2PInfect); both are now flagged instead of returning empty. Writeup, hashes, and the evasion-effort analysis: [`writeups/2026-06-29-unhusk-vs-real-rust-malware.md`](writeups/2026-06-29-unhusk-vs-real-rust-malware.md).

## Robustness against stripping and evasion

- Phase 1 needs only `.rela.dyn`, `.rodata`, and `.data.rel.ro`. It survives `-C force-unwind-tables=no`, `panic=abort`, and physical removal of `.eh_frame`.
- If `.eh_frame` is removed but `.eh_frame_hdr` survives (what `objcopy --remove-section .eh_frame` actually does), unhusk reads the function-address table out of the header and gets the same result as an intact binary. If both are removed it falls back to a CALL-target map (degraded; still about 93% of STRONG).
- If the section header table is stripped (`sstrip`), the regions are recovered from the program headers (PT_LOAD, PT_GNU_RELRO, PT_DYNAMIC), so both phases still run.
- Degraded or evaded inputs print warnings rather than returning empty: no user paths (likely `--remap-path-prefix`), no `.text` (packed), no `.rela.dyn` (static). Downstream tooling can branch on these.

Optimization-invariance was checked across thin-LTO, `lto=true,codegen-units=1`, `opt-level=z`, `panic=abort`, and `-C force-unwind-tables=no`.

## Usage

```sh
# Identify user-authored functions in a stripped binary
unhusk <stripped-elf>

# Emit only the STRONG tier (best signature seeds)
unhusk <stripped-elf> --precision

# Precision dial: STRONG requires N distinct user Locations
#   pooled  1 -> ~86% (full recall),  2 -> ~94%,  3 -> ~96%   (CLI ~98%, async ~87%)
unhusk <stripped-elf> --min-anchors 3

# JSON for downstream tooling (suppresses the human report)
#   emits {start, end, size, tier, anchor_count, anchor_files} per function
unhusk <stripped-elf> --precision --json

# Score against DWARF ground truth from an unstripped twin
unhusk <stripped-elf> --validate <unstripped-elf>

# Set the root crate (cargo-install binaries; auto-detected otherwise)
unhusk <stripped-elf> --crate ripgrep

# Recover struct/field names from #[derive(Debug)] artifacts (diagnostic)
unhusk <stripped-elf> --types
```

## Limitations

- Functions with no reachable panic site are not found. Pure computation, getters, and code where the optimizer proved every panic unreachable have nothing to anchor on. Recall is partial by design (about 15-46% of user functions on the test set), which is fine for signature generation since that needs a few good seeds, not every function.
- async and generic-heavy code lowers precision (the ~87% weak spot), and this is irreducible in a stripped binary.
- User code reached only through trait objects, function pointers, or library dispatch shows up as `library`; the xref scan follows static call edges only.
- Defeated by packing, `--remap-path-prefix`, and `-Z build-std panic_immediate_abort`. Real malware uses the first two (both flagged); the last removes the panic metadata entirely but is nightly-only and changes runtime behavior. The malware writeup covers the full evasion-effort gradient.
- The precision numbers come from benign tools plus a handful of malware samples. That is a start, not a representative study. Windows PE Rust malware is not supported.
- x86-64 ELF only.

## Build and test

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

Dual-licensed: AGPL-3.0 for open-source and general use, or a commercial license for proprietary use. See `LICENSE`.

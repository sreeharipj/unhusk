# unhusk

Finds author-written functions in stripped Rust binaries using panic metadata. No symbols, debug info, or signature databases.

In a stripped, LTO-optimized Rust release binary, most functions come from the standard library and Cargo dependencies. The author's own code is a small fraction, and nothing labels it. unhusk identifies that fraction by reading the panic metadata Rust embeds.

Rust stores a `core::panic::Location` (source file, line, column) for every reachable `panic!`, `.unwrap()`, and bounds-check, so a crash can print `panicked at src/main.rs:42`. These strings survive `strip` because they are data, not symbols. unhusk reconstructs them, classifies each path (`src/…` is the author, `…/cargo/registry/…` is a dependency, `/rustc/…/library/…` is std), maps them back to functions via `.eh_frame`, and ranks each function by how many distinct author panic sites it references.

The primitive question, "which bytes in this stripped Rust binary are the author's," is useful for malware fingerprinting (YARA-seed extraction), reverse-engineering triage (labelling the few functions worth reading), and dependency/SBOM recovery. The motivating use case is a Rust-malware to YARA-X rule generator, which is a separate project; unhusk is the backend behind a JSON contract.

## Install

```sh
cargo build --release      # Rust 1.70+, no C deps
```

Docker:

```sh
docker build -t unhusk .
docker run --rm -v "$(pwd)":/work -w /work unhusk <stripped-elf>
```

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

## Example output

Run with `--precision --json` against a real, stripped Akira ransomware sample —
one entry from the `functions` array:

```json
{
  "start": "0xd25af",
  "end": "0xd38a5",
  "size": 4854,
  "tier": "strong",
  "anchor_count": 6,
  "anchor_files": [
    "akiranew/src/path_finder.rs"
  ]
}
```

Six distinct author panic sites in one function, from `akiranew`'s own source tree — a STRONG-tier seed, no symbols or debug info required. This is one of the functions [winnow](https://github.com/sreeharipj/winnow) later builds a Tier 1 YARA-X rule from; see its [example rule](https://github.com/sreeharipj/winnow/blob/main/examples/akira_v2_x_tier1.yar).

## Status and scope

- x86-64 ELF (PIE and non-PIE) — shipped, this is the CLI path.
- x86-64 PE (`x86_64-pc-windows-msvc`) — **experimental, library-only.** Parsing, `Location`/xref extraction, and the classifier all run and are tested (`container::pe::PeImage`), but there is no `--pe` flag or CLI dispatch yet, so using it today means writing code against the library directly. Not wired in because its core precision claim has the same open gap ELF has (below), not because the port itself is unfinished — see `architecture.md`'s verdict.
- No Mach-O or aarch64.
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

Pooled symbol-ground-truth precision on a 34-binary corpus (13 source-built, 8 `cargo install`, 13 chosen to be adversarial), measured by the `realval` harness: STRONG (>= 2 Locations, default) ~94%, SINGLE (1 Location) ~80%. Precision is workload-dependent — STRONG is ~98% on CLI/systems tools but ~87% on async/web-framework code, which matters because malware skews async (C2, scanners, network). `--min-anchors 3` raises async to ~91% at a recall cost. Full derivation, the pre-registered stress test, and two corrected measurement artifacts: [`docs/validation.md`](docs/validation.md) — that page also has the pointer to a second, independent, non-comparable measurement (`bench/origin/`) and why the two aren't combined.

## How the numbers were measured

The validation tries to disprove its own conclusions: two independent ground-truth rulers (DWARF and symbol) that disagree by ~30 points for a diagnosed reason, a pre-registered stress test with hypotheses written down before the data, and a headline correction (~97% to ~94%) once that stress test added async-heavy binaries the earlier corpus lacked. Two `cargo install`-specific classifier confounds were found and controlled for, and a "source-file coherence" tier was shipped and then retracted once a cleaner measurement showed it was a harness artifact. Full write-up: [`docs/validation.md`](docs/validation.md).

## Real Rust malware

unhusk has been run against in-the-wild Rust malware (KrustyLoader, Akira, BlackCat/ALPHV, 01flip, P2PInfect; samples from [decoderloop/rust-malware-gallery](https://github.com/decoderloop/rust-malware-gallery), static analysis only, never executed). On current samples it reads the author's source files, the module structure (Akira's `lock.rs`, `path_finder.rs`, `prng.rs`), and a dependency-derived capability profile (KrustyLoader is an async HTTP downloader with AES) off a stripped binary. Real Rust malware tends to be async-heavy, so the ~87% weak spot is the common case. Two evasions showed up, `--remap-path-prefix` (01flip) and packing (P2PInfect); both are now flagged instead of returning empty. Case study, hashes, and the evasion-effort analysis: [`docs/case-study-real-malware.md`](docs/case-study-real-malware.md).

## Robustness against stripping and evasion

- Phase 1 needs only `.rela.dyn`, `.rodata`, and `.data.rel.ro`. It survives `-C force-unwind-tables=no`, `panic=abort`, and physical removal of `.eh_frame`.
- If `.eh_frame` is removed but `.eh_frame_hdr` survives (what `objcopy --remove-section .eh_frame` actually does), unhusk reads the function-address table out of the header and gets the same result as an intact binary. If both are removed it falls back to a CALL-target map (degraded; still about 93% of STRONG).
- If the section header table is stripped (`sstrip`), the regions are recovered from the program headers (PT_LOAD, PT_GNU_RELRO, PT_DYNAMIC), so both phases still run.
- Degraded or evaded inputs print warnings rather than returning empty: no user paths (likely `--remap-path-prefix`), no `.text` (packed), no `.rela.dyn` (static). Downstream tooling can branch on these.

Optimization-invariance was checked across thin-LTO, `lto=true,codegen-units=1`, `opt-level=z`, `panic=abort`, and `-C force-unwind-tables=no`.

## Limitations

- Functions with no reachable panic site are not found. Pure computation, getters, and code where the optimizer proved every panic unreachable have nothing to anchor on. Recall is partial by design (about 15-46% of user functions on the test set), which is fine for signature generation since that needs a few good seeds, not every function.
- async and generic-heavy code lowers precision (the ~87% weak spot), and this is irreducible in a stripped binary.
- **A monomorphized library function can absorb a user closure's panic Location via inlining and get misattributed as the user's own code** (`slice::sort_by`, `rayon`, futures combinators, and similar generic-over-callback shapes). This is a `classify.rs`/`xref.rs` property, not a format limitation — it hits ELF (shipped) and PE (experimental library) identically, and ELF has carried it since before it had a name. No general mitigation exists yet. Measured in detail, with real (not just constructed) instances, in [`bench/origin/INLINE_LEAK_INCIDENCE.md`](bench/origin/INLINE_LEAK_INCIDENCE.md); the first real-corpus instance of it (`rage`, crypto category) is in [`docs/validation.md`](docs/validation.md).
- User code reached only through trait objects, function pointers, or library dispatch shows up as `library`; the xref scan follows static call edges only.
- Defeated by packing, `--remap-path-prefix`, and `-Z build-std panic_immediate_abort`. Real malware uses the first two (both flagged); the last removes the panic metadata entirely but is nightly-only and changes runtime behavior. The case study covers the full evasion-effort gradient.
- The precision numbers come from benign tools plus a handful of malware samples. That is a start, not a representative study.
- PE is experimental and library-only (see Status and scope above) — no Mach-O or aarch64 either.

## Prior work

The core insight, that Rust embeds `panic!` source-location metadata that survives `strip` and can be mined to recover authorship and dependencies, is not original to unhusk. SentinelLabs' Project 0xA11C ("Deoxidizing the Rust Hive", RECON 2024) demonstrated it as an IDAPython workflow: reconstruct the `Location`/slice structs, recover `src/*.rs` panic paths, and mine `registry/src/…` strings for crate dependencies. Cindy Xiao's ["Using panic metadata to recover source code information from Rust binaries"](https://cxiao.net/posts/2023-12-08-rust-reversing-panic-metadata/) is the write-up unhusk's Phase 1 is built on (archived in `references/`). unhusk automates the same idea for x86-64 ELF without IDA, and adds the part those do not, a precision-ranked authorship classifier (the multiplicity lever and confidence tiers) with a measured false-positive story and a JSON output contract for downstream tooling.

Microsoft's RIFT ("advanced pattern matching for Rust libraries") solves the same separation problem from the opposite direction: it recognizes *library* code by recompiling the exact dependencies and compiler and matching them with FLIRT signatures and Diaphora binary diffing, so the author's code is the unlabeled residue. unhusk is additive rather than subtractive: it marks the author directly from intrinsic panic metadata, needs only the binary (no recompilation, network, or signature corpus), and treats author bytes as a positive signal rather than a by-elimination remainder, which is the better fit for YARA-seed extraction. Full contrast in [`references/rift-vs-unhusk.md`](references/rift-vs-unhusk.md).

## License

Licensed under the Apache License, Version 2.0. See `LICENSE`.

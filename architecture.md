> AGENTS: read this first, and keep it true. This is the architecture and design document for
> unhusk: what it is, why it exists, and where it is going. Read it before changing code, and update
> it whenever a decision, finding, interface, or number changes. If the code and this document
> disagree, fix one of them.

# unhusk: architecture and design

## What unhusk is

unhusk recovers which functions in a stripped Rust release binary were written by the author, as
opposed to the standard library and dependencies, with no symbols, debug info, or signature
database. It does this by reading the panic metadata Rust embeds unconditionally.

## It is one component, not the product

unhusk answers a single reusable question, "which bytes in this stripped Rust binary are the
author's," and emits a machine-readable answer. The main downstream consumer is a Rust-malware to
YARA-X rule generator, which is a separate project and is not built here. The primitive is kept
standalone because other consumers want the same answer: RE tooling (labelling the few functions
worth reading in Ghidra/IDA), malware-family clustering (the author's `src/` module layout is itself
a fingerprint), and binary SBOM / dependency recovery. Keeping unhusk a separate, independently
testable component behind a JSON contract is deliberate; several of the harder bugs were caught only
because it can be validated on its own.

## Priorities, in order

1. Precision of user-function attribution. A false seed poisons a downstream signature.
2. Recall, second. A rule needs a few good seeds, not every function.
3. Robustness across compilation. The adversary picks the compiler flags, so unhusk must work at any
   LTO or optimization level and survive section stripping.

## How it works

### Phase 1: source attribution

Rust stores a `core::panic::Location` struct in `.data.rel.ro` for every reachable `panic!`,
`assert!`, bounds-check, and `.unwrap()`, holding the source file path, line, and column so a crash
can print `panicked at src/main.rs:42`. These survive stripping because they are data, reached
through `R_X86_64_RELATIVE` relocations into `.rodata` strings. unhusk reconstructs each Location and
classifies its path:

| Path pattern | Origin |
|---|---|
| `src/*.rs`, `tests/*.rs`, `examples/*.rs` | User |
| `/rustc/HASH/library/…`, `library/…` | std/core/alloc |
| `*/cargo/registry/src/*/CRATE-VER/…`, `/rust/deps/…` | dependency crate |

For `cargo install` binaries (paths under `~/.cargo/registry/`), pass `--crate <name>` or rely on
auto-detection to promote the root crate from Dep to User.

### Phase 2: function attribution

`.eh_frame` FDEs give exact `[start, end)` function ranges. An x86-64 xref scan (iced-x86) finds
every function that references a user Location and marks it `certain`. The `certain` set is split
into confidence tiers by user-Location multiplicity (below). A forward call-graph BFS (`inferred`)
and a reverse BFS (`certain_by_backtrace`) exist but are not user code; they measure reachability,
which is the wrong signal for precision, so they are kept only as diagnostics.

## Multiplicity is the precision lever

A monomorphized library generic (for example `core::iter::FilterMap<…, user::closure>`) inlines one
user closure and so references one user Location. A real user function references several of its own
panic sites.

| Tier | Rule | CLI/systems | async/web | pooled |
|---|---|---:|---:|---:|
| STRONG | >= N distinct user Locations (`--min-anchors`, default 2) | ~98% | ~87% | ~94% |
| SINGLE | exactly 1 user Location | ~90% | ~75% | ~80% |

`--min-anchors` is the precision dial: pooled 1 -> ~86% (full recall), 2 -> ~94%, 3 -> ~96%, with
recall falling as the threshold rises. The lever is optimization-invariant because it keys on
Location structure rather than inlining; this was checked across thin-LTO, `lto=true,cgu=1`,
`opt-level=z`, `panic=abort`, and `-C force-unwind-tables=no`.

Precision is workload-dependent, measured on a 34-binary, deliberately adversarial corpus
(`realval/CORPUS_STRESS.md`). CLI and systems tools sit around 98%; async and web-framework code
around 87% (the weak spot, below). Earlier 13- and 21-binary corpora read ~97% because they were
light on async. For malware, which is mostly async, expect the lower end and prefer `--min-anchors 3`.

### Tried and rejected (do not re-add without new evidence)

- Source-file coherence. Once shipped as a "CONFIRMED" middle tier; it turned out to be a harness
  artifact (the eval re-parsed human output and swept call-closure functions into the bucket).
  Coherent versus incoherent single-anchor functions are both about 93%, so coherence separates
  nothing. The lesson: measure tiers from the tool's own assignment (`UNHUSK_DUMP_TIERS`), never by
  re-parsing human reports.
- `#[derive(Debug)]` cross-confirmation. Nearly disjoint from `certain`, and type layouts are not
  ABI-stable.
- Call-graph adjacency rescue of SINGLE. Anti-correlated, since "called by a STRONG function" is
  itself the monomorphized-helper pattern.

### Known weak spot

async, parallel, and framework-heavy binaries. Futures combinators (`Pin<Box<closure>>`, `PollFn`,
`tokio::Timeout`), rayon generics, and framework handler-adapters inline a user closure that itself
has several panic points, producing a library function with >= 2 user Locations. In a stripped
binary there is no signal that separates these from real user functions.

## The right ruler: symbol, not DWARF

Validation uses two ground truths from an unstripped twin: DWARF `decl_file` and `nm -C` symbol
leading-crate. Symbol is the correct ruler for authorship. DWARF attributes user `FnOnce`/`FnMut`
closure shims to `core/src/ops/function.rs`, which is a measurement artifact worth about 30 points,
not a real error. Two classifier confounds make symbol ground truth undercount and must be
controlled for: std forwarding wrappers (`__rust_begin_short_backtrace::<user>`,
`LocalKey::with::<user>`) and an author's own workspace crates pulled from the registry.

## Robustness against stripping and evasion

- Phase 1 needs only `.rela.dyn`, `.rodata`, and `.data.rel.ro`. It survives
  `-C force-unwind-tables=no`, `panic=abort`, and physical removal of `.eh_frame`.
- If `.eh_frame` is removed but `.eh_frame_hdr` survives (what `objcopy --remove-section .eh_frame`
  actually does), unhusk reads the function-address table from the header and gets the same result
  as an intact binary. If both are removed, it falls back to a CALL-target map (degraded; about 93%
  of STRONG).
- If the section header table is stripped (`sstrip` / `objcopy --strip-section-headers`), `elf.rs`
  recovers `.text`, `.rodata`, `.data.rel.ro`, `.rela.dyn`, and `.eh_frame_hdr` from the program
  headers (PT_LOAD, PT_GNU_RELRO, PT_DYNAMIC). Boundaries are coarser but both phases still run.
- Degraded or evaded inputs print warnings instead of an empty result: no user paths (likely
  `--remap-path-prefix`), no `.text` (packed), no `.rela.dyn` (static). Downstream tooling should
  branch on these.

## Real-malware validation (2026-06-29)

First run against in-the-wild Rust malware (decoderloop/rust-malware-gallery, static only). Full
writeup in `writeups/2026-06-29-unhusk-vs-real-rust-malware.md`. Findings that shaped the code:

- Works on the current generation. KrustyLoader yields `linux/src/main.rs` plus an
  async-HTTP-downloader-with-AES dependency profile; Akira yields its module map (`lock.rs`,
  `path_finder.rs`, `prng.rs`) and 7 STRONG functions; BlackCat yields its ESXi-targeting modules.
  Real Rust malware is async-heavy, so the weak spot is the common case.
- Two classifier fixes, both from BlackCat (built on an old toolchain with vendored deps): recognize
  `crates.io/<crate>-<ver>/` deps and the pre-2018 `src/lib{core,alloc,std}/` std layout. Without
  them, `aes`, `alloc`, and `core` code counted as user and produced universal-false-positive seeds.
- Two evasions observed: `--remap-path-prefix` (01flip, scrubs source paths; one stable flag, the
  cheapest effective counter) and packing / section stripping (P2PInfect). The effort gradient: cheap
  evasions attack the path and section convenience layer; removing the structural multiplicity signal
  needs `-Z build-std panic_immediate_abort`, which is nightly-only, fragile, behavior-changing, and
  itself anomalous. unhusk's durable foundation is the structure, not the path strings.

## Module map

| Module | Layer | Role |
|---|---|---|
| `elf` | core | mmap and section index; everything holds a `&ParsedElf`. |
| `frame` | core | `.eh_frame` FDE to `FunctionMap`; `.eh_frame_hdr` and CALL-target fallbacks. |
| `strings` | pipeline | classify embedded `.rs` paths User/Std/Dep; auto-detect root crate. |
| `locate` | pipeline | reconstruct `Location` structs from `.data.rel.ro`, tag origin. |
| `xref` | pipeline | x86-64 scan: certain set, call graph, dep boundary, per-function Location hits. |
| `classify` | pipeline | attribution buckets and backward BFS. |
| `report` | output | tiering (`tier_certain` to STRONG/SINGLE), human and `--json` output. |
| `types` | optional | `#[derive(Debug)]` struct/field recovery (diagnostic, not a precision signal). |
| `dwarf` | optional | DWARF ground-truth validation (`--validate`). |

## Interfaces that matter

- `--json` is the machine contract for downstream tooling: `{start, end, size, tier, anchor_count,
  anchor_files}` per function. It honors `--precision` (STRONG only) and `--min-anchors`. This is the
  integration seam; keep it stable.
- Env-gated diagnostics: `UNHUSK_DUMP_TIERS` (authoritative tier source), `UNHUSK_DUMP_DEPS`
  (complete dep list for measurement), plus `UNHUSK_DUMP_ATTRS`, `UNHUSK_DUMP_EDGES`, and
  `UNHUSK_DUMP_ALL_FNS`.

## Validation and layout

- `realval/` holds the symbol-GT precision harnesses (`tier_eval.py`, `stress_analyze.py`), corpus
  builders, and the running record of findings and retractions (`PRECISION_TIERS.md`,
  `CORPUS_STRESS.md`).
- `bench/` holds performance benchmarking, not `realval/`.
- Scope: x86-64 ELF only (PIE and non-PIE).

## Open problems

- Recall is unsolved. Coherence, derive(Debug), and call-graph rescue all failed; the only lever is
  the `--min-anchors` threshold (drop to 1 for full `certain` recall at about 91%).
- async and parallel precision. No in-stripped-binary signal yet separates user-closure-bearing
  library generics from real user functions.

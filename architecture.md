> **AGENTS: READ THIS FIRST, AND KEEP IT TRUE.** This is the canonical vision-and-architecture
> document for unhusk — the single source of truth for *what this is, why it exists, and where it's
> going*. Read it before touching code. Edit it whenever a decision, finding, interface, or number
> changes — this document must not drift. If the code and this document disagree, fix one of them.

# unhusk — Architecture & Vision

## What unhusk is (one sentence)

unhusk recovers **which functions in a stripped Rust release binary were written by the author**
(versus the standard library and dependencies), with no symbols, no debug info, and no signature
database — by exploiting the panic metadata Rust embeds unconditionally.

## This is a modular part of something bigger

unhusk is **one component**, not the whole product. It answers a single, reusable question —
*"which bytes in this stripped Rust binary are the author's?"* — and emits a machine-readable answer.
The headline downstream consumer is a **one-shot Rust-malware → YARA-X rule generator** (a *separate*
project — do not build it here). But the primitive is deliberately standalone because other consumers
want the same answer: RE-tooling (label the ~3% worth reading in Ghidra/IDA), malware-family
clustering (the author's `src/` module layout is itself a fingerprint), and binary SBOM / dependency
provenance. Keeping unhusk a clean, independently-testable entity behind a JSON contract is a design
decision, not an accident — several of our hardest bugs were caught precisely because it can be
validated in isolation.

## Priorities (in order)

1. **Precision** of user-function attribution — a false seed poisons a downstream signature.
2. **Recall** — second. A rule needs a handful of good seeds, not every function.
3. **Robustness across compilation** — the adversary picks the compiler flags; unhusk must work at any
   LTO / optimization level and survive section-stripping.

## How it works

### Phase 1 — panic-site source attribution (robust; needs no unwind info)
Rust embeds a `core::panic::Location` struct in `.data.rel.ro` for every reachable `panic!`,
`assert!`, bounds-check, and `.unwrap()` — holding the **source file path + line + column** so a crash
can print `panicked at src/main.rs:42`. These survive stripping because they are *data*, reached via
`R_X86_64_RELATIVE` relocations into `.rodata` strings. unhusk reconstructs each Location and
classifies its path deterministically:

| Path pattern | Origin |
|---|---|
| `src/*.rs`, `tests/*.rs`, `examples/*.rs` | **User** |
| `/rustc/HASH/library/…`, `library/…` | std/core/alloc |
| `*/cargo/registry/src/*/CRATE-VER/…`, `/rust/deps/…` | dependency crate |

For `cargo install` binaries (paths under `~/.cargo/registry/`), pass `--crate <name>` or rely on
auto-detection to promote the root crate from Dep → User.

### Phase 2 — function attribution
`.eh_frame` FDEs give exact function `[start,end)` ranges. An x86-64 xref scan (iced-x86) finds every
function that directly references a **user** Location → `certain`. The `certain` set is then split into
confidence tiers by **user-Location multiplicity** (see below). A forward call-graph BFS (`inferred`)
and a reverse BFS (`certain_by_backtrace`) exist but are **not** user-authored output — they measure
*reachability*, which is the wrong signal for precision; they are demoted to diagnostics.

## The core finding: multiplicity is the one robust precision lever

A monomorphized library generic (e.g. `core::iter::FilterMap<…, user::closure>`) inlines **exactly
one** user closure → one user Location. A genuine user function carries **several** of its own panic
sites. So:

| Tier | Rule | CLI/systems | async/web | broad pooled |
|---|---|---|---|---|
| **STRONG** | ≥ N distinct user Locations (`--min-anchors`, default 2) | ~98% | ~87% | **~94%** |
| **SINGLE** | exactly 1 user Location | ~90% | ~75% | ~80% |

`--min-anchors` is the precision dial — pooled symbol precision roughly **1 → ~86% (full recall) ·
2 → ~94% · 3 → ~96%** (recall falls as the threshold rises). It is **optimization-invariant** (keys on
Location structure, not inlining) — verified across thin-LTO, `lto=true,cgu=1`, `opt-level=z`,
`panic=abort`, and `-C force-unwind-tables=no`.

> **Precision is workload-dependent** — validated on a 34-binary, deliberately-adversarial corpus
> (`realval/CORPUS_STRESS.md`). CLI/systems tools ~98%; async/web-framework ~87% (the weak spot,
> below). Earlier 13/21-binary corpora read ~97% because they were light on async. For malware
> (disproportionately async) expect the lower end and prefer `--min-anchors 3`.

### Things that were tried and REJECTED (do not re-add without new evidence)
- **Source-file coherence** — once shipped as a "CONFIRMED" middle tier; it was a *contaminated-harness
  artifact* (the eval re-parsed human output and swept call-closure functions into the bucket). Real
  coherent-vs-incoherent single-anchor: ~93% vs ~93% — no separation. **Lesson: measure tiers from the
  tool's own assignment (`UNHUSK_DUMP_TIERS`), never by re-parsing human reports.**
- **`#[derive(Debug)]` cross-confirmation** — nearly disjoint from `certain`; type layouts aren't
  ABI-stable.
- **Call-graph adjacency rescue** of SINGLE — anti-correlated (called-by-strong *is* the monomorphized
  helper pattern).

### Known weak spot
**async / parallel / framework-heavy binaries.** Futures combinators (`Pin<Box<closure>>`, `PollFn`,
`tokio::Timeout`), rayon generics, and framework handler-adapters inline a user closure that itself
spans multiple panic points → a *library* function with ≥2 user Locations → STRONG false positive.
This is the irreducible limit: in a stripped binary there is no signal separating these from genuine
user functions.

## The right ruler: symbol GT, not DWARF
Validation uses two ground truths from an unstripped twin: DWARF `decl_file` and `nm -C` symbol
leading-crate. **Symbol is correct for authorship**; DWARF homes user `FnOnce`/`FnMut` closure shims to
`core/src/ops/function.rs`, a ~30pp measurement artifact, not a real error. Beware classifier
confounds: std *forwarding wrappers* (`__rust_begin_short_backtrace::<user>`, `LocalKey::with::<user>`)
and an author's own workspace crates pulled from the registry both make symbol-GT *under*-count —
control for them before trusting any precision number.

## Robustness against stripping & evasion
- **Phase 1 is unconditionally robust** — only needs `.rela.dyn` + `.rodata` + `.data.rel.ro`.
- **`.eh_frame` removed but `.eh_frame_hdr` intact** (the realistic `objcopy --remove-section
  .eh_frame`): unhusk parses the hdr's function-address table → **results identical to an intact
  binary**. Both removed → CALL-target fallback (degraded; ~93% of STRONG).
- **Section headers stripped** (`sstrip` / `objcopy --strip-section-headers`): `elf.rs` recovers
  `.text`/`.rodata`/`.data.rel.ro`/`.rela.dyn`/`.eh_frame_hdr` from the **program headers**
  (PT_LOAD/PT_GNU_RELRO/PT_DYNAMIC). Boundaries are coarser but Phase 1+2 still run.
- **Diagnostics, not silence.** Degraded/evaded inputs emit loud `⚠` flags rather than an empty
  result: no user paths (likely `--remap-path-prefix`), no `.text` (packed), no `.rela.dyn` (static).
  Downstream tooling MUST branch on these.

## Real-malware validation (2026-06-29)
First run against in-the-wild Rust malware (decoderloop/rust-malware-gallery; static only). Full
writeup: `writeups/2026-06-29-unhusk-vs-real-rust-malware.md`. Findings that shaped the code:
- **Works on the current generation.** KrustyLoader → `linux/src/main.rs` + an async-HTTP-downloader-
  with-AES dep profile; Akira → its module map (`lock.rs`, `path_finder.rs`, `prng.rs`), 7 STRONG;
  BlackCat → ESXi-targeting modules. Real Rust malware is **async-heavy** — the known weak spot is the
  common case.
- **Two classifier fixes** (both from BlackCat, built on an old toolchain with vendored deps):
  recognize `crates.io/<crate>-<ver>/` deps and the pre-2018 `src/lib{core,alloc,std}/` std layout —
  without them, `aes`/`alloc`/`core` code counted as user (universal-false-positive seeds).
- **Two evasions observed:** `--remap-path-prefix` (01flip — scrubs source paths; one stable flag,
  the highest-ROI counter) and packing/section-stripping (P2PInfect). The **effort gradient**: cheap
  evasions attack the path/section *convenience layer*; killing the *structural* multiplicity signal
  needs `-Z build-std panic_immediate_abort` (nightly, fragile, behavior-changing, itself anomalous).
  → unhusk's durable foundation is the structure, not the path strings.

## Module map

| Module | Layer | Role |
|---|---|---|
| `elf` | core | mmap + section index; everything holds a `&ParsedElf`. |
| `frame` | core | `.eh_frame` FDE → `FunctionMap`; `.eh_frame_hdr` + CALL-target fallbacks. |
| `strings` | pipeline | classify embedded `.rs` paths User/Std/Dep; auto-detect root crate. |
| `locate` | pipeline | reconstruct `Location` structs from `.data.rel.ro`, tag origin. |
| `xref` | pipeline | x86-64 scan: certain set, call graph, dep-boundary, per-fn Location hits. |
| `classify` | pipeline | attribution buckets + backward BFS. |
| `report` | output | tiering (`tier_certain` → STRONG/SINGLE), human + `--json` feeds. |
| `types` | optional | `#[derive(Debug)]` struct/field recovery (diagnostic; not a precision signal). |
| `dwarf` | optional | DWARF ground-truth validation (`--validate`). |

## Interfaces that matter
- **`--json`** — the machine contract for downstream tooling:
  `{start, end, size, tier, anchor_count, anchor_files}` per function. Honors `--precision` (STRONG
  only) and `--min-anchors`. This is the integration seam; keep it stable.
- **Diagnostics (env-gated):** `UNHUSK_DUMP_TIERS` (authoritative tier source), `UNHUSK_DUMP_DEPS`
  (complete dep list for measurement), plus `UNHUSK_DUMP_ATTRS / EDGES / ALL_FNS`.

## Validation & layout
- `realval/` — symbol-GT precision harnesses (`tier_eval.py`, `stress_analyze.py`), corpus builders,
  and the running record of findings/retractions (`PRECISION_TIERS.md`, `CORPUS_STRESS.md`).
- `bench/` — performance benchmarking lives here, not in `realval/`.
- Scope: **x86-64 ELF only** (PIE and non-PIE).

## Open problems
- **Recall** is unsolved — coherence, derive(Debug), and call-graph rescue all failed; the only lever
  is the `--min-anchors` threshold (drop to 1 for full `certain` recall at ~91%).
- **async / parallel precision** — no in-stripped-binary signal yet separates user-closure-bearing
  library generics from genuine user functions.

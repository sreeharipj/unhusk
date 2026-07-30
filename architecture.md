# unhusk — architecture

*An honest, current account of what unhusk is, what actually works, what's dead
weight, and whether the PE port is ready to wire into anything. Rewritten
2026-07-27 after auditing every module against its test coverage, its git
history, and fresh measurements run this session (not just re-reading old
docs).*

## What this is

unhusk answers one question about a **stripped Rust release binary**, with no
symbols and no debug info: *which functions did the author write*, as opposed
to the standard library or a Cargo dependency? It answers that question by
reading `core::panic::Location` structs — the file/line/column metadata Rust
embeds at every `panic!`/`.unwrap()`/bounds-check site so a crash can print
`panicked at src/main.rs:42`. That metadata is data, not a symbol, so it
survives `strip`.

unhusk is a **library first, CLI second** — a backend behind a stable JSON
contract, not a finished product. The motivating downstream consumer is
[winnow](https://github.com/sreeharipj/winnow), a Rust-malware → YARA-X rule
generator. **Correction from the last write-up: winnow does not currently
depend on the `unhusk` crate.** Its `Cargo.toml` has no `unhusk` dependency and
its own `object` crate is built without the `pe` feature — it reimplements an
ELF-only pipeline in parallel (`elfview.rs`, `ingest.rs`) rather than importing
this one. "The backend behind winnow" is the design intent, not yet the wiring.
Keep that in mind: the interesting API surface for a downstream project is the
attribution output, not the CLI UX — but as of this writing, nothing outside
this repo actually consumes it as a library.

## The pipeline

Two phases, run in that order, both format-independent in design (see
[Container seam](#the-container-seam-elf-shipped-pe-library-only-not-ready) below):

```
Phase 1 — source attribution
  read-only data  →  Location structs  →  classify each path
  (.data.rel.ro/.rdata)   (file, line, col)    User / Std / Dep / Unknown

Phase 2 — function attribution
  function ranges  →  xref scan  →  certain set  →  confidence tier
  (.eh_frame/.pdata)  (which fn references   (multiplicity of
                        which Location)        distinct user Locations)
```

**The precision lever is multiplicity, not presence.** A monomorphized
library generic (e.g. a `FilterMap<…, user_closure>`) inlines exactly one
user closure and so references exactly one user Location. A real user
function references several of its own panic sites. Requiring ≥N distinct
user Locations (`--min-anchors`, default 2) rejects most single-closure false
positives — but see [The hard case](#the-hard-case-a-real-unmitigated-false-positive-mechanism)
below: multiplicity is not sufficient when the *library's own* function
absorbs several distinct user Locations via inlining. This is the one place
the architecture's core assumption has a known, reproduced hole.

Four attribution buckets fall out of the scan (`src/classify.rs`):

| Bucket | Meaning | Trust it? |
|---|---|---|
| `Certain` | direct xref to a user Location | yes, with the caveat above |
| `Inferred` | reachable only from certain-user code | diagnostic only (~5-10% precision) |
| `Indeterminate` | reachable from user code but also from library code | no |
| `Library` | everything else | no |

`Certain` functions are further split into **STRONG** (≥ `min_anchors` user
Locations) and **SINGLE** (exactly 1).

## Module map

Status column: **Shipped** = in the default CLI path and load-bearing.
**Library** = compiles, tested, reachable only by hand-writing code against it.
**Diagnostic** = wired behind a flag, produces output, but that output is not
trustworthy for the tool's stated purpose. **Dead** = compiled but nothing
in this repo or its known consumer ever calls it.

| Module | Lines | Tests | Status | Notes |
|---|---:|---:|---|---|
| `elf.rs` | 346 | 0¹ | Shipped | mmap an ELF, index sections |
| `container/mod.rs` | 55 | — | Shipped | `BinaryImage` trait, the format seam |
| `container/elf_image.rs` | 118 | 0¹ | Shipped | ELF behind the trait; one dead field (`strings`, `#[allow(dead_code)]`, stored and never read) |
| `container/pe.rs` | 603 | 9 | **Library, not production-ready** | see hard-case section |
| `frame.rs` | 243 | 0¹ | Shipped | `.eh_frame` → function ranges, with fallbacks |
| `strings.rs` | 603 | 22 | Shipped | path classification — the most heavily tested module, correctly so: it's the precision-critical Phase 1 logic |
| `locate.rs` | 99 | 0¹ | Shipped | Location struct reconstruction |
| `xref.rs` | 255 | 0¹ | Shipped | x86-64 decode, certain set — **the module with the unmitigated hard-case gap, and zero direct unit tests**; only covered by integration tests and real-corpus validation |
| `classify.rs` | 374 | 6 | Shipped | BFS propagation into the four buckets |
| `report.rs` | 1023 | 7 | Shipped | human report, tiering, `--json`, `--types` printer. Largest file by design — it's where all presentation logic lives, not bloat (`too_many_lines` is an explicit clippy exemption) |
| `types.rs` | 440 | 0¹ | **Diagnostic, empirically ~0% useful** | see [Dead code](#dead-code-and-unshipped-surfaces) |
| `dwarf.rs` | 735 | 7 | Shipped (validation only) | secondary ground truth for `--validate`; had 3 real bugs, all fixed this month — see below |
| `pdb_oracle.rs` | 562 | 12 | Library (validation only) | ground truth for the PE library path |
| `bin/anchor_headroom.rs` | 589 | 0 | **Dead** | research probe, concluded "structural ceiling," never wired to anything |

¹ Zero direct `#[test]`s in the file itself; behavior is covered by
`tests/integration.rs` (7 tests) and the real-corpus measurement in `realval/`.
This is a legitimate methodology (measuring against real binaries catches
things unit tests on synthetic input wouldn't), but it means `elf.rs`,
`frame.rs`, `locate.rs`, and — most importantly — `xref.rs` have no isolated
regression test for the specific mechanism the hard case exploits. The hard
case would not have been caught by anything currently in `cargo test`; it
took a deliberately adversarial construction to surface.

## The container seam: ELF shipped, PE library-only, **not ready**

`src/container/` defines `BinaryImage`, a trait that speaks one address space
per image (vaddr on ELF, RVA on PE) and exposes `function_ranges`,
`locations`, `xref_locations_in`, `bytes_at`. The idea holds up structurally:
both impls exist, are unit-tested, and the ELF impl is the regression oracle
for the PE one. The container seam itself is not the problem.

**The `unhusk` CLI binary (`src/main.rs`) only ever loads `elf::ParsedElf` —
there is no `--pe` flag or any code path that routes a binary through
`PeImage`.** That was already true in the last write-up. What's changed is
*why that's now clearly the right call*, not just an unfinished task:

### What's actually built on the PE side

This is real, substantial, tested work — the verdict below is about
production-readiness, not about whether the port exists:

- **`container/pe.rs` (603 lines, 9 tests):** parses PE32+, walks `.pdata` for
  function `[start, end)` ranges (the RVA analogue of `.eh_frame` FDEs — no
  unwind-table equivalent needed since `.pdata` already gives exact bounds),
  extracts `Location` structs from `.rdata`, and runs the same iced-x86
  RIP-relative xref scan as the ELF side, just in RVA space instead of vaddr.
- **`pdb_oracle.rs` (562 lines, 12 tests):** an independent ground-truth
  reader over `.pdb` files via the `pdb` crate — the PE-side counterpart to
  `dwarf.rs`, answering "what file was this function declared in" from
  Microsoft's debug format instead of DWARF, including inline-site data
  (which function's body a comparator closure actually got inlined into —
  this is what let session 4 corroborate the hard case two independent ways
  in one measurement: xref-address coincidence *and* the PDB's own inline
  stream).
- **Toolchain:** cross-compiled via `cargo-xwin` to `x86_64-pc-windows-msvc`
  on the same active nightly (`1.98.0-nightly`, `9e2abe0c6`) used for every
  other measurement in this repo — not a different channel skewing results.
- **A genuinely useful practical finding from session 4:** for lld-link-produced
  PE images, MSVC debug info lives entirely out-of-process in the `.pdb`; the
  linked `.exe` carries nothing `strip`/`llvm-strip --strip-all` removes,
  regardless of the `debug`/`strip` profile settings. Concretely: an
  `oracle`-profile build and a `--strip-all`'d copy of it were **byte-for-byte
  identical** (`md5sum` match on the whole file, not just `.text`/`.pdata`).
  So on this target, "build once with debug info, strip a copy to simulate
  the wild binary" — the two-file dance the ELF side needs — collapses to
  "build once." That's a real simplification for anyone extending this work.
- **The measurement history, honestly:** session 2 (`procs`, sync) measured
  STRONG 9/9, 0 FP. Session 3 (`dufs`, async) measured STRONG 14/14, 0 FP,
  and concluded the hard-case FP mechanism was "structural[ly] absent."
  Session 4 (below) built a construction that defeats that conclusion
  directly. All three measurements are real and reproducible on their own
  binaries — the mistake was generalizing "0 occurrences on two crates" to
  "rare in optimized Rust," not the measurements themselves.

## The hard case: a real, unmitigated false-positive mechanism

Two prior PE-port sessions (procs, dufs — see `docs/PDB_ORACLE_procs.md`,
`docs/PDB_ORACLE_dufs.md`) measured STRONG-tier precision of 9/9 and 14/14
with zero false positives, and concluded the specific FP mechanism the whole
validation effort was built to catch — a library generic absorbing multiple
distinct user Locations via inlining — was "rare-to-absent by construction."

**That conclusion was survivorship bias from crate selection, not a property
of the optimizer.** `docs/PDB_ORACLE_hardcase.md` (session 4) built a
construction that defeats it directly: five ordinary wrapper functions handing
small user closures to `slice::sort_by`, `sort_unstable_by_key`, and rayon's
`par_iter().map()/for_each()`. Result: **8 of 13 false positives land at
STRONG tier** — the tier downstream signature generation is supposed to
trust unconditionally. `--min-anchors` does not help; the anchors are
genuinely distinct user Locations, just attributed to the library's function
instead of the user's.

**I reproduced this independently this session, on ELF, using DWARF ground
truth** — a completely different oracle mechanism from the PDB one the
original finding used. Same construction (`slice::sort_by` + rayon closures,
300k-element input, `lto=true, codegen-units=1, opt-level=3`), built natively
for `x86_64-unknown-linux-gnu`, validated with `unhusk --validate`:

```
certain    15 predicted   TP=  2  FP= 13  unknown=  0   precision=13.3%
```

6 of 7 STRONG-tier hits were `core::slice::sort::*` internals carrying the
`sort_by` comparator's panic sites, not user code. **This confirms the
mechanism is not a PE artifact.** It lives in `classify.rs`/`xref.rs`, which
ELF and PE share through the container seam by design — the same code that
makes "adding a format is adding an impl" true also means a gap in the shared
multiplicity heuristic hits both formats identically.

**No fix exists yet, and the one cheap candidate is a documented dead end.**
Session 4 measured whether reference fan-out (how many distinct functions
reference the same Location) separates the false positives from real hits:
it works for the `std::slice::sort` sub-family (fan-out 5-6 vs. 1 for genuine
hits, zero measured recall cost) but **cannot** separate the `rayon`-bridge
shape — those false positives sit at fan-out 1, identical to genuine STRONG
attributions. A real fix needs new structural detection (recognizing generic
monomorphization over a closure/callback parameter, independent of the
xref-address coincidence classify.rs currently relies on entirely) — that's a
research task, not a threshold tweak, and it hasn't been scoped, let alone
attempted.

**Confirmed, not just plausible — `bench/origin/INLINE_LEAK_INCIDENCE.md`
did the cross-reference this paragraph used to call for.** Mining the
already-built 43-crate × 8-config corpus (no adversarial construction, no
rebuild) found 3605 real instances of a non-AUTHOR-declared function
absorbing a user Location, and resolved every one's demangled symbol name:
89.9% are genuine inline-absorption (futures/tokio/actix_web combinators,
`core::slice::sort` internals, rayon, serde generics — not just the
`sort_by`/rayon shape this section's construction used), only 10.1% are the
already-handled forwarding-wrapper shape (`LocalKey::with`/
`__rust_begin_short_backtrace`). Converted to a precision figure over the
STRONG+SINGLE population directly (not the whole-FDE pooled rate): 86.3%
combined pooled across all 8 configs, 86.17% specifically at
`lto-fat,opt-3,panic-abort` — the profile real stripped release binaries
actually ship at. `docs/validation.md:41` already had one real-corpus
instance of this exact mechanism (`rage`, crypto category, "genuine (rayon,
sevenz generics)") sitting unconnected to this section since before it was
written up here — now cross-linked both directions. **These two
measurements (`realval`'s 94.4%/87.3% and `bench/origin`'s 86.3%) are not
comparable and must not be arithmetically combined** — different oracle
implementation detail, different corpus, and materially different
build-config breadth (`realval` builds one config per binary; this figure
pools a systematic 8-config sweep). See `docs/validation.md`'s "Two
measurements" section for the full accounting.

### Verdict: PE is not ready to connect to main

- Not CLI-wired (no dispatch, no `--pe` flag) — a downstream consumer has to
  hand-write code against `container::pe::PeImage`.
- The one real downstream consumer (winnow) doesn't depend on this crate at
  all yet, PE or otherwise — there's no integration point waiting on this.
- The core trust claim for PE's STRONG tier (the tier a signature generator
  is told to trust unconditionally) is reversed from "clean, 0 FP" to
  "8/13 FPs at STRONG on an ordinary-Rust construction, no mitigation."
- The mechanism is shared with ELF, so this isn't fixable by staying on the
  PE side of the container seam — it needs work in `classify.rs`/`xref.rs`
  that benefits both formats, meaning "finish the PE port" and "fix this" are
  the same task, not sequential ones.

Wiring PE into the CLI today would present it with the same trust framing as
ELF's STRONG tier, which the STRONG tier does not currently earn on PE. Don't
connect it until either the hard case has a real mitigation, or the CLI/JSON
contract carries an explicit lower-trust label for PE output.

## The output contract — this is the integration seam

```sh
unhusk <stripped-elf> --precision --json
```

emits one JSON object per attributed function; nothing else. This is the
contract a downstream tool should parse:

```json
{"start": "0xd25af", "end": "0xd38a5", "size": 4854, "tier": "strong",
 "anchor_count": 6, "anchor_files": ["akiranew/src/path_finder.rs"]}
```

`--precision` restricts output to STRONG-tier functions only. Without it,
`--json` still tiers but includes SINGLE too. `--min-anchors N` changes what
counts as STRONG. All of this was re-verified this session against a fresh
`cargo install`-built binary (`pastel`): `--precision --json`, plain `--json`
tier counts, and a `--min-anchors 1..4` sweep all behaved exactly as
documented (27 → 16 → 14 → 5 STRONG functions as N increases, monotonic).
`--infer-depth`, `--backtrace-depth`, `--show-call-closure`, and `--crate`
were also exercised directly and match their documented behavior; `--crate`
given explicitly produced byte-identical JSON to auto-detection on the same
binary.

Beyond the JSON contract, a handful of env-gated diagnostics
(`UNHUSK_DUMP_TIERS`, `UNHUSK_DUMP_DEPS`, `UNHUSK_DUMP_ATTRS`,
`UNHUSK_DUMP_EDGES`, `UNHUSK_DUMP_ALL_FNS`, `UNHUSK_DUMP_GT`) exist for
building measurement harnesses; not part of the stable contract.

One flag ships without a validated payoff: `--backtrace-depth` /
`certain_by_backtrace` (reverse-BFS from certain functions) is implemented,
wired, and off by default. Its own `--help` text says "use `--validate` to
measure precision of the backtrace bucket," but no such measurement appears
anywhere in `README.md`, `docs/validation.md`, or `realval/`. It's a real,
working feature with an unfulfilled promise attached to it, not dead code —
just unvalidated.

## Precision, by tier and workload

Pooled numbers, 32-binary symbol-ground-truth corpus (`realval/`, stratified
sync/async, Wilson + cluster-bootstrap CIs — see `docs/validation.md` and
`realval/results_body.md`):

| Tier | Rule | sync/CLI | async | pooled |
|---|---|---:|---:|---:|
| STRONG | ≥ `min-anchors` (default 2) | ~96% | ~86-88% | ~93.5-94% |
| SINGLE | exactly 1 | ~86% | ~57-60% | ~80-81% |

**Ground-truth provenance matters here, and it was recently audited.** The
*primary* published numbers above come from a symbol/`cargo-metadata`-based
oracle (`realval/`), not from `dwarf.rs`. `dwarf.rs` is a secondary,
diagnostic ground truth used for `--validate` and the `--infer-depth`
measurements. This month's audit (`docs/dwarf-oracle-audit.md`, current
branch) found and fixed **three real bugs** in it: std generics misread via
sysroot paths, vendored C/asm misread as Rust authorship (31,030 functions
mislabelled across a 58-binary corpus — up to 99% of a single binary's
reported "user" set), and build-script output attributed to the consumer
instead of the generator. **None of these moved the headline STRONG/SINGLE
numbers above** — they never touched the symbol-based `realval/` oracle — but
they did silently distort DWARF-based recall figures until fixed (one
DWARF-derived recall number was wrong until the fix brought it back in line
with the already-published symbol-based figure). Four property tests
(`prop_std_is_std_in_every_spelling`, `prop_only_rust_sources_can_be_author`,
`prop_build_script_output_follows_its_generating_crate`,
`prop_elf_and_pe_oracles_agree`) now guard the class of bug that caused all
three — a guard present on the PE oracle side, missing on the ELF side, three
times in a row. `cargo test` is 70/70 passing post-fix (63 unit + 7
integration, confirmed this session).

## Using unhusk from another project

**As a CLI**, shell out and parse stdout JSON — this path is real and tested.

**As a library**, depend on the `unhusk` crate and either drive the phases
directly (as `src/main.rs` does) or go through `container::elf_image::ElfImage`
/ `container::pe::PeImage` behind `BinaryImage`. Both compile and are tested
in isolation. **What doesn't exist yet is a real consumer exercising this
path** — winnow, the motivating use case, currently reimplements its own
ELF-only pipeline rather than depending on this crate (see
[What this is](#what-this-is)). Anyone integrating today would be the first
to actually exercise the library surface as a dependency rather than a
same-repo module.

## Dead code and unshipped surfaces

Quantified: of 6,437 source lines, roughly **1,080 (~17%)** are either
compiled-but-uncalled or shipped-but-empirically-ineffective:

- **`src/bin/anchor_headroom.rs` (589 lines) — dead.** A research probe
  (bare-anchor recall-headroom measurement). It compiles into its own binary
  on every `cargo build --release` but nothing calls it — not the CLI, not
  `winnow`, not any test. Its own conclusion (git log, `1ac13cb`-era commits):
  recall headroom was 0.16-0.47% by two different ground truths, "structural
  ceiling" — correctly informed the decision *not* to pursue that direction.
  As research it did its job; as shipped code it's inert weight.
- **`--types` (440 lines in `types.rs` + ~50 across `main.rs`/`report.rs`)
  — shipped, reachable, empirically useless.** Git history already concludes
  this ("types: wire --types flag; run 13-binary sweep; conclude approach
  fails" — 3 user-tier hits across 13 binaries, all 3 false positives at the
  type-name level). I re-ran it fresh this session against `pastel`: one
  non-std hit, name `Completely`, fields `bg, blue, brightness, chroma,
  color, deuterSet, fraction, hue, luminance, random, rgb, strategyDeadlock,
  textbold` — a plainly nonsensical amalgam, exactly the failure mode already
  documented. It ships as "experimental diagnostic only," which is accurate,
  but 14 for 14 binaries with zero real signal is past the point of "maybe
  useful with more work" and into "keep for the idea, don't route decisions
  through it."
- **`container/elf_image.rs`'s `strings` field (1 line, explicit
  `#[allow(dead_code)]`)** — stored at construction, never read after.
  Trivial, but real.
- **`bench/results.jsonl`, `bench/run_bench.sh`, `bench/corpus.txt` — REMOVED
  2026-07-30, previously a dead artifact that looked like data.** All 53
  successful rows reported `n_certain: 0` and `sym_user: 0` — zero signal
  across a 53-binary `cargo install` corpus. This was diagnosed same-week
  (`be2f387`, 2026-06-17: "why n_certain=0 for all cargo-installed
  binaries — registry source paths are indistinguishable from dep crates")
  and the *actual fix* (`--crate` flag + auto-detection, `9a1c14f`,
  2026-06-19) landed three days later, but `bench/results.jsonl` was never
  re-run after the fix. The team's real response at the time was to pivot
  same-day to `run_local.sh` (git-clone + local build, sidesteps the whole
  problem via relative paths) and later to `realval/`'s stratified
  methodology — both of which remained the load-bearing measurements. This
  whole cargo-install corpus (plus `bench/aggregate.py`, `parse_metrics.py`,
  `run_cargo_install.sh`, `run_local.sh`, and their result/corpus files) was
  a superseded, unfixed false start with no external references anywhere in
  the repo, and was deleted as part of consolidating this project's
  measurement harnesses into `scripts/oracle.py` + `realval/` + `bench/origin/`.
- **`--backtrace-depth`** — see [output contract](#the-output-contract--this-is-the-integration-seam)
  above; not dead, but shipped ahead of its own promised validation.

## Robustness — re-verified this session

Stripped `.eh_frame` on a fresh binary: falls back to `.eh_frame_hdr`,
recovered 1,069 of the same function starts, output stayed at the identical
27 STRONG+SINGLE functions. Stripped both `.eh_frame` and `.eh_frame_hdr`:
falls back to a call-target map (771 entries, explicitly flagged
"approximate; tier precision is degraded" on stderr), output dropped to 17
functions rather than silently returning nothing. Both fallback paths behave
as documented.

## Status and scope

- **Shipped end-to-end via the CLI:** x86-64 ELF, PIE and non-PIE.
- **Library-only, not production-ready:** PE (`x86_64-pc-windows-msvc`) — see
  the [verdict](#verdict-pe-is-not-ready-to-connect-to-main) above. Not "not
  CLI-wired yet" as a to-do item; not ready because its core trust claim was
  reversed and the fix is unscoped.
- **Robust against stripping:** survives `.eh_frame` removal, section-header
  stripping, and `panic=abort` — re-confirmed this session, not just cited
  from old docs. Defeated by `--remap-path-prefix`, packing, and
  `-Z build-std panic_immediate_abort`.
- **Recall is a known, structural open problem**, not a bug — confirmed
  independently by `anchor_headroom`'s now-dead-but-conclusive research.
- **A previously undocumented gap** (found during independent validation
  against the cxiao panic-metadata write-up, not yet acted on): non-PIE
  binaries defeat both `locate.rs`'s relocation walk *and* `xref.rs`'s
  RIP-relative-only scan independently — `movabs` immediate loads have no
  memory operand for `xref.rs` to see. And `#[track_caller]` helper functions
  (custom `assert_valid()`-style wrappers) are structurally invisible to
  Certain/STRONG: the Location lives at the call site, not in the helper's
  own body, so multiplicity distributes across N callers instead of landing
  on the one function that's actually 100% user-authored. Full detail:
  `PANIC_ORACLE_GAPS.md` (repo root, untracked working notes).

## Where to go next

- `README.md` — install, full CLI reference. States ELF as the only supported
  input format and the PE/PDB code as a tested in-tree library that is not
  wired to the CLI and cannot be reached from it (matching the verdict above),
  and carries the same inline-absorption caveat as this document, worded once
  and applying to both formats.
- `docs/validation.md`, `realval/results_body.md` — the precision derivation.
- `docs/dwarf-oracle-audit.md` — this month's ground-truth bug audit.
- `docs/PDB_ORACLE_hardcase.md` — the session-4 finding this document leans on.
- `docs/PDB_ORACLE_procs.md`, `docs/PDB_ORACLE_dufs.md` — the earlier,
  since-corrected "clean" PE measurements; useful for the reversal's context.
- `PANIC_ORACLE_GAPS.md` — non-PIE and `#[track_caller]` gaps, untracked.
- `references/` — prior art (SentinelLabs 0xA11C, Cindy Xiao's panic-metadata
  post) and the RIFT contrast.

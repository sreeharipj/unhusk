# unhusk

Identifies user-authored functions in stripped Rust release binaries using panic metadata and call-graph inference — no symbol tables, no signature databases, no debug info required.

## What it does

A stripped, LTO release Rust binary is dominated by the standard library and Cargo dependencies. The author's code is a small fraction. `unhusk` finds user-authored functions in two phases.

**Phase 1 — string classification:** Rust embeds a `core::panic::Location` struct in `.data.rel.ro` for every reachable `panic!`, `assert!`, bounds-check, and `.unwrap()` call site. Each struct holds a source-path string pointer. `unhusk` classifies every such path as `User`, `Std`, or `Dep` and prints a location-level breakdown.

**Phase 2 — function attribution:** `.eh_frame` FDEs give exact function ranges. An x86-64 xref scan identifies functions that directly reference user `Location` structs (`certain`). A BFS over the call graph propagates attribution outward (`inferred`). An optional reverse BFS finds callers-of-certain-callers (`certain_by_backtrace`). An optional scan recovers struct/field names from `#[derive(Debug)]` artifacts (`--types`).

**Attribution buckets:**

| Bucket | How | Precision |
|---|---|---|
| `certain` | Direct reference to a user panic Location | ~94% by symbol, ~67% by DWARF `decl_file` |
| `inferred` | Reachable from certain; all callers are user | ~9–10% |
| `certain_by_backtrace` | Callers of certain functions (reverse BFS, flag-gated) | ~72% by symbol |
| `indeterminate` | Reachable from both user and library — diagnostic only | ~0% |

The gap between symbol and DWARF precision is not primarily algorithm error: ~80% of the DWARF-scored false positives are user closures dispatched through `FnOnce`/`FnMut` whose `decl_file` DWARF attributes to `core/src/ops/function.rs`. By symbol name, those functions belong to the user crate. The irreducible error (~6% by symbol) is std/dep generics monomorphized with user types — indistinguishable in a stripped binary.

**Measured on 13 real-world Rust binaries** (ripgrep, bat, fd, just, dust, hyperfine, xsv, pastel, grex, hexyl, tokei, sd, zoxide):

| Precision ruler | Median | Mean | Genuine FP rate |
|---|---|---|---|
| Symbol name (crate ownership) | **94.4%** | 88.7% | **5.2%** |
| DWARF `decl_file` | 66.7% | 64.1% | — |

**Certain recall** (DWARF denominator): median **15.8%**, range 0.4%–45.5%. Recall tracks panic density and how much user code survives as standalone functions after inlining. Combined certain+inferred recall: median **46.2%** (DWARF upper bound), **19.0%** (symbol denominator — more honest, larger denominator).

## Precision tiers (for signature / YARA-seed extraction)

For a precision-first backend, the `certain` set is split into confidence tiers using only
Location structure — **no symbols, no DWARF, and optimization-invariant** (verified stable from
thin-LTO through `lto=true, codegen-units=1`). Pooled across 13 binaries + a full-LTO build
(symbol ground truth):

| Tier | Rule | Symbol precision |
|---|---|---|
| **STRONG** | ≥ N distinct user Locations (N = `--min-anchors`, default 2) | ~98% |
| **CONFIRMED** | 1 Location, but its source file also hosts a STRONG function | ~93% |
| **WEAK** | 1 Location in a file that never hosts a STRONG function | ~51% (noise) |

A source file containing any multi-panic function is "confirmed user"; single-panic functions in
it are genuine, while single-panic functions in never-confirmed files are mostly monomorphized
library generics (the false-positive concentrate). **`--precision` emits STRONG + CONFIRMED**
(≈95.5% precision at ≈77% of certain recall) and suppresses WEAK + the call closure.
`--min-anchors` is the precision dial: 1 → 94.9%, 2 → 97.9%, 3 → 99.5% (recall falls 100→41→24%).

The `--types` `#[derive(Debug)]` signal was evaluated as a cross-confirmation booster and
**rejected** — it is nearly disjoint from `certain` (fmt functions rarely panic) and compiled type
layouts are not ABI-stable. Source-file coherence is the independent signal that pays off.

## How it works

```
.rela.dyn  R_X86_64_RELATIVE { offset, addend }
    │   offset  → slot in .data.rel.ro  (the file-ptr field of the Location)
    └── addend  → string in .rodata     ("src/main.rs", "/rustc/…", …)

.data.rel.ro  [ ptr(reloc) | len(u64) | line(u32) | col(u32) ]
```

Source-path classification (deterministic, no heuristics):

| Pattern | Attribution |
|---|---|
| `src/*.rs`, `tests/*.rs`, `examples/*.rs` | **User code** |
| `/rustc/HASH/library/…` or `library/…` | std/core/alloc |
| `/rust/deps/CRATE-VER/…` | toolchain-embedded dep |
| `*/cargo/registry/src/*/CRATE-VER/…` | Cargo registry dep |

For binaries installed via `cargo install`, source paths live under `~/.cargo/registry/src/…`. Pass `--crate <name>` to promote those paths from `Dep` to `User`, or let unhusk auto-detect the root crate from the binary filename and embedded paths.

## Usage

```sh
# Identify user-authored functions in a stripped binary
unhusk <stripped-elf>

# Specify the root crate (required for `cargo install` binaries, auto-detected otherwise)
unhusk <stripped-elf> --crate ripgrep

# Validate precision/recall against DWARF ground truth from an unstripped twin
unhusk <stripped-elf> --validate <unstripped-elf>

# Cap call-graph BFS at N hops from certain functions:
#   --infer-depth 1: 1.8× precision gain (~9.3%), -4pp recall — high-precision audits
#   --infer-depth 2: 1.3× precision gain (~6.4%), -1pp recall — best balance
unhusk <stripped-elf> --infer-depth 2

# Walk back N hops from certain functions via the reverse call graph (default off):
#   depth=1 recommended; deeper gains are negligible on real binaries
#   ~72% marginal symbol precision, +0.9pp median symbol recall
unhusk <stripped-elf> --backtrace-depth 1

# Recover struct/field names from #[derive(Debug)] artifacts in .rodata/.data.rel.ro
unhusk <stripped-elf> --types

# Show full call-closure list instead of capping at 20
unhusk <stripped-elf> --show-call-closure

# PRECISION MODE — emit only STRONG + CONFIRMED tiers, suppress weak + call closure
unhusk <stripped-elf> --precision

# Precision dial: STRONG tier requires N distinct user Locations
#   1 → 94.9% precision (100% recall) · 2 → 97.9% (41%) · 3 → 99.5% (24%)
unhusk <stripped-elf> --min-anchors 3

# JSON feed for a downstream signature/YARA generator (suppresses human report)
#   honors --precision and --min-anchors; emits start/end/size/tier/anchor_files
unhusk <stripped-elf> --precision --json
```

When `.eh_frame` is absent (e.g. an adversary ran `objcopy --remove-section`), unhusk falls back
to a call-target-derived function map so Phase 2 degrades (recovering ~93% of STRONG functions)
instead of producing nothing. Phase 1 source attribution is unaffected — it needs no unwind info.

## Precision and recall — key findings

Validation methodology: 13 popular pure-Rust CLI tools, each built twice (`CARGO_PROFILE_RELEASE_DEBUG=true CARGO_PROFILE_RELEASE_STRIP=false` for the debug twin, default release for the stripped copy), then `unhusk <bin>.stripped --validate <bin>.debug`. Two ground-truth rulers were applied: DWARF `decl_file` and `nm -C` symbol-name leading-crate classification.

**Why the two rulers diverge:** 67% of all DWARF-scored false positives are `FnOnce`/`FnMut` closure shims — user closures whose monomorphized `call_once` body is the user's code but whose DWARF `decl_file` points to `core/src/ops/function.rs:250`. Symbol-name GT correctly attributes these to the user crate; DWARF does not. The 80% of the symbol/DWARF disputed set that falls into this category represents genuine user logic recovery, not algorithm failure.

**Depth-limit guidance for `--infer-depth`** (pooled across 13 binaries):

| depth | inferred precision | inferred count | recall loss vs ∞ |
|---|---|---|---|
| 1 | 9.3% | −59% fewer predictions | −3.9pp |
| 2 | 6.4% | −30% fewer predictions | −1.1pp |
| ∞ (default) | 5.1% | — | — |

**Backward BFS (`--backtrace-depth`):** Marginal symbol precision 72% at depth=1. Median recall gain +0.9pp (symbol), bimodal — 6 of 13 binaries gain >1pp; the other 7 gain near zero. Depth=1 converges on all 13 binaries; deeper sweeps are redundant. Off by default because DWARF recall can't confirm the gain for the FnOnce-heavy binaries.

## Limitations

**Closure shims and generic monomorphizations reduce certain precision.** When user code is a closure invoked through `Fn*`, or when user types are passed to std/dep generics (sort, iter adapters, lazy-init), the resulting monomorphized function may contain a user-path panic Location even though DWARF attributes the function to core/std. These account for most false positives on real binaries and are indistinguishable from real user functions in a stripped binary — no available signal separates them.

**Functions with no reachable panic site are not found.** Pure computation, getters, and code where the optimizer proved every panic unreachable have zero Location structs — nothing to anchor on.

**User code invoked only through trait objects, function pointers, or library dispatch** appears as `library`. The xref scan only follows static call edges.

**x86-64 ELF only.** PIE (`ET_DYN`, default for `cargo build --release`) and non-PIE (`ET_EXEC`) are both supported.

## Type name recovery (`--types`)

`#[derive(Debug)]` generates `fmt` functions that call `f.debug_struct("Name").field("field", …)`. The string literals live in `.rodata`; `unhusk` locates them via RIP-relative LEA/MOV pairs in the function body. Results are tiered:

- **user** — struct/field name appears in a `certain` or `inferred` function
- **non-std** — name found in an unattributed function (dep or unconfirmed)
- **std** — name matches a known std/core/alloc type

## Build

```sh
cargo build --release
```

Requires Rust 1.70+. No C library deps, no external tools at runtime.

## Docker

```sh
docker build -t unhusk .

# Mount the current directory and analyze a binary
docker run --rm -v "$(pwd)":/work -w /work unhusk <stripped-elf>

# Validate against an unstripped binary
docker run --rm -v "$(pwd)":/work -w /work unhusk <stripped-elf> --validate <unstripped-elf>
```

## Tests

```sh
cargo test
```

Integration tests require fixture binaries under `/tmp/unhusk-research/` (see `tests/integration.rs`). Unit tests for the string classifier run without fixtures.

## License

Dual-licensed:
1. **GNU Affero General Public License v3.0 (AGPLv3)** — for open-source and general use.
2. **Commercial License** — for proprietary or commercial use where AGPLv3 restrictions are not applicable.

See the `LICENSE` file for details.

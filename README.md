# unhusk

Identifies user-authored functions in stripped Rust release binaries using panic metadata — no disassembly, no symbol tables, no signature databases.

## What it does

A stripped, LTO release Rust binary is dominated by the standard library and Cargo dependencies. The author's code is a small fraction. `unhusk` finds the user-authored functions with high precision by exploiting a structural property of the Rust panic machinery.

**Primary output — `certain` functions:** 100% precision, validated against DWARF ground truth on three independent binaries. These are functions that directly reference a `core::panic::Location` struct in `.data.rel.ro` whose source path resolves to user code (`src/`, `tests/`, `examples/`). Every such function was written by the binary's author.

**Measured recall:** certain catches roughly 1/3 of user functions (37.5% on the unhusk-on-unhusk fixture). The ceiling is structural — see Limitations below.

**Call closure (not user code):** `inferred` and `indeterminate` functions are reachable from user code via call edges but are not user-authored. DWARF precision on real binaries: ~5% (mostly dep/std glue transitively called from user panic sites). These are labelled separately and never counted as user code.

## How it works

Rust embeds a `core::panic::Location` struct in `.data.rel.ro` for every reachable `panic!`, `assert!`, bounds-check, and `.unwrap()` call site. Each struct holds a fat `&'static str` pointer (via a PIE relocation in `.rela.dyn`) into the source-path string in `.rodata`, plus the line and column numbers.

**Phase 1** — reconstruct every Location struct and classify its source path:

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

**Phase 2** — `.eh_frame` FDE-based function range map + RIP-relative xref scan. Any function that contains a reference to a user Location struct is marked `certain`.

## Precision validation

The `--validate <UNSTRIPPED>` flag compares unhusk's attribution against DWARF `.debug_info` ground truth from a companion unstripped binary:

```sh
unhusk binary.stripped --validate binary.unstripped
```

Measured results across three fixtures:

| Fixture | FDEs | DWARF-user fns | Certain precision | Certain recall |
|---|---|---|---|---|
| medium_debug (synthetic) | 541 | 1 | 100% (1/1) | 100% |
| unhusk-on-unhusk | 1490 | 8 | 100% (3/3) | 37.5% |
| scored_debug (designed) | 529 | 19 | 100% (6/6) | ~84% |

Certain precision is 100% in every measurement. A CI regression test in `tests/integration.rs` enforces this: if a code change introduces a false positive, `certain_precision_never_drops_below_100_pct` fails.

## Limitations

**Functions with no reachable panic site** are not found. Pure computation, getters, and code compiled with `lto = true` where the optimizer proved every panic unreachable will have zero panic Location structs in the binary — nothing to anchor on.

**User code invoked through std machinery or indirect dispatch** is not found. Functions called only via trait objects, function pointers, or callbacks that pass through std/dep dispatch layers appear as `library` (not reached by the xref scan from a certain anchor).

These are structural, not implementation gaps. The tool's guarantee is precision: when it says "user-authored," it is right. It does not guarantee coverage of all user functions.

**x86-64 ELF only.** PIE (`ET_DYN`, default for `cargo build --release`) and non-PIE (`ET_EXEC`) are both supported.

## Build

```sh
cargo build --release
```

Requires Rust 1.70+. No C library deps, no external tools at runtime.

## Usage

```sh
# Identify user-authored functions in a stripped binary
unhusk <stripped-elf>

# Also report DWARF-validated precision/recall numbers
unhusk <stripped-elf> --validate <unstripped-elf>

# Show full call-closure list (reachable from user, mostly dep/std)
unhusk <stripped-elf> --show-call-closure
```

## Tests

```sh
cargo test
```

Integration tests require fixture binaries under `/tmp/unhusk-research/` (see `tests/integration.rs`). Unit tests for the string classifier run without fixtures.

## License

MIT OR Apache-2.0

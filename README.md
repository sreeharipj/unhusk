# unhusk

Identifies user-authored functions in stripped Rust release binaries using panic metadata — no disassembly, no symbol tables, no signature databases.

## What it does

A stripped, LTO release Rust binary is dominated by the standard library and Cargo dependencies. The author's code is a small fraction. `unhusk` finds the user-authored functions by exploiting a structural property of the Rust panic machinery.

**Primary output — `certain` functions:** functions that directly reference a `core::panic::Location` struct in `.data.rel.ro` whose source path resolves to user code (`src/`, `tests/`, `examples/`). Every such function contains user-path panic metadata.

**Measured precision on 13 real-world Rust binaries (ripgrep, bat, fd, just, dust, …):**

| Ground-truth method | Median precision | Mean | Genuine FP rate |
|---|---|---|---|
| Symbol name (crate ownership) | **94.4%** | 88.7% | **5.2%** |
| DWARF `decl_file` | 66.7% | 64.1% | — |

The symbol-name figure (94.4%) is the more honest measurement. The DWARF figure is lower because DWARF attributes `FnOnce`/`FnMut` closure shims to `core/src/ops/function.rs` even when the closure body is entirely user code; these account for ~67% of DWARF-scored false positives. The irreducible 5.2% error comes from std/dep generic functions monomorphized with user types — unhusk cannot distinguish these from real user functions in a stripped binary.

**Measured recall:** certain catches roughly 15% of user functions on real binaries (median 15.8%, range 0.4%–45.5%). The ceiling is structural — see Limitations below.

**Call closure (not user code):** `inferred` functions are reachable from user code via call edges. DWARF precision ~5% on real binaries (mostly std/dep glue transitively called from user panic sites). Labelled separately.

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

Measured results across three small/synthetic fixtures (where user functions are standalone, non-inlined):

| Fixture | FDEs | DWARF-user fns | Certain precision | Certain recall |
|---|---|---|---|---|
| medium_debug (synthetic) | 541 | 1 | 100% (1/1) | 100% |
| unhusk-on-unhusk | 1490 | 8 | 100% (3/3) | 37.5% |
| scored_debug (designed) | 529 | 19 | 100% (6/6) | ~84% |

On real-world binaries, precision drops (median 66.7% by DWARF, 94.4% by symbol) because user code expressed as closures or library-generic instantiations is attributed by DWARF to its definition site in core/std. See `REAL_BINARY_VALIDATION.md` for full results on 13 binaries.

## Limitations

**Closure shims and generic monomorphizations reduce precision.** When user code is a closure invoked through `Fn*`, or when user types are passed to std/dep generics (sort, iter adapters, lazy-init), the resulting monomorphized function may contain a user-path panic Location even though the bulk of the function body is library logic. unhusk marks these `certain`; they account for most false positives in real binaries.

**Functions with no reachable panic site** are not found. Pure computation, getters, and code compiled with `lto = true` where the optimizer proved every panic unreachable will have zero panic Location structs in the binary — nothing to anchor on.

**User code invoked through std machinery or indirect dispatch** is not found. Functions called only via trait objects, function pointers, or callbacks that pass through std/dep dispatch layers appear as `library`.

**x86-64 ELF only.** PIE (`ET_DYN`, default for `cargo build --release`) and non-PIE (`ET_EXEC`) are both supported.

## Build

```sh
cargo build --release
```

Requires Rust 1.70+. No C library deps, no external tools at runtime.

## Docker

You can easily build and run `unhusk` using Docker, which provides an isolated environment without needing to install the Rust toolchain.

### Build the Image

```sh
docker build -t unhusk .
```

### Run the Container

When running via Docker, you need to mount the directory containing your binaries as a volume so the container can access them.

```sh
# Mount the current directory and analyze a binary
docker run --rm -v "$(pwd)":/work -w /work unhusk <stripped-elf>

# Validate against an unstripped binary
docker run --rm -v "$(pwd)":/work -w /work unhusk <stripped-elf> --validate <unstripped-elf>
```

## Usage

```sh
# Identify user-authored functions in a stripped binary
unhusk <stripped-elf>

# Also report DWARF-validated precision/recall numbers
unhusk <stripped-elf> --validate <unstripped-elf>

# Show full call-closure list (reachable from user, mostly dep/std)
unhusk <stripped-elf> --show-call-closure

# Cap call-graph BFS at N hops (measured on 13 real binaries):
#   depth 1: 9.3% inferred precision (+1.8x), -3.9pp recall — high-precision audits
#   depth 2: 6.4% inferred precision (+1.3x), -1.1pp recall — best balance
unhusk <stripped-elf> --infer-depth 2
```

## Tests

```sh
cargo test
```

Integration tests require fixture binaries under `/tmp/unhusk-research/` (see `tests/integration.rs`). Unit tests for the string classifier run without fixtures.

## License

MIT OR Apache-2.0

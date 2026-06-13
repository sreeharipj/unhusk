# unhusk

Recovers user-authored logic from stripped Rust release binaries.

A stripped, release-mode, LTO Rust binary is dominated by the standard library
and Cargo dependencies.  The application logic the author wrote is a tiny
fraction of the functions.  `unhusk` separates the two without symbol tables,
debug info, or pre-computed signature databases.

## Status

**Phase 1 (this release):** panic-site attribution — finds every
`core::panic::Location` struct in the binary and attributes it to the
user crate, std, or a specific dep crate, with exact file/line/column.

**Phase 2 (next):** `.eh_frame` function-range mapping + RIP-relative xref
scan to attribute every function, not just those with reachable panic sites.

## How it works

Rust's panic machinery embeds a `core::panic::Location` struct in
`.data.rel.ro` for every reachable `panic!`, `assert!`, bounds-check, and
`.unwrap()` call site.  Each struct holds a fat `&'static str` pointer (via a
PIE relocation in `.rela.dyn`) into the source-path string in `.rodata`, plus
the line and column numbers.

`unhusk` reconstructs the full chain without a disassembler:

```
.rela.dyn  R_X86_64_RELATIVE { offset, addend }
    │   offset  → slot in .data.rel.ro  (the file-ptr field of the Location)
    └── addend  → string in .rodata     ("src/main.rs", "/rustc/…", …)

.data.rel.ro  [ ptr(reloc) | len(u64) | line(u32) | col(u32) ]
                                ^              ^          ^
                           cross-checked    directly   directly
                           against string   readable   readable
```

Source-path classification rules (deterministic, no heuristics):

| Pattern | Attribution |
|---|---|
| `src/*.rs`, `tests/*.rs`, `examples/*.rs` | **User code** |
| `/rustc/HASH/library/…` or `library/…` | std/core/alloc |
| `/rust/deps/CRATE-VER/…` | toolchain-embedded dep |
| `*/cargo/registry/src/*/CRATE-VER/…` | Cargo registry dep |

## Build

```sh
cargo build --release
```

Requires: Rust 1.70+, no C library deps, no external tools at runtime.

## Usage

```sh
unhusk <stripped-elf-binary>
```

Example — analyzing a real binary:

```
$ strip --strip-all target/release/myapp -o myapp.stripped
$ unhusk myapp.stripped
```

## Limitations (Phase 1)

- **LTO dead-code elimination:** if the optimizer proves a panic site
  unreachable, it removes the Location struct.  A binary compiled with
  `lto = true` and statically-known-safe code will show zero user locations.

- **Functions with no panic sites** are not attributed in Phase 1.  Pure
  math, getters, and other non-panicking functions require the Phase 2 xref
  scan.

- **Workspace subcrates** with paths like `crates/mylib/src/foo.rs` are
  not yet classified as user code (treated as Unknown).  Phase 2 will add
  a `--workspace-root` option.

- **x86-64 ELF only** in Phase 1.  PIE (ET_DYN) binaries, which is the
  default for `cargo build --release`.  Non-PIE static binaries (ET_EXEC)
  need a fallback scanner (planned).

## Tests

```sh
cargo test
```

Integration tests require the fixture binaries under `/tmp/unhusk-research/`
(see `tests/integration.rs`).  Unit tests for the string classifier run
without any fixtures.

## License

MIT OR Apache-2.0

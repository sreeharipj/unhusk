# Adversarial audit of the DWARF ground-truth oracle

Prompted by three ground-truth defects found while benchmarking RIFT against
unhusk. Every one had already been guarded on the PE side and was missing on the
ELF side, so this audit assumes the ELF oracle is the weaker of the two and
enumerates every remaining route by which a function can be labelled AUTHOR.

Scope: `strings::classify_path`, `dwarf::classify_path_for_dwarf` (ELF oracle),
`pdb_oracle::classify_decl_file` (PE oracle). Evidence is the 65 archived
ground-truth dumps from the 58-binary benchmark corpus; no corpus was re-run.

## How a function can be labelled AUTHOR

`classify_path` returns `User` by exactly three routes:

1. a cargo-registry path whose crate is in `root_crates`
2. a `crates.io/<crate>-<ver>/` path whose crate is in `root_crates`
3. **any relative path** — the catch-all at the end of the function

The ELF oracle adds a fourth: `Unknown` is promoted to `User`, because genuine
user paths in DWARF are absolute and match none of the guards above.

Routes 3 and 4 are unbounded by construction: they classify by *failure to match
a guard*, so every guard that is missing becomes author code. All three known
bugs live here, and so does every residual risk below.

## Path classes

| Path class | Example | Current label | Correct? | Guard |
|---|---|---|---|---|
| std, remapped | `/rustc/<hash>/library/core/src/ptr/mod.rs` | Std | yes | Y |
| std, local sysroot | `…/lib/rustlib/src/rust/library/core/src/ptr/mod.rs` | Std | yes | **Y (bug 1, fixed)** |
| std, pre-2018 layout | `src/libcore/slice/mod.rs` | Std | yes | Y |
| registry dependency | `…/registry/src/<idx>/serde-1.0.0/src/lib.rs` | Dep | yes | Y |
| registry root crate | `…/registry/src/<idx>/myapp-0.1.0/src/main.rs` | User | yes | Y |
| toolchain-embedded dep | `/rust/deps/hashbrown-0.14/src/lib.rs` | Dep | yes | Y |
| vendored C/asm, absolute | `/aws-lc/crypto/bytestring/cbs.c` | Unknown | yes | **Y (bug 2, fixed)** |
| vendored C/asm, relative | `vendor/ring/crypto/chacha.S` | Unknown | yes | **Y (asymmetry, fixed)** |
| build-script output, dep | `…/build/serde-sarif-<hash>/out/schema.rs` | Dep | yes | **Y (bug 3, fixed)** |
| build-script output, root | `…/build/tokei-<hash>/out/language_type.rs` | User | yes | **Y (bug 3, fixed)** |
| user source, relative | `src/main.rs` | User | yes | Y |
| user source, absolute | `/home/u/proj/src/main.rs` | User | yes | Y (route 4) |
| `include!` of in-tree file | `src/generated_table.rs` | User | yes | Y |
| `include!` of OUT_DIR file | `…/build/<crate>-<hash>/out/tbl.rs` | per generating crate | yes | Y (bug 3 fix) |
| proc-macro expansion | call-site file | inherits call site | yes | N/A |
| **workspace sibling, cargo-install** | `…/registry/src/<idx>/zellij-server-0.44.3/…` | **Dep** | **no** | **N** |
| **workspace sibling, source build** | `zellij-server/src/lib.rs` | **User** | yes | **N** |
| **`cargo vendor` directory** | `vendor/serde-1.0.0/src/lib.rs` | **User** | **no** | **N** |
| **`[patch]` to a local path** | `/home/u/forks/serde/src/lib.rs` | **User** | **no** | **N** |
| **path dependency** | `../mylib/src/lib.rs` | **User** | ambiguous | **N** |

Proc-macro expansion is marked N/A rather than unguarded: DWARF attributes
generated code to the macro's call site, which is the correct answer for
authorship, so no guard is required.

## Residual risks, in severity order

### 1. Workspace siblings are labelled inconsistently by build method — unfixed

The same program yields different ground truth depending on how the corpus was
built. Under `cargo install` the siblings are registry crates and classify as
Dep; built from source they are relative paths and classify as User.

Measured on `zellij`: **1,608 functions** in `zellij-server`, `zellij-client` and
`zellij-utils` are labelled LIB, while only the 20 functions of the `zellij`
root crate are USER. Those 1,608 are unambiguously the same authors' code and
are most of the program.

Effect: it *shrinks* the author denominator, so it does not inflate recall; a
tool that correctly identifies `zellij-server` code is penalised with false
positives instead. Both tools are penalised equally, so the comparison is not
biased, but the absolute precision numbers for workspace-heavy binaries are
understated for both.

Left unfixed because it is a definitional question, not a defect: whether
sibling workspace members are "the author" depends on what the number is for.
For YARA-seed extraction they clearly are. Fixing it means promoting the whole
workspace, which requires knowing the workspace membership — recoverable from
the root crate's `Cargo.toml`, but not from the binary.

### 2. `cargo vendor` and local `[patch]` dependencies read as author code — unfixed

`vendor/serde-1.0.0/src/lib.rs` is relative and ends in `.rs`, so route 3 claims
it. A `[patch]` pointing at a local checkout produces an absolute non-registry
`.rs` path, which route 4 claims. Both are dependency code reported as author
code.

**Zero occurrences in this corpus** — `cargo install` neither vendors nor
patches — so this had no effect on any published number. It is listed because
real malware is far more likely to vendor than a crates.io CLI tool is, and the
`crates.io/` guard already exists for exactly this reason (added after
BlackCat/Sphynx was seen with vendored deps).

Deliberately not fixed: no data to validate a guard against, and inventing a
`vendor/` matcher without a sample risks a guard that is wrong in a new way.

### 3. Route 3 remains unbounded

Any relative `.rs` path is author code. That is the correct default for a
project-relative build, but it means every future build layout that produces
relative paths is author code until someone notices. `prop_only_rust_sources_can_be_author`
bounds this to Rust sources only; nothing bounds it further.

## Property tests

Four tests in `src/dwarf.rs`, each stating an invariant rather than an example.
Verified to **fail against the pre-fix implementation** and pass after it:

| Test | Invariant | Catches |
|---|---|---|
| `prop_std_is_std_in_every_spelling` | every std file is Std in all three spellings rustc emits | bug 1 |
| `prop_only_rust_sources_can_be_author` | only `.rs` files can be author code, absolute or relative | bug 2 + asymmetry |
| `prop_build_script_output_follows_its_generating_crate` | generated Rust is author only when its generating crate is a root crate | bug 3 |
| `prop_elf_and_pe_oracles_agree` | the two oracles agree on every path either can see | all three, and recurrence |

The fourth is the load-bearing one. All three bugs shared a cause — a guard
present on the PE side and absent on the ELF side — so asserting the
relationship directly means the next divergence fails a test instead of
silently corrupting a ground truth.

Verification, pre-fix:

```
test dwarf::tests::prop_build_script_output_follows_its_generating_crate ... FAILED
test dwarf::tests::prop_only_rust_sources_can_be_author ... FAILED
test dwarf::tests::prop_std_is_std_in_every_spelling ... FAILED
test dwarf::tests::prop_elf_and_pe_oracles_agree ... FAILED
test result: FAILED. 0 passed; 4 failed
```

Post-fix: 4 passed, and the full suite is 70 passed / 0 failed.

## Effect of the bug-3 fix on published numbers

165 functions corpus-wide were build-script output labelled USER; roughly 146
belonged to dependencies (`serde-sarif` 130, `cssparser` 14, `html5ever` 2) and
19 to root crates (`tokei`, `onefetch`). This is a ~0.2% correction to the
6,744-function author denominator — far smaller than bug 2's 31,030 — and does
not move any headline figure. Recorded for completeness, not because it changes
a conclusion.

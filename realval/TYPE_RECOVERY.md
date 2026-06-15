# Type-name recovery via `#[derive(Debug)]` artifacts

## Method

`src/types.rs` implements two scans:

**Phase A — `.data.rel.ro` fat-pointer slots:**
Read each R_X86_64_RELATIVE reloc whose offset lands in `.data.rel.ro` and addend
in `.rodata`. Interpret the 8 bytes after the slot as a length field. If the bytes at
that length in `.rodata` look like an identifier (ASCII alphanum+`_`, no `.rs` suffix),
record it as a potential field name.

**Phase B — LEA+MOV pair scan in `.text`:**
Decode every instruction. For each `lea reg, [rip+X]` where X lands in `.rodata`,
push `(fn_start, X)` into a 6-instruction sliding window. When a subsequent `mov reg,
imm` is seen (imm in [2,100]), try to read `imm` bytes at each recent LEA address and
validate as an identifier with pre/post boundary checks (the byte before and after must
not be an ident character). If it passes, record it for that function.

**Tiering** (per recovered function):
- `user` — if the host function is in the `certain` or `inferred` bucket
- `std` — if the struct name matches a hard-coded std/core/alloc type list
- `non-std` — everything else

## Results — 13-binary sweep

| Binary     | Total | User | Non-std | User structs (name, host fn) |
|------------|-------|------|---------|------------------------------|
| bat        |   6   |   1  |    5    | Creative (0x35cab0) |
| dust       |   2   |   0  |    2    | — |
| fd         |   6   |   0  |    6    | — |
| grex       |   2   |   0  |    2    | — |
| hexyl      |   0   |   0  |    0    | — |
| hyperfine  |   4   |   2  |    2    | Execute (0x62e90), The (0x55eb0) |
| just       |   4   |   0  |    4    | — |
| pastel     |   1   |   0  |    1    | — |
| ripgrep    |   4   |   0  |    4    | — |
| sd         |   1   |   0  |    1    | — |
| tokei      |   1   |   0  |    1    | — |
| xsv        |   2   |   0  |    2    | — |
| zoxide     |   0   |   0  |    0    | — |
| **total**  |  33   |   3  |   30    | |

## Quality assessment (user-tier)

**hyperfine `Execute` (0x62e90):** DWARF confirms this is a TP function from
`src/cli.rs`. However "Execute" as a recovered struct name is unverifiable — it is
plausible (hyperfine's CLI may have a struct named ExecuteOpts or similar) but the
fields `auto, sortweek` make no sense for any real struct. These are incidental
identifier-shaped strings from documentation or other rodata contents co-located with
the actual Debug output.

**hyperfine `The` (0x55eb0):** DWARF confirms this function is NOT user code — it
is absent from every DWARF-user bucket (certain, inferred, indeterminate, library),
meaning it is a dep/std function that fell into `inferred`. "The" is an English article,
not a struct name. Clear FP at both function and type level.

**bat `Creative` (0x35cab0):** DWARF validation was not run for bat in this sweep.
"Creative" with fields `called, metadata` is almost certainly an artifact of "Creative
Commons" appearing in bat's licence or theme strings; the field names `called` and
`metadata` are too generic to be meaningful.

**Non-std noise examples:**
- `AZaz10` (dust, fd, just, sd) — the regex crate's internal byte-range class
  representation; not a struct name at all.
- `BCFPfx` (hyperfine) — regex automata prefix table artifact.
- `Could` (bat) — English word, not a struct name.
- `Completely`, `Converts`, `Erin`, `VSCodium` — all dictionary words or proper nouns
  from rodata strings (theme names, license text, etc.) mis-identified as struct names.
- `Alias` (bat) with fields `autoData, commandDetermine, diff, ...` — this is clap's
  internal command reflection data, not a user struct. Field names are clap-generated
  option names in camelCase.

## Why the approach fails

1. **LEA+MOV pairs are not exclusive to `fmt` functions.** Any code that loads a
   string pointer followed by a length (error messages, log strings, match arms, doc
   strings, enum-variant displays) generates the same pattern. The sliding-window
   pairing cannot distinguish `debug_struct("MyStruct")` from `write!(f, "The {}",
   value)` or `eprintln!("Could not …")`.

2. **The boundary check is necessary but not sufficient.** It prevents accepting
   substrings of longer identifiers, but a perfectly-bounded 7-byte string "Execute"
   in `.rodata` can be the word from an error message and still get attributed to a
   Debug fmt function that happens to reference nearby bytes.

3. **fmt functions are almost never `certain` or `inferred`.** They implement the
   `Debug` or `Display` traits and don't panic. The call graph from panic sites rarely
   reaches a fmt method. Of 33 total recoveries, only 3 are user-tier — and all 3
   are FPs at the type-name level (even if the host function is a TP by DWARF for
   `Execute`).

4. **Serde/clap `.data.rel.ro` slots add dep noise, not user signal.** The dro scan
   (Phase A) finds serde field-name arrays and clap option-name tables from dep crates.
   These are well-formed identifiers in `.data.rel.ro` but belong to dep code.

## Verdict

The type-recovery scanner does not produce actionable signal. Across 13 real-world
binaries:
- 11/13 binaries yield zero user-tier structs.
- The 3 user-tier recoveries are false positives at the type-name level.
- The 30 non-std recoveries are noise (regex internals, dep crate strings, English words).

The fundamental limit is the same as for bare anchors (see `ANCHOR_HEADROOM.md`): the
functions that carry self-referential user type information (`fmt` implementations) are
not reachable from user panic sites and thus not in `certain`/`inferred`. The missing
backward-reachability problem cannot be solved by scanning more string patterns.

**No classifier change warranted.** The `--types` flag ships as an experimental
diagnostic; its output should be treated as low-confidence hints only.

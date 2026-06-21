# turbo.1 — performance branch

Highly experimental. Do not merge into `main` without extended validation.

## Measured speedup

| Binary | Size | `main` | `turbo.1` | Speedup |
|---|---|---|---|---|
| rust-analyzer (stable) | 44 MB | 1.76 s | 0.19 s | **9.3×** |
| warp-svc | 62 MB | 0.86 s | 0.25 s | **3.4×** |

Output is bit-for-bit identical to `main` across all tested binaries.

The speedup scales with the number of panic `Location` structs in the binary.
Binaries with more locations (more panic/assert sites) see larger gains because
the hot-path bottleneck was a linear scan over all location ranges on every
RIP-relative instruction.

---

## What changed

### 1. Binary-search location table (`src/xref.rs`)

**Before:** Three `Vec<(u64, u64)>` ranges (`all_loc_ranges`, `user_loc_ranges`,
`dep_loc_ranges`), each scanned linearly for every RIP-relative memory operand.
Cost: O(n_locations) per operand — for a binary with 300 locations, that is 300
comparisons per instruction per operand; for 3 000 locations, 3 000.

**After:** A single `Vec<LocEntry>` sorted by `struct_vaddr`.  A `partition_point`
binary search (`O(log n)`) returns `(LocKind, struct_start)` in one call,
replacing the three separate scans and two `location_struct_start` calls.

For 300 locations: ~33× fewer comparisons per operand.
For 3 000 locations: ~250× fewer.

### 2. Per-function decoding (`src/xref.rs`)

**Before:** A single `iced_x86::Decoder` consumes all of `.text` as a flat byte
stream.  For every decoded instruction, `frame::find_function` performs a BTreeMap
range query (`O(log n_fns)`, ~11 comparisons for 1 500 functions) to find the
containing function.

**After:** The sorted FDE list is iterated directly.  A separate `Decoder` is
created for each function's exact byte slice with the function's start address as
the initial IP.  `fn_start` is known from the loop variable — zero BTreeMap
lookups in the hot path.

Side effect: non-function bytes (padding, PLT stubs, alignment fills) between
functions are never decoded, saving ~5–20% of instruction decode work.

### 3. Early RIP-relative filter (`src/xref.rs`)

**Before:** Inner loop over all operands (`for op_idx in 0..op_count`), calling
`effective_address` (which internally checks `memory_base() == RIP`) for each.

**After:** Single check `instr.memory_base() == Register::RIP` before any operand
loop.  In x86-64 at most one operand can be RIP-relative per instruction, and
`memory_base()` returns `Register::None` for non-memory instructions, making
this a free early exit for the majority of instructions.

### 4. Parallel classify + parse\_eh\_frame (`src/main.rs`)

**Before:** `strings::classify` ran sequentially, then `frame::parse_eh_frame`.

**After:** `rayon::join` runs them concurrently on separate threads.  Both
functions only require a shared `&ParsedElf` (`Sync`).  For large binaries where
`.eh_frame` parsing takes 20–50 ms, this hides that cost behind the string
classification pass.

New dependency: `rayon = "1"`.

---

## What was NOT changed

- Attribution algorithm (`src/classify.rs`) — identical BFS logic.
- ELF loading (`src/elf.rs`) — still `fs::read` + owned section Vecs.
- String classification (`src/strings.rs`) — identical path rules.
- Location reconstruction (`src/locate.rs`) — identical struct parsing.
- All diagnostic env-var outputs (`UNHUSK_DUMP_ATTRS`, `UNHUSK_DUMP_ALL_FNS`,
  `UNHUSK_DUMP_EDGES`) — same data, same format.
- All 32 tests pass without modification.

---

## Known limitations of this branch

- Only benchmarked on two large binaries. Correctness on all real-world targets
  is assumed (identical algorithm) but not exhaustively re-validated.
- `rayon` thread pool adds ~1–2 ms startup overhead on first run; negligible for
  binaries that take > 100 ms to analyse.
- `memmap2` (zero-copy ELF loading) was considered but not implemented; the
  `Section::data: Vec<u8>` ownership model would require pervasive lifetime changes.

# PE Spike — raw evidence for the §3 Location-layout unknown

**Status:** evidence only. This document records what the probe binary *shows*.
It deliberately does **not** contain `enumerate_locations` / `parse_location_struct`
or any extraction code — that is written after we read this together (design §3:
"STOP at evidence").

Companion to `docs/pe-port-design.md`. Answers the four §3 spike questions with
raw bytes + a reading of each. The decision-tree outcome is at the bottom.

---

## 0. Toolchain gate — msvc IS buildable in this environment

The gate (design §4) is **passed**, and the artifact is genuinely msvc, not a
gnu fallback. How it was produced here (Linux, no Visual Studio):

- `x86_64-pc-windows-msvc` std target installs from static.rust-lang.org.
- `lld-link` is present at `/usr/bin/lld-link` (an MSVC-flavored linker).
- No Windows SDK / CRT import libraries exist on the box, but egress to
  Microsoft's CDN works (`aka.ms/vs/17/release/channel` → a real 91 KB VS
  manifest) and to crates.io, so `cargo-xwin` fetches the CRT + SDK import
  libs and drives `lld-link`.

Build command actually used:

```bash
cargo install cargo-xwin           # one-time
XWIN_ACCEPT_LICENSE=1 cargo xwin build --release \
    --target x86_64-pc-windows-msvc
```

**Gate verification (the check that decides the spike is even valid):**

```
$ file pespike.exe
pespike.exe: PE32+ executable (console) x86-64, for MS Windows

$ objdump -h pespike.exe          # sections
  .text  .rdata  .data  .pdata  .00cfg  .tls  .reloc
```

`.eh_frame` is **ABSENT**; `.pdata` is **present**. That is the msvc/SEH
signature — a gnu build would show `.eh_frame` and no `.pdata`. We are looking
at the right world. **ImageBase = `0x140000000`.**

Section map used throughout this doc (from `objdump -h`):

| Section | file offset | RVA      | VMA (base+RVA) |
|---------|-------------|----------|----------------|
| `.text` | `0x00400`   | `0x1000` | `0x140001000`  |
| `.rdata`| `0x16600`   | `0x18000`| `0x140018000`  |
| `.pdata`| `0x1e400`   | `0x21000`| `0x140021000`  |
| `.reloc`| `0x1f800`   | `0x24000`| `0x140024000`  |

### The probe

`src/main.rs`, three **distinct** user panic sites, release:

```rust
#[inline(never)] fn site_bounds(v: &[u32], i: usize) -> u32 { v[i] }              // L6:  bounds index
#[inline(never)] fn site_unwrap_option(o: Option<u32>) -> u32 { o.unwrap() }      // L11: Option::unwrap
#[inline(never)] fn site_parse_unwrap(s: &str) -> u32 { s.parse::<u32>().unwrap() } // L16: parse().unwrap
```

(`black_box` in `main` keeps all three sites live; `#[inline(never)]` keeps them
in distinct functions with distinct `Location`s. Full source in the scratchpad
probe crate.)

---

## Dump 1 — the src path string in `.rdata`

**Separator is `/` (0x2f), NOT `\`.** The user source path is stored with a
forward slash. (The std-library paths in the same binary are stored with mixed
separators — `/rustc/<hash>/library\std\src\...` — but the *user* path, which is
what the classifier keys on, uses `/`.)

Raw bytes at file `0x16630` (RVA `0x18030`, VA `0x140018030`):

```
00016630: 7372 632f 6d61 696e 2e72 73             src/main.rs
          73 72 63 2f 6d 61 69 6e 2e 72 73
           s  r  c  /  m  a  i  n  .  r  s
                    ^^ 0x2f = '/'
```

- **Content:** `src/main.rs`
- **Length:** 11 bytes (no NUL terminator — it is a Rust `&str`, length lives in
  the `Location` struct, see Dump 2)
- **Location:** file `0x16630` / RVA `0x18030` / VA `0x140018030`

Reading: the classifier's `src/` vs `\src\` question (design §3 Q1, §6.3 note) is
answered — for a Linux-hosted cross-compile the user path keeps `/`. **The
existing ELF `src/`-matcher works unchanged on this artifact.** (Caveat worth a
follow-up: a binary built *on Windows* may embed `src\main.rs`; the classifier
should normalize separators before matching so it is host-agnostic. Not resolved
by this spike — only the Linux-host case is observed here.)

---

## Dump 2 — the `Location` struct referencing that string

Three consecutive 24-byte structs sit right after the string, at file
`0x16640`/`0x16658`/`0x16670`. Raw bytes:

```
             |------- file.ptr (8) -----|  |------- file.len (8) -----|
00016640:    30 80 01 40 01 00 00 00       0b 00 00 00 00 00 00 00        <- struct #1 (site_bounds)
             |-- line(4) --| |-- col(4) -|
00016650:    06 00 00 00     05 00 00 00
                                          30 80 01 40 01 00 00 00        <- struct #2 (site_parse_unwrap) ptr
00016660:    0b 00 00 00 00 00 00 00       10 00 00 00 16 00 00 00        <- #2 len / line / col
00016670:    30 80 01 40 01 00 00 00       0b 00 00 00 00 00 00 00        <- struct #3 (site_unwrap_option)
00016680:    0b 00 00 00 07 00 00 00                                      <- #3 line / col
```

Decoded:

| struct | RVA (VA)                 | file.ptr (VA)   | file.len | line       | col       | source site                       |
|--------|--------------------------|-----------------|----------|------------|-----------|-----------------------------------|
| #1     | `0x18040` (`0x140018040`)| `0x140018030`   | `0x0b`=11| `0x06`=6   | `0x05`=5  | `v[i]` at main.rs:6:5             |
| #2     | `0x18058` (`0x140018058`)| `0x140018030`   | `0x0b`=11| `0x10`=16  | `0x16`=22 | `.unwrap()` at main.rs:16:22      |
| #3     | `0x18070` (`0x140018070`)| `0x140018030`   | `0x0b`=11| `0x0b`=11  | `0x07`=7  | `o.unwrap()` at main.rs:11:7      |

Every line/col matches the probe source exactly (col 22 on line 16 is the
`unwrap` after `.parse::<u32>()`; col 5 on line 6 is the `v` of `v[i]`). This is
the strongest possible confirmation that these are real `Location`s and that the
field decode is correct.

**Field order / size / alignment — the load-bearing answer to §3 Q2:**

```
offset  0  [8 bytes]  file.ptr   absolute VA of the path string  (0x140018030)
offset  8  [8 bytes]  file.len   usize length                    (11)
offset 16  [4 bytes]  line       u32
offset 20  [4 bytes]  col        u32
------------------------------------------------------------------
size = 24 bytes, alignment = 8
```

- **`file` IS a `(ptr, len)` fat pointer** — 8-byte data pointer + 8-byte length,
  exactly `&'static str`. The optimizer did **not** reshape it.
- **This layout is byte-for-byte identical to the ELF path** already documented
  in `src/locate.rs` (offset 0 ptr / 8 len / 16 line / 20 col). The struct is
  `core::panic::Location<'static> { file: &str, line: u32, col: u32 }` on both
  formats.
- **One PE-vs-ELF difference in the *encoding* of the pointer field** (not the
  layout): on PE the 8 pointer bytes in the file **already hold the absolute VA**
  (`30 80 01 40 01 00 00 00` = `0x140018030`), preferred-ImageBase-relative; the
  loader only adds the ASLR delta. On ELF (PIE) those bytes are **zero** and the
  value lives in the `R_X86_64_RELATIVE` addend. Consequence for extraction: on
  PE the path pointer can be read straight out of the struct bytes; the reloc
  (Dump 3) is needed only to *identify which slots are pointers*, not to recover
  their value.
- All three structs share the same `file.ptr` (`0x140018030`) because all three
  sites are in the same file — only line/col differ. Enumeration must not assume
  one string per struct.

---

## Dump 3 — `.reloc` has a DIR64 entry on each struct's pointer field (happy path)

`.reloc` (file `0x1f800`) opens with a base-relocation block for page `0x18000`
(the `.rdata` page holding the structs):

```
0001f800: 00 80 01 00   8c 00 00 00   18a0 20a0 28a0 40a0
          |PageRVA   |  |BlockSize |  |--- 2-byte entries ...
0001f810: 58a0 70a0 a8a0 f8a0 ...
```

- **Block header:** PageRVA = `0x00018000`, BlockSize = `0x8c` = 140 bytes →
  `(140 − 8) / 2` = 66 entries.
- **Entry decode:** each entry is little-endian u16; `type = raw >> 12`,
  `offset = raw & 0x0fff`. `18a0` → raw `0xa018` → **type `0xA` = 10 =
  `IMAGE_REL_BASED_DIR64`**, offset `0x018` → target RVA `0x18000 + 0x018 =
  0x18018`.
- The first several entries and their target RVAs:

  | entry | raw    | type      | offset  | target RVA | note                          |
  |-------|--------|-----------|---------|------------|-------------------------------|
  | `18a0`| `0xa018`| DIR64 (10)| `0x018` | `0x18018`  |                               |
  | `20a0`| `0xa020`| DIR64 (10)| `0x020` | `0x18020`  |                               |
  | `28a0`| `0xa028`| DIR64 (10)| `0x028` | `0x18028`  |                               |
  | `40a0`| `0xa040`| DIR64 (10)| `0x040` | **`0x18040`** | **= struct #1 ptr field** |
  | `58a0`| `0xa058`| DIR64 (10)| `0x058` | **`0x18058`** | **= struct #2 ptr field** |
  | `70a0`| `0xa070`| DIR64 (10)| `0x070` | **`0x18070`** | **= struct #3 ptr field** |

**Answer to §3 Q3: YES.** There is a `DIR64` base relocation whose target lands
exactly on each `Location` struct's pointer field (`0x18040`, `0x18058`,
`0x18070` — offset 0 of each 24-byte struct from Dump 2). This is the **happy
path**: enumerate `Location` structs by walking `DIR64` relocs into `.rdata`, the
direct analog of the ELF `R_X86_64_RELATIVE` walk. Type 0 (`ABSOLUTE`) padding
and non-DIR64 types are skipped, exactly as design §6.1 already specifies.

---

## Dump 4 — panic sites reference the struct with a RIP-relative `lea`

Disassembly of the three sites (`objdump -d -M intel`). Each computes its
`Location`'s address with a **RIP-relative `lea`**, then passes it to the panic
handler — no absolute immediate anywhere.

```
site_bounds (the bounds-check failure path):
  140001042: 48 8d 05 f7 6f 01 00   lea rax,[rip+0x16ff7]   # 0x140018040   <- struct #1
  140001049: 4c 89 c1               mov rcx,r8
  14000104c: 49 89 c0               mov r8,rax                                (Location -> arg r8)
  14000104f: e8 0f 5b 01 00         call 0x140016b63                          (panic handler)
  140001054: 0f 0b                  ud2

site_parse_unwrap:
  140001204: 48 8d 05 4d 6e 01 00   lea rax,[rip+0x16e4d]   # 0x140018058   <- struct #2

site_unwrap_option:
  14000129e: 48 8d 0d cb 6d 01 00   lea rcx,[rip+0x16dcb]   # 0x140018070   <- struct #3
```

- **All three are `lea reg, [rip+disp32]`.** Target = `insn_rva + insn_len +
  disp32` (e.g. `0x140001042 + 7 + 0x16ff7 = 0x140018040`), resolving to the
  struct RVAs from Dump 2/3.
- **Answer to §3 Q4: RIP-relative `lea`, not absolute immediate.** The iced-x86
  xref logic in `src/xref.rs` ports directly with the RVA tweak of design §6.2 —
  the same `memory_base() == RIP` / `memory_displacement64()` path the ELF
  scanner already uses.

---

## Decision-tree outcome (design §3)

Every axis lands on the **happy path**:

| §3 question                                   | Observed                                             |
|-----------------------------------------------|------------------------------------------------------|
| Q1 path string present & separator            | Yes; `src/main.rs`, separator `/`                    |
| Q2 struct layout                              | `(ptr,len,line,col)` = 24B, align 8 — same as ELF    |
| Q3 pointer carries a DIR64 reloc              | Yes — DIR64 on each struct's offset-0 pointer field  |
| Q4 site references the struct                 | RIP-relative `lea`                                   |

So the branch is: **"Struct is (ptr,len,line,col), pointer carries `DIR64`, sites
use RIP-`lea`" → the happy path.** §6.1 enumerates structs via `DIR64`→`.rdata`;
§6.2 xref ports with the RVA tweak; §6.3 `parse_location_struct` uses the offsets
in Dump 2. No inverted-path fork, no layout adjustment needed.

**Not built in this session (correctly gated):** `enumerate_locations`,
`parse_location_struct`, `classify_path`. Per design §3 we stop at evidence and
write those together. The PE `BinaryImage::locations()` shipped this session is an
explicit `todo!()` referencing this document.

### One extraction nuance this spike surfaces (for when we write the code)

Because the PE pointer field holds its absolute VA **in-file** (unlike ELF's
zero-slot + addend), the enumerator has two consistent sources for the path
pointer: the `DIR64` reloc target *identifies* the struct, and the 8 bytes at
that target *are* the path VA. The ELF `find_locations` reads the value from the
reloc addend; the PE version reads it from the struct bytes and uses the reloc
only as the "this slot is a pointer" filter. Same enumeration shape, one field
sourced differently. (Recorded here, not implemented.)

# unhusk PE Port — Design

**Status:** design complete; implementation gated on one binary-inspection spike (§3).
**Target triple:** `x86_64-pc-windows-msvc` (see §4 for why, and why this matters before you inspect anything).
**Scope of this doc:** how each ELF phase maps to PE, what is writable now vs. what the spike must resolve, the two non-obvious scope additions (msvc/gnu, PDB oracle), and what explicitly stays out.

This is a design, not the port. It commits real code for the parts that do not depend on unknown rustc emit behavior (Phase 2 bounds, `.reloc` parsing, the container seam) and specifies a precise interface + a stated hypothesis for the one part that does (Phase 1 `Location` extraction from `.rdata`). The hypothesis is written **as a hypothesis to be falsified by the spike**, not as fact. Do the spike first.

---

## 1. What does not change

The conceptual core is format-independent and ports untouched:

- The premise. `rustc` emits `core::panic::Location` at every panic/bounds/`.unwrap()` site on Windows exactly as on Linux — same struct, same source-path/line/col payload. The seam exists on PE. This is not an assumption about layout (that's §3); it's the fact that the metadata is emitted at all, which is a property of the panic machinery, not the object format.
- The classification rule. `src/*.rs` = User, `/rustc/...` = Standard Library, cargo-registry path = Dependency. Path strings, once recovered, classify identically.
- The multiplicity heuristic. Rank functions by count of distinct in-range user `Location`s; STRONG = ≥2 (`--min-anchors`, default 2). Unchanged.
- **Phase 3 (winnow) is entirely format-agnostic and comes free.** It consumes the attributed function set — masked code atom from one function, behavioral string from a disjoint function, two-factor rule. It never touches the object container. Once Phase 1+2 produce attributions on PE, winnow runs as-is with zero changes.

The port is three plumbing layers in Phase 1+2. One gets *easier* than ELF, one is a mechanical reformat, one is the spike.

---

## 2. What the port actually is (map)

| Concern | ELF (current) | PE (this port) | Difficulty |
|---|---|---|---|
| Container parse | `object` ELF | `object` `PeFile64` | trivial (crate does it) |
| Absolute pointers / relocs | `R_X86_64_RELATIVE` in `.rela.dyn` | `IMAGE_REL_BASED_DIR64` in `.reloc` | mechanical reformat (§6.1) |
| `Location` structs + path strings | `.data.rel.ro` → `.rodata` | `.rdata` (merged) | **spike-gated (§3)** |
| Function bounds | `.eh_frame` FDE walk via `gimli` | `.pdata` RUNTIME_FUNCTION | **easier** than ELF (§5) |
| Panic-site → function xref | `iced-x86` scan of `[start,end)` | same, RVA-based targets (§6.2) | mostly ports; one spike dependency |
| Address model | file offsets / vaddrs | RVAs everywhere (§7) | cross-cutting gotcha |
| Validation oracle | DWARF `decl_file` + `nm`/rustfilt | **PDB reader** (§9) | **new plumbing** |

---

## 3. The one unknown, and the spike that closes it

**Everything uncertain about this port lives here. Do this before writing any Phase 1 code.**

On ELF your pipeline is clean because `RELATIVE` relocs point at `Location` structs in `.data.rel.ro`, and you resolve the file path from the `&str` inside. On PE the analog lands in `.rdata`, but the exact shape — how the `Location` struct is laid out, whether its `&str` data pointer is a full 64-bit pointer carrying a `DIR64` base reloc, and how panic *sites* reference the struct — is emit-dependent and must be observed, not assumed.

### The spike (≈1 hour)

```bash
# 1. A minimal program with a handful of DISTINCT user panic sites.
cat > src/main.rs <<'EOF'
fn a(x: &[u8]) -> u8 { x[3] }              // bounds panic, one site
fn b(v: Option<u32>) -> u32 { v.unwrap() } // unwrap panic, another site
fn main() {
    let _ = a(&[1,2,3,4]);
    let _ = b(Some(9));
    println!("{}", "x".parse::<i32>().unwrap()); // a third
}
EOF

# 2. Build for the REAL target (see §4). Release, so it matches malware.
rustc --target x86_64-pc-windows-msvc -O -o probe.exe src/main.rs
#   (or: cargo build --release --target x86_64-pc-windows-msvc)

# 3. Confirm the triple you actually got:
#    file probe.exe   — must say PE32+ / x86-64, NOT ELF, NOT windows-gnu artifacts
```

### What to look at, and with what

Inspect `probe.exe` — you want to answer four concrete questions. Any PE-aware tool works (`objdump -h`/`-s`, LIEF, `pefile`, or `object` in a throwaway Rust bin; a hex view of `.rdata` alongside the reloc table):

1. **Path strings.** Grep `.rdata` for `src\main.rs` (note: Windows path separator may be `\`, or rustc may keep `/` — *look*, don't assume; the classifier's `src/` vs `\src\` matcher depends on the answer). Confirm the source path bytes are present and locate them.
2. **`Location` struct layout.** Find the struct that references that string. Expected fields for `Location<'a> { file: &str, line: u32, col: u32 }`: a data pointer (8B) + length (8B) + line (4B) + col (4B) = 24B, likely 8-aligned. **Verify the real order, size, and whether `&str` is (ptr,len) or something the optimizer reshaped.**
3. **Is the string pointer relocated?** Check the `.reloc` table for a `DIR64` entry whose target offset lands on the struct's data-pointer field. This is the load-bearing question: if yes, you enumerate `Location` structs by walking `DIR64` relocs into `.rdata` (direct analog of walking `RELATIVE`). If the pointer is encoded differently, the enumeration strategy changes — record exactly how.
4. **How panic sites reference the struct.** Disassemble `a`/`b`. Expected: a `lea reg, [rip+disp]` computing the struct's address before the panic call (same as PIE ELF). Confirm it's RIP-relative `lea` (→ iced-x86 xref ports directly, §6.2) vs. an absolute immediate (→ different scan target computation).

### Decision tree out of the spike

- **Struct is (ptr,len,line,col), pointer carries `DIR64`, sites use RIP-`lea`** → the happy path. §6.1 enumerates structs via `DIR64`→`.rdata`; §6.2 xref ports with an RVA tweak; write it as designed.
- **Struct layout differs** → adjust the field offsets in `parse_location_struct` (§6.3); everything else holds.
- **Pointer not individually relocated** (e.g. structs reached only via code references, not a reloc into `.rdata`) → invert Phase 1: discover structs *from* the xref scan (find `lea`-into-`.rdata` targets, then parse as `Location`) instead of reloc-first. This is a real fork; the spike tells you which world you're in.

Until the spike is run, `parse_location_struct` and `enumerate_locations` below are **hypotheses**. Do not ship them unverified.

---

## 4. Why msvc, and why the target matters before you inspect

Rust has two Windows x64 targets and they are structurally different binaries:

- `x86_64-pc-windows-gnu` — MinGW-flavored, keeps `.eh_frame` (DWARF-style CFI). Your ELF Phase 2 would port almost verbatim. **But almost no real-world Windows malware ships gnu.**
- `x86_64-pc-windows-msvc` — native PE/SEH. No `.eh_frame`; unwind info is in `.pdata`/`.xdata`. Debug info is PDB, not DWARF. **This is what real samples are.**

Consequence: **target msvc.** And beware the inspection trap — if you cross-compile on Linux with a default/gnu toolchain you may silently produce a gnu artifact and inspect the wrong world (you'd see `.eh_frame`, conclude Phase 2 is trivial, and build against a format real malware doesn't use). Step 3 of the spike (`file` + section check) exists to catch this. Confirm PE32+ and the absence of `.eh_frame` before trusting anything you see.

---

## 5. Phase 2 — function bounds (writable now, easier than ELF)

The pleasant surprise. You currently decode variable-length CFI instructions from `.eh_frame` FDEs via `gimli` to recover ranges. msvc-PE hands you ranges directly: `.pdata` is a sorted array of fixed 12-byte `RUNTIME_FUNCTION` structs.

```rust
/// x64 .pdata entry. Sorted by begin_rva. All fields are RVAs.
#[repr(C)]
#[derive(Clone, Copy, Debug)]
struct RuntimeFunction {
    begin_rva: u32,
    end_rva: u32,
    unwind_info_rva: u32,
}

/// Read [start,end) RVA ranges for every function with unwind info.
/// (object API surface drifts between versions — verify method names
///  against your pinned object version; the byte layout below is stable.)
fn function_ranges(pe: &object::read::pe::PeFile64) -> Vec<Range<u32>> {
    let sec = pe.section_by_name(".pdata")
        .expect("no .pdata — is this a gnu target or a leaf-only stub?");
    let data = sec.data().expect(".pdata unreadable");

    data.chunks_exact(12)
        .map(|c| RuntimeFunction {
            begin_rva:       u32::from_le_bytes(c[0..4].try_into().unwrap()),
            end_rva:         u32::from_le_bytes(c[4..8].try_into().unwrap()),
            unwind_info_rva: u32::from_le_bytes(c[8..12].try_into().unwrap()),
        })
        .map(|rf| rf.begin_rva..rf.end_rva)
        .collect()
}
```

### Coverage caveat — and why it doesn't bite us

`.pdata` only contains functions with unwind info. Leaf functions that allocate no stack and call nothing may be omitted. **But** the x64 ABI requires unwind data for every function that makes a call, and a function containing a panic `Location` reference makes a call (to the panic machinery). So **every function we attribute over is non-leaf, hence guaranteed present in `.pdata` by construction.** Coverage is complete for the subset that matters. The omitted leaves are exactly the functions with no panic sites — irrelevant to attribution. This is a *stronger* guarantee than the "coverage is high" hand-wave; it's "coverage is total over the attributable set."

Net: this layer is *less* code than the gimli FDE walk, with a cleaner correctness argument.

---

## 6. Phase 1 — relocations, Location structs, xref

### 6.1 `.reloc` parsing (writable now)

Direct reformat of your `.rela.dyn` walk. `.reloc` is a sequence of base-relocation *blocks*: an 8-byte header (page RVA + block size) followed by 2-byte entries; top 4 bits = type, low 12 bits = offset within the page. You want `IMAGE_REL_BASED_DIR64` (10); skip `ABSOLUTE` (0, padding).

```rust
const IMAGE_REL_BASED_ABSOLUTE: u8 = 0;
const IMAGE_REL_BASED_DIR64: u8 = 10;

/// All RVAs that carry a DIR64 base relocation (i.e. hold an absolute
/// 64-bit pointer). These are the candidate sites of Location-struct
/// data pointers (pending spike confirmation, §3).
fn dir64_reloc_rvas(pe: &object::read::pe::PeFile64) -> Vec<u32> {
    let sec = match pe.section_by_name(".reloc") {
        Some(s) => s,
        None => return Vec::new(), // stripped/relocs-removed → fail closed upstream
    };
    let data = sec.data().expect(".reloc unreadable");
    let mut out = Vec::new();
    let mut off = 0usize;

    while off + 8 <= data.len() {
        let page_rva  = u32::from_le_bytes(data[off..off+4].try_into().unwrap());
        let block_sz  = u32::from_le_bytes(data[off+4..off+8].try_into().unwrap()) as usize;
        if block_sz < 8 || off + block_sz > data.len() { break; }

        let entries = &data[off+8 .. off+block_sz];
        for e in entries.chunks_exact(2) {
            let raw = u16::from_le_bytes([e[0], e[1]]);
            let typ = (raw >> 12) as u8;
            let ofs = (raw & 0x0FFF) as u32;
            match typ {
                IMAGE_REL_BASED_DIR64 => out.push(page_rva + ofs),
                IMAGE_REL_BASED_ABSOLUTE => {}      // padding
                _ => {}                             // other types irrelevant here
            }
        }
        off += block_sz;
    }
    out
}
```

### 6.2 Panic-site → function xref (mostly ports)

iced-x86 decodes the same x86-64. Your scan of `[start,end)` for instructions referencing a `Location` address ports directly, with one change: on PE you work in RVAs, and the reference is (per spike hypothesis) a RIP-relative `lea` whose target you compute as `instruction_rva + insn_len + disp32`, then match against the enumerated struct RVAs. If the spike shows absolute-immediate references instead of RIP-`lea`, the target computation changes here — this is the one spike dependency in Phase 2's xref logic.

### 6.3 `Location` struct enumeration + parse (SPIKE-GATED — hypothesis)

> **Do not ship until §3 confirms layout and reloc behavior.** Written as the expected shape for the happy-path branch of the decision tree.

```rust
/// HYPOTHESIS (verify via spike §3):
///   Location<'a> { file: &'a str /* (ptr:u64, len:u64) */, line:u32, col:u32 }
///   24 bytes, 8-aligned, file.ptr carries a DIR64 reloc.
#[derive(Debug)]
struct RawLocation {
    file_ptr_rva: u32, // where file.ptr points, as an RVA (post-reloc, image-based)
    file_len: u64,
    line: u32,
    col: u32,
}

/// Happy-path enumeration: each DIR64 reloc into .rdata whose target parses
/// as a plausible Location is a candidate. Reloc-first, mirroring the ELF
/// RELATIVE walk. (Alt branch if pointer isn't relocated: discover from xref
/// targets instead — see §3 decision tree.)
fn enumerate_locations(
    pe: &object::read::pe::PeFile64,
    dir64_rvas: &[u32],
) -> Vec<RawLocation> {
    // For each dir64 rva that lands inside .rdata, read 24B, sanity-check
    // (len small, line/col nonzero and plausible, file_ptr resolves into a
    //  string section), and keep. Reject anything failing the shape check —
    // fail closed, exactly like the ELF path rejects malformed structs.
    todo!("fill offsets/section bounds from spike result")
}

/// Resolve the path string an RVA points at, then classify.
/// NOTE: separator may be '\\' — spike question 1 decides whether the
/// classifier matches `src/` or `src\\` (or normalize before matching).
fn classify_path(bytes: &[u8]) -> Origin { /* User | Std | Dependency */ todo!() }
```

---

## 7. Cross-cutting: RVA vs file offset

PE addressing is RVAs throughout — `.pdata`, `.reloc`, and the pointer payloads all speak RVA (image-base-relative), not file offsets and not the vaddrs your ELF code may assume. To *read bytes* at an RVA you map RVA → file offset via the section headers (find the section whose `[virtual_addr, virtual_addr+virtual_size)` contains the RVA; file offset = `raw_data_ptr + (rva - virtual_addr)`). `object` exposes this, but confirm you're using the RVA-correct accessor and not conflating with file offsets anywhere the ELF code took shortcuts. This touches every layer; get one small `rva_to_offset` helper right and route all reads through it.

---

## 8. Module layout / the seam

Keep the conceptual core (ranking, STRONG-tier selection) and all of Phase 3 format-blind. Put the container behind a trait; ELF and PE implement only the plumbing.

```
core/                      # unchanged
  location.rs              # RawLocation, Origin, classify_path (separator-aware)
  rank.rs                  # multiplicity heuristic, STRONG selection, --min-anchors
  attribute.rs             # orchestration: enumerate → xref → rank

container/
  mod.rs                   # trait BinaryImage
  elf.rs                   # existing: .rela.dyn / .data.rel.ro / .eh_frame(gimli)
  pe.rs                    # new: .reloc / .rdata / .pdata   (§5,§6)

winnow/                    # UNTOUCHED — consumes core output, format-agnostic
```

```rust
trait BinaryImage {
    /// [start,end) RVA (PE) or vaddr (ELF) ranges of real functions.
    fn function_ranges(&self) -> Vec<Range<u64>>;
    /// All Location structs recovered from read-only data.
    fn locations(&self) -> Vec<RawLocation>;
    /// Decode [start,end) and yield addresses of referenced Location structs.
    fn xref_locations_in(&self, range: Range<u64>) -> Vec<u64>;
    /// Read raw bytes at an address (RVA/vaddr), for winnow's code atom.
    fn bytes_at(&self, addr: u64, len: usize) -> Option<&[u8]>;
}
```

`attribute.rs` and everything downstream depend only on this trait. Adding PE = adding `pe.rs`; the ranking, STRONG selection, and rule generation don't know which format they're on. This is also the seam that keeps the ELF path a regression oracle: PE must produce the *same* attributions on a from-source binary with a debug twin (§9).

---

## 9. Validating the PE port — the sharp edge

Your ELF precision numbers (94.2%/93.5% pooled, the async strata, the whole `--min-anchors` story) were locked against a **DWARF `decl_file`** oracle plus `nm`/rustfilt symbols. **msvc-PE has neither.** Debug info is PDB (CodeView), symbols come from PDB too. So the oracle that certified ELF does not exist on the target you must ship for.

Options, in order of honesty:

1. **PDB oracle (correct, more work).** Read the PDB (Rust `pdb` crate) to get per-address function names and source file/line — the msvc analog of `decl_file` + `nm`. Build from source with `/DEBUG` (or cargo release + split debuginfo) so you have the twin. This is new validation plumbing, parallel to but separate from your DWARF harness. Budget it explicitly; it's not free and it's not the tool code.
2. **Validate on `-gnu`, ship on `-msvc` (tempting, wrong).** gnu keeps DWARF so your existing oracle works — but you'd be certifying a *different binary* than the one attribution runs on in the wild. The bounds source (`.eh_frame` vs `.pdata`), the reloc format, and the emit details all differ. A precision number from gnu does not transfer to msvc. At most this is a smoke test that the phases wired up, never a precision claim.

**Recommendation:** the PDB oracle is the real path, and this is the honest cost of the port that isn't in the "weekend" estimate — the target real malware uses is precisely the one where ground truth is hardest to obtain. Plan for it up front rather than discovering it after the phases work.

**The inline-info trap (do not skip).** PDB inline information is materially weaker than DWARF's. When a user closure is inlined into a library generic — which is *precisely* the mechanism behind the async/framework precision soft spot — the PDB may report only the enclosing library function's range and never surface the inlined user frame, where DWARF's inline records would. Consequence: a PDB oracle can attribute genuinely-user inlined code to library source and score it a miss, **systematically understating async precision as an oracle artifact, not a tool result.** This is the same failure class as the v0-demangler bug that silently dropped async rows — a defect in ground truth masquerading as a defect in the tool, and it would hit exactly the stratum that's already softest. Mitigations: (a) use a `-gnu` DWARF build only to *validate the oracle itself*, never to claim msvc precision; (b) when the PDB lacks inline detail for a function, mark it **undeterminable rather than miss** — the same "don't count what the method can't see" discipline that fixed the rage/legacy-mangling error. Validate the oracle before trusting any async number it prints.

---

## 10. Fail-closed boundaries on PE

Same principle as ELF, new triggers:

- No `.reloc` / relocations stripped → can't enumerate structs → emit nothing.
- `--remap-path-prefix` / `-Zlocation-detail=none` → paths gone or absent → same refusal as ELF.
- **Packed sample** (the common Windows case) → sections are compressed/obfuscated; `.rdata`/`.pdata` aren't meaningful until unpacked → attribution yields nothing, tool refuses. Unpacking is a **separate project**, explicitly out of scope for this port (§11). The fail-closed boundary already covers it: no unpack → no rule, by design, not by bug.

---

## 11. Explicitly out of scope

- **Cross-variant detection on PE.** Do **not** run the author-edit variant experiment on PE variant pairs until the rule-language question is settled (the D16/D19 matrix: string-alone survival vs. *real*-operand-masked survival). Today `reduce_atom` never wildcards and the AND-everywhere structure can't fire on changed code, so a cross-variant run would be null-by-construction and uninterpretable — the offset-209 non-result again, just on PE. The port unlocks the *input* (real variant pairs); it does nothing about the *output* blocker, which is upstream. Fix the rule language first, then the PE inputs are worth pointing at it.
- **Unpacking.** Real Windows malware is heavily packed; that's a distinct research effort, not part of the port. Until then the PE demo runs on unpacked / self-built samples.
- **Arsenal.** None of this is on the July 19 path — Arsenal is submitted and correctly lists PE as in-progress. This is the BAR Seoul (mid-January) track.

---

## 12. Effort, honestly

- Phase 2 bounds (`.pdata`): **hours.** Less code than the FDE walk, complete coverage over the attributable set.
- `.reloc` parsing: **~a day.** Mechanical reformat of a walk you've written.
- Container seam (`BinaryImage` trait + wiring ELF behind it): **~a day**, and it pays for itself by making ELF a regression oracle.
- **The `.rdata` `Location` spike + extraction:** an **afternoon to a few days**, entirely dependent on what the spike shows — and uncompressible without running it. This is the whole variance in the estimate.
- **PDB validation oracle (§9):** separate, non-trivial, **not** in the "weekend" — budget it as its own line item.

So: the known plumbing is a solid weekend; the spike is the variance; the PDB oracle is the hidden cost. The port is not *hard* — you own the entire conceptual stack. It has exactly one unknown and one under-budgeted dependency, and both are named above. Run the spike (§3) first; it turns half this document from hypothesis into code.

---

## 13. MSVC linker & hardening features — review triage

A review raised four MSVC-specific concerns. Triaged against the actual input domain — stripped **release** Rust binaries from default `cargo build --release`, malware author settings. Severity corrected where the review's mechanism was wrong. None changes the design; the entries are verifications to run, not rework.

| Feature | Review claim | Actual severity | Reasoning |
|---|---|---|---|
| **ICF** (`/OPT:ICF`) | Destroys function boundaries and multiplicity; demotes STRONG | **Low, bounded — check, don't fear** | On by default in release, real. But it operates at *whole-function* granularity — it cannot remove individual anchors from inside a function, so it cannot reduce a function's multiplicity. And it folds only bitwise-identical functions *including their relocation targets*; a user function references ≥1 `src/` Location a library function does not, so **ICF cannot fold across the user/library boundary** — the references that would have to match are what encode authorship. The partition unhusk computes is ICF-invariant. Net effect: fewer *physical* functions (folded monomorphizations), multiplicity-per-survivor preserved. Add a one-line function-count sanity check; no redesign. |
| **32-bit relative Location pointer** (no `.reloc`) | Happy path dead on arrival; build the `.text`-scan fallback first | **Already designed for; do NOT pre-build** | Exactly the §3 spike question and the §6.3 alt branch. `Location.file` is `&'static str` — a type-fixed fat pointer whose data field is a real 64-bit pointer needing a `DIR64` reloc under ASLR; the layout argues *for* the happy path. Building the slower, FP-prone full-`.text` fallback *first* optimizes for the unlikely branch at real cost and inverts measure-first. Run the 1-hour spike; it is cheaper than building the wrong path. Fallback is fully spec'd (§3/§6.3), so no exposure if the spike says otherwise. |
| **CFG** (`__guard_check_icall_fptr`) | Heavily used; unmasked thunks kill variant recall | **Low — off by default** | rustc's `-C control-flow-guard` is opt-in; default builds don't emit it and malware won't add defensive hardening. "Windows binaries heavily use CFG" holds for Microsoft-*shipped* binaries, not default-built Rust. If a real sample carries CFG, the guard-pointer load is RIP-relative and already displacement-masked, and a `call reg` thunk is stable bytes. Add explicit guard-thunk masking only when a sample actually shows CFG. |
| **ILT** (incremental-link thunks) / `/GS` | `call` targets are jump tables; code atoms useless | **N/A** | Incremental linking is a debug feature, **mutually exclusive with `/OPT:ICF`**, disabled in release. Input domain is stripped release binaries → no ILT. `/GS` stack-cookie instrumentation (`__security_check_cookie`) does not apply to Rust functions the way it does to MSVC C++ → marginal. |

One real strengthening (PDB inlining, §9), one already in the design (32-bit pointer — the spike resolves it; don't pre-build the fallback), two overstated (CFG off-by-default, ILT release-disabled).

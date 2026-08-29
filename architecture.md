# unhusk — System Specification

**Status:** normative for the shipped ELF path. Describes `unhusk` as built, not
as intended. Every behavioural claim cites the code that implements it
(`file:line`); every quantitative claim cites the measurement that produced it
and the corpus it was measured on. Claims without one of those two anchors do
not belong in this document.

**Working notes:** paths under `docs/local/` are unpublished measurement
writeups kept out of the repository; they are cited here for provenance, not
as links a reader can follow.

**Verification basis:** `cargo test` — 103 passing (96 unit + 7 integration),
0 failing, 0 ignored. Source tree: 7,342 lines across 18 files.

---

## 1. Scope

### 1.1 Problem statement

`unhusk` answers one question about an x86-64 **stripped Rust release binary**:
*which functions did the author of the target program write*, as opposed to the
Rust standard library or a Cargo dependency.

It answers without symbols and without debug information, by reading
`core::panic::Location` structs — the file/line/column metadata `rustc` embeds
at every reachable `panic!` / `.unwrap()` / bounds-check site so a crash can
print `panicked at src/main.rs:42`. That metadata is *data*, not symbols, so it
survives `strip`.

### 1.2 In scope

- Recovering source-path strings and `Location` structs from read-only data.
- Classifying each recovered path as user / std / dependency.
- Mapping `Location` references to the functions that reference them.
- Assigning a confidence tier to each user-attributed function.
- Emitting that set over a stable machine-readable contract (§6.2).

### 1.3 Out of scope

The following are **not goals** and are not implemented:

- Recall completeness. Functions containing no reachable panic site are
  structurally invisible (§9.1). Recall is partial by design.
- Symbol or type recovery as a product surface. A `--types` diagnostic
  (`#[derive(Debug)]` struct-name recovery) was built, measured ineffective
  on a 13-binary sweep, and removed (§10.3).
- Unpacking, deobfuscation, or emulation. Packed input is detected and
  reported (`src/elf.rs:143-149`), never unpacked.
- Any dynamic analysis. `unhusk` never executes the target.

### 1.4 Supported input — normative

- The CLI **accepts x86-64 ELF and x86-64 PE**, auto-detected by magic bytes
  (`src/main.rs`'s `is_pe` sniff routes to `pe_pipeline::run`; ELF falls
  through to the pre-existing `elf::ParsedElf::load` path unconditionally).
  PE is STRONG/SINGLE tier only — no Inferred/Indeterminate — and every PE
  run prints an experimental-support disclosure banner (§10.2, updated).
  `src/elf.rs:96-99` hard-fails any non-x86-64 ELF architecture; PE is
  PE32+ (`PeFile64`) only, PE32 (32-bit) is rejected the same way.
- Mach-O, aarch64, and 32-bit x86 (both formats) are unimplemented.

---

## 2. Threat model and trust boundaries

`unhusk` is a static analyzer whose intended input is **malware**. The input
file is adversarial in full; nothing derived from it is trusted.

| Boundary | Trusted? | Enforcement |
|---|---|---|
| Target binary bytes | **No** | `object` crate parsing; every read bounds-checked (`Section::read_u64_le`, `slice_at`) |
| Section headers | **No** | May be absent or lying; program-header fallback at `src/elf.rs:126-137` |
| Embedded source-path strings | **No** | Only checks are "valid UTF-8" and "ends in `.rs`" (`src/strings.rs:95-100`) |
| `Location` field values | **No** | Cross-validated against known string length (`src/locate.rs:62-64`); `line` range-checked (`src/locate.rs:76`) |
| Path→origin classification | Derived | Prefix rules only (`src/strings.rs:221-340`); an attacker controls these strings |
| Unstripped companion (`--validate`) | Operator-supplied | Separate file, separate load; validation-only |

**Consequence, normative:** source-path strings are attacker-controlled data.
They may contain quotes, backslashes, newlines, or control bytes.
Serialization to the JSON contract **MUST** go through `serde` and **MUST NOT**
use hand-rolled quoting (`src/report.rs:262-269`). This is stated in the code
as a standing requirement, not an incidental implementation choice.

**Non-goal of this boundary:** `unhusk` does not attempt to detect a binary
that has been *deliberately salted* with fake user-looking paths. A crafted
sample can inflate the user set. Nothing in the pipeline defends against this.

---

## 3. Data model

### 3.1 `core::panic::Location` — 24 bytes, x86-64

Layout, verified empirically and relied upon by both container implementations
(`src/locate.rs:3-8`, `src/container/pe.rs:174-177`):

```
offset  0  [8]  file ptr   — PIE relocation slot (zero on disk)
offset  8  [8]  file len   — u64, stored directly
offset 16  [4]  line       — u32
offset 20  [4]  col        — u32
```

The 24-byte size is normative across the codebase: the xref containment probe
tests `addr < entry.start + 24` on both the ELF side (`src/xref.rs:82`) and the
PE side (`src/container/pe.rs:332`).

### 3.2 `Origin` — shipped path classification

`src/strings.rs:20-29`. Four variants: `User`, `Std`, `Dep { crate_name,
version }`, `Unknown`. This is the classification the shipped pipeline acts on.

### 3.3 `PathClass` — origin-classifier composition (library only)

`src/origin.rs:28-36`. Seven variants with **explicit stable discriminants**
(`User=0 … Unknown=6`) because they index a fixed-size array
(`FnProfile::counts`, `src/origin.rs:173`). Reordering the variants for
readability would silently corrupt every profile; the discriminants are load-
bearing.

This is a strictly finer partition than `Origin`, used only by the measurement
path in §10.4.

### 3.4 Attribution buckets

`src/classify.rs:31-36`. Four-way, mutually exclusive, total over the function
map:

| Bucket | Definition | Contract status |
|---|---|---|
| `Certain` | Direct RIP-relative reference to a `User` Location | The only bucket in the output contract |
| `Inferred` | No direct reference; reached from certain via call edges, all known callers user | Diagnostic only |
| `Indeterminate` | Reached from user code **and** from library code | Diagnostic only |
| `Library` | Everything else | Not user-attributed |

`Score::user_total()` counts **`Certain` only** (`src/classify.rs:198-200`).
`Inferred` is excluded deliberately: the code documents ~5% precision against
DWARF ground truth, and `Indeterminate` 0% (`src/classify.rs:8-14`). Both are
retained as labels, not as attributions.

### 3.5 Confidence tiers

`src/report.rs:184-190`. `Certain` functions are partitioned by **multiplicity
of distinct user Locations**:

- `Strong` — `anchor_count >= max(min_anchors, 1)`
- `Single` — exactly 1

The `max(…, 1)` floor at `src/report.rs:224` means `--min-anchors 0` is
normalized to 1; there is no zero-anchor STRONG tier.

---

## 4. Pipeline specification

Four stages, strictly ordered. Stages 1 and 2 are independent given a loaded
image and are executed concurrently via `rayon::join` (`src/main.rs:133-136`).

### 4.0 Stage 0 — image load

`ParsedElf::load`, `src/elf.rs:91-166`.

1. Read the whole file; parse with `object` (`:92-94`).
2. Reject non-x86-64 (`:96-99`).
3. Index every named, readable section (`:105-121`).
4. **Fallback:** if `.text` or `.rodata` is missing, recover regions from
   PT_LOAD/PT_GNU_RELRO/PT_GNU_EH_FRAME/PT_DYNAMIC program headers
   (`:126-137`, implemented `:185-319`). Boundaries are coarser than real
   sections; the degradation is recorded as a warning, not hidden.
5. Parse `R_X86_64_RELATIVE` entries from `.rela.dyn` (`:139`).
6. Emit operator-facing warnings for two evasion-shaped conditions: no readable
   `.text` (likely packed, `:143-149`) and no relocation table (static/non-PIE,
   `:150-156`).

**Invariant:** load never panics on malformed input; every failure path is a
`warning` or a bounded `continue`.

### 4.1 Stage 1 — source attribution

**Discovery** (`strings::rs_path_strings`, `src/strings.rs:69-104`). Walk the
relocation table, not a null-terminated scan. For each entry, require:

- the slot lies in `.data.rel.ro` and the addend lies in `.rodata` (`:79`);
- each pointee address is yielded exactly once (`:82`);
- the fat-pointer length at `slot+8` satisfies `0 < len <= 512` (`:88-91`);
- the bytes are valid UTF-8 (`:95`) and end in `.rs` (`:98`).

Using the fat pointer's own `len` field — rather than a sentinel byte — is what
makes extraction exact on data an attacker controls.

**Classification** (`strings::classify_path`, `src/strings.rs:221-340`).
First-match-wins, in this order:

1. **Separator normalization** (`:230-236`). Backslashes → forward slashes,
   applied *first*. Every subsequent guard keys on `/`. Without this, a
   Windows-built dependency path matches no std/dep guard, falls through to the
   relative-path branch, and is misattributed as user code. Ordering here is
   load-bearing, not cosmetic.
2. **Std**: `/rustc/` (`:240`), `library/` (`:245`), and the pre-2018
   `src/lib{core,alloc,std,…}/` layout (`:252-268`). The third form exists
   because those are *relative* paths that would otherwise reach the User
   branch; it matches `src/libcore/`, never a genuine `src/lib.rs`.
3. **Dep**: toolchain-embedded `/rust/deps/` (`:271`), cargo registry
   `cargo/registry/src/` (`:290`), vendored/remapped `crates.io/` (`:315`).
4. **Root-crate promotion**: a registry or vendored path whose crate name
   appears in `root_crates` is promoted to `User` (`:297-299`, `:321-323`).
   This exists for `cargo install` builds, where the target's own source lives
   in the registry.
5. **User**: any remaining path not starting with `/` (`:335-337`).
6. **Unknown**: everything else (`:339`).

**Root-crate determination** (`src/main.rs:96-129`). Explicit `--crate` always
wins. Otherwise `auto_detect_root` (`src/strings.rs:155-198`) infers it: a
unique registry crate carrying a `/src/main.rs` or `/src/bin/` signal, else a
unique match against the binary filename stem. Ambiguity yields `Fallback`
(no promotion) and, when the binary looks like a registry build with no
relative user paths, a warning that `n_certain` may be 0
(`src/main.rs:112-123`).

**Reconstruction** (`locate::find_locations`, `src/locate.rs:38-99`). For each
relocation whose addend is a known source string:

- read `len` at `slot+8` and require it to equal the known string length
  (`:56-64`) — this cross-check is what rejects coincidental matches;
- read `line` at `+16` and `col` at `+20` (`:66-72`);
- require `1 <= line <= 200_000` (`:76`), rejecting all-zero and absurd values.

Output is sorted by `(origin, file, line, col)` (`:90-96`) — deterministic
ordering, independent of relocation-table order.

### 4.2 Stage 2 — function attribution

**Function ranges** (`frame::parse_eh_frame`, `src/frame.rs:34-79`). Every FDE
in `.eh_frame` yields an exact `[start, end)`. Zero-address and zero-length
FDEs are dropped (`:67-69`). `.eh_frame` survives `strip --strip-all` because
unwinding needs it.

**Instruction scan** (`xref::scan`, `src/xref.rs:91-145`). One
`iced_x86::Decoder` per function over its exact `.text` slice, with the IP
pre-set to `fn_start` (`:190-195`) so RIP-relative effective addresses come out
absolute and must not be IP-adjusted again (`:206-209`). Per instruction:

- **Location hit:** if `memory_base() == RIP` (`:205` — a cheap early-out for
  the overwhelming majority of instructions), resolve the effective address
  against a `struct_vaddr`-sorted table via one `partition_point` binary search
  with 24-byte containment (`:76-87`). A `User` hit marks the function
  `certain` and records the anchor; a `Dep` hit marks it a dep boundary
  (`:216-228`). **All** hits, regardless of class, are recorded in
  `all_loc_hits` (`:212-215`) — this superset is what §10.4 consumes.
- **Call edge:** direct near-branch targets that resolve to a known function
  are recorded (`:237-243`). A target counts as an edge iff it has an FDE;
  this admits the occasional PLT stub carrying its own FDE, accepted knowingly
  rather than filtered (`:234-236`).

**Determinism under parallelism.** Functions are scanned in parallel, but every
collection is keyed by `fn_start` and each function is scanned exactly once, so
thread-local partials merge by **disjoint-key union** — `extend` is exact, not
last-write-wins (`:160-170`). The result does not depend on how `rayon` splits
the work. Anchor lists are then sorted and deduplicated (`:133-136`), because
one function may load the same Location from both arms of a branch.

**Propagation** (`classify::attribute`, `src/classify.rs:65-161`). BFS forward
from the certain set over call edges, with two barriers:

- **Dep boundary** (`:111-113`): a function anchored to a dep Location is
  neither marked nor recursed through, so user attribution cannot leak across
  a dependency.
- **Depth cap** (`:98-100`): `--infer-depth N` stops expansion at N hops.

Reached functions are tentatively `Inferred`, then **downgraded to
`Indeterminate` if any caller lies outside the user set** (`:129-142`). A
function with no recorded callers stays `Inferred` (`:137-141`). Everything
unreached is `Library` (`:145-147`).

**Backward walk** (`classify::backtrace_walk`, `src/classify.rs:224-267`).
Flag-gated, default off. Walks the reverse call graph up to N hops. Results go
to a strictly separate bucket: seeds are never returned (`:236`), and the dep
boundary is honoured identically (`:258-261`).

### 4.3 Stage 3 — tiering and emission

`report::tier_certain` (`src/report.rs:219-237`) assigns tiers by anchor count.
It is deliberately **shared by the human and JSON reporters so the two can
never disagree** (`:217-218`). In `--precision` mode the JSON rows are filtered
to `Strong` only (`src/report.rs:289`).

---

## 5. System invariants

Numbered for reference. Each is enforced at the cited site.

- **I1 — Address-space unity.** Within one image, `function_ranges`,
  `locations().struct_addr`, `xref_locations_in`, and `bytes_at` all speak one
  address space: vaddr on ELF, RVA on PE (`src/container/mod.rs:9-12`).
  Mixing them across images is undefined.
- **I2 — Location size is 24 bytes.** Both containment probes depend on it
  (`src/xref.rs:82`, `src/container/pe.rs:332`).
- **I3 — Length cross-validation.** A `Location` is accepted only if its stored
  `len` equals the length of the string its pointer resolves to
  (`src/locate.rs:62-64`).
- **I4 — Line plausibility.** `1 <= line <= 200_000` (`src/locate.rs:76`).
- **I5 — String bound.** Source-path strings are `0 < len <= 512` bytes and
  valid UTF-8 (`src/strings.rs:88-97`).
- **I6 — Separator normalization precedes all classification**
  (`src/strings.rs:230-236`). Violating the order misattributes every
  Windows-built dependency as user code.
- **I7 — Scan determinism.** Partial merge is a disjoint-key union; output is
  independent of thread scheduling (`src/xref.rs:160-170`).
- **I8 — Anchor sets are deduplicated** before tiering (`src/xref.rs:133-136`),
  so `anchor_count` counts *distinct* Locations.
- **I9 — Dep boundaries block propagation** in both directions
  (`src/classify.rs:111-113`, `:258-261`).
- **I10 — Buckets are total and disjoint** over the function map: every FDE
  gets exactly one attribution (`src/classify.rs:145-157`).
- **I11 — Only `Certain` is user-attributed** (`src/classify.rs:198-200`).
- **I12 — STRONG threshold has a floor of 1** (`src/report.rs:224`).
- **I13 — Tiering is single-sourced** across reporters
  (`src/report.rs:219-237`).
- **I14 — Attacker-controlled strings are serialized only via `serde`**
  (`src/report.rs:262-269`).

---

## 6. Interfaces

### 6.1 CLI surface

`src/main.rs:12-87`. One positional argument (the ELF path) and:

| Flag | Default | Effect |
|---|---|---|
| `--crate NAME[,NAME]` | auto-detect | Promote registry paths for these crates to User |
| `--min-anchors N` | 2 | Distinct user Locations required for STRONG |
| `--precision` | off | Restrict output to STRONG; suppress call-closure buckets |
| `--json` | off | Emit the machine contract; suppress human reports |
| `--validate UNSTRIPPED` | off | DWARF ground-truth precision/recall report |
| `--infer-depth N` | unlimited | Cap inference hops from certain |
| `--backtrace-depth N` | 0 (off) | Reverse-BFS bucket (§10.5) |
| `--show-call-closure` | off | Print full inferred/indeterminate list |

### 6.2 JSON contract — normative

```sh
unhusk <stripped-elf> --precision --json
```

Schema (`src/report.rs:242-260`):

```json
{
  "binary": "<path>",
  "arch": "x86-64",
  "min_anchors": 2,
  "functions": [
    {"start": "0xd25af", "end": "0xd38a5", "size": 4854,
     "tier": "strong", "anchor_count": 6,
     "anchor_files": ["akiranew/src/path_finder.rs"]}
  ]
}
```

Normative properties:

- `start` and `end` are **hex strings, not numbers** — JSON numbers are f64 and
  a 64-bit address does not round-trip through one (`src/report.rs:244-246`).
- `min_anchors` is echoed post-floor (`max(N,1)`, `src/report.rs:308`).
- Rows are sorted by `start` (`src/report.rs:287`).
- `tier` is `"strong"` or `"single"`. Under `--precision`, `"single"` never
  appears (`src/report.rs:289`).
- **The envelope is identical on the degraded path.** A binary with no usable
  function map emits the same schema with an empty `functions` array
  (`src/main.rs:150-164`). It previously emitted a narrower schema
  (`binary: null`, no `arch`, no `min_anchors`), which broke consumers on
  exactly the degraded binaries they most needed to report on. Consumers
  **MAY** rely on all four top-level keys always being present.

### 6.3 Library surface

`BinaryImage` (`src/container/mod.rs:40-55`) is the format seam: four methods
(`function_ranges`, `locations`, `xref_locations_in`, `bytes_at`). Both
`ElfImage` and `PeImage` implement it. The ranking and tiering core depends
only on this trait.

**Status of this surface:** compiles and is unit-tested; **no external
consumer exercises it.** `winnow`, the motivating downstream project, does not
depend on the `unhusk` crate — it reimplements an ELF-only pipeline in
parallel. "The backend behind winnow" is design intent, not current wiring.

### 6.4 Diagnostics — explicitly not part of the contract

Six environment-gated dumps exist for building measurement harnesses:
`UNHUSK_DUMP_TIERS` (`src/main.rs:231`), `UNHUSK_DUMP_DEPS` (`:213`),
`UNHUSK_DUMP_ATTRS` (`:306`), `UNHUSK_DUMP_EDGES` (`:344`),
`UNHUSK_DUMP_ALL_FNS` (`:334`), `UNHUSK_DUMP_GT` (`:290`). Format is
tab-separated and **unstable**. `UNHUSK_DUMP_TIERS` is the authoritative tier
source for harnesses because it reads the real tier assignment rather than
parsing the human listing.

---

## 7. Degraded modes

Specified, tested behaviour under adversarial or lossy input. In each case the
tool degrades and says so rather than silently returning less.

| Condition | Response | Site |
|---|---|---|
| Section headers stripped | Recover regions from program headers; warn that boundaries are approximate | `src/elf.rs:126-137` |
| `.eh_frame` removed, `.eh_frame_hdr` intact | Recover function starts from the hdr binary-search table; near-complete, results comparable to intact | `src/frame.rs:114-118`, `:155-230` |
| Both absent | Call-target fallback map: every direct `call rel32` target is a function entry, each running to the next; recovers ~half of true starts (2413/5088 measured on stripped `tokei`); tier precision degrades | `src/frame.rs:97-145` |
| No usable map at all | Emit the full JSON envelope with empty `functions`; exit 0 | `src/main.rs:149-166` |
| No readable `.text` | Warn: likely packed, static analysis cannot proceed | `src/elf.rs:143-149` |
| No `.rela.dyn` | Warn: static/non-PIE, Location reconstruction may find nothing | `src/elf.rs:150-156` |

`.eh_frame_hdr` recovery handles the 4- and 8-byte datarel/pcrel/absptr
encodings and bails on anything else (`src/frame.rs:168-174`, `:221-226`)
rather than guessing.

---

## 8. Measured characteristics

Numbers below carry their corpus and oracle. **They are not interchangeable.**

### 8.1 Primary — symbol ground truth, `realval/`

**32 binaries scored** (13 source-built, 8 `cargo install`, 11 adversarial).
The per-binary table in `realval/results_body.md` contains 32 rows and
`realval/corpus_src/` holds exactly 32 stripped binaries. The stress corpus was
designed as 34; two of its binaries were never scored — `mprocs` failed to
build (`corpus_src/mprocs.FAILED`) and `dog` has no artifact in `corpus_src` at
all — so 34 is the intended corpus and 32 the measured one
(`docs/local/validation.md:32-34`, corrected there). Every figure below rests on the
32.

Scored against `nm -C` symbol leading-crate (`docs/local/validation.md:9-16`):

| Tier | Rule | CLI/systems | async/web | pooled |
|---|---|---:|---:|---:|
| STRONG | `>= min_anchors` (default 2) | ~98% | ~87% | ~94% |
| SINGLE | exactly 1 | ~90% | ~75% | ~80% |

Threshold ladder (`docs/local/validation.md:20-24`):

| `--min-anchors` | pooled | async only |
|---:|---:|---:|
| 1 | 85.8% | 79.9% |
| 2 (default) | 94.4% | 87.3% |
| 3 | 96.1% | 90.9% |

**Oracle choice is deliberate.** DWARF and symbol ground truth disagree by
~30 points because DWARF homes user closure-dispatch shims to
`core/src/ops/function.rs`. That is an artifact of DWARF's closure attribution,
not a classification error, so symbol is the ruler for headline numbers
(`docs/local/validation.md:5-7`).

**The async gap is real and irreducible.** It survived a pre-registered stress
test whose controls removed two *measurement* artifacts (a `LocalKey::with`
forwarding wrapper on `fclones`, an own-library confound on `typos`) and lifted
pooled STRONG from 90.3% to 94.4% — while async stayed at 87.3% with no
artifact to blame (`docs/local/validation.md:34-50`). Named outlier inside that
average: `miniserve` at 7/14 STRONG FPs = 50.0% (`docs/local/validation.md:52-57`).

**The async stratum is 8 binaries.** By the `domain` column of
`realval/results_body.md`'s per-binary table: `bandwhich`, `dufs`, `gping`,
`miniserve`, `oha`, `rustscan`, `trippy`, `xh` (the remaining 24 split 16 cli,
4 macro, 2 crypto, 1 parallel, 1 framework). The 87.3% async figure is an
8-binary average containing one binary at 50.0%, which is why §9.2 states a
range rather than a point estimate.

### 8.2 Secondary — inline-leak incidence, `bench/origin/`

43-crate × 8-config corpus — 344 builds, 2,953,905 pooled FDE rows — mined
without rebuild: 3,605 instances of a non-author-declared function
absorbing a user Location, 89.93% genuine inline-absorption and 10.07% the
already-handled forwarding-wrapper shape (§9.2). One row is one FDE in one
build, so the same source function contributes up to 8 rows.

Converted to precision over the claimed-user population
(`INLINE_LEAK_INCIDENCE.md:467-489`, known-label denominator):

| Tier | pooled | ship profile¹ |
|---|---:|---:|
| STRONG | 91.312% | 91.78% (1473/1605) |
| SINGLE | 81.884% | 80.92% (1387/1714) |
| COMBINED | 86.291% | 86.17% (2860/3319) |

¹ `lto-fat, opt-3, panic-abort` — the profile real stripped release binaries
ship at (`INLINE_LEAK_INCIDENCE.md:551-572`).

The pooled figures are known-label-only. UNKNOWN (no `nm`-visible symbol
resolves to a classifiable crate) is 204 / 26,501 = 0.77% of the claimed-user
population, which bounds each tier within ≤0.8 points: STRONG lies in
90.957-91.346%, COMBINED in 85.627-86.397%, depending on whether UNKNOWN is
charged as FP or credited as TP.

### 8.3 Combination rule — normative

**§8.1 and §8.2 MUST NOT be arithmetically combined or compared as if they
measured the same quantity.** They differ in oracle implementation, corpus, and
build-config breadth (`realval` builds one config per binary; `bench/origin`
pools a systematic 8-config sweep). Neither figure may be quoted without its
corpus and oracle attached. Full accounting: `docs/local/validation.md`, "Two
measurements" section.

**Corpus relationship: containment, not partial overlap.** All 32 of
`realval`'s scored binaries appear in `bench/origin/corpus.tsv`'s 43 —
checked per binary against the manifest, zero missing — including all 8
async-domain binaries (§8.1). `INLINE_LEAK_INCIDENCE.md:341-343` states the
same containment; this is an independent confirmation of it, not a restatement.

Two crates named in `validation.md:32`'s stress list, `mprocs` and `dog`, are
absent from both measurements — `mprocs` failed to build in `realval`
(`corpus_src/mprocs.FAILED`) and is not in `bench/origin/corpus.tsv`; `dog` has
no `realval` artifact and is one of `bench/origin`'s four build failures. Since
neither is in `realval`'s scored 32, neither contributes to the 87.3% async
figure, and their absence from `bench/origin` does not break the containment
above.

**Containment does not license combining the two.** The corpora nest; the
measurements do not. `bench/origin` scores 11 crates `realval` does not, at 8
build configs each, under independently written scoring code — so the wider
corpus is measuring a different thing over a superset, not the same thing more
thoroughly.

### 8.4 Ground-truth provenance

The headline numbers come from the symbol oracle, **not** from `dwarf.rs`.
`dwarf.rs` is a secondary oracle used for `--validate` and the `--infer-depth`
measurements. An audit (`docs/local/dwarf-oracle-audit.md`) found and fixed three
real bugs in it: std generics misread via sysroot paths; vendored C/asm misread
as Rust authorship (31,030 functions mislabelled across a 58-binary corpus, up
to 99% of a single binary's reported user set); and build-script output
attributed to the consumer rather than the generator. **None moved the §8.1
numbers** — they never touched the symbol oracle — but they distorted
DWARF-derived recall until fixed. Four property tests now guard that bug class
(`prop_std_is_std_in_every_spelling`,
`prop_only_rust_sources_can_be_author`,
`prop_build_script_output_follows_its_generating_crate`,
`prop_elf_and_pe_oracles_agree`).

---

## 9. Known limitations

### 9.1 Structural recall gaps

- Functions with no reachable panic site have nothing to anchor on. Recall is
  ~15-46% of user functions on the test set — partial by design, adequate for
  signature generation, which needs good seeds rather than every function.
- User code reached only via trait objects, function pointers, or library
  dispatch classifies as `library`: the scan follows **static call edges only**
  (`src/xref.rs:237-243`).
- Non-PIE binaries defeat both the relocation walk and the RIP-relative-only
  scan independently — `movabs` immediate loads present no memory operand for
  `xref.rs` to see.
- `#[track_caller]` helper wrappers are structurally invisible to STRONG: the
  `Location` lives at the call site, not in the helper body, so multiplicity
  distributes across N callers instead of concentrating in the one function
  that is wholly user-authored.

### 9.2 Inline absorption — the multiplicity assumption's known hole

**Specification of the failure.** The precision lever is multiplicity: a
monomorphized library generic inlines exactly one user closure and so
references exactly one user Location, while a real user function references
several of its own. Requiring `>= N` distinct user Locations rejects
single-closure monomorphizations.

**That assumption fails when the library's own function absorbs several
distinct user Locations via inlining.** A large library generic
(`slice::sort_by`, `sort_unstable_by_key`, `rayon` bridges, futures/tokio/actix
combinators, serde generics) can inline a multi-panic user closure into its own
body while remaining too large to inline into its caller. The resulting
function is library-authored and library-declared but carries several genuine
user Locations, satisfying STRONG by construction.

#### Primary evidence — real-corpus incidence

The mechanism is established by mining naturally-occurring code, not by
constructing it. `bench/origin/INLINE_LEAK_INCIDENCE.md` reads the already-built
43-crate × 8-config matrix with no rebuild: **344 builds, 2,953,905 pooled FDE
rows**, every build carrying data. Four further crates (`bore`, `dog`,
`sniffnet`, `spotify-tui`) failed to build at all 8 configs and are excluded —
they sit outside the 43, not within it, so no unbuilt crate is counted as
zero-leak. A **leak instance** is one ground-truth FDE in one build that an
independent symbol oracle labels non-author, whose `origin_probe` counts
nonetheless include at least one user-class Location.

**3,605 instances**, split into two parallel scopes
(`INLINE_LEAK_INCIDENCE.md:19-34`):

| Scope | Instances | Rate over non-author FDEs |
|---|---:|---:|
| DEP (dependency-declared) | 1,024 / 1,170,733 | 0.0875% |
| STD (core/alloc/std-declared) | 2,581 / 1,164,095 | 0.2217% |
| **Combined** | **3,605 / 2,334,828** | **0.1544%** |

Every one of the 3,605 was resolved to a demangled symbol name and classified —
100% resolved, 0 unresolved (`INLINE_LEAK_INCIDENCE.md:517-537`):

- **3,242 (89.93%) genuine inline-absorption** — library code of its own
  absorbing a user Location. By shape: unclassified library generic 1,541,
  core generic 809, futures combinator 550, framework handler-adapter 169,
  rayon generic 143, serde generic 30.
- **363 (10.07%) forwarding wrappers** — `__rust_begin_short_backtrace::<F>`
  and `LocalKey::with::<F>`, whose entire body *is* the user's code reached
  through a std-declared generic. Already handled. The split is far more
  lopsided on the DEP side (4 forwarding of 1,024) than the STD side (359 of
  2,581).

**The mechanism occurs in real, widely-read code.** `ripgrep` shows zero
DEP-side leak — it looked clean in the DEP-only table — but 112 / 19,101
(0.586%) STD-side leak, including an instance whose files are
`library/core/src/slice/sort/stable/quicksort.rs` together with
`crates/core/haystack.rs` (`INLINE_LEAK_INCIDENCE.md:209-214`). That is the
`core::slice::sort` family occurring in ripgrep's own code, not in a synthetic
construction.

This is an existence result, not a typicality one. ripgrep's STD-side rate is
**~2.6× the corpus STD average** (0.586% versus 0.2217%), so it is the
strongest single example rather than a representative one. The corpus-level
rates in the table above are the prevalence claim; ripgrep answers only whether
the shape reaches ordinary, widely-read code.

By raw incidence the dominant contributors are async runtimes, not sorts:
`futures` 158 (15.4%), `tokio` 145 (14.2%), `rayon` 131 (12.8%), `wasmtime` 88,
`actix_web` 77 (`INLINE_LEAK_INCIDENCE.md:186-190`). Incidence is more
crate-concentrated than config-dependent: the top 5 crates account for 586/1024
= 57.2% of DEP-side instances, 16 of 43 crates show zero.

#### Secondary evidence — mechanism demonstration

An adversarial probe (`docs/PDB_ORACLE_hardcase.md`, tracked on branch
`pe-port/hardcase-probe`) forces the mechanism deliberately: five ordinary
wrappers handing small closures to `slice::sort_by`, `sort_unstable_by_key`,
and `rayon`'s `par_iter().map()/for_each()`. It reproduces on both formats,
by two independent oracles:

- **PE / PDB:** 21 of 22 user-Location xref sites land in a non-user-declared
  procedure; 13 false positives, **8 at STRONG tier**, corroborated both by
  xref address and by the PDB's own inline-site stream.
- **ELF / DWARF:** the same construction built natively and run under
  `--validate` — `certain 15 predicted, TP=2, FP=13, precision=13.3%`, with
  6 of 7 STRONG hits being `core::slice::sort::*` internals.

**The probe's precision figure is not a corpus figure and MUST NOT be quoted
as one.** A construction built to trigger the mechanism reports the rate at
which a triggering construction triggers it; it says nothing about prevalence.
The corpus figures above are the prevalence claim. The probe also
*under*-represents severity in one measurable respect: RuleA catches 27.3% of
the probe's instances versus 47.5% in the wild (§10.4).

**Therefore the mechanism is not a PE artifact.** It lives in
`classify.rs`/`xref.rs`, which both formats share through the container seam
(§6.3) — the same property that makes "adding a format is adding an impl" true
also makes a gap in the shared heuristic hit both formats identically.

**`--min-anchors` does not mitigate it.** The anchors are genuinely distinct
user Locations; the multiplicity test is satisfied on the library's function.

**Measured dead end.** Reference fan-out (how many distinct functions reference
the same Location) separates the `core::slice::sort` sub-family cleanly —
fan-out 5-6 versus 1 for genuine hits, zero measured recall cost — but
**cannot** separate the `rayon`-bridge shape, whose false positives sit at
fan-out 1, the exact value of genuine attributions. No threshold separates
them. Detecting generic monomorphization over a closure/callback type parameter
is the structurally different approach; it has not been scoped or attempted.

**Status: open and unmitigated on the DEFAULT path, shared by both formats —
updated 2026-08-25.** A candidate rule measured against this population
catches roughly half of it, with a large scope-dependent blind spot; it is
measurement-only and not in any decision path (§10.4). Separately, corpus-scale
STRONG-tier precision measurement now exists for both formats (not mechanism-
instance counting — direct precision against ground truth, matched crate
sets): `bench/{elf,pe}_corpus/REPORT.md` and their independent-corpus
confirmations `bench/corpus2_{elf,pe}/REPORT.md`, ~87-91% STRONG precision
pooled across four separate corpus measurements (two ELF, two PE),
statistically indistinguishable between formats. Two opt-in flags exist as
partial mitigation, both held-out validated: `--rule-r2` (`n_rel>=2 &
caller_rel>=1`) reaches ~93-95% STRONG precision on both formats, the most
consistent single result across all four corpora; `--min-size`/`--max-density`
also help on both formats but with a corpus-dependent effect *size* (unlike
R2's). Neither is the default — `--min-anchors` still is, for reproducibility
— so "unmitigated on the shipped path" remains true for what `unhusk <binary>`
does with no flags, but is no longer true of the tool's full surface.
**A genuine mining-search retraction happened the same day**: an earlier
finding that R1/R3 (window-corroboration rules) hurt PE precision reversed
sign entirely on a second, independent PE corpus — the original result was
corpus-composition-dependent, not evidence of a PE-specific structural
difference, and is marked retracted in place in `bench/pe_corpus/REPORT.md`
rather than silently corrected.

**Consumers of the STRONG tier MUST NOT treat it as certainty.** Six
independent measurements bound it (two from §8.1/§8.2's ELF-only work, four
from the later matched ELF/PE corpus work below), and §8.3 forbids merging
the first two, so all are stated with what produced them:

| Measurement | STRONG precision | Corpus | Oracle / breadth |
|---|---|---|---|
| §8.1 `realval` | 94.4% pooled, 87.3% async | 34 binaries | `nm -C` symbol leading-crate, one default build per binary |
| §8.2 `bench/origin` | 91.312% pooled, 91.78% at ship profile | 43 crates × 8 configs (344 builds) | symbol oracle over per-build FDE rows, 8-config sweep |
| `bench/elf_corpus` | 86.76% | 36 crates | DWARF, `--validate` |
| `bench/corpus2_elf` | 87.09% | 40 crates, zero overlap with the above | DWARF, `--validate` |
| `bench/pe_corpus` | 89.17% (89.52% on a same-day rebuild, run to add R2 data — within noise) | 39 crates | PDB, `--validate` |
| `bench/corpus2_pe` | 90.91% | 34 crates, zero overlap with the above | PDB, `--validate` |

Four more independent readings, same spread as §8.1/§8.2's two — not reconciled
into a single number here either, for the same reason (§8.3). The two ELF
numbers and two PE numbers each pair closely (within ~1-4pp of each other);
ELF and PE as groups are statistically indistinguishable from each other. A
consumer choosing a threshold should read the spread — roughly 87% to 94%
depending on corpus, workload, and build config — as the operating range, and
§8.1's async stratum as the lower bound for async-heavy targets, which is what
malware skews toward.

### 9.3 Evasion

Defeated by packing, `--remap-path-prefix`, and `-Z build-std
panic_immediate_abort`. The first two are observed in real malware and both are
flagged (§7). The third removes panic metadata entirely, is nightly-only, and
changes runtime behaviour.

---

## 10. Component inventory and status

**Status vocabulary.** *Shipped* — in the default CLI path, load-bearing.
*Library* — compiles and is tested, reachable only by writing code against it.
*Diagnostic* — flag-reachable, output not trustworthy for the stated purpose.
*Dead* — compiled, called by nothing in this repo.

| Module | Lines | Unit tests | Status |
|---|---:|---:|---|
| `report.rs` | 1087 | 7 | Shipped — human + JSON reporters, tiering (R2's `print_r2_json_report` added 2026-08-25, no new in-file test — reuses already-tested `user_anchor_count`/`anchor_files`, validated against real ELF binaries instead) |
| `dwarf.rs` | 738 | 7 | Shipped, validation only (§8.4) |
| `origin.rs` | 726 | 33 | Library — origin-composition classifier (§10.4) |
| `strings.rs` | 603 | 22 | Shipped — Phase 1 classification |
| `container/pe.rs` | 682 | 12 | Shipped — CLI-reachable via `pe_pipeline.rs` (§10.2) |
| `pe_pipeline.rs` | 479 | 0² | Shipped — CLI entry point for PE (§10.2) |
| `pdb_oracle.rs` | 562 | 12 | Library, validation only |
| `main.rs` | 468 | 0 | Shipped — CLI |
| `classify.rs` | 374 | 6 | Shipped — bucket propagation |
| `elf.rs` | 346 | 0¹ | Shipped — load, section index, relocations |
| `xref.rs` | 325 | 2 | Shipped — decode + certain set (`caller_rel`, R2's term, tested since 2026-08-25; the rest of the module is still 0¹) |
| `frame.rs` | 243 | 0¹ | Shipped — function ranges + fallbacks |
| `bin/origin_probe.rs` | 175 | 0 | Library harness for §10.4 |
| `container/elf_image.rs` | 118 | 0¹ | Shipped — ELF behind `BinaryImage` |
| `locate.rs` | 99 | 0¹ | Shipped — Location reconstruction |
| `container/mod.rs` | 55 | — | Shipped — the seam |
| `lib.rs` | 12 | — | Shipped — module roots |

¹ No in-file `#[test]`; covered by `tests/integration.rs` (7) and real-corpus
measurement in `realval/`.

² No in-file `#[test]`; a thin composition of already-tested calls into
`container::pe`/`report`/`xref`/`pdb_oracle`, validated end-to-end instead
against real PE binaries each time a flag landed (`bench/pe_corpus`,
`bench/elf_corpus`, `bench/corpus2_{elf,pe}` — same gap this table already
accepts for `container/pe.rs` itself before its own in-file tests existed).

**Coverage asymmetry worth stating plainly:** `xref.rs` — the module carrying
the §9.2 gap — has **zero isolated unit tests**. The hard case would not have
been caught by anything currently in `cargo test`; it required a deliberately
adversarial construction. `strings.rs`, the other precision-critical module,
is the most heavily tested at 22.

### 10.1 Dependencies

`object` (ELF/PE read), `gimli` (`.eh_frame`, DWARF), `iced-x86` (decode),
`pdb`, `rayon`, `clap`, `serde`/`serde_json`, `anyhow`. Pure Rust, no C
dependencies, no network, no runtime tooling.

Clippy runs at `pedantic` with a documented exemption list (`Cargo.toml`). The
numeric-cast exemptions are justified by x86-64-only support making
`u64 <-> usize` lossless, and by the position that rewriting guarded casts as
`try_into().unwrap()` would add panic paths to a parser of hostile input.

### 10.2 PE / PDB — wired into the CLI, STRONG/SINGLE tier only

`container/pe.rs` parses PE32+, walks `.pdata` for function ranges (the RVA
analogue of FDEs; `.pdata` gives exact bounds directly), extracts `Location`
structs from `.rdata`, and runs the same iced-x86 RIP-relative scan in RVA
space. `pdb_oracle.rs` is the PE-side counterpart to `dwarf.rs`, including
inline-site data — which is what allowed §9.2 to be corroborated two
independent ways in a single measurement. `PeImage::call_targets_in` (added
2026-08-25) runs the same decoder filtered to CALL instead of RIP-relative
memory operands, giving PE a real CALL-edge graph for the first time; it
feeds `xref::caller_rel` (R2) but not `classify::attribute`'s
Inferred/Indeterminate BFS, which also needs a `dep_boundary` set that isn't
built for PE — so STRONG/SINGLE stays the shipped ceiling.

`src/pe_pipeline.rs` is the CLI-facing entry point: `main.rs` sniffs the
input's magic bytes and routes PE binaries there instead of the ELF path.
Output is STRONG/SINGLE tier only, matches what `--precision` already
restricts ELF to, and every PE run — human report, `--json`, `--validate`
against a `.pdb` — prints a fixed disclosure banner before any result. Two
mined rules are shipped as opt-in flags on PE (as well as ELF):
`--min-size`/`--max-density` (held-out validated on both formats, though the
effect *size* looks more corpus-dependent than R2's — `bench/size_signal/
REPORT.md`) and `--rule-r2` (`n_rel>=2 & caller_rel>=1`; measured at 95.27%
pooled precision across two independent PE corpora vs the incumbent's
90.01%, `bench/corpus2_pe/REPORT.md`).

Practical finding worth recording: for lld-link-produced PE images, MSVC debug
info lives entirely out-of-process in the `.pdb`. An `oracle`-profile build and
an `llvm-strip --strip-all` copy of it were **byte-for-byte identical**
(whole-file `md5sum` match). The ELF side's "build once, strip a copy" dance
collapses to "build once" on this target.

**Normative constraint.** PE output **MUST NOT** be presented under the ELF
STRONG trust framing. The STRONG tier does not currently earn that framing on
PE (§9.2), the mechanism is shared rather than PE-specific — but unlike when
this constraint was first written, there **is** now a lower-trust label: the
disclosure banner every PE entry point prints, and PE's own corpus-scale
measurement (`bench/pe_corpus/REPORT.md`, `bench/corpus2_pe/REPORT.md`)
giving it a real, disclosed number (89.5%/90.9% STRONG precision across two
corpora) rather than an unmeasured caveat.

### 10.3 Inert surfaces

Two components previously lived here as inert-but-retained code and were
removed outright on 2026-08-28, once the ideas they carried were already
recorded in this document — nothing about the decision they informed
depended on the code still compiling.

- **`bin/anchor_headroom.rs` (589 lines) — removed, was dead.** Referenced by
  nothing outside `src/bin/`; built its own binary on every `cargo build` for
  no consumer. Its research conclusion (recall headroom 0.16-0.47% by two
  ground truths, a structural ceiling) correctly informed the decision not to
  pursue that direction; that conclusion is preserved here, the code wasn't
  needed to preserve it.
- **`--types` / `types.rs` (440 lines) — removed, was empirically ineffective.**
  A 13-binary sweep produced 3 user-tier hits, all false at the type-name
  level; a further check produced a single nonsensical amalgamated struct.
  14 binaries, zero real signal. The negative result stands; the flag is gone
  from the CLI.
- **`container/elf_image.rs:26-27`** — a `strings` field stored at construction
  and never read, carrying an explicit `#[allow(dead_code)]`.

### 10.4 Origin-composition classifier — measurement only

`origin.rs` (33 unit tests, the most in the tree) is a **pure function of
existing output**: it reads `ScanResult::all_loc_hits` and `PanicLocation` and
touches no ELF/PDB data directly (`src/origin.rs:12-14`). Where the shipped
pipeline asks "does this set contain a user Location, and how many", this asks
what the *whole composition* is, and whether a stricter rule over that
composition separates real author functions from a library generic that
absorbed a user closure (§9.2).

Three rules are implemented for sweeping (`src/origin.rs:283-367`): `RuleA`
(strict — any non-user Location is a hard DEP trigger), `RuleB` (std-tolerant —
only registry/git are hard triggers), `RuleC` (ratio baseline, no ambiguous
tier). Decisions are `AUTHOR` / `DEP` / `AMBIGUOUS` / `NONE`.

**Measured coverage of the §9.2 population.** `RuleA`'s exact `decide`
condition (`non_user(counts) > 0`) applied to all 3,605 leak instances
(`INLINE_LEAK_INCIDENCE.md:139-148`):

| Scope | Instances | Vetoed (caught) | Blind (user-only) | Catch rate |
|---|---:|---:|---:|---:|
| DEP | 1,024 | 776 | 248 | **75.8%** |
| STD | 2,581 | 937 | 1,644 | **36.3%** |
| **Combined** | **3,605** | **1,713** | **1,892** | **47.5%** |

**The STD-side blind fraction is the part that matters: 1,644 of 2,581 = 63.7%
of in-the-wild STD-scope instances carry no co-referenced non-user Location at
all, so the rule cannot see them.** STD scope is also the larger half of the
population. A rule of this shape addresses most of the DEP side and a minority
of the STD side.

The adversarial probe understates this coverage in every scope — 2/2 DEP,
1/9 STD, 3/11 = 27.3% combined — because its construction produced almost no
incidental co-referenced Locations inside the sort internals it hit, where real
instances more often carry a second nearby Location
(`INLINE_LEAK_INCIDENCE.md:160-177`). This is one of the reasons §9.2 treats
the probe as a demonstration rather than a prevalence measurement.

On the separate question of attribution precision rather than leak coverage,
`bench/origin/REPORT.md:165,221,313` reports `RULE_A@2` at 92.8% pooled
(workspace-merged scoring) and 91.5% pooled / 93.0% crate-averaged on async
code, against the shipped tool's 87.3% async stratum — a matched-stratum
comparison, not a controlled experiment.

**The controlled experiment has since been run** (`docs/local/origin-veto-headtohead.md`):
same 32 binaries as `docs/local/validation.md`, same symbol ground truth, same
strata, `RuleA`'s veto condition as the only variable, joined to the shipped
tool's own per-function verdicts at 2225/2225 with zero anchor-count
disagreements. It changes the reading above in one specific way. The right
baseline is not the shipped tool's *default* but the shipped tool's *dial at
matched recall* — a veto raises precision by discarding functions, which
`--min-anchors` already does, so the comparison must hold retention fixed.
Under that correction: pooled the veto is a **net negative** (-1.5pp,
destroying 13 genuine author functions per false one removed); on CLI and
macro-heavy code it is clearly harmful; on the async domain it retains a
+4.2pp advantage whose paired cluster bootstrap is [-8.7, +21.2] — and even
that is the veto's best-case framing, since comparing against the dial's
actual settings rather than an interpolated point shows `--min-anchors 4`
matching RULE_A@2's async precision (94.0%) at 23.5% retention against its
14.0%. The
mechanism account in this section survives intact — the veto catches 5/5
rayon bridges, 12/15 futures combinators and 6/8 handler-adapters while
missing `core` iter/sort shims, the same DEP-favouring pattern the 75.8% /
36.3% split above predicts. What does not survive is the implication that
`RuleA` is a better decision rule than the dial it would replace.

Not wired to the CLI; driven by `bin/origin_probe.rs`. **Nothing above is in
the shipped decision path**, which is why §9.2 records the gap as unmitigated.
Full sweep and comparison: `bench/origin/REPORT.md`; controlled head-to-head:
`docs/local/origin-veto-headtohead.md`.

### 10.5 `--backtrace-depth` — shipped, unvalidated

Implemented, wired, off by default, and strictly separated from the certain
bucket. Its own help text directs the operator to `--validate` to measure the
bucket's precision, but **no such measurement exists** in `README.md`,
`docs/local/validation.md`, or `realval/`. A working feature with an unfulfilled
promise attached — not dead code, and not validated either.

---

## 11. Verification

- `cargo test` — 103 passing (96 unit + 7 integration), 0 failing.
- **Extraction is optimization-invariant; the false-positive rate is not.**
  These are two separate claims and only the first holds across configs.

  *Extraction* — recovering `Location` structs and mapping them to FDEs — was
  checked across thin-LTO, `lto=true,codegen-units=1`, `opt-level=z`,
  `panic=abort`, and `-C force-unwind-tables=no`. It keys on Location struct
  layout and relocation structure, neither of which optimization changes.

  *The FP rate* varies with build config, because the §9.2 mechanism **is**
  inlining, and inlining is exactly what these flags govern. Measured over the
  8-config sweep, the two available metrics move in **opposite directions**,
  and neither is "the" config effect on its own:

  - **Raw leak incidence** (instances per non-author FDE) is higher at `opt-3`:
    roughly 2-2.5× the `opt-z` rate at matching lto/panic — DEP side
    `lto-fat,opt-3,panic-abort` 145/98,446 = 0.147% versus
    `lto-fat,opt-z,panic-abort` 117/133,311 = 0.088%. STD side moves the same
    direction (opt-3 0.24-0.43%, opt-z 0.14-0.24%).
    `INLINE_LEAK_INCIDENCE.md:74-92`.
  - **Precision over claimed-user** is *lower* at `opt-z`: opt-z sits
    consistently 1-2pp below opt-3 at matching lto/panic. Across all 8 configs
    STRONG spans 89.75-92.64% (2.9pp), SINGLE 80.31-83.31% (3.0pp), COMBINED
    84.99-87.72% (2.7pp). `INLINE_LEAK_INCIDENCE.md:551-578`.

  The directions differ because the denominators do: leak incidence is measured
  per non-author FDE, and `opt-z` emits far more FDEs (133,311 versus 98,446 at
  matching lto/panic on the DEP side), so a lower per-FDE rate coexists with
  slightly worse precision over the claimed-user set. Config effect on
  precision is real but modest — under 3pp across the whole sweep — and smaller
  than the per-crate spread, where the top 5 of 43 crates carry 57.2% of
  DEP-side instances.
- Real-malware exercise (static only, never executed): KrustyLoader, Akira,
  BlackCat/ALPHV, 01flip, P2PInfect. Two evasions observed and now flagged —
  `--remap-path-prefix` (01flip) and packing (P2PInfect). Details:
  `docs/local/case-study-real-malware.md`.

### Related documents

| Document | Contents |
|---|---|
| `README.md` | Install, CLI reference, worked example |
| `docs/local/corpora.md` | **Corpus registry — which corpus backs which number, and which figures are not comparable. Read before quoting anything from the tables below.** |
| `docs/local/validation.md` | Precision derivation, pre-registered stress test, two-measurements accounting |
| `docs/local/origin-veto-headtohead.md` | The controlled origin-veto vs `--min-anchors` comparison (§10.4's open question, closed) |
| `realval/results_body.md` | Per-binary results, 67-row STRONG false-attribution table |
| `docs/local/dwarf-oracle-audit.md` | The three DWARF oracle bugs and their property-test guards |
| `bench/origin/REPORT.md` | Origin-classifier sweep (§10.4) |
| `bench/origin/INLINE_LEAK_INCIDENCE.md` | §8.2 corpus mining |
| `docs/PDB_ORACLE_hardcase.md` | §9.2 on PE, with the fan-out null result (branch `pe-port/hardcase-probe`) |
| `docs/local/pe-port-design.md` | PE port design notes |
| `docs/local/case-study-real-malware.md` | Sample hashes, evasion-effort gradient |

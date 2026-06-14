# Recall-headroom diagnostic: non-panic user-provenance anchors

**Date:** 2026-06-15
**Question:** unhusk's recall is bound (median certain-recall 15.8%) because its only user
anchor is the panic `Location`. Would broadening the anchor to *other* user-provenance
`&'static str`s — `module_path!` (`"crate::mod"`), `file!` outside panics, `type_name::<UserType>()`
— materially raise recall, and at what precision cost?
**Method:** the 13 rebuilt validation binaries (stripped + debug twin). Diagnostic tool
`src/bin/anchor_headroom.rs`. The classifier was **not** changed.

---

## BOTTOM LINE (blunt)

**Not worth building. The recall ceiling is structural, not an anchor-coverage problem.**

Three independent reasons, each sufficient on its own:

1. **The headroom is ~zero.** Across all 13 binaries, bare anchors reach **8** additional
   user functions by DWARF `decl_file` ground truth (**0.16%** of user fns) and **27** by the
   more generous symbol-name ground truth (**0.47%**). Either way it is noise.

2. **The anchor is mostly redundant with the panic anchor.** Of the 143 functions any bare
   anchor points at, **79 (55%) are already `certain`** — the functions that carry a
   `module_path!`/`type_name`/`file!` string are overwhelmingly the same functions that already
   carry a user panic `Location`. Logging, error-context and type-introspection live in the same
   "doing real work with error handling" functions that panic.

3. **Where it is incremental, it is often contaminated.** The bare-anchor set's symbol-name
   precision is bimodal: clean on ripgrep (92%) and tokei (75%), but **0%** on just, grex, sd,
   dust — the same library-generic / dep-submodule frontier that caps the panic anchor.

The functions unhusk actually misses — closures, leaf helpers, and monomorphized generic
instances reached only through trait dispatch — **do not carry their own user-provenance string.**
They are *called*, not *logged*. No string-anchor lever reaches them.

---

## A finding that changes how to read the question

**User `module_path!`/`type_name` strings are slot-less.** Unlike panic `Location`s — whose
`file` field is a relocated fat-pointer constant in `.data.rel.ro` (an `R_X86_64_RELATIVE`
slot, which is exactly what unhusk scans) — the compiler materializes `module_path!`/`type_name`
strings inline at the use site (`lea reg,[rip+rodata]; mov len,imm`). They have **no
`.data.rel.ro` slot and no relocation.**

Consequence: the literal "same RIP-relative xref scan unhusk uses for Locations" (scan
`.rela.dyn` slots) finds essentially **none** of them. For ripgrep the slot scan yields **1**
bare `.rs` slot and **0** ident slots, against 319 panic slots.

To measure the lever fairly we **inverted** the scan: every RIP-relative memory operand in
`.text` whose effective address lands in `.rodata` is a candidate; we classify the bytes at
that address. This recovers the exact slot-less string start. All numbers below use the
inverted scan (the optimistic reading of the lever).

The user-crate set for the ident test is derived purely from the stripped binary:
`{snake_case leading idents of "ident::" runs in .rodata} \ {std} \ {registry deps seen as
dep .rs paths}`. This is the same complement logic unhusk uses for `.rs` paths.

---

## Two ground truths (and why both)

DWARF `decl_file` (the README's ground truth) **undercounts user functions**: it homes
monomorphized closures to `core/ops/function.rs` and frequently fails to map generic instances
at all (no `low_pc` match). Example — ripgrep functions DWARF calls "unmapped" that are
plainly user code by symbol:

```
0x256800  <rg::search::SearchWorker<...>>::search
0x26e740  <rg::flags::hiargs::HiArgs>::from_low_args
0x2ca710  <ignore::gitignore::GitignoreBuilder>::add::<&std::path::Path>
0x21fb00  <grep_searcher::searcher::Searcher>::search_reader::<...>   (×many monomorphizations)
```

So we report **both**:
- **DWARF** `decl_file` (matches the existing FP analysis), and
- **symbol-name**: a function is user iff its demangled symbol's leading crate ∉ {std} ∪ {deps}
  (counts monomorphized generics by authoring crate; this is the "by symbol authorship" view
  the real-binary FP write-up already acknowledged).

The symbol view raises the user denominator everywhere (ripgrep 3533→4013, just 181→478, bat
70→293), confirming the undercount — yet the verdict holds under it.

---

## RESULTS — recall headroom

`A` = DWARF/symbol-user fn already `certain`. `B` = missed by certain, reachable via a bare
anchor (**recoverable headroom**). `C` = missed, no bare anchor (**residue**).
`B` is a lower bound (the user denominator still undercounts).

| binary | DWARF user | A | **B** | B/(A+B+C) | symbol user | sA | **sB** | sB/(sA+sB+sC) | bare-anchor fns |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ripgrep | 3533 | 143 | **5** | 0.14% | 4013 | 328 | **19** | 0.47% | 91 |
| just | 181 | 25 | **0** | 0.00% | 478 | 119 | **0** | 0.00% | 3 |
| bat | 70 | 11 | **2** | 2.86% | 293 | 132 | **2** | 0.68% | 9 |
| tokei | 48 | 10 | **0** | 0.00% | 160 | 34 | **5** | 3.12% | 20 |
| fd | 737 | 3 | **1** | 0.14% | 99 | 10 | **1** | 1.01% | 6 |
| grex | 34 | 3 | **0** | 0.00% | 86 | 11 | **0** | 0.00% | 4 |
| hexyl | 26 | 4 | **0** | 0.00% | 72 | 12 | **0** | 0.00% | 3 |
| hyperfine | 32 | 10 | **0** | 0.00% | 95 | 15 | **0** | 0.00% | 0 |
| sd | 6 | 2 | **0** | 0.00% | 34 | 5 | **0** | 0.00% | 4 |
| xsv | 65 | 25 | **0** | 0.00% | 133 | 45 | **0** | 0.00% | 0 |
| dust | 33 | 15 | **0** | 0.00% | 78 | 15 | **0** | 0.00% | 3 |
| pastel | 71 | 19 | **0** | 0.00% | 139 | 26 | **0** | 0.00% | 0 |
| zoxide | 19 | 3 | **0** | 0.00% | 64 | 8 | **0** | 0.00% | 0 |
| **AGG** | **4855** | **273** | **8** | **0.16%** | **5744** | **760** | **27** | **0.47%** |  |

Bare anchors recover **8 / 4855** user functions (DWARF) or **27 / 5744** (symbol) across the
whole corpus. The single largest contributor is ripgrep at 19. Six binaries have a `B` of zero
under both ground truths.

---

## RESULTS — bare-anchor precision (is the anchor clean?)

Over the entire bare-anchor function set (hit or miss), what fraction does ground truth call
user vs library-generic/dep?

| binary | bare fns | symbol user | symbol non-user | symbol precision | DWARF user/nonuser/unmapped |
|---|---:|---:|---:|---:|---|
| ripgrep | 91 | 84 | 7 | **92.3%** | 6 / 6 / 79 |
| tokei | 20 | 15 | 5 | 75.0% | 2 / 5 / 13 |
| bat | 9 | 5 | 4 | 55.6% | 5 / 4 / 0 |
| hexyl | 3 | 1 | 2 | 33.3% | 1 / 2 / 0 |
| fd | 6 | 1 | 5 | 16.7% | 1 / 5 / 0 |
| just | 3 | 0 | 3 | 0.0% | 0 / 3 / 0 |
| grex | 4 | 0 | 4 | 0.0% | 0 / 4 / 0 |
| sd | 4 | 0 | 4 | 0.0% | 0 / 4 / 0 |
| dust | 3 | 0 | 3 | 0.0% | 0 / 3 / 0 |
| **AGG** | **143** | **106** | **37** | **74.1%** | 15 / 36 / 92 |

The DWARF `decl_file` view shows the **same contamination mechanism as the panic anchor**: the
non-user functions that carry a user-provenance string are library/dep generics with user code
inlined in (`dependency crate`, `Once/OnceLock init shim`, etc. — the 32%-irreducible frontier).
The 92 DWARF-"unmapped" are mostly genuine user monomorphizations (the symbol view rescues them),
which is *why* the symbol precision looks high — but high precision on a redundant set buys
nothing.

---

## Per-binary callouts requested

**ripgrep (logging-heavy, `log` crate).** The richest bare-anchor binary: 91 functions, 92%
symbol-clean. But **65 of 91 (71%) are already `certain`** — the bare anchor re-discovers what
the panic anchor already found. Of the 26 it adds, only 19 are user (symbol) / 5 (DWARF).
Incremental recall 0.47%. The ident strings are real workspace crates (`grep_searcher::`,
`ignore::`, `rg::`, `grep_regex::`) — the lever *works*, it just lands on the wrong (already-known)
functions.

**just (assumed logging-heavy — it is not).** just embeds **zero `just::` strings** (verified:
`strings just.stripped | grep just:: → 0`). It uses neither `log`/`tracing` module paths nor
user `type_name` that survive to `.rodata`. Its 3 bare anchors are all dep/noise idents,
0% user, B=0. **The premise that a CLI tool is "logging-heavy" does not imply it carries user
module-path anchors** — most don't.

**Terse binaries (zoxide, xsv, pastel, hyperfine).** bare-anchor fns = **0**. No user-provenance
string beyond panic Locations is referenced anywhere in `.text`. B=0. Nothing to recover.

---

## VERDICT

| test | result |
|---|---|
| Is B large? | **No.** 0.16% (DWARF) / 0.47% (symbol) aggregate; max 19 fns (ripgrep). |
| Is the bare-anchor set clean? | **Bimodal.** 92% (ripgrep) down to 0% (just/grex/sd/dust). |
| Net | **Small B → recall ceiling is structural.** Build nothing. |

Broadening the anchor to `module_path!`/`file!`/`type_name` would **not materially raise recall**.
The lever fails for a structural reason, not a coverage one: the functions unhusk misses are
the ones with *no* self-referential user string — closures, leaf helpers, and trait-dispatched
generic instances. They are reached only by **backward** reachability (who calls them), which no
forward string-anchor scan provides. This is the same conclusion the panic-Location recall
analysis reached, now confirmed against a second, independent anchor family.

To move recall one would need backward reachability (callers of user code) or type-layout
recovery — not more string anchors.

---

## Reproducing

```
cargo build --release --bin anchor_headroom
./target/release/anchor_headroom realval/out/<name>.stripped realval/out/<name>.debug
# DUMP_BARE_FNS=1 prefix dumps per-function (addr, anchor kind, certain/missed, DWARF label).
```

Per-binary full outputs in `realval/anchor/<name>.txt`. `nm -C` on the `.debug` twin supplies
the symbol-name ground truth; DWARF `.debug_info` supplies the `decl_file` ground truth (unhusk's
own `dwarf::read_function_sources`). The tool reuses unhusk's `elf`/`frame`/`locate`/`xref`/`dwarf`
modules unchanged.

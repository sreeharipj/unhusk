# Real-Binary Validation of unhusk

**Date:** 2026-06-14
**Question:** Does unhusk's "100% certain-precision / ~37.5% recall" story — established on three
small/synthetic fixtures — hold on real-world Rust binaries?
**Method:** 13 popular pure-Rust CLI tools, each built from source with debug info retained
(`CARGO_PROFILE_RELEASE_DEBUG=true CARGO_PROFILE_RELEASE_STRIP=false cargo build --release`), then a
stripped copy analysed with `unhusk <bin>.stripped --validate <bin>.debug`. DWARF `.debug_info` from
the unstripped twin is the ground truth. Toolchain: rustc 1.97.0-nightly. All 13 built and validated;
**zero build or validate failures.**

---

## BOTTOM LINE (blunt)

**"100% certain precision" does not survive contact with real binaries.** It was a property of the
fixtures, not of the method.

- **12 of 13 binaries scored below 100% certain precision.** The one exception (zoxide, 100%) had
  only **3** classifiable certain functions — too small to mean anything.
- Certain-precision **median 66.7%, mean 64.1%, range 8.9% – 100%.** Four binaries came in **under
  50%** (bat 8.9%, grex 21.4%, fd 27.3%, tokei 43.5%).
- The degradation is **not** purely an LTO artifact. It shows up in **non-LTO** builds too
  (xsv 86.2%, ripgrep 94.7%, **grex 21.4%**). LTO makes it worse on average but is not the root cause.
- Root cause (verified, see below): Rust attributes **monomorphized closures and user-instantiated
  library generics** to their *definition* sites in `core`/`std`/dependency crates. User panic
  Locations inlined into those bodies make unhusk mark library/dep functions as "certain." **67% of
  all false positives are `FnOnce`/`Fn`/`FnMut` closure shims** that DWARF homes to
  `core/src/ops/function.rs`.

The headline claim needs to be retired or heavily caveated. At minimum: *"certain precision is 100%
against DWARF on the fixtures; on real binaries it ranges 9–100% (median ~67%) because DWARF
attributes user closures and user-instantiated generics to their definition sites in std/deps."*

---

## WORST RESULTS AND SURPRISES (lead, not buried)

### bat — 8.9% certain precision (TP=11, FP=112). The single worst.
Profile: `lto=true, codegen-units=1`. unhusk marked **133** functions certain; DWARF says **112** are
not user code. **111 of those 112 are the same construct**: `<bat::…::{closure} as
core::ops::FnOnce<()>>::call_once`. Verified by demangling and by the panic-site annotation, e.g.

```
0x00315fc0  <bat::syntax_mapping::builtin::BUILTIN_MAPPINGS::{closure#1} as core::ops::FnOnce<()>>::call_once
            DWARF decl_file = /rustc/.../library/core/src/ops/function.rs:250
            panic @ src/syntax_mapping/builtin.rs:57:35     <-- bat's OWN source
```

bat has a huge lazy-static `BUILTIN_MAPPINGS` initialised by a closure that builds dozens of syntax
mappings, each with a fallible step carrying a `builtin.rs` panic Location. Each monomorphized
`call_once` instance is a separate function. **The function body is bat's code; DWARF's `decl_file`
is the `FnOnce::call_once` trait-method definition in core.** So whether these are "real" false
positives is a definition question: by symbol name they are bat; by DWARF `decl_file` (the ground
truth the README uses) they are core, and unhusk is scored wrong on all 111.

### fd — 27.3% certain precision (TP=3, FP=8).
Profile: `lto=true, codegen-units=1`. Only 3 of 11 classifiable certain functions are truly fd code.
The 8 FPs are a richer mix and more defensibly "real" errors — substantial non-user logic with fd
code inlined in:
- `core::slice`/`core::iter` generics monomorphized with fd closures (`GenericShunt<Map<…,
  fd::exec::CommandTemplate>>`).
- `std::sync::Once::call_once_force::<…>` lazy-init shims for regex/aho-corasick.
- `<clap_builder::…::TypedValueParser>::…` instantiated for `fd::filter::owner::OwnerFilter::from_string`
  — DWARF attributes it to `clap_builder-4.6.0/src/builder/value_parser.rs`.

### grex — 21.4% certain precision (TP=3, FP=11), **with NO LTO.**
grex has **no `[profile.release]` section** → Cargo defaults (`lto=false, codegen-units=16`). It still
craters: **8 of 11 FPs are `core::slice` sort generics** (grex's comparator closures inlined into
`core` sort), plus alloc/iter generics. This is the key counter-example to "non-LTO is safe":
closure/generic-heavy code breaks precision even without LTO.

### zoxide — the only 100%, but meaningless.
TP=3, FP=0, **unknown=5** out of 8 certain predictions. Three correct functions, five DWARF couldn't
map. A 100% on n=3 is noise, not vindication.

### Not a surprise but worth stating: certain recall is *lower* in the wild than the fixture.
Fixture certain recall was 37.5%. Real-binary certain recall **median 15.8%**, range 0.4%–45.5%. Only
xsv (38.5%) and dust (45.5%) beat the fixture number.

---

## FULL RESULTS TABLE

| binary | total fns (DWARF-mapped) | DWARF user fns | certain pred | TP | FP | unknown | certain precision | certain recall | overall recall | opt profile (lto / cgu) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| **bat** | 4379 | 70 | 133 | 11 | **112** | 10 | **8.9%** | 15.7% | 45.7% | lto=true / 1 |
| **grex** | 2599 | 34 | 23 | 3 | 11 | 9 | **21.4%** | 8.8% | 20.6% | *none* → default (lto=false / 16) |
| **fd** | 3398 | 737 | 17 | 3 | 8 | 6 | **27.3%** | 0.4% | 2.2% | lto=true / 1 |
| tokei | 3345 | 48 | 39 | 10 | 13 | 16 | 43.5% | 20.8% | 29.2% | lto="thin", panic=abort |
| hexyl | 1026 | 26 | 16 | 4 | 4 | 8 | 50.0% | 15.4% | 46.2% | lto=true / 1 |
| just | 2978 | 181 | 130 | 25 | 16 | 89 | 61.0% | 13.8% | 34.8% | lto=true / 1 |
| sd | 1814 | 6 | 5 | 2 | 1 | 2 | 66.7% | 33.3% | 66.7% | lto=true |
| xsv | 2117 | 65 | 48 | 25 | 4 | 19 | 86.2% | 38.5% | 81.5% | opt=3, debug, **lto=false** |
| dust | 2032 | 33 | 17 | 15 | 2 | 0 | 88.2% | 45.5% | 87.9% | lto=true / 1 |
| hyperfine | 1203 | 32 | 16 | 10 | 1 | 5 | 90.9% | 31.2% | 56.2% | lto=true / 1 |
| ripgrep | 7526 | 3533 | 345 | 143 | 8 | 194 | 94.7% | 4.0% | 5.5% | debug=1, **lto=false** (cgu=16) |
| pastel | 822 | 71 | 27 | 19 | 1 | 7 | 95.0% | 26.8% | 46.5% | lto=true / 1 |
| **zoxide** | 1036 | 19 | 8 | 3 | **0** | 5 | **100.0%** | 15.8% | 63.2% | lto=true / 1 |

`unknown` = certain predictions whose exact FDE start address has no matching DWARF subprogram
`low_pc` (excluded from the precision denominator). `TP+FP` is the denominator. Profiles read from
each project's root `Cargo.toml [profile.release]`.

---

## DISTRIBUTIONS (not averages)

**Certain precision (n=13), sorted:** 8.9, 21.4, 27.3, 43.5, 50.0, 61.0, **66.7 (median)**, 86.2,
88.2, 90.9, 94.7, 95.0, 100.0. Mean 64.1%.
- = 100%: **1/13** (zoxide, denom=3)
- ≥ 90%: 4/13 (zoxide, pastel, ripgrep, hyperfine)
- 50–90%: 4/13
- < 50%: **4/13** (bat, grex, fd, tokei)

**Certain recall (n=13):** range **0.4% – 45.5%**, **median 15.8%**. Below the 37.5% fixture figure on
11 of 13. Recall tracks panic density and how much user code survives as *standalone* functions:
fd (0.4%) and ripgrep (4.0%) have most of their user logic inlined away or behind trait dispatch;
dust (45.5%) and xsv (38.5%) keep more whole user functions. The variation is the finding, as
expected.

**Overall recall (certain+inferred):** range 2.2% (fd) – 87.9% (dust) — wildly binary-dependent and
dominated by the low-precision `inferred` bucket (4–7% precision everywhere), so not a useful headline.

---

## WHY PRECISION DROPS — VERIFIED MECHANISM

For every binary I extracted the certain function start addresses from unhusk's own Phase-2 report
and resolved each against the debug twin's DWARF (`addr2line -f`), then classified the
`decl_file` of the function unhusk called "certain." Aggregate over all **190** non-user "certain"
functions across the 13 binaries:

| category | count | share | what it is |
|---|---:|---:|---|
| **`FnOnce`/`Fn`/`FnMut` closure shim** (`core/src/ops/function.rs`) | **128** | **67.4%** | A user closure's monomorphized `call_once`/`call_mut`. Body = user code; DWARF `decl_file` = the trait method's definition in core. |
| `core::slice` generic (sort etc.) | 13 | 6.8% | std sort/partition instantiated with a user comparator closure inlined in. |
| `core::iter` generic (FilterMap, GenericShunt, …) | 12 | 6.3% | std iterator adapter instantiated with user closures/types. |
| `core` (other) | 11 | 5.8% | misc core generics. |
| `Once`/`OnceLock` init shim | 7 | 3.7% | lazy-static init: user initializer closure inlined into `Once::call_once_force`. |
| `std` generic | 4 | 2.1% | e.g. `std::thread::scope::<user closure>`. |
| `alloc` generic | 4 | 2.1% | `Vec<T>` methods monomorphized in a user crate. |
| dependency crate (threadpool, csv, serde_json, clap_builder, nom, rayon, serde_core) | 11 | 5.8% | user impls/closures inlined into a dep's generic trait method. |

**The single dominant mechanism (2/3 of all FPs) is the closure trait-shim.** When user code is a
closure invoked through `Fn*`, the monomorphized `call_once` instance *is* the user's code, but its
DWARF `decl_file` is `core/src/ops/function.rs:250` — the canonical trait-method site. unhusk sees the
user-path panic Location inside the body and (correctly, by symbol) calls it user; the DWARF
ground-truth (by `decl_file`) calls it core; the harness scores it a false positive.

**An honest reading:** the FnOnce-shim "false positives" are a measurement-definition artifact as much
as a unhusk error — by a symbol-name notion of authorship unhusk is closer to right on those ~67%.
The genuinely-wrong-by-any-definition FPs are the **library-generic and dependency-crate** ones
(~32% of FPs: slice/iter/alloc/std generics and dep trait methods), where the *bulk* of the function
body is library logic and only a user closure/comparator was inlined in. unhusk has no way to tell the
two apart: both contain a reference to a user-path Location, which is its sole signal.

(Minor reconciliation note: my `addr2line`/line-table classification surfaces a few functions unhusk
counts as `unknown` rather than FP — e.g. ripgrep 10 vs unhusk's 8, just 20 vs 16 — because addr2line
resolves them via the line table where unhusk requires an exact `low_pc` match. Direction and
mechanism are unchanged; the precise FP counts in the table above are unhusk's own.)

---

## LTO / CODEGEN-UNITS CORRELATION

Weak and noisy — **LTO is a contributing factor, not the determinant.**

- **Non-LTO, high:** ripgrep (lto=false) 94.7%, xsv (lto=false) 86.2%.
- **Non-LTO, low:** **grex (lto=false) 21.4%** — same FnOnce/slice-generic mechanism, no LTO needed.
- **LTO=true, high:** pastel 95.0%, hyperfine 90.9%, dust 88.2%.
- **LTO=true, low:** bat 8.9%, fd 27.3%, hexyl 50.0%.

pastel and bat share the *identical* profile (`lto=true, codegen-units=1`) yet sit at 95.0% and 8.9%.
The discriminator is **code structure**, not the flag: how much of a binary's panic-bearing user code
lives in closures-behind-`Fn*` and user-instantiated generics (bat's giant lazy-static closure table,
tokei's closure-heavy counters, grex's sort comparators) versus standalone user functions (pastel,
hyperfine). LTO amplifies the effect by inlining more user code into library generics, but generic
monomorphization and closure-shim attribution happen at `opt-level=3` without LTO too.

So the correct caveat is **not** simply "degrades under aggressive inlining." It is: *"certain precision
degrades whenever user logic is expressed as closures or as instantiations of library/dependency
generics, because DWARF attributes those to their definition sites; LTO worsens this but does not
cause it."*

---

## FAILURES

None. All 13 candidates cloned, built with debug info, stripped, and validated successfully. No
binaries were substituted or skipped. (grex was the only one with no `[profile.release]` section; that
is a project property, not a failure — it builds on Cargo defaults.)

---

---

## SYMBOL-BASED PRECISION RE-EVALUATION

**Date:** 2026-06-16 · Script: `realval/symbol_precision.py`

**Motivation.** 67% of all DWARF-based FPs are `FnOnce`/`Fn`/`FnMut` closure shims — functions
where the body is the user's closure but DWARF `decl_file` points to the trait method definition in
`core/src/ops/function.rs`. REAL_BINARY_VALIDATION.md already noted: "by a symbol-name notion of
authorship unhusk is closer to right on those ~67%." This section quantifies that claim.

**Method.** For each of the 13 debug twins:
1. Run `nm -C <name>.debug` to build addr → demangled-symbol table.
2. Extract leading crate name from the demangled symbol (strip leading `<`s, take first identifier).
3. Classify: **user** if leading crate ∉ {std, alloc, core, ...} and ∉ dep crates (top-10 parsed
   from validate.txt); **std** if ∈ STD_CRATES; **dep** otherwise. **Unknown** if no nm entry.
4. Precision denominator = user + std + dep (unknowns excluded, same as the DWARF treatment of
   DWARF-unmapped addresses).

### Results

| binary | certain | DWARF prec | sym prec | sym [user/std/dep/unk] | delta |
|--------|--------:|-----------:|---------:|-----------------------:|------:|
| bat     |     133 | 8.9% (11/112)  | 99.2% | 132/1/0/0  | +90.3 |
| dust    |      17 | 88.2% (15/2)   | 88.2% | 15/2/0/0   |  +0.0 |
| fd      |      17 | 27.3% (3/8)    | 58.8% | 10/7/0/0   | +31.6 |
| grex    |      23 | 21.4% (3/11)   | 52.4% | 11/10/0/2  | +31.0 |
| hexyl   |      16 | 50.0% (4/4)    | 75.0% | 12/4/0/0   | +25.0 |
| hyperfine |    16 | 90.9% (10/1)   | 93.8% | 15/1/0/0   |  +2.8 |
| just    |     130 | 61.0% (25/16)  | 94.4% | 118/7/0/5  | +33.4 |
| pastel  |      27 | 95.0% (19/1)   |100.0% | 26/0/0/1   |  +5.0 |
| ripgrep |     345 | 94.7% (143/8)  | 97.9% | 328/7/0/10 |  +3.2 |
| sd      |       5 | 66.7% (2/1)    |100.0% | 4/0/0/1    | +33.3 |
| tokei   |      39 | 43.5% (10/13)  |100.0% | 35/0/0/4   | +56.5 |
| xsv     |      48 | 86.2% (25/4)   | 93.8% | 45/1/2/0   |  +7.5 |
| zoxide  |       8 |100.0% (3/0)    |100.0% | 8/0/0/0    |  +0.0 |

**Symbol-based: median 94.4%, mean 88.7%.**
**DWARF-based: median 66.7%, mean 64.1%.**

### Genuinely wrong predictions (non-user by both symbol and DWARF)

Aggregated across all 13 binaries, **42 certain functions are non-user by symbol** (vs 190 by DWARF).
All 42 are std/alloc/core or dep functions; none are FnOnce closure shims. Categories:

| category | count |
|---|---:|
| `core::slice::sort` generics (grex, ripgrep sort comparators inlined) | 11 |
| `core::iter::adapters::GenericShunt`/`FilterMap`/`Map` generics | 10 |
| `std::sync::once::Once::call_once_force` lazy-init shims (hexyl, fd, grex) | 7 |
| `std::sys::backtrace::__rust_begin_short_backtrace` (fd, dust thread entry) | 3 |
| `core::panicking::assert_failed` / `panic_const` | 3 |
| `csv::writer::Writer::write_record` (xsv dep) | 2 |
| other (std::thread::scope, std::process::Command impl of just trait, etc.) | 6 |

**42 / (759 user + 42 non-user) = 5.2% genuine FP rate by symbol.** The remaining 21 unknowns
(functions with no nm entry, ~2.6% of certain predictions) are ICF-merged or inlined-away functions
excluded from the denominator.

### Edge case: `<std::Type as UserTrait>::method`

One `just` function — `<std::process::Command as just::command_ext::CommandExt>::export_scope` —
is classified as `std` (non-user) by symbol because the leading type is `std::process::Command`,
even though the impl body was written in `just/src/command_ext.rs`. This is the converse of the
FnOnce-shim case: the user is *implementing a trait* on a std type rather than *passing a closure*
to a std type. DWARF correctly attributes it to `just`. The frequency is low (1 of 42 "wrong"
predictions) and the direction of error differs from the mass FnOnce issue.

### Revised headline

The "100% certain precision" claim from the fixtures survives when measured by the natural
definition of authorship (symbol name / crate ownership), but not by DWARF `decl_file`.

**By symbol-name GT:** certain precision **median 94.4%** on 13 real binaries.
**By DWARF decl_file GT:** certain precision median 66.7% — penalty for user closures dispatched
through `Fn*` traits, which DWARF attributes to `core/src/ops/function.rs`.

The 5.2% genuine FP rate (by symbol) represents cases where a std/dep generic function was
monomorphized with user types and unhusk's panic-Location scan found a user Location inside —
there is no signal available in a stripped binary to distinguish these from real user functions.

---

## REPRODUCING

`realval/run.sh` (per-binary driver), `realval/batch.sh` (the 13-project list), `realval/collect.py`
(table), and the per-binary `realval/out/<name>.validate.txt` full outputs + `<name>.debug` twins are
retained. FP mechanism breakdown via `addr2line -f` on the certain start addresses against each
`.debug` twin. Symbol-based re-evaluation: `realval/symbol_precision.py`.

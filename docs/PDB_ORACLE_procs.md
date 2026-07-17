# PDB oracle — first real double-built measurement (procs)

**Status:** measurement, session 2. The first Windows precision number that means
anything. Reported honestly; the session-1 authorship rule + PE guards were NOT
tuned to it. Companion to `docs/pe-port-design.md` §9 and the session-1 reader
(`src/pdb_oracle.rs`).

**Headline:** STRONG-tier precision on procs = **9/9 = 100 %**, all sync, **n = 9**.
But the case this session existed to stress — user code inlined into a library
function, and async precision — **did not occur on procs**. The 100 % is a real
result on a small sync sample, not evidence the tool avoids the false-positive
case. See §4–5.

---

## 1. Target and why

`procs` v0.14.12 — a cross-platform process viewer. Picked from the ELF corpus as
the one async candidate that cross-compiles cleanly to `x86_64-pc-windows-msvc`
via `cargo-xwin`: no `ring` / `openssl-sys` / `aws-lc-sys` / `native-tls` in its
lock (every network-async candidate — oha, dufs, bandwhich, miniserve — pulls
one). It carries `windows-sys` with a large feature set, so it has genuine
Windows syscall code paths, and it links `tokio` + `hyper` + `dockworker` through
its default `docker` feature (the framework/async surface).

Genuine user code confirmed: unhusk recovers **34 User `Location`s** in procs'
own files (`src/main.rs`, `src/process/windows.rs`, `src/columns/*.rs`, …),
embedded as relative `src/…` paths → classified User.

## 2. The double build — and a real finding

Two builds, intended to differ only in debug info:

```
[profile.oracle]   inherits="release", debug=2, strip=false   → procs.exe + procs.pdb
[profile.stripped] inherits="release", debug=0, strip=true     → procs.exe
```

Both inherit `lto=true, codegen-units=1`, opt-level 3, panic=unwind.

**FINDING — under LTO, debug=0 and debug=2 are NOT byte-identical.** The two
separate compiles differ in code layout:

| section | oracle (debug=2) | stripped (debug=0) |
|---------|------------------|--------------------|
| `.text` size | `0x2f08f6` | `0x2efe36` (~43 KB less) |
| `.pdata` size / VMA | `0x17fa0` / `0x1403e1000` | `0x18000` / `0x1403e0000` |

This differs from the session-1 toy probe, where `debug=false` vs `debug=2` were
byte-identical. With fat LTO, debug-info presence perturbs
import/inline/layout decisions enough to move `.text`. **So a debug=2 PDB cannot
be an oracle for a *separately compiled* debug=0 binary — the RVAs do not line
up.** (design §9 / the session preconditions call for stopping here.)

**Resolution — strip the debug=2 image.** The wild binary is the `oracle` build
with symbols stripped (`llvm-strip`), not a fresh debug=0 compile. Same linked
image ⇒ `.text`/`.pdata` **byte-identical by construction** (verified: md5
`8ebdbf53…` / `200e0d17…` match between the stripped copy and the oracle exe).
This is a real-world-faithful pairing: ship a stripped exe, keep the PDB for
symbolication. unhusk reads only `.pdata`/`.reloc`/`.rdata`/`.text` and has no
PDB code path, so no oracle information leaks into attribution — the stripped
exe still carries a (harmless, unread) CodeView directory entry.

**Precondition 1 (RVA validity): PASS** — `.text` and `.pdata` identical between
the binary unhusk attributes and the binary the PDB describes.

## 3. Scale

| | |
|---|---|
| unhusk `.pdata` function ranges | **8184** |
| unhusk certain (user-anchored) | 19 — **STRONG 9**, SINGLE 10 |
| oracle procedures | 3375 (**126** User) |
| match kinds (containment) | exact 2976 / **fragment 5159** / none 49 |

**63 % of unhusk's ranges are `.pdata` fragments** of larger functions (session 1
saw 21 % on the toy). The session-1 containment matcher (`MatchKind::Fragment`)
was load-bearing here: start-only matching would have discarded 5159 rows.

## 4. STRONG-tier precision — THE number

Of the 9 functions unhusk marks STRONG, the oracle confirms **all 9** as User.
**Precision = 9/9 = 100 %** (n = 9). Every SINGLE-tier function is also
oracle-User, so certain precision is 19/19 across tiers.

| STRONG function (oracle name) | anchors | sites |
|---|---|---|
| `procs::get_config` | 3 | main.rs:93/97/98 |
| `procs::run` | 2 | main.rs:181/202 |
| `procs::view::View::new` | 5 | view.rs + **process/windows.rs** |
| `procs::view::View::display` | 3 | view.rs |
| `procs::term_info::TermInfo::write_line` | 2 | term_info.rs:40 |
| `procs::util::format_sid` | 3 | util.rs:287 (×3 distinct structs) |
| `procs::columns::tree::…::gen_root` | 2 | columns/tree.rs |
| `procs::columns::gid::…::add` | 2 | columns/gid.rs |
| `procs::columns::tree::…::display_content` | 2 | columns/tree.rs |

**sync vs async split: sync n = 9 / async n = 0.** There are **0** async-looking
User procedures in the oracle at all (no `procs::` `poll`/`Future`/`async`
functions survive as User-decl). procs' async is docker-only and lives in
`dockworker` (Dep). So the async-precision figure is **not measurable on procs**.

**Nuance worth recording:** `format_sid`'s 3 anchors are 3 *distinct* `Location`
structs all resolving to `util.rs:287` — one source-level panic monomorphized
several ways, not 3 distinct source panics. STRONG's "≥2 distinct user Locations"
can be reached by monomorphization multiplicity of a single panic site. The
oracle still confirms User, so precision holds, but STRONG multiplicity is not a
proxy for "distinct source panic sites".

## 5. The false-positive case — 0, and why that is NOT a validation

FPs (unhusk certain-User, oracle Std/Dep): **0**, any tier. Confirmed by the
library's tested `compare()` — the FP direction is 0; all 924 disagreements are
the recall direction (§6).

**But the FP mechanism was never available on procs.** Counting library-decl
(Std/Dep) oracle procedures whose range contains a user `Location`: **0**. The
optimizer, under LTO + opt-level 3, inlines library generics *into* their user
callers (which are then correctly User-attributed) rather than leaving library
functions that absorb user closures. So the "user code inlined into a library
function" case — the entire reason this crate needed async/framework code —
**structurally did not occur**. Zero FPs here is *absence of the case*, not
evidence the authorship rule rejects it correctly.

**This is the session's central caveat.** The async/inline-into-library
precision question that motivated the PDB oracle is still open after procs.

## 6. Recall misses (expected, not errors)

Oracle-User procedures unhusk did not mark certain: **107 of 126** by exact
start (924 counted over fragments). This is the safe direction — a user function
that references no user `Location` (no `unwrap`/index/`panic!` on a user path)
gives unhusk nothing to anchor on, so it correctly declines rather than guessing.
Recall is not this pipeline's claim; precision is.

## 7. Decision discipline

The authorship rule and the two PE-path guards are exactly as committed in
session 1. Nothing was changed to reach 100 %. A low number would have been a
tool property or an oracle bug to diagnose, never a reason to retune; a high
number on a sample that doesn't exercise the hard case is reported as exactly
that.

## 8. What the next session needs

procs was cross-compile-clean but async-thin, so it cannot answer the async
question. The next crate must **actually produce surviving library functions with
inlined user code** — i.e. genuine async state machines (tokio/hyper poll fns)
and heavy combinator use where user closures land inside library monomorphizations
that don't fully inline away. That likely means paying the `ring`/rustls
cross-compile cost (dufs is the lightest such candidate: rustls, no openssl).
Until then, the async-precision figure is **unmeasured**, not 100 %.

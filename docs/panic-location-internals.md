# `core::panic::Location`: compiler mechanics and their forensic consequences

## Summary

Every reachable `panic!`, `.unwrap()`, bounds check, and overflow check in a Rust binary carries
a `core::panic::Location` — a small struct naming the source file, line, and column the check
was written at. This data is not debug info. It is a compiled-in value, referenced by ordinary
data relocations, and it survives `strip` because `strip` only removes the *symbol table* — it
has no concept of "this pointer happens to name a source location" and nothing to remove. That
single fact is the entire reason panic metadata is usable as a stripped-binary recovery
primitive at all.

This document is the compiler-side half of that story: how a `Location` value comes to exist,
what rustc merges versus duplicates versus discards along the way, and — for each of those
behaviors — what it implies about what you can and can't trust when reconstructing structure
from the result. None of this is Rust-version trivia; it is the causal explanation for
observables analysts already run into empirically (why some panic sites appear to "belong" to
the wrong function, why the same file path can show up dozens of times, why one build of the
same crate looks structurally different from another). The goal is to replace "the compiler
just does that" with an actual mental model, so heuristics can be built on what rustc guarantees
rather than on what a handful of samples happened to look like.

## 1. What gets embedded, and why it survives stripping

`core::panic::Location<'a>` is a plain, `#[repr]`-stable struct: a fat pointer to a filename
string, plus a line and a column, three fields, twenty-four bytes on a 64-bit target. It is not
attached to DWARF, not listed in `.symtab`, and not gated behind any debug-info flag — it exists
in a fully-stripped release binary exactly as much as in a `-g` build. The only thing debug
builds add on top is the *separate* DWARF line-table machinery; panic-`Location` is a parallel,
independent mechanism that ships unconditionally, because it has to: `panic!("...")` needs to
print `panicked at src/main.rs:42` in a release binary with no debug info at all.

Mechanically, a `Location` is compiled as an anonymous constant: a `(pointer, len, line, col)`
tuple placed in read-only or relocation-read-only data, referenced from code by the address of
that constant. There is no separate "panic table" section and no fixed layout convention beyond
what LLVM emits for any private constant global — this is why locating them is a search-and-xref
problem rather than a parse-a-known-section problem.

## 2. The one choke point: a source span becomes a value

Every consumer of panic-location data — both codegen backends and the const evaluator used for
compile-time panics — funnels through a single compiler function that turns "a span of source
text" into "a resolved (filename, line, column) triple." There is exactly one such function in
the entire compiler; nothing downstream reimplements span resolution.

Two details of that resolution matter for reading the result:

- **Macro-hygiene substitution is deliberate.** Before resolving any position, the compiler
  walks *up* the macro-expansion chain to the outermost user-visible call site. This is why a
  `panic!()` invocation — which itself expands into a call to an internal formatting/unwind
  helper — reports the line where the user wrote `panic!(...)`, not some line inside the macro's
  own expansion. The practical consequence: the Location value you recover always points at
  *call-site* source text, never at macro-internal plumbing, even though the actual function
  being called at the machine level is deep inside `core`/`std`.
- **The filename is a *display* string, not a filesystem path lookup.** It's produced by the
  same machinery that honors `--remap-path-prefix`, because the string is meant to be
  reproducible and redaction-aware across machines. See §5 — this is not a cosmetic detail, it's
  the reason path-prefix-based classification is trusting an assertion, not verifying a fact.

## 3. Two independent identities: the string versus the struct

This is the single most consequential distinction for anyone counting or grouping panic sites.

**Filename bytes are unconditionally, content-keyed merged.** The compiler interns byte strings:
if two `Location`s end up with byte-identical (already-remapped) filenames, they are guaranteed
to reference the *same* underlying string allocation — this merge is unconditional and applies
across the whole compilation unit, not scoped to a function or module. This is exactly what
makes "group panic-struct referrers by which filename they point at" a sound signal: a real
compiler-level many-to-one relationship, not a coincidence of a particular sample.

**The `Location` struct itself is never merged at the identity level — by explicit design.** Each
call site that needs a `Location` gets its own freshly minted allocation for the struct, even
if two call sites happen to share the same file, line, and column (rare, but not impossible with
generated or macro-repeated code). The compiler's own allocation-identity code states outright
that two allocations with identical bytes still get different identities, because "they are
different places in memory." Underneath that, there is an *incidental* byte-level interning step
that can make identical-content structs share the same underlying storage object — but that is a
storage optimization, not an identity merge, and by the time you're looking at object-file bytes
it has already been overtaken by the mechanism in §4, which is the one that actually governs what
you observe in a compiled artifact.

Net effect: expect **many distinct filename references pointing at one string**, and **one
struct allocation per call site** as the starting design intent — but read §4 before treating the
second half of that as a hard guarantee at the disassembly level.

## 4. The dedup boundary that actually matters: per codegen-unit, not whole-program

This is the one most likely to surprise someone reasoning from "the compiler surely merges
identical constants globally."

Constant deduplication in codegen — the step that decides whether two `Location` structs with
byte-identical content end up as the *same* physical global object in the compiled output, or as
two separate ones — is keyed on the reconstructed target-IR constant value, and the cache doing
that keying is created **once per codegen unit**. Within one codegen unit, identical `Location`
constants are guaranteed to merge into a single global. Across codegen units, there is no such
cache in rustc at all — two codegen units that each independently need a byte-identical `Location`
will each emit their own private, unnamed global for it. Those globals are deliberately marked
with linkage that makes them *eligible* for later folding by an LTO pass or a linker's
identical-code-folding step, but rustc does not perform or guarantee that folding itself.

For an analyst, this converts directly into an expectation about build configuration:

- **Default multi-codegen-unit release builds** (the common case for `cargo build --release`
  without further tuning) will show comparatively more distinct struct globals for what is
  conceptually "the same" location, roughly tracking codegen-unit boundaries, which in turn
  roughly tracks source-module boundaries.
- **`codegen-units=1` or LTO builds** collapse far more aggressively — either because there was
  only ever one codegen unit to begin with, or because a post-rustc merge pass had the chance to
  fold cross-unit duplicates. Fan-in counts, "how many distinct call sites reference this
  function," and similar structural signals measured on an LTO'd binary are not directly
  comparable to the same measurement on a non-LTO binary of the same source — the difference can
  be a build-configuration artifact rather than a code-structure difference.

This is worth checking explicitly (codegen-units, LTO flags, or their absence) before treating a
struct-level merge/no-merge pattern as evidence of anything about the source.

## 5. The filename string is an assertion, not a verified fact

Because the embedded filename comes from span-resolution machinery that explicitly honors
path-remapping, the string in the binary is whatever the *build* chose to say, not a fact
independently checked against any real filesystem. Two consequences follow directly:

- **Ordinary reproducible-build pipelines routinely remap paths.** A CI system building with
  `--remap-path-prefix` will produce filenames that don't correspond to any path that ever
  existed on the machine that compiled the code. This is normal and not itself suspicious.
- **Nothing later in the pipeline re-validates the string.** The remap happens once, at span
  resolution, and every subsequent stage (allocation, interning, codegen, object-file emission)
  treats it as opaque bytes. A build script — including one an adversary controls — can cause
  author-written code to embed a filename shaped like a well-known open-source dependency's path
  convention (or the reverse: make vendored/dependency code look like first-party source), purely
  by choosing what string to remap to. Path-prefix classification (first-party vs. dependency vs.
  standard library, by directory-shape convention) is reading the *compiler's* stated opinion of
  where the code came from, and that opinion is exactly as trustworthy as the build environment
  that produced the binary. Treat a classification built on this signal as a strong prior for
  cooperative/non-adversarial builds and as a spoofable channel when the build pipeline itself is
  hostile.

## 6. `#[track_caller]`: why the visible reference moves to the caller

`#[track_caller]` functions do not embed a `Location` for their own panics at all. Instead, the
function's ABI gains one extra trailing argument — a pointer, passed like any other argument —
and the *caller* is responsible for supplying it. At the call site, the compiler decides between
two behaviors: **synthesize** a fresh `Location` for that call (the normal case, when the caller
is not itself `#[track_caller]`), or **forward** the location the caller itself already received
as its own extra argument (when the caller is *also* `#[track_caller]`, chaining the obligation
one level further out). This decision is resolved purely from the call/inlining scope chain, at
the point a `Location` value is actually needed — nothing about it changes what MIR looks like
structurally.

The consequence generalizes past the single-hop case: an arbitrarily long chain of
`#[track_caller]` helper functions — a custom `ensure!()`-style macro built on a shared
validation helper, itself called by another shared helper — never contributes its own struct
reference at any point in the chain. The visible `Location` reference lives entirely at the
first frame, walking outward, that is *not* itself `#[track_caller]` (or, if the whole chain got
inlined into one function, at whatever call site remains after inlining). Every function strictly
between "the actual `panic!`" and "the first non-`#[track_caller]` caller" is structurally
invisible to a direct-reference scan — it neither allocates nor references a `Location` of its
own; it only ever receives one as an incoming argument. This is not a rare edge case: it is the
mechanism behind ordinary, idiomatic shared assertion/validation helpers, and it means the
function that *contains* the panic and the function that shows up as the panic's *anchor* in a
disassembly-level scan are routinely different functions.

Trait default methods add one more wrinkle worth knowing: if a trait method's declaration (not
its implementations) carries `#[track_caller]`, every implementation silently inherits the ABI
obligation, with no compile-time check that the implementer intended it. A mismatch between what
a trait promises and what a concrete `impl` does is resolved invisibly, later, only when a
vtable entry actually needs populating (§7) — so the calling convention of a concrete method may
not be predictable from that method's own attributes in isolation.

## 7. Indirect calls: small forwarding stubs are an ABI artifact, not obfuscation

Two situations force the compiler to insert a tiny, otherwise-empty forwarding function:
coercing a `#[track_caller]` function item to a bare function pointer, and populating a
trait-object vtable slot for a method whose concrete implementation adds `#[track_caller]` that
the trait's own signature didn't promise. In both cases, a plain function pointer or vtable slot
has no room to say "and also pass an extra Location argument," so the compiler generates a shim:
a single opaque call that exists purely to reconcile the two calling conventions. The shim's body
does nothing else — no branching, no computation, just a forward.

If you encounter a very small function near a vtable or a function-pointer table whose only
content is a single forwarding call with no distinguishing logic, this ABI-reconciliation shim is
a mundane and common explanation, distinct from packer stubs, trampolines, or hand-written
indirection — and it is generated purely from type-level reasoning at compile time, with no
run-time or obfuscation-related origin.

## 8. Instruction shape is a backend artifact, not compiler-side logic

Whether the machine code that references a `Location` struct's address shows up as a
RIP-relative load (`lea reg, [rip+disp]`) or a bare absolute immediate (`movabs $addr, reg`) is
decided entirely by the target backend's handling of "take the address of a private global,"
under the prevailing relocation model (position-independent vs. not). Nothing in the
`Location`-specific compiler machinery branches on relocation model at all — the same abstract
"address of this constant" step feeds both PIE and non-PIE code generation, and the difference in
resulting instruction encoding is a generic backend/target concern, unrelated to panic metadata
specifically. Practically: any scan built to find `Location` references by instruction shape has
to account for both forms, because the underlying data and its role in the binary are identical
either way — only the addressing-mode encoding differs, and it differs for *every* private
constant reference in the binary, not just panic locations.

## 9. The one deliberate discard point, and the total-blindness extreme

Exactly one flag in the entire pipeline deliberately throws away provenance: an unstable
compiler option that can redact the filename to the literal string `"<redacted>"` and zero out
line and column independently. This is a real, recognizable output — seeing that literal
sentinel string means the build pipeline deliberately chose it, not that the recovery approach
failed or the data is corrupted. Because the flag is nightly-only, its presence is itself a signal
about how the toolchain producing the binary was configured (an ordinary stable-toolchain release
build cannot produce it).

At the far end of the spectrum, an unstable panic strategy paired with a from-source standard
library build removes panic infrastructure at a much coarser grain: message text and location
data disappear together, and every panic site collapses to a bare trap instruction with nothing
left to recover — not a redacted placeholder, but no site at all. This, too, requires an
unusual, deliberately-configured nightly toolchain rather than anything reachable from a default
`cargo build --release`.

## 10. What optimization passes never do

Worth stating explicitly, because it underwrites the trustworthiness of everything above: no MIR
optimization pass — inlining aside, which only *transports* existing span/scope information, never
manufactures it — ever computes, folds, or forges a `Location` value. Constant-propagation,
value-numbering, and jump-threading passes all treat a call's result (including a `&'static
Location` reference) as fully opaque data, subject to the same generic copy/CSE treatment as any
other pointer-sized value, never specially reasoned about. And provably-unreachable code paths —
exhaustiveness-checked match fallbacks, never-patterns — generate no `Location` and no panic
machinery at all, because the compiler has already proven they can't execute; a missing panic
site on such a path is a compiler decision made **before** codegen even starts, not a gap in
whatever recovery approach is being used.

## Cheat sheet

- **Filenames merge globally, structs don't (by default).** A shared filename string with many
  distinct referring structs is a real, structural fan-in signal. A shared *struct* across call
  sites is not something to expect outside of LTO/single-CGU builds.
- **Struct-level merging is a build-configuration artifact, not a source-code one.** Compare
  fan-in/anchor counts only between binaries built with comparable codegen-unit/LTO settings.
- **The filename string is what the build claims, not a filesystem fact.** Path-prefix
  classification is reading compiler-recorded intent, and it degrades gracefully against
  ordinary reproducible builds but is a real evasion surface against a hostile build pipeline.
- **`#[track_caller]` chains make the true panic site and the visible anchor different
  functions, by design, for any depth of shared-helper wrapping.** The anchor always lands on the
  first non-`#[track_caller]` frame outward, not on the function that lexically contains the
  `panic!`.
- **Tiny opaque forwarding functions near vtables/fn-pointer tables are routinely ABI shims**,
  not obfuscation, generated purely from type-level reasoning.
- **`lea [rip+..]` vs `movabs` is a relocation-model artifact, universal to all private-constant
  references** in the binary, not something specific to panic data — a recovery approach has to
  handle both, and doing so buys nothing beyond what it already needed for full PIE/non-PIE
  coverage.
- **`"<redacted>"` and all-zero line/col are a real output**, not corruption — and imply an
  unstable-toolchain build.
- **No optimization pass ever fabricates a `Location`.** A reference you find really does trace
  back to a real, distinct compile-time call site — never a compiler-synthesized artifact — and a
  panic site absent from a provably-unreachable path is expected, not a detection gap.

---

*Traced against the rust-lang/rust compiler source: attribute parsing and lang-item registration
(`rustc_attr_parsing`, `rustc_hir`), the span-to-value nexus and lang-item plumbing
(`rustc_middle`), MIR construction (`rustc_mir_build`), MIR transform passes
(`rustc_mir_transform`), constant allocation and interning (`rustc_const_eval`), and codegen
emission for both the LLVM and Cranelift backends (`rustc_codegen_ssa`, `rustc_codegen_llvm`,
`rustc_codegen_cranelift`).*

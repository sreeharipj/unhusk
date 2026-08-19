# Exploratory: attempting a compiler-internals-grounded RULE_D

Prompted by a request to read `~/Videos/rustc_doc/panic_location_lifecycle/
LOCATION_LIFECYCLE.md` (a from-source trace of `core::panic::Location`
through rustc, commit `701a6513a48eac30d49110ba06187648b7553622`) and attempt
a genuinely new decision rule grounded in an actual compiler mechanism —
not a threshold tweak on RULE_A/B/C. **Conclusion up front: no viable rule
was found.** What follows is why, mechanistically, rather than a rule.

## The one mechanism that looked promising

`LOCATION_LIFECYCLE.md` §7.2 (`get_caller_location`, `rustc_codegen_ssa/src/
mir/block.rs:2138-2147`) describes a binary decision every `#[track_caller]`-
relevant call site resolves at codegen time, by walking the MIR inlining
chain (`SourceScopeData::inlined`, populated unconditionally by
`inline.rs::Integrator::visit_source_scope_data`, §8):

- **forward** — reuse the enclosing function's own already-received
  `Location` argument (a register/stack-slot value), when every inlined
  frame between the call site and the function boundary is itself
  `#[track_caller]`.
- **synthesize** — call `span_as_caller_location(span)` fresh, using the
  *innermost non-`#[track_caller]` inlined frame's own span* — i.e., when a
  library function (not itself `#[track_caller]`) inlines a user closure,
  and that closure's own panic/assert site is reached, the Location gets
  synthesized from the **closure's own source span**, and the resulting
  static reference to that Location constant physically ends up inside the
  *library function's* compiled byte range (its FDE), because that's where
  the inlined code now lives.

This is the FP mechanism `architecture.md`'s "hard case" describes, named
precisely: a monomorphized library generic (`sort_by`, a rayon combinator)
inlines a user closure; the closure's panic site synthesizes a Location from
the user's own file/line; that reference lands inside the library
function's FDE because MIR inlining merged the two bodies before codegen
ever ran. The classifier this whole branch measures (`src/origin.rs`) sees
exactly one symptom of this — a Location whose path classifies `user` sitting
in an FDE that also references other, non-`user` Locations (RULE_A) or that
doesn't get corroborated by enough distinct `user` Locations (RULE_B/C's `N`)
— but has no way to see the *forward-vs-synthesize decision itself*, because:

## Why it can't be recovered from a stripped binary

1. **MIR inlining merges basic blocks before codegen runs.** By the time
   `rustc_codegen_ssa`/`rustc_codegen_llvm` emit machine code, the inlined
   closure's instructions and the library function's own instructions are
   one flat sequence with a single `TerminatorKind`-derived control-flow
   graph. There is no LLVM-IR-level, let alone final-object-level, boundary
   marker separating "this instruction originated from an inlined frame"
   from "this instruction was always part of the enclosing function." The
   `.eh_frame` FDE this measurement's whole classifier operates on covers the
   *entire* merged function as one contiguous `[start, end)` range — by
   construction, not as a limitation of any particular parser.
2. **The inline-site information that *does* exist (`SourceScopeData::
   inlined`) is a `rustc_middle::mir::Body` field — compiler-internal,
   erased at codegen.** Its closest binary-level analogue, DWARF
   `DW_TAG_inlined_subroutine` / a PDB inline-sites stream, requires debug
   info. `architecture.md`'s own PE-side work (`docs/PDB_ORACLE_hardcase.md`)
   used exactly that — the PDB inline stream — to *corroborate* the hard
   case two independent ways, but that was on an unstripped-with-PDB build.
   unhusk's stated target is "a stripped Rust release binary, no symbols, no
   debug info" (`architecture.md`'s opening line); a malware author strips
   this by definition, so an inline-site oracle is not available in the
   actual threat model, only in a research corroboration step.
3. **The "forward" case, when it does apply, produces no new static
   reference at all** — it's a register/stack-slot value already present in
   the function's own incoming arguments, not a fresh RIP-relative load of a
   `.data.rel.ro` constant. This has a real, checkable consequence, not just
   a theoretical one: this pilot's own measurement found **80.0% of
   ground-truth AUTHOR FDEs reference zero Locations of any class**
   (`REPORT.md`'s diagnostics section) — consistent with a large fraction of
   genuinely-authored functions being ordinary non-panicking code, or
   `#[track_caller]`-forwarding wrappers whose own body never materializes a
   fresh Location reference at all (the exact gap
   `docs/panic-location-internals.md` names: the Location lives at the call
   site, not in the helper's own body). The compiler doc explains the mechanism; the pilot data shows
   its magnitude. They agree.

## What was NOT re-litigated

Fan-out (how many distinct functions reference the same Location struct) was
already measured and rejected in prior work (`architecture.md`'s hard-case
section, session 4): it separates the `std::slice::sort` sub-family
(fan-out 5-6 for the FP vs 1 for genuine hits) but **cannot** separate the
rayon-bridge shape, which sits at fan-out 1, identical to genuine STRONG
attributions. This exploration did not re-propose fan-out as RULE_D; it
looked specifically for a *new* signal implied by the compiler internals,
not a repackaging of an already-dead one.

## Honest conclusion

There is no field, relocation, or byte-level pattern surviving into a
stripped `.eh_frame`/`.rodata`/`.data.rel.ro`-only binary that distinguishes
"this Location reference was synthesized from an inlined frame" from "this
Location reference was always this function's own." The compiler merges the
two cases into indistinguishable machine code by design (inlining's whole
point is that the result is as if the code were written inline by hand), and
the one piece of information that *would* disambiguate it (`SourceScopeData::
inlined`) is compiler-internal and erased before object-code emission,
recoverable only via debug info unavailable in the threat model this tool
targets. A real fix, if one exists, would need a signal orthogonal to
Location-path composition entirely (e.g. something in the instruction
sequence itself that correlates with "this block was inlined from a
generic/closure parameter" — control-flow shape, register-allocation
patterns around the call site that's now gone) — that is a genuinely
different research question from anything this branch's classifier (or any
rule over its output) can answer, and it was not attempted here: it's a
different measurement, not a rule over this one's data.

Good call on DWARF — that's the right diagnosis. Symbol-name crate attribution fails on
monomorphized generics (attributed to the defining crate, not where instantiated), closures
({{closure}} context), and the binary crate — exactly the functions that dominate inferred.
DWARF .debug_line maps addresses to real source files robustly. Build the ground truth from
that, not symbols.

Two things first.

"All 110 certain are authored" is NOT settled — it's the convenient resolution and the
denominator was admittedly broken. The DWARF rebuild confirms or refutes it; don't carry
"certain is solid" forward as fact until the DWARF numbers say so.

And the subtlety that makes DWARF the *correct* ground truth, not just a better one: a
monomorphized Vec<RustupType>::push maps via DWARF to its definition in alloc/src/vec/ — i.e.
std — and that is right, because the user wrote the *call* to push, not push itself. DWARF
attributing monomorphizations and inlined library bodies to their defining source is exactly
the "user-authored" line you want. User closures, by contrast, map to the user file where
they're written. That robustness is what symbols can't give you.

Build it:

1. Ground truth from DWARF: rustup is already built with debug=true, so .debug_line is present.
   For each .eh_frame function range, take the source file at the function's ENTRY address from
   the line program (entry maps to the function's own outermost source, not an inlined callee).
   Classify that path with the same rules — project-relative → first-party, /rustc/.../library/
   → std, cargo registry or /rust/deps/ → dep. Independent of symbol demangling.

2. Re-run the entire harness against this DWARF ground truth and re-report ALL precision/recall
   — certain, inferred, indeterminate — before AND after the barrier. The symbol-based numbers
   are dead; replace them.

3. Surface two headline numbers explicitly:
   - Certain precision against DWARF — this confirms or kills "certain is solid."
   - Of all DWARF-first-party functions, the fraction caught in certain (the real recall ceiling
     of the rock-solid signal) vs the fraction reachable only via inference. That ratio decides
     what the tool can honestly claim to do.

Same standing rule: report the numbers, surface anything that doesn't fit, and don't call any
bucket "sound" until the DWARF ground truth backs it.

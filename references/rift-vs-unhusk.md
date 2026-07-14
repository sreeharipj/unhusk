# RIFT vs unhusk: prior work and where unhusk differs

Two projects share unhusk's problem statement (a stripped Rust binary is mostly
library code; separate the author's code from everything else) and are worth
naming explicitly.

- **Project 0xA11C** ("Deoxidizing the Rust Hive", SentinelLabs, RECON 2024).
  An IDAPython toolkit that reconstructs the `Location`/slice structs, recovers
  `src/*.rs` panic paths, and mines `registry/src/…` strings for crate
  dependencies. It is the manual, in-IDA prior art for unhusk's Phase 1.
- **RIFT** (Microsoft, MSTIC/Mirage, open-sourced under the Microsoft org).
  Two IDA Pro plugins plus a Python generator that recognize *library* code by
  recompiling the exact dependencies and compiler and matching them against the
  malware with FLIRT signatures and Diaphora binary diffing.

unhusk is built on Cindy Xiao's panic-metadata blog
([`cxiao-panic-metadata-2023.md`](cxiao-panic-metadata-2023.md)). RIFT is the
strongest thing to compare against, so the delta is stated here in full rather
than glossed.

## The structural split: subtractive vs additive

RIFT and unhusk attack the same problem from opposite directions.

**RIFT is subtractive. It recognizes the library and removes it.**
Pipeline: read the crate strings and the `rustc` commit hash → resolve the hash
to a compiler version via the `static.rust-lang.org` TOML database → re-download
and recompile the exact dependencies and compiler → generate FLIRT signatures /
Diaphora diffs from the rebuilt `.o`/COFF files → match against the malware →
whatever stays unlabeled is, by elimination, the author. It identifies the known
(the crates.io + `rustc` ecosystem) and subtracts it.

**unhusk is additive. It recognizes the author directly.**
It reads the panic `Location` metadata already in the binary, classifies each
path (`src/*.rs` = author), attributes sites to functions via `.eh_frame` + an
xref scan, and ranks by author-Location multiplicity. It positively marks the
author from the author's own source-file names. Nothing is reconstructed,
nothing is subtracted.

Everything downstream follows from that one axis:

| | RIFT (subtractive) | unhusk (additive) |
|---|---|---|
| What it finds | Library functions; author = the residue | Author functions directly |
| Evidence | External: rebuilt libraries matched by similarity | Intrinsic: bytes already in the file |
| Needs | `rustc` bucket + crates.io + recompile + IDAT + Diaphora + PCF | just the ELF |
| Network / infra | Required (reproduce the exact toolchain) | None |
| Output | Function identity ("this is std FS stat") | Authorship class + source file + `[start,end)` tiers |
| Deliverable | Analyst triage (rename in IDA, read faster) | Signature seeds (feed a YARA-X generator) |
| Author-code confidence | By-elimination residue; "needs manual validation," no large-scale FP study (author's own Q&A) | Positive signal, measured ~87-98% |
| Platform tested | Windows PE | x86-64 ELF |

## Why the additive direction fits unhusk's purpose

The purpose is extracting bytes that are provably the author's, to seed a YARA-X
rule. On that specific job the direction matters more than the size of the team
behind the tool.

1. **RIFT's "author code" is a residue; unhusk's is a positive claim.** Anything
   RIFT fails to match (a crate version it could not reproduce, an LTO-inlined
   function, a compiler-flag mismatch) lands in the unlabeled pile that RIFT
   presents as candidate author code. For a YARA seed that is the wrong error
   direction: you would sign on "whatever we could not identify," including
   mismatched library code. unhusk signs on the author's own `src/lock.rs`.

2. **No reproduction infrastructure.** RIFT's power is ecosystem-scale:
   precompile the crates.io x `rustc`-version matrix and keep a large FLIRT
   database. unhusk's signal is in the file, so it scales with the binary, not
   with a corpus. Being a single-author project is only a disadvantage under
   RIFT's model, not unhusk's.

3. **Both lean on strings, for different reliability-critical jobs.** RIFT's
   static stage needs the crate strings and the commit hash to know what to
   rebuild; scrub them and FLIRT is (in the author's words) "basically screwed,"
   falling back to slow diffing. unhusk's panic paths are also strings, but they
   are relocation-referenced `Location` structs in `.data.rel.ro`, and unhusk
   already handles degraded inputs (`.eh_frame_hdr` fallback, `sstrip`
   program-header recovery) and flags `--remap-path-prefix`/packing instead of
   emitting garbage.

## Where RIFT genuinely wins

Stated plainly so the comparison survives scrutiny:

- **RIFT can label the library side; unhusk cannot.** unhusk only sees author
  functions that have a reachable panic site. Pure computation, getters, and
  code where the optimizer proved every panic unreachable are invisible to it.
  RIFT, by matching rebuilt libraries, can identify library functions
  comprehensively.
- **RIFT gives identity, unhusk gives class.** RIFT says "this is `reqwest::…`."
  unhusk says "author, from `path_finder.rs`." Different resolution.
- **RIFT is production tooling with a team and a Microsoft repo; unhusk is
  single-author research.** The claim is not "better tool," it is "structurally
  better fit for author-byte extraction with no infrastructure."

## Bottom line

They are complementary, opposite-direction tools. RIFT subtracts the known
library mass so a human can read what is left; unhusk positively marks the
author core so a generator can sign it. For the YARA-seed job the additive,
intrinsic-signal design is the right shape, and it is the reason a project with
no reconstruction infrastructure can compete on this one narrow axis.

## Related work (decompilation and demangling, not authorship attribution)

Two further papers address adjacent problems in Rust reverse engineering —
recovering readable structure from a Rust binary, rather than separating
author from library code — and are cited here rather than hosted, since they
are third-party published work:

- Yibo Liu, Zion Leonahenehe Basque, Arvind S Raj, Chavin Udomwongsa, Chang
  Zhu, Jie Hu, Changyu Zhao, Fangzhou Dong, Adam Doupé, Tiffany Bao, Yan
  Shoshitaishvili, Ruoyu Wang. **"Oxidizer: Toward Concise and High-fidelity
  Rust Decompilation."** IEEE Symposium on Security and Privacy (S&P), 2026.
  Arizona State University / Stanford. Recovers Rust-specific abstractions
  (enums, pattern matching) that C-oriented decompilers lose; a decompilation
  quality problem, not an authorship/library separation problem.
- Meirambek Dinmukhammed. **"Bridging the Rust Reverse Engineering Gap:
  Automated Demangling and Function Identification in Ghidra."** Proceedings
  of the 13th International Scientific Conference, p. 352. Astana IT
  University. A Ghidra plugin for Rust v0 symbol demangling and
  FunctionID-based standard-library identification — complementary tooling
  for the *unstripped* or symbol-partial case, versus unhusk's fully-stripped,
  symbol-free target.

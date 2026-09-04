# unhusk

**Finds the author's own code inside a stripped Rust binary.** No symbols, no debug info, no signature database.

## The problem

When you compile Rust for release and run `strip`, the names go away. What's left is a few megabytes of machine code with no labels — and the overwhelming majority of it isn't code the author wrote. It's the standard library and third-party packages, pulled in and inlined by the compiler. The author's own logic is a thin slice of the total, and nothing in the file says which slice.

That matters if you're triaging malware (you want the few functions worth reading), building detection signatures (you want to match the author's code, not code shared with every other Rust program), or recovering a dependency list from a binary you can't rebuild.

## How it works

Rust leaves a trail it can't easily remove. Every place the program can crash — an `.unwrap()`, an array bounds check, an explicit `panic!` — the compiler stores the source file, line, and column, so a crash can print `panicked at src/main.rs:42`. That's stored as ordinary data, not as a symbol, so `strip` doesn't touch it. It's still there in a fully stripped release build.

unhusk reads those records back out and sorts them by where the path points:

| Path shape | Verdict |
|---|---|
| `src/…` | the author's own code |
| `…/cargo/registry/…` | a third-party dependency |
| `/rustc/…/library/…` | the Rust standard library |

Then it maps each record back to the function that references it, and ranks functions by **how many distinct author crash-sites they contain**. That count is the precision lever: a library function that inlined one of the author's closures picks up a single author record, while a genuine author function usually references several of its own. Requiring at least two is the default, and raising the bar trades recall for precision.

Compiler-side mechanics, and what they mean for what you can trust: [`docs/panic-location-internals.md`](docs/panic-location-internals.md). Full system spec: [`architecture.md`](architecture.md).

## Install

```sh
cargo build --release      # Rust 1.70+, no C dependencies
```

Docker:

```sh
docker build -t unhusk .
docker run --rm -v "$(pwd)":/work -w /work unhusk <stripped-elf>
```

## Usage

```sh
unhusk <stripped-elf>                          # identify author functions
unhusk <stripped.exe>                          # PE works too, auto-detected (see Limitations)
unhusk <stripped-elf> --precision              # only the high-confidence tier
unhusk <stripped-elf> --min-anchors 3          # stricter: more precision, less recall
unhusk <stripped-elf> --precision --json       # machine-readable, for downstream tools
unhusk <stripped-elf> --validate <unstripped>  # score against debug-info ground truth
unhusk <stripped-elf> --crate ripgrep          # name the root crate (usually auto-detected)
```

### A readable reference implementation

[`unhusk_pe_poc.py`](unhusk_pe_poc.py) is the whole PE method in one dependency-light
file (`pip install pefile iced-x86`): read the `Location` structs out of `.rdata`,
classify each embedded path, disassemble the functions `.pdata` names, record which
ones load an author `Location` through a RIP-relative address, and rank by
multiplicity. It reproduces the shipped tool's output exactly on the PE samples
in this repository. Read it if you want the mechanism without the hardening.

## Example

`--precision --json` against a real stripped Akira ransomware sample, one entry from `functions`:

```json
{
  "start": "0xd25af",
  "end": "0xd38a5",
  "size": 4854,
  "tier": "strong",
  "anchor_count": 6,
  "anchor_files": ["akiranew/src/path_finder.rs"]
}
```

Six distinct author crash-sites in one function, from `akiranew`'s own source tree, recovered with no symbols and no debug info. [winnow](https://github.com/sreeharipj/winnow) turns functions like this one into YARA-X rules ([example](https://github.com/sreeharipj/winnow/blob/main/examples/akira_v2_x_tier1.yar)).

Same thing against a real PE build — Hive ransomware, sample
`01ea06db82a72d8eaa3209311b20f3da34aebda948204f615c63e5cb62057538` (SHA-256, lookup on any
public malware DB). Its ELF sibling (a separate Hive sample, `vmware_encrypt` instead of
`windows_encrypt`) was found the same way in an earlier validation pass:

```json
{
  "start": "0x156df",
  "end": "0x1b9a4",
  "size": 25285,
  "tier": "strong",
  "anchor_count": 81,
  "anchor_files": ["windows_encrypt/src/main.rs"]
}
```

81 distinct author crash-sites in one function — same `windows_encrypt`/`config`/`libs`
crate layout the ELF-side Hive sample showed under `vmware_encrypt`, cross-compiled for two
different targets and recovered from both with no symbols, no PDB, no debug info.

## How well it works

**Measured 2026-09-04 on [`bench/run1/`](bench/run1/)**: 168 crates, 667 builds,
14,625,936 labelled functions, ground truth from debug info. The corpus was split
by crate before the search ran and sealed — 91 crates for development, 36 held
out and read once.

Figures below are for a default `cargo build --release`, which is what a
real-world binary is built with. Intervals are 95%, bootstrapped over crates
rather than functions, because functions within a crate are not independent.

| | Precision | Recall |
|---|---|---|
| default (`--min-anchors 2`) | **90.5%** [87.5, 92.8] | 8.5% |
| the same rule on held-out crates only | **89.4%** [86.2, 91.7] | — |
| single-anchor functions (reported separately, lower tier) | 82.7% [78.4, 85.9] | 9.7% |

Against a 6.1% base rate: naming a function author-written at random would be
right 6% of the time.

Two things to read before trusting a number:

- **Precision is workload-dependent.** It is strongest on synchronous
  command-line and systems code and clearly weaker on async and heavily generic
  code — which is the harder case, because real Rust malware skews async.
- **Recall is partial by design**, and low by construction: the method can only
  find functions that contain a crash-site. For signature generation that is
  acceptable, since a few good seeds are enough.

Build configuration matters too — optimisation level and codegen-unit count change
what gets inlined, and so change what a function references. `bench/run1/REPORT.md`
carries every rule against every configuration.

The rule names in that report (`A@2`, `R1`, `C@0.70` and so on) grew during the
search and are not self-describing. [`docs/rule-taxonomy.md`](docs/rule-taxonomy.md)
is the index: what each one means, which feature family it draws on, and which
predicate the shipped tool actually implements.

The validation is built to attack its own conclusions: two independent ground-truth
rulers that disagree for a diagnosed reason, hypotheses registered before the data,
a headline precision figure corrected downward once harder binaries were added, and
one confidence tier shipped and then withdrawn when a cleaner measurement showed it
was an artifact of the harness. Superseded measurements are kept in `bench/` with
dated correction notes rather than silently edited away.

## Limitations

- **Functions that can't crash can't be found.** Pure computation and simple accessors have no crash-site to anchor on, so recall is partial by design.
- **Async and generic-heavy code is measurably weaker**, and that is irreducible in a stripped binary.
- **A library function can absorb an author's inlined closure** and get misattributed as author code (`sort_by`, `rayon`, futures combinators). This is a property of the classifier, not of the file format — it occurs at the same rate on ELF and PE — and it has no general fix yet.
- **Code reached only indirectly** — through trait objects or function pointers — reads as library code, because the scan follows static call edges only.
- **Defeated by packing and by `--remap-path-prefix`**, both of which real malware uses. Both are detected and reported rather than silently returning nothing. Nightly's `panic_immediate_abort` removes the metadata outright, but changes how the program behaves.
- **x86-64 only — ELF and Windows PE**, auto-detected. PE is high-confidence/single tier only; the inferred and indeterminate buckets aren't wired for PE yet, so every PE run prints a disclosure banner. No Mach-O, no aarch64.
- Most validation is on benign open-source programs. Malware testing has started, but the corpus is small.

An opt-in alternate rule (`--rule-r2`, `--json` required) trades recall for
precision by requiring corroboration from a function's callers. It is off by
default so the standard rule stays the reproducible one; see the taxonomy for what
it computes.

## Prior work

The core insight — that Rust embeds panic source-location metadata that survives `strip` and can be mined for authorship and dependencies — is not original to unhusk. SentinelLabs' Project 0xA11C ("Deoxidizing the Rust Hive," RECON 2024) demonstrated it as an IDAPython workflow. Cindy Xiao's ["Using panic metadata to recover source code information from Rust binaries"](https://cxiao.net/posts/2023-12-08-rust-reversing-panic-metadata/) is the write-up this tool's extraction is built on. unhusk automates the idea for x86-64 ELF and PE without IDA, and adds what those don't have: a precision-ranked authorship classifier with a measured false-positive story and a stable JSON contract for downstream tooling.

Microsoft's RIFT solves the same separation from the opposite direction — it recognizes *library* code by recompiling the exact dependencies and matching them, leaving the author's code as the unlabeled remainder. unhusk is additive rather than subtractive: it marks the author directly, needs only the binary (no recompilation, no network, no signature corpus), and treats author bytes as a positive signal — a better fit for extracting signature seeds.

## License

Licensed under the Apache License, Version 2.0. See `LICENSE`.

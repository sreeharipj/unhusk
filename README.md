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

Precision is workload-dependent, and that dependency is the main thing to understand before trusting a result: it is strongest on synchronous command-line and systems code, and clearly weaker on async and heavily generic code — which is the harder case, because real Rust malware skews async.

Rather than restate figures that drift as the corpus grows, the measurements live with the data that produced them. **As of 2026-08-19:**

- [`realval/`](realval/) — the precision harness, its build scripts, and [`results_body.md`](realval/results_body.md), which carries the per-binary inventory and the precision tables with confidence intervals.
- [`bench/origin/`](bench/origin/) — a second, independent measurement on a different corpus, with a different methodology. It is *not* comparable to the harness numbers and the two are deliberately not pooled; [`REPORT.md`](bench/origin/REPORT.md) explains why.
- [`bench/origin/INLINE_LEAK_INCIDENCE.md`](bench/origin/INLINE_LEAK_INCIDENCE.md) — how often the main false-positive mode actually fires, with real instances rather than constructed ones.
- [`bench/malwarebazaar_survey/`](bench/malwarebazaar_survey/) — how much Rust malware is actually out there, measured rather than assumed.

**As of 2026-08-25:** PE is measured at the same corpus scale as ELF, on the identical
39 crates — [`bench/pe_corpus/REPORT.md`](bench/pe_corpus/REPORT.md) and
[`bench/elf_corpus/REPORT.md`](bench/elf_corpus/REPORT.md). The two formats' STRONG-tier
precision is statistically indistinguishable, confirming the inline-absorption false
positive below is one shared classifier bug, not a PE-specific defect. A second, fully
independent 40-crate corpus ([`bench/corpus2_elf/REPORT.md`](bench/corpus2_elf/REPORT.md),
[`bench/corpus2_pe/REPORT.md`](bench/corpus2_pe/REPORT.md)) confirmed this and R2, but
**retracted** an earlier finding that R1/R3 hurt precision on PE — that result reversed sign
on the second corpus and was corpus-composition-dependent, not a real PE limitation. Kept
visible in the original reports with dated correction notes rather than silently edited away.

The validation is built to attack its own conclusions: two independent ground-truth rulers that disagree for a diagnosed reason, hypotheses registered before the data, a headline precision figure corrected downward once harder binaries were added, and one confidence tier shipped and then withdrawn when a cleaner measurement showed it was an artifact of the harness.

## Limitations

- **Functions that can't crash can't be found.** Pure computation and simple accessors have no crash-site to anchor on, so recall is partial by design. That's acceptable for signature generation, which needs a few good seeds rather than every function.
- **Async and generic-heavy code is measurably weaker**, and that is irreducible in a stripped binary.
- **A library function can absorb an author's inlined closure** and get misattributed as author code (`sort_by`, `rayon`, futures combinators). This is a property of the classifier, not of the file format — confirmed by measuring it independently on ELF and PE at matched corpus scale, same rate on both ([`bench/elf_corpus/REPORT.md`](bench/elf_corpus/REPORT.md) / [`bench/pe_corpus/REPORT.md`](bench/pe_corpus/REPORT.md)) — and it has no general fix yet. Also measured in [`INLINE_LEAK_INCIDENCE.md`](bench/origin/INLINE_LEAK_INCIDENCE.md).
- **Code reached only indirectly** — through trait objects or function pointers — reads as library code, because the scan follows static call edges only.
- **Defeated by packing and by `--remap-path-prefix`**, both of which real malware uses. Both are detected and reported rather than silently returning nothing. Nightly's `panic_immediate_abort` removes the metadata outright, but changes how the program behaves.
- **x86-64 only — ELF and Windows PE**, auto-detected. PE is STRONG/SINGLE tier only: CALL-edge extraction exists now, but inferred/indeterminate tiering doesn't (needs a dep_boundary set and BFS propagation too, neither wired for PE yet), so every PE run still prints a disclosure banner. No Mach-O, no aarch64.
- Most validation is on benign open-source programs. Malware testing has started, but the corpus is small.

## In progress

- **PE inferred/indeterminate tiering** — CALL-edge extraction landed (`PeImage::call_targets_in`), enough to compute R2 (caller-corroborated) for PE for the first time, but the BFS propagation and dep_boundary machinery `classify::attribute` uses for ELF's inferred/indeterminate buckets isn't wired for PE yet — STRONG/SINGLE only stays the shipped ceiling until it is.
- **Mining the attribution rule from first principles** — deriving the classifier from the data instead of hand-tuning it, and checking candidate rules against held-out crates. Method, results, and the negative findings: [`bench/rulemine/REPORT.md`](bench/rulemine/REPORT.md). One result already shipped as an opt-in, on both ELF and PE: `--rule-r2` (`--json` required) measured at 92.95% STRONG precision vs the default rule's 86.76% on a matched ELF corpus ([`bench/elf_corpus/REPORT.md`](bench/elf_corpus/REPORT.md)), and 95.27% vs 90.01% pooled across two independent PE corpora ([`bench/corpus2_pe/REPORT.md`](bench/corpus2_pe/REPORT.md)) — off by default so the standard rule stays the reproducible one. Whether it becomes the default is still open. Two more candidate rules, `--min-size`/`--max-density`, are held-out validated on both formats too ([`bench/size_signal/REPORT.md`](bench/size_signal/REPORT.md)), though their effect size looks more corpus-dependent than R2's.

## Prior work

The core insight — that Rust embeds panic source-location metadata that survives `strip` and can be mined for authorship and dependencies — is not original to unhusk. SentinelLabs' Project 0xA11C ("Deoxidizing the Rust Hive," RECON 2024) demonstrated it as an IDAPython workflow. Cindy Xiao's ["Using panic metadata to recover source code information from Rust binaries"](https://cxiao.net/posts/2023-12-08-rust-reversing-panic-metadata/) is the write-up this tool's extraction is built on. unhusk automates the idea for x86-64 ELF without IDA, and adds what those don't have: a precision-ranked authorship classifier with a measured false-positive story and a stable JSON contract for downstream tooling.

Microsoft's RIFT solves the same separation from the opposite direction — it recognizes *library* code by recompiling the exact dependencies and matching them, leaving the author's code as the unlabeled remainder. unhusk is additive rather than subtractive: it marks the author directly, needs only the binary (no recompilation, no network, no signature corpus), and treats author bytes as a positive signal — a better fit for extracting signature seeds.

## License

Licensed under the Apache License, Version 2.0. See `LICENSE`.

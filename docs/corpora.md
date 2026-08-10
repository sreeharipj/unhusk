# Corpus registry

Every measurement in this repo runs on a different corpus, because they answer different
questions. That is fine. What was not fine, and is what this page fixes, is that no single
place said **which corpus backs which number** — so a reader hitting "94.2%", "0.1%",
"13.3%" and "8 of 13" in four documents had no way to tell whether they were commensurable.
They mostly are not.

Rule of thumb before quoting any figure from this repo: find it in the reverse index at the
bottom, check its unit of analysis, and check whether the corpus it came from was built to
measure prevalence or to demonstrate a mechanism. Those two are routinely confused and the
confusion is always in the direction of overclaiming.

## The corpora

| # | corpus | size | ground truth | unit | build config | backs |
|---|---|---|---|---|---|---|
| 1 | `realval/corpus_src/` | 32 stripped ELF + debug twins | `nm -C` symbol leading crate + `cargo metadata` authorship (primary); DWARF `decl_file` (secondary) | certain function (n=2225) | one config: `cargo build --release --locked`, debug info forced, `objcopy --strip-all` | `docs/validation.md`, `docs/origin-veto-headtohead.md` |
| 2 | `bench/origin/build/` | 43 crates x 8 configs = 344 builds, 2,953,905 FDEs | cargo authorship (`bench/origin/ground_truth.py`), scored strict *and* workspace-merged | FDE | matrix: lto{fat,thin} x opt{3,z} x panic{unwind,abort}, codegen-units=1 | `bench/origin/REPORT.md`, `INLINE_LEAK_INCIDENCE.md` |
| 3 | in-the-wild malware | 5 ELF samples, by SHA-256 | none — no source exists | whole sample, qualitative | as shipped by the authors | `docs/case-study-real-malware.md` |
| 4 | hard-case probe | 1 constructed crate, 5 wrappers | PDB inline-site stream (PE); DWARF (ELF) | xref site | built both MSVC/PE and native ELF | `docs/PDB_ORACLE_hardcase.md`, `architecture.md` §10 |
| 5 | PDB oracle | 2 crates (`dufs`, `procs`) | PDB | procedure | `x86_64-pc-windows-msvc` | `docs/PDB_ORACLE_dufs.md`, `_procs.md` |
| — | `realval/out/` | 13 binaries | — | — | — | **superseded, see below** |
| — | benign FP corpus | 78 + 76 + 60 + 8 | — | binary | — | **downstream, not measured here** |

### 1. `realval/corpus_src/` — the shipped tool's precision

The corpus behind every precision number the README and `docs/validation.md` quote. 32
stripped release ELF binaries, each with an unstripped twin kept as the symbol oracle.

Composition, per `docs/validation.md`: 13 source-built, 8 `cargo install`, 11 chosen
adversarially for the pre-registered stress test. The design called for 34; `mprocs` failed
to build and `dog` produced no artifact, so **the measured corpus is 32** — a correction
already made at source, but one that outlived it in a few places and is worth re-checking
against whenever a "34" appears.

By domain (`report_results.py`'s `DOMAIN_CATEGORY`): cli 16, async 8, macro 4, crypto 2,
parallel 1, framework 1.

**One build configuration.** Default `cargo build --release` — so opt-level 3, panic=unwind,
and cargo's default (thin-local) LTO. Corpus 2 shows this matters: the rate at which genuine
author functions reference a rustc path swings from 2.2% at thin/opt-z to 18.5% at fat/opt-3.
Anything measured here is measured at one point in that space, and not the point real
malware is usually built at.

**Provenance gate.** `check_provenance.py` drops any binary needing root-crate promotion,
because feeding the tool the authorship answer measures the promotion heuristic instead of
the mechanism. All 32 PASS (`realval/provenance_src.tsv`).

**Pins.** Cloned repos under `realval/corpus_src/src/`. Not lock-pinned to commit hashes —
weaker than corpus 2, and the one real reproducibility gap in this registry.

### 2. `bench/origin/build/` — the origin classifier

43 crates built across an 8-config matrix. The only corpus here that varies build flags, and
therefore the only source of evidence about how any of this behaves under fat LTO.

**Overlaps corpus 1 by construction.** `corpus.tsv`'s own header records it: 16 of the crates
were reused from `realval/corpus_src/src/`. The two corpora are not independent samples, and
a result appearing in both is not two-for-two replication. It *is* still meaningful when the
two disagree, since the ground truths and units differ.

Four crates failed at every config (`bore`, `dog`, `sniffnet`, `spotify-tui`) and are in
`build_failures.tsv`. `mprocs` never entered the matrix at all.

**Pins.** `corpus.lock` records each repo's HEAD and Cargo.lock hash; `build_matrix.sh`
refuses loudly on a mismatch. This is the reproducibility standard the other corpora should
be held to.

**Base rate matters here more than anywhere else.** AUTHOR is 3.1% of labeled FDEs (strict) /
4.8% (workspace-merged). A precision figure from this corpus is an enrichment over *that*,
not over an implied 50%.

### 3. In-the-wild malware — the case study

Five ELF samples, identified by SHA-256 in `docs/case-study-real-malware.md`. Corpus credit
is Cindy Xiao's. Static analysis only; nothing is executed.

**No ground truth exists** — the source is not available, so nothing here is a precision
measurement and none of it belongs in a precision table. What it establishes is different
and still load-bearing: that the pipeline runs end-to-end on real samples, and that the
fail-closed path triggers where it should (`01flip` path-remapped → 0 user functions;
`P2PInfect` packed → 0 sections).

### 4. Hard-case probe — a mechanism demonstration, not a rate

One deliberately constructed crate: five ordinary wrappers handing closures to
`slice::sort_by`, `sort_unstable_by_key`, and `rayon`'s `par_iter().map()/for_each()`. Built
for both PE and ELF and scored by two independent oracles, which is what makes it evidence
that the gap lives in shared `classify.rs`/`xref.rs` rather than in either container.

**Its numbers must never be quoted as corpus figures.** `architecture.md` states this
directly, and it is the single most important entry on this page: "8 of 13 STRONG false
positives" and "precision=13.3%" are the rate at which a construction built to trigger a
mechanism triggers it. They say nothing about prevalence. The prevalence claim is corpus 2's
0.1% inverse leak, which is three orders of magnitude away and is not in conflict with it.

### 5. PDB oracle — the PE side

Two crates built for `x86_64-pc-windows-msvc` with PDBs retained, scored against the PDB's
own procedure and inline-site records. Small by design: these were built to check that the PE
path produces the same *kind* of answer as the ELF path, not to produce a rate. `dufs`'s
"async STRONG 9/9" is a count, and `docs/PDB_ORACLE_dufs.md` says so in the headline.

### Superseded: `realval/out/`

13 binaries, gitignored, with `rows_out.json` in an older schema (`{min_anchors, binaries}`
rather than the flat map `report_results.py` reads). Predates the current corpus and feeds no
published number — `run_all.sh` measures `rows_src.json` only. Listed here solely so nobody
finds it later and mistakes it for a second measurement.

### Out of scope here: the benign false-positive corpus

The 78 / 76 / 60 / 8 binary FP sets belong to the downstream rule generator, are measured
there, and are not reproducible from this repo. Mentioned only so this registry is complete.
Two things to settle on that side rather than here: the 78+76 split totals 154, which should
be reconciled against the 158 figure that also circulates; and the held-out half's
independence claim depends on generator-side details this repo cannot verify.

## Overlap map

Independence matters when the same finding shows up twice. It usually is not independent.

- **Corpus 1 ∩ corpus 2**: 16 crates, shared source trees. Same clones, different build
  configs, different ground truth, different unit.
- **Corpus 2 ⊃ corpus 1's stress additions**: the async-heavy crates added to corpus 2 over
  three expansion rounds are largely the ones corpus 1's stress test introduced.
- **Corpus 4 ∩ everything else**: none. Purpose-built, standalone.
- **Corpus 3 ∩ everything else**: none. No overlap is possible — real samples, no source.
- **Corpus 5 ∩ corpus 1**: `dufs` and `procs` appear in both, but built for a different
  target with a different oracle. Not a replication of corpus 1's result on those binaries.

## Reverse index: where each quoted number comes from

| figure | corpus | unit | source |
|---|---|---|---|
| STRONG ~94% / SINGLE ~80% pooled precision | 1 | certain function | `docs/validation.md` |
| `--min-anchors` ladder: 87.2 / 94.2 / 96.1 / 97.5% | 1 | certain function | `realval/results_body.md` |
| async 87.3% vs CLI ~98% | 1 (domain cut: 8 async binaries) | certain function | `docs/validation.md` |
| `miniserve` 7/14 STRONG FPs = 50.0% | 1 | certain function | `realval/results_body.md` |
| 67-row STRONG false-attribution table | 1 | certain function | `realval/results_body.md` |
| veto iso-retention -1.5pp pooled / +4.2pp async | 1 | certain function | `docs/origin-veto-headtohead.md` |
| inverse leak 0.1% (1024 / 1,170,733 DEP FDEs) | 2 | FDE | `bench/origin/REPORT.md` |
| AUTHOR w/ rustc path 10.0% pooled, 18.5% at fat/opt-3 | 2 | FDE | `bench/origin/REPORT.md` |
| RULE_A@2 92.8% pooled / 91.5% async (workspace-merged) | 2 | FDE | `bench/origin/REPORT.md` |
| AUTHOR base rate 3.1% strict / 4.8% merged | 2 | FDE | `bench/origin/REPORT.md` |
| zero-Location majority ~73-80% pooled | 2 | FDE | `bench/origin/REPORT.md` |
| KrustyLoader 1 STRONG / Akira 7 STRONG | 3 | whole sample | `docs/case-study-real-malware.md` |
| 8 of 13 STRONG FPs, precision 13.3% | 4 | xref site | `docs/PDB_ORACLE_hardcase.md` — **demonstration, not a rate** |
| async STRONG 9/9 | 5 | procedure | `docs/PDB_ORACLE_dufs.md` — a count, not a rate |
| 0 false positives on benign binaries | downstream | binary | not measured in this repo |

## Standing rules

1. **State the corpus with the number.** A precision figure without its corpus is not a
   result. Every table in this repo that quotes one should be traceable through the reverse
   index above.
2. **Never compare across corpora without saying so.** `bench/origin/REPORT.md`'s async
   comparison did this and reached a conclusion that a controlled run then had to qualify
   (`docs/origin-veto-headtohead.md`). That is the worked example of why this rule exists.
3. **Demonstration corpora do not produce rates.** Corpora 3, 4 and 5 answer "does this
   happen / does this run"; only 1 and 2 answer "how often".
4. **Check the unit before comparing.** Corpus 1 counts certain functions, corpus 2 counts
   FDEs. A percentage from one is not a percentage from the other, even when both are
   labelled "precision".
5. **New corpus, new row.** Adding a measurement without adding it here recreates exactly
   the problem this page exists to fix.

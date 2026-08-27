#!/usr/bin/env python3
"""
select_v5.py — regenerates v5/corpus_candidates.tsv.

The v5 candidate pool is winnow's pinned benign-corpus manifest minus every
crate already used anywhere in bench/rulemine (main 43, v2, v3, v4's 40),
keeping only rows with an intact .eh_frame and dropping `_noeh` variants.

Run from bench/rulemine/v5/.  Reads ../../../../winnow/corpus/manifest.csv.
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.normpath(os.path.join(HERE, "..", "..", "..", "..",
                                         "winnow", "corpus", "manifest.csv"))

# Every crate name that appears in an earlier bench/rulemine corpus.
USED = set("""
oha xh miniserve dufs procs starship typos taplo tokei ripgrep trippy just hexyl xsv zoxide pastel
bandwhich bat bottom dprint dust eza fclones fd gping grex hyperfine ouch rage rustscan sd tealdeer
zellij websocat mqttui rathole feroxbuster pueue wormhole-rs oxker netscanner ferium topgrade
choose diskus vivid htmlq kibi diffr jaq kondo tre-command sad xcp dua-cli git-graph rust-parallel
rustypaste diskonaut onefetch hgrep kalker so broot csvlens delta fend git-cliff lsd mdbook navi
presenterm rip viu watchexec xplr numbat stylua skim serie joshuto cotp oxipng
""".split())

# Large clones / long builds: excluded from the default build set, offered back.
MEGA = {"mise", "nushell", "gitoxide", "ruff", "atuin", "yazi", "sccache", "slumber"}


def main():
    rows = list(csv.DictReader(open(MANIFEST)))
    pool = [r for r in rows
            if r["eh_frame_removed"] == "false"
            and not r["name"].endswith("_noeh")
            and r["name"] not in USED]
    core = [r for r in pool if r["name"] not in MEGA]
    mega = [r for r in pool if r["name"] in MEGA]
    out = os.path.join(HERE, "corpus_candidates.tsv")
    with open(out, "w") as f:
        f.write("name\tbin_name\tgit_url\tpinned_sha\tactual_sha\t"
                "cargo_lock_sha256\tstrong_functions_winnow\ttier\n")
        for r in core + mega:
            tier = "mega-optional" if r["name"] in MEGA else "core"
            f.write(f"{r['name']}\t{r['bin_name']}\t{r['git_url']}\t"
                    f"{r['commit_sha']}\tPENDING\tPENDING\t"
                    f"{r['strong_functions']}\t{tier}\n")
    print(f"{len(rows)} manifest rows -> {len(core)} core + {len(mega)} mega "
          f"candidates -> {out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
select_v5.py — v5 candidate list: crates.io's most-downloaded command-line
*applications* that ship their own binary and are in no earlier bench/rulemine
corpus.

The raw `category=command-line-utilities, sort=downloads` ranking is mostly
libraries that happen to carry the tag, plus `cargo-*` subcommands and the
`uu_*` coreutils fragments. Those are filtered out:

  * drop crates already used (main 43, v2, v3, v4);
  * drop `cargo-*` subcommands and `uu_*` fragments (thin wrappers / one-repo
    fragments -- not representative author code);
  * drop a small hand block-list of libraries whose only binary is a dev helper;
  * keep only crates whose newest version lists a `bin_names` entry;
  * walk deep enough (PAGES) to reach TARGET keepers.

A curated ALLOW set of well-known standalone Rust CLI apps is merged in first so
the corpus is not at the mercy of the ranking's noise. The COMMITTED
corpus_candidates.tsv is the hand-curated result of one such run (45 crates);
re-running this script regenerates the raw pool, which then needs the same
manual pass (drop alias-dupes like taplo-cli/fd-find, drop library helpers).

Commit hashes are not pinned here (`pinned_sha = HEAD`); build_v5.sh records the
actual checked-out SHA per crate, as v4 does. Run from bench/rulemine/v5/.
"""
import json
import os
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = "unhusk-bench corpus-selection (github.com/this-is-SPJ; sreehari.nitt@gmail.com)"
TARGET = 46
PAGES = 14

USED = set("""
oha xh miniserve dufs procs starship typos taplo tokei ripgrep trippy just hexyl xsv zoxide pastel
bandwhich bat bottom dprint dust eza fclones fd gping grex hyperfine ouch rage rustscan sd tealdeer
zellij websocat mqttui rathole feroxbuster pueue wormhole-rs oxker netscanner ferium topgrade
choose diskus vivid htmlq kibi diffr jaq kondo tre-command sad xcp dua-cli git-graph rust-parallel
rustypaste diskonaut onefetch hgrep kalker so broot csvlens delta fend git-cliff lsd mdbook navi
presenterm rip viu watchexec xplr numbat stylua skim serie joshuto cotp oxipng
""".split())

# libraries in the CLI category whose "binary" is only a dev helper
BLOCK = set("""
inferno crc64fast-nvme any_ascii serde-saphyr human_name hayagriva comrak pelite build-fs-tree
names petname honggfuzz sark0y_tam_rst syd boa_gc ariadne wasm-smith clap-markdown run_script
cmd_lib serde-env paw paw-raw paw-attributes tqdm kopium clippy-sarif sarif-fmt is-wsl is-docker
wl-clipboard-rs self_update reqsign-core xwin
""".split())

# standalone Rust CLI apps, high profile, verified not in USED — merged first
ALLOW = [
    ("mise", "mise", "https://github.com/jdx/mise"),
    ("gitui", "gitui", "https://github.com/gitui-org/gitui"),
    ("nushell", "nu", "https://github.com/nushell/nushell"),
    ("difftastic", "difft", "https://github.com/Wilfred/difftastic"),
    ("bacon", "bacon", "https://github.com/Canop/bacon"),
    ("yazi-fm", "yazi", "https://github.com/sxyazi/yazi"),
    ("atuin", "atuin", "https://github.com/atuinsh/atuin"),
    ("television", "tv", "https://github.com/alexpasmantier/television"),
    ("jless", "jless", "https://github.com/PaulJuliusMartinez/jless"),
    ("mprocs", "mprocs", "https://github.com/pvolok/mprocs"),
    ("gitoxide", "gix", "https://github.com/GitoxideLabs/gitoxide"),
    ("silicon", "silicon", "https://github.com/Aloxaf/silicon"),
    ("monolith", "monolith", "https://github.com/Y2Z/monolith"),
    ("dua-cli", "dua", "https://github.com/Byron/dua-cli"),  # (already USED, will drop)
    ("rink", "rink", "https://github.com/tiffany352/rink-rs"),
    ("genact", "genact", "https://github.com/svenstaro/genact"),
    ("hurl", "hurl", "https://github.com/Orange-OpenSource/hurl"),
    ("rustic", "rustic", "https://github.com/rustic-rs/rustic"),
    ("tuc", "tuc", "https://github.com/riquito/tuc"),
    ("jnv", "jnv", "https://github.com/ynqa/jnv"),
    ("wiki-tui", "wiki-tui", "https://github.com/Builditluc/wiki-tui"),
    ("taskwarrior-tui", "taskwarrior-tui", "https://github.com/kdheepak/taskwarrior-tui"),
    ("gitu", "gitu", "https://github.com/altsem/gitu"),
    ("hwatch", "hwatch", "https://github.com/blacknon/hwatch"),
]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def crate_ok(name):
    try:
        full = get(f"https://crates.io/api/v1/crates/{name}")
        time.sleep(1.1)
    except Exception:  # noqa: BLE001
        return None
    vers = [v for v in full.get("versions", []) if not v.get("yanked")]
    if not vers:
        return None
    newest = vers[0]
    bins = newest.get("bin_names") or []
    repo = (full.get("crate", {}).get("repository") or "")
    if not bins or not repo.startswith("http"):
        return None
    return {"bin_name": bins[0], "newest_version": newest["num"],
            "git_url": repo.split("/tree/")[0].rstrip("/").removesuffix(".git")}


def main():
    kept, seen = [], set()

    for name, binn, url in ALLOW:
        if name in USED or name in seen:
            continue
        seen.add(name)
        info = crate_ok(name)
        ver = info["newest_version"] if info else "?"
        kept.append({"name": name, "bin_name": binn, "git_url": url,
                     "newest_version": ver, "downloads": "", "recent_downloads": "",
                     "tier": "core-allow"})
        print(f"  allow {name:24s} bin={binn}")

    for p in range(1, PAGES + 1):
        d = get("https://crates.io/api/v1/crates?category=command-line-utilities"
                f"&sort=downloads&per_page=100&page={p}")
        time.sleep(1.1)
        for c in d.get("crates", []):
            if len([k for k in kept if k["tier"] != "core-allow"]) >= TARGET:
                break
            name = c["id"]
            if name in seen or name in USED or name in BLOCK:
                continue
            if name.startswith(("cargo-", "cargo_", "uu_")):
                continue
            seen.add(name)
            info = crate_ok(name)
            if not info or info["bin_name"].startswith("cargo-"):
                continue
            kept.append({"name": name, "bin_name": info["bin_name"],
                         "git_url": info["git_url"],
                         "newest_version": info["newest_version"],
                         "downloads": c["downloads"],
                         "recent_downloads": c.get("recent_downloads") or 0,
                         "tier": "core"})
            print(f"  keep  {name:24s} bin={info['bin_name']:20s} "
                  f"dl={c['downloads']:>12,}")

    out = os.path.join(HERE, "corpus_candidates.tsv")
    with open(out, "w") as f:
        f.write("name\tbin_name\tgit_url\tpinned_sha\tactual_sha\tcargo_lock_sha256\t"
                "newest_version\tdownloads\trecent_downloads\ttier\n")
        for k in kept:
            f.write(f"{k['name']}\t{k['bin_name']}\t{k['git_url']}\tHEAD\tPENDING\t"
                    f"PENDING\t{k['newest_version']}\t{k['downloads']}\t"
                    f"{k['recent_downloads']}\t{k['tier']}\n")
    print(f"\n{len(kept)} candidates -> {out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
token_budget.py — how many LLM tokens is a stripped Rust binary, whole vs the
author-only slice unhusk hands back?

Rust-decompilation papers keep proposing "feed the disassembly to an LLM." A
release Rust binary statically links libstd + every crate; the disassembly of
the whole thing blows past any context window. unhusk's job here is triage: it
names the functions that are the malware author's own code. This measures the
token bill for

    whole binary   — every function's disassembly
    any_anchor     — functions with >=1 author panic::Location
    C@0.70         — >=70% of a function's anchors are user-path   (recall row)
    B@2            — >=2 author anchors, no registry/git anchor     (precision)
    R3             — the incumbent composite rule

Disassembly = capstone x86-64 linear sweep over each FDE range, rendered
"addr:\\tmnemonic\\toperands" per line (what a disassembler listing looks like;
raw opcode bytes excluded). Tokeniser: tiktoken o200k_base (GPT-4o) and
cl100k_base (GPT-4). Cross-checked against `token-count` v0.4.0
(shaunburdick/token-count) --model gpt-4o / claude-sonnet-4-5.
"""
import glob, json, os, subprocess, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
import tiktoken

HERE = os.path.dirname(os.path.abspath(__file__))
RULEMINE = os.path.join(os.path.dirname(HERE), "rulemine")
sys.path.insert(0, os.path.join(RULEMINE, "lib"))
sys.path.insert(0, os.path.join(RULEMINE, "extractor"))
import mining                       # noqa: E402
from features import build_rows     # noqa: E402
EXTRACT = os.path.join(RULEMINE, "extractor", "target", "release", "rulemine_extract")
TOKCOUNT = os.path.expanduser(
    "/tmp/claude-1000/-home-user-Videos-unhusk/95d02b40-0876-4421-a1cf-dc095ffc9cef/"
    "scratchpad/token-count/target/release/token-count")

ENC = {"o200k_base": tiktoken.get_encoding("o200k_base"),
       "cl100k_base": tiktoken.get_encoding("cl100k_base")}
MD = Cs(CS_ARCH_X86, CS_MODE_64)

WINDOWS = [("128K", 128_000), ("200K", 200_000), ("1M", 1_000_000), ("2M", 2_000_000)]

# (name, path, kind).  kind: "malware" | "control" | "degenerate" (kept in the
# per-sample table, excluded from the aggregate — the extractor recovers only 41
# FDEs from p2pinfect: statically linked, section headers stripped, sparse
# .eh_frame, so neither "whole" nor the rule slices are meaningful).
SAMPLES = [
    ("01flip",          "~/malware-samples/01flip_x/e5834b7bdd70ec904470d541713e38fe933e96a4e49f80dbfb25148d9674f957.elf", "malware"),
    ("krusty",          "~/malware-samples/krusty_x/030eb56e155fb01d7b190866aaa8b3128f935afd0b7a7b2178dc8e2eb84228b0.elf", "malware"),
    ("akira_v2",        "~/malware-samples/akira_v2_x/0ee1d284ed663073872012c7bde7fac5ca1121403f1a5d2d5411317df282796c.elf", "malware"),
    ("p2pinfect",       "~/malware-samples/p2pinfect_x/3a43116d507d58f3c9717f2cb0a3d06d0c5a7dc29f601e9c2b976ee6d9c8713f.elf", "degenerate"),
    ("blackcat_sphynx", "~/malware-samples/blackcat_sphynx_x/c0e70e69d8f7432383fa37528cd42db764b73dd08eb75d72229c2a0d02e538cc.elf", "malware"),
    ("tokei[benign]",   "~/malware-samples/tokei_sh.bin", "control"),
]


def load_segments(elf_path):
    segs = []
    with open(elf_path, "rb") as f:
        ef = ELFFile(f)
        for seg in ef.iter_segments():
            if seg["p_type"] == "PT_LOAD" and (seg["p_flags"] & 0x1):  # exec
                segs.append((seg["p_vaddr"], seg["p_vaddr"] + seg["p_filesz"],
                             seg.data()))
    return segs


def fn_text(segs, s, e):
    for v0, v1, data in segs:
        if v0 <= s < v1:
            b = data[s - v0: min(e, v1) - v0]
            return "\n".join(f"{i.address:x}:\t{i.mnemonic}\t{i.op_str}".rstrip()
                             for i in MD.disasm(b, s))
    return ""


def tok(texts, enc):
    return np.array([len(enc.encode(t, disallowed_special=())) if t else 0
                     for t in texts], int)


def tokcount_tool(text, model):
    try:
        r = subprocess.run([TOKCOUNT, "--model", model], input=text,
                           capture_output=True, text=True, timeout=120)
        return int(r.stdout.strip().split()[0])
    except Exception as ex:                       # noqa: BLE001
        return f"ERR:{ex}"


def main():
    rows_out = []
    for name, rel, kind in SAMPLES:
        elf = os.path.expanduser(rel)
        if not os.path.exists(elf):
            print(f"skip {name}: missing"); continue
        raw_p = f"/tmp/tb_{os.path.basename(elf)}.json"
        subprocess.run([EXTRACT, elf, "--crate-name", "sample", "--config", "adhoc",
                        "-o", raw_p], check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        df = pd.DataFrame(build_rows(json.load(open(raw_p)), None)[0])
        s = df.fn_start.to_numpy(); e = df.fn_end.to_numpy()
        cu = df.C_user.to_numpy(); pt = df.P_total.to_numpy()
        rg = df.C_registry.to_numpy() + df.C_git.to_numpy()
        with np.errstate(all="ignore"):
            ratio = np.where(pt > 0, cu / np.maximum(pt, 1), 0.0)
        rules = {
            "whole binary": np.ones(len(df), bool),
            "any_anchor": df.M_rel_structs.to_numpy() >= 1,
            "C@0.70": (pt > 0) & (ratio >= 0.70),
            "B@2": (cu >= 2) & (rg == 0),
            "R3": mining.eval_expr(df, "M_rel_structs >= 1 AND N_win_rel >= 5"),
        }
        segs = load_segments(elf)
        asm = [fn_text(segs, int(a), int(b)) for a, b in zip(s, e)]
        t_o = tok(asm, ENC["o200k_base"])
        t_c = tok(asm, ENC["cl100k_base"])
        nins = df.G_n_insn.to_numpy(); fsz = df.G_size.to_numpy()
        base_o = max(int(t_o.sum()), 1)
        rec = {"sample": name, "kind": kind,
               "file_KB": round(os.path.getsize(elf) / 1024),
               "n_functions": len(df), "rules": {}}
        for rn, m in rules.items():
            rec["rules"][rn] = {
                "n_fns": int(m.sum()), "code_bytes": int(fsz[m].sum()),
                "insns": int(nins[m].sum()),
                "tok_o200k": int(t_o[m].sum()), "tok_cl100k": int(t_c[m].sum()),
                "frac_of_whole": round(float(t_o[m].sum()) / base_o, 4),
            }
        # tool cross-check (shaunburdick/token-count v0.4.0): whole & C@0.70,
        # across an exact BPE (gpt-4o), an estimator (claude), an exact SP (gemini)
        whole_txt = "\n\n".join(a for a in asm if a)
        c70_txt = "\n\n".join(a for a, m in zip(asm, rules["C@0.70"]) if m and a)
        rec["toolcheck"] = {
            "whole/gpt-4o": tokcount_tool(whole_txt, "gpt-4o"),
            "C@0.70/gpt-4o": tokcount_tool(c70_txt, "gpt-4o"),
            "C@0.70/claude-sonnet-4-6": tokcount_tool(c70_txt, "claude-sonnet-4-6"),
            "C@0.70/gemini-2.5-pro": tokcount_tool(c70_txt, "gemini-2.5-pro"),
        }
        rows_out.append(rec)

        print(f"\n=== {name} [{kind}]  ({rec['file_KB']} KB, {len(df)} functions) ===")
        print(f"{'slice':14s} {'fns':>6s} {'code B':>9s} {'tok o200k':>12s} {'tok cl100k':>12s} {'% whole':>8s}")
        for rn, r in rec["rules"].items():
            print(f"{rn:14s} {r['n_fns']:6d} {r['code_bytes']:9d} {r['tok_o200k']:12,d} {r['tok_cl100k']:12,d} {r['frac_of_whole']:8.2%}")
        tc = rec["toolcheck"]
        print(f"  token-count xcheck: whole/gpt-4o={tc['whole/gpt-4o']}  "
              f"C@0.70: gpt-4o={tc['C@0.70/gpt-4o']} claude={tc['C@0.70/claude-sonnet-4-6']} "
              f"gemini={tc['C@0.70/gemini-2.5-pro']}")
        for lbl, lim in WINDOWS:
            fits = [rn for rn in ("whole binary", "any_anchor", "C@0.70", "B@2")
                    if rec["rules"][rn]["tok_o200k"] and rec["rules"][rn]["tok_o200k"] <= lim]
            print(f"    <= {lbl:4s}: {', '.join(fits) if fits else '(none)'}")

    def aggregate(kinds):
        subset = [r for r in rows_out if r["kind"] in kinds]
        a = {}
        for rn in ("whole binary", "any_anchor", "C@0.70", "B@2", "R3"):
            vals = [r["rules"][rn] for r in subset]
            a[rn] = {k: sum(v[k] for v in vals) for k in ("n_fns", "code_bytes", "tok_o200k", "tok_cl100k")}
        whole = max(a["whole binary"]["tok_o200k"], 1)
        for rn, x in a.items():
            x["frac_of_whole"] = round(x["tok_o200k"] / whole, 5)
            x["reduction_x"] = round(whole / max(x["tok_o200k"], 1), 1)
        a["_samples"] = [r["sample"] for r in subset]
        return a

    aggs = {"malware": aggregate({"malware"}),
            "malware+control": aggregate({"malware", "control"})}
    for tag, a in aggs.items():
        print(f"\n\n=== AGGREGATE [{tag}]  ({', '.join(a['_samples'])}) ===")
        print(f"{'slice':14s} {'fns':>7s} {'code B':>12s} {'tok o200k':>14s} {'tok cl100k':>14s} {'x smaller':>10s} {'fits':>6s}")
        for rn in ("whole binary", "any_anchor", "C@0.70", "B@2", "R3"):
            x = a[rn]
            fit = next((lbl for lbl, lim in WINDOWS if x["tok_o200k"] and x["tok_o200k"] <= lim), ">2M")
            print(f"{rn:14s} {x['n_fns']:7d} {x['code_bytes']:12,d} {x['tok_o200k']:14,d} "
                  f"{x['tok_cl100k']:14,d} {x['reduction_x']:9.1f}x {fit:>6s}")

    json.dump({"samples": rows_out, "aggregate": aggs,
               "tokenisers": ["tiktoken o200k_base (GPT-4o)", "tiktoken cl100k_base (GPT-4)",
                              "cross-check: token-count v0.4.0 --model gpt-4o / claude-sonnet-4-5"],
               "disasm": "capstone x86-64 linear sweep per FDE range, 'addr:\\tmn\\top' lines"},
              open(os.path.join(HERE, "results", "token_budget.json"), "w"), indent=1)
    print("\nwrote results/token_budget.json")


if __name__ == "__main__":
    main()

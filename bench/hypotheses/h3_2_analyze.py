#!/usr/bin/env python3
"""
h3_2_analyze.py — Phase 3 / hypothesis 3.2, analysis half.

Prerequisite: bench/hypotheses/h3_2_build_pe_targets.sh (rebuilds dufs/procs
for x86_64-pc-windows-msvc) and then running the new
target/release/pe_rulemine_probe binary (built from src/bin/
pe_rulemine_probe.rs, see work/PHASE_3.md (local run notes, not committed) for what that file adds and why)
against each, e.g.:

  cargo build --release --bin pe_rulemine_probe
  ./target/release/pe_rulemine_probe bench/hypotheses/v_pe/dufs.debug2.exe \
      --pdb bench/hypotheses/v_pe/dufs.pdb --crate-name dufs \
      --out bench/hypotheses/v_pe/dufs_rows.json
  (same for procs)

Computes the ceiling and A@2/R1/R3 (R2 is not attempted -- no X_caller_rel
on PE, see pe_rulemine_probe.rs's header) on dufs and procs individually and
pooled -- the first time these rules have touched a non-ELF binary.

C_user (A@2's own multiplicity term) == m_rel_structs here: both count
distinct User-origin Location structs a function directly references: same
definition, different container. P_nonrel is emitted directly by the probe.

Outputs: bench/hypotheses/h3_2_output.json, bench/hypotheses/h3_2_output.md
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PE_DIR = os.path.join(HERE, "v_pe")

RULES = {
    "A@2": lambda r: r["m_rel_structs"] >= 2 and r["p_nonrel"] <= 0,
    "R1": lambda r: r["m_rel_structs"] >= 2 and r["n_win_rel"] >= 3,
    "R3": lambda r: r["m_rel_structs"] >= 1 and r["n_win_rel"] >= 5,
    "any_anchor": lambda r: r["m_rel_structs"] >= 1,
}


def load(name):
    p = os.path.join(PE_DIR, f"{name}_rows.json")
    if not os.path.exists(p):
        return None
    return json.load(open(p))


def score(rows, rule_fn):
    labeled = [r for r in rows if r["label"] not in ("NONE", "UNKNOWN")]
    is_author = [r["label"] == "AUTHOR" for r in labeled]
    pred = [rule_fn(r) for r in labeled]
    tp = sum(1 for a, p in zip(is_author, pred) if a and p)
    pp = sum(pred)
    n_author = sum(is_author)
    return {
        "fires": pp, "tp": tp, "n_author": n_author,
        "precision": round(tp / pp, 4) if pp else None,
        "recall": round(tp / n_author, 4) if n_author else None,
    }


def main():
    data = {name: load(name) for name in ("dufs", "procs")}
    missing = [n for n, d in data.items() if d is None]
    if missing:
        print(f"MISSING: run pe_rulemine_probe for {missing} first "
              f"(see this script's header).")
        return 1

    out = {}
    for name, rows in data.items():
        out[name] = {"n_functions": len(rows)}
        for rule, fn in RULES.items():
            out[name][rule] = score(rows, fn)

    pooled_rows = data["dufs"] + data["procs"]
    out["pooled"] = {"n_functions": len(pooled_rows)}
    for rule, fn in RULES.items():
        out["pooled"][rule] = score(pooled_rows, fn)

    with open(os.path.join(HERE, "h3_2_output.json"), "w") as fh:
        json.dump(out, fh, indent=2)

    lines = ["# h3.2 -- R1/R3/A@2 and the ceiling, on PE for the first time", ""]
    lines.append("R2 not attempted: no X_caller_rel on PE (see pe_rulemine_probe.rs header).")
    lines.append("")
    for name in ("dufs", "procs", "pooled"):
        d = out[name]
        lines.append(f"## {name} (n={d['n_functions']} functions)")
        lines.append("")
        lines.append("| rule | fires | tp | precision | recall (of n_author={}) |".format(
            d["any_anchor"]["n_author"]))
        lines.append("|---|---:|---:|---:|---:|")
        for rule in ("any_anchor", "A@2", "R1", "R3"):
            r = d[rule]
            lines.append(f"| {rule} | {r['fires']} | {r['tp']} | {r['precision']} | {r['recall']} |")
        lines.append("")

    with open(os.path.join(HERE, "h3_2_output.md"), "w") as fh:
        fh.write("\n".join(lines))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

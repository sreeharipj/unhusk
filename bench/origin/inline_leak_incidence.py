#!/usr/bin/env python3
"""
inline_leak_incidence.py — per-instance mining of the "inverse leak" REPORT.md's
"The inverse leak" section already summarizes as a pooled fraction (0.1%,
`REPORT.md:50-51`). Reads only already-produced `build/*/*/{probe,ground_truth}.json`
on disk. No `cargo build`, no re-running `origin_probe`/`build_matrix.sh`.

A "leak" instance is exactly `reanalyze.py`'s `leaking` definition
(`reanalyze.py:263`): a ground-truth FDE whose `origin_probe` counts include
>=1 user-class Location, despite an independent symbol oracle (`ground_truth.py`,
nm+rustfilt) calling the *function itself* non-AUTHOR. `reanalyze.py` scopes
this to DEP only; this script reports DEP (the REPORT.md-defined "inverse
leak", unchanged) AND STD (core/alloc/std-declared functions — the
`std::slice::sort`-shaped half of `architecture.md`'s hard case, which DEP-only
scoring is blind to by construction) as two parallel, separately-labeled
breakdowns, since distinguishing them turned out to matter for interpreting
how the adversarial hardcase_probe construction (mostly STD-shaped:
`core::slice::sort` internals) relates to real-corpus incidence (mixed
STD+DEP, dominated by async-runtime DEP crates — see the accompanying
INLINE_LEAK_INCIDENCE.md).

RuleA-veto bucketing: `non_user(counts) > 0` is exactly `src/origin.rs`'s
`RuleA::decide` / `rules.py::rule_a`'s condition for returning DEP regardless
of `n` — a leak instance with >=1 non-user-class Location co-referenced in
the same FDE is one RuleA already rejects; a leak instance with ONLY
user-class Locations is invisible to RuleA (same distinction as the
hardcase_probe per-function table from the prior turn).

Every (crate, config) directory under build/ that `iterate_builds` skips
(missing probe.json or ground_truth.json — i.e. the build failed or verify_pair
never ran) is listed explicitly in the `excluded` list with which file is
missing, never silently dropped.

Usage: python3 inline_leak_incidence.py [--pretty]
Writes inline_leak_instances.json (full per-instance dump) next to this script.
"""
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from rules import iterate_builds, load_build, non_user  # noqa: E402

BUILD_ROOT = os.path.join(HERE, "build")
LEAK_SCOPES = ["DEP", "STD"]


def mine(build_root):
    instances = {scope: [] for scope in LEAK_SCOPES}
    per_crate = {scope: defaultdict(lambda: {"n_total": 0, "n_leaking": 0}) for scope in LEAK_SCOPES}
    per_config = {scope: defaultdict(lambda: {"n_total": 0, "n_leaking": 0}) for scope in LEAK_SCOPES}
    covered = set()

    for crate, config_id, dest in iterate_builds(build_root):
        covered.add((crate, config_id))
        rows, probe, gt = load_build(dest)

        gt_extra = {f["start"]: f for f in gt["functions"]}
        probe_extra = {f["start"]: f for f in probe["functions"]}

        for scope in LEAK_SCOPES:
            scoped_rows = [r for r in rows if r["actual"] == scope]
            per_crate[scope][crate]["n_total"] += len(scoped_rows)
            per_config[scope][config_id]["n_total"] += len(scoped_rows)

            for r in scoped_rows:
                if r["counts"].get("user", 0) < 1:
                    continue
                per_crate[scope][crate]["n_leaking"] += 1
                per_config[scope][config_id]["n_leaking"] += 1
                gt_row = gt_extra.get(r["start"], {})
                probe_row = probe_extra.get(r["start"], {})
                nu = non_user(r["counts"])
                instances[scope].append({
                    "crate": crate,
                    "config": config_id,
                    "start": r["start"],
                    "end": gt_row.get("end") or probe_row.get("end"),
                    "gt_crate": gt_row.get("crate"),
                    "counts": r["counts"],
                    "files": probe_row.get("files", []),
                    "rule_a_veto": nu > 0,
                })

    # Explicit exclusion listing: every (crate, config) dir on disk that
    # iterate_builds did NOT yield, with the specific missing file named.
    excluded = []
    seen_crate_dirs = sorted(os.listdir(build_root)) if os.path.isdir(build_root) else []
    for crate in seen_crate_dirs:
        cdir = os.path.join(build_root, crate)
        if not os.path.isdir(cdir):
            continue
        for config_id in sorted(os.listdir(cdir)):
            ddir = os.path.join(cdir, config_id)
            if not os.path.isdir(ddir) or (crate, config_id) in covered:
                continue
            probe_path = os.path.join(ddir, "probe.json")
            gt_path = os.path.join(ddir, "ground_truth.json")
            missing = []
            if not os.path.exists(probe_path):
                missing.append("probe.json")
            if not os.path.exists(gt_path):
                missing.append("ground_truth.json")
            if not missing:
                missing.append("unknown (dir present, both files present, but not yielded — investigate)")
            excluded.append({"crate": crate, "config": config_id, "missing": missing})

    out = {"excluded": excluded, "n_crates_covered": len({c for c, _ in covered}),
           "n_configs_covered": len({cfg for _, cfg in covered})}

    for scope in LEAK_SCOPES:
        pooled_total = sum(v["n_total"] for v in per_crate[scope].values())
        pooled_leaking = sum(v["n_leaking"] for v in per_crate[scope].values())
        insts = instances[scope]
        veto_yes = sum(1 for i in insts if i["rule_a_veto"])
        veto_no = len(insts) - veto_yes
        out[scope] = {
            "pooled_n_total": pooled_total,
            "pooled_n_leaking": pooled_leaking,
            "pooled_fraction": (pooled_leaking / pooled_total) if pooled_total else None,
            "per_crate": dict(sorted(per_crate[scope].items(), key=lambda kv: -kv[1]["n_leaking"])),
            "per_config": dict(sorted(per_config[scope].items(), key=lambda kv: -kv[1]["n_leaking"])),
            "rule_a_veto_yes": veto_yes,
            "rule_a_veto_no": veto_no,
            "instances": insts,
        }
    return out


def main():
    out = mine(BUILD_ROOT)
    with open(os.path.join(HERE, "inline_leak_instances.json"), "w") as fh:
        if "--pretty" in sys.argv:
            json.dump(out, fh, indent=2)
        else:
            json.dump(out, fh)

    print(f"crates covered: {out['n_crates_covered']}, configs covered: {out['n_configs_covered']}")
    for scope in LEAK_SCOPES:
        s = out[scope]
        frac = s["pooled_fraction"] or 0.0
        print(f"\n=== {scope} leak ===")
        print(f"pooled: {s['pooled_n_leaking']}/{s['pooled_n_total']} = {frac*100:.4f}%")
        print(f"RuleA veto: yes={s['rule_a_veto_yes']} no={s['rule_a_veto_no']} "
              f"(n={len(s['instances'])})")
    print(f"\nexcluded (crate,config) dirs: {len(out['excluded'])}")
    for e in out["excluded"]:
        print(f"  EXCLUDED {e['crate']}/{e['config']}: missing {', '.join(e['missing'])}")


if __name__ == "__main__":
    main()

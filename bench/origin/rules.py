"""
rules.py — Python mirror of `src/origin.rs`'s `Rule` implementations, and the
loader that joins one build's `probe.json` (origin_probe's raw per-FDE class
counts) against its `ground_truth.json` (the symbol oracle's per-FDE label).

Why a Python mirror instead of shelling out to a Rust binary per (N, r)
value: `origin_probe` deliberately emits counts only, not decisions (see its
module docstring) — re-running it per sweep value would mean re-invoking the
probe ~21 times per binary for no new information, since every decision here
is a pure function of the same seven counts. This mirror's three functions
are validated against the exact boundary cases `src/origin.rs`'s own
`rule_a_*`/`rule_b_*`/`rule_c_*` unit tests cover (`total==0`, the N-1/N
edge, the ratio-exactly-at-r edge) — see `test_rules.py`.
"""
import json
import os
import re

CLASSES = ["user", "workspace", "registry", "git", "rustc", "generated", "unknown"]
GT_ACTUAL_CLASSES = ["AUTHOR", "WORKSPACE", "DEP", "STD"]
PREDICTED_CLASSES = ["AUTHOR", "DEP", "AMBIGUOUS", "NONE"]

N_SWEEP = [1, 2, 3, 4, 5, 6]
R_SWEEP = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]


def total(counts):
    return sum(counts.get(c, 0) for c in CLASSES)


def non_user(counts):
    return total(counts) - counts.get("user", 0)


def rule_a(counts, n):
    """RULE_A (strict) — src/origin.rs's `RuleA::decide`."""
    if total(counts) == 0:
        return "NONE"
    if non_user(counts) > 0:
        return "DEP"
    return "AUTHOR" if counts.get("user", 0) >= n else "AMBIGUOUS"


def rule_b(counts, n):
    """RULE_B (std-tolerant) — src/origin.rs's `RuleB::decide`."""
    if total(counts) == 0:
        return "NONE"
    if counts.get("registry", 0) > 0 or counts.get("git", 0) > 0:
        return "DEP"
    u = counts.get("user", 0)
    if u >= n:
        return "AUTHOR"
    if u == 0:
        return "DEP"
    return "AMBIGUOUS"


def rule_c(counts, r):
    """RULE_C (ratio baseline) — src/origin.rs's `RuleC::decide`."""
    t = total(counts)
    if t == 0:
        return "NONE"
    ratio = counts.get("user", 0) / t
    return "AUTHOR" if ratio >= r else "DEP"


def all_rules():
    """[(name, fn(counts) -> decision), ...] for the full N/r sweep."""
    rules = []
    for n in N_SWEEP:
        rules.append((f"A@{n}", lambda c, n=n: rule_a(c, n)))
    for n in N_SWEEP:
        rules.append((f"B@{n}", lambda c, n=n: rule_b(c, n)))
    for r in R_SWEEP:
        rules.append((f"C@{r:.2f}", lambda c, r=r: rule_c(c, r)))
    return rules


def sanitize(rule_name):
    return rule_name.replace("@", "_").replace(".", "p")


CONFIG_RE = re.compile(r"lto-(?P<lto>\w+)_opt-(?P<opt>\w+)_panic-(?P<panic>\w+)")


def parse_config(config_id):
    m = CONFIG_RE.match(config_id)
    if not m:
        return {"lto": "?", "opt": "?", "panic": "?"}
    return m.groupdict()


def iterate_builds(build_root):
    """Yield (crate, config_id, dest_dir) for every build with both probe.json
    and ground_truth.json present (i.e. verify_pair passed and both
    downstream steps ran — see build_matrix.sh)."""
    if not os.path.isdir(build_root):
        return
    for crate in sorted(os.listdir(build_root)):
        cdir = os.path.join(build_root, crate)
        if not os.path.isdir(cdir):
            continue
        for config_id in sorted(os.listdir(cdir)):
            dest = os.path.join(cdir, config_id)
            probe_path = os.path.join(dest, "probe.json")
            gt_path = os.path.join(dest, "ground_truth.json")
            if os.path.exists(probe_path) and os.path.exists(gt_path):
                yield crate, config_id, dest


def load_build(dest):
    """Return (rows, probe_doc, gt_doc). Each row: {start, counts, actual}."""
    with open(os.path.join(dest, "probe.json")) as fh:
        probe = json.load(fh)
    with open(os.path.join(dest, "ground_truth.json")) as fh:
        gt = json.load(fh)

    gt_by_start = {f["start"]: f["label"] for f in gt["functions"]}
    rows = []
    for f in probe["functions"]:
        rows.append({
            "start": f["start"],
            "counts": f["counts"],
            "actual": gt_by_start.get(f["start"]),  # None if GT has no FDE at this addr
        })
    return rows, probe, gt

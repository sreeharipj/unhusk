#!/usr/bin/env python3
"""Re-run the current unhusk build against the arsenal_run_20260712_2324 corpus
(352 wild malware samples, 8 shipped-release benign tools, 60 non-Rust binaries,
63 labeled opt/lto/panic/rustc variant binaries, 9 DWARF debug/stripped pairs) --
the same binaries that July's arsenal readiness run used, so results are a direct
before/after against variants/index.json and results/B_attribution_summary.json.

Does not touch or copy the malware samples into the repo. Only adds owner-read
(chmod u+rX, no execute) to the malware corpus so this process can read it --
same no-execute safety invariant the July run already enforced.
"""
import json
import re
import subprocess
import time
from pathlib import Path

ARSENAL = Path("/home/user/arsenal_run_20260712_2324")
UNHUSK = Path("/home/user/Videos/unhusk/target/release/unhusk")
HERE = Path(__file__).resolve().parent
TIMEOUT = 60

HEADLINE_RE = re.compile(
    r"Certain precision\s*:\s*([\d.]+)%\s*\n"
    r"\s*Certain recall\s*:\s*([\d.]+)%\s*\((\d+)/(\d+) DWARF-user fns reached by certain\)\s*\n"
    r"\s*Overall recall\s*:\s*([\d.]+)%"
)


def run_unhusk(args, timeout=TIMEOUT):
    try:
        p = subprocess.run([str(UNHUSK)] + list(args), capture_output=True, timeout=timeout, text=True)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"


def magic(path):
    try:
        with open(path, "rb") as f:
            b = f.read(4)
    except Exception as e:
        return f"unreadable:{e}"
    if b[:4] == b"\x7fELF":
        return "ELF"
    if b[:2] == b"MZ":
        return "PE"
    return "unknown"


def precision_json(path):
    rc, out, err = run_unhusk(["--precision", "--json", str(path)])
    row = {"returncode": rc}
    if rc == 0:
        try:
            d = json.loads(out)
            row["n_functions"] = len(d.get("functions", []))
            row["arch"] = d.get("arch")
        except Exception as e:
            row["parse_error"] = str(e)
            row["n_functions"] = None
    else:
        row["error"] = (err or "").strip()[-300:]
        row["n_functions"] = None
    return row


def malware_rows():
    rows = []
    subprocess.run(["chmod", "-R", "u+rX", str(ARSENAL / "corpus" / "malware")], check=True)
    malware_dir = ARSENAL / "corpus" / "malware"
    dirs = sorted([d for d in malware_dir.iterdir() if d.is_dir()])
    for i, d in enumerate(dirs):
        files = [f for f in d.iterdir() if f.is_file()]
        for f in files:
            fmt = magic(f)
            row = {"category": "malware", "hash_dir": d.name, "filename": f.name, "format": fmt}
            if fmt in ("ELF", "PE"):
                row.update(precision_json(f))
            else:
                row["n_functions"] = None
                row["skipped"] = True
            rows.append(row)
        if (i + 1) % 50 == 0:
            print(f"  malware: {i+1}/{len(dirs)} dirs done", flush=True)
    return rows


def benign_shipped_rows():
    rows = []
    bs_dir = ARSENAL / "corpus" / "benign_shipped"
    for tool_dir in sorted(bs_dir.iterdir()):
        bindir = tool_dir / "bin"
        if not bindir.is_dir():
            continue
        for f in sorted(bindir.iterdir()):
            if not f.is_file():
                continue
            fmt = magic(f)
            row = {"category": "benign_shipped", "tool": tool_dir.name, "filename": f.name, "format": fmt}
            row.update(precision_json(f))
            rows.append(row)
    return rows


def nonrust_rows():
    rows = []
    nr_dir = ARSENAL / "corpus" / "nonrust"
    for f in sorted(nr_dir.iterdir()):
        if not f.is_file():
            continue
        fmt = magic(f)
        row = {"category": "nonrust", "filename": f.name, "format": fmt}
        row.update(precision_json(f))
        rows.append(row)
    return rows


def variant_rows():
    rows = []
    old_index = json.loads((ARSENAL / "variants" / "index.json").read_text())
    old_by_id = {e["variant_id"]: e for e in old_index}
    matrix_dir = ARSENAL / "variants" / "matrix"
    for proj_dir in sorted(matrix_dir.iterdir()):
        if not proj_dir.is_dir():
            continue
        for f in sorted(proj_dir.iterdir()):
            if not f.is_file():
                continue
            variant_id = f.name
            row = {"category": "variant", "variant_id": variant_id, "project": proj_dir.name}
            row.update(precision_json(f))
            old = old_by_id.get(variant_id)
            if old:
                row["july_n_functions"] = old.get("location_entries_recovered")
                row["july_status"] = old.get("status")
                row["opt"] = old.get("opt")
                row["lto"] = old.get("lto")
                row["panic"] = old.get("panic")
                row["rustc"] = old.get("rustc")
            rows.append(row)
    return rows


def validate_rows():
    rows = []
    db_dir = ARSENAL / "variants" / "_debug_baseline"
    dbs_dir = ARSENAL / "variants" / "_debug_baseline_stripped"
    for proj in sorted(p.name for p in db_dir.iterdir()):
        unstripped = db_dir / proj
        stripped = dbs_dir / proj
        if not (unstripped.is_file() and stripped.is_file()):
            continue
        rc, out, err = run_unhusk(["--validate", str(unstripped), str(stripped)], timeout=60)
        vrow = {"project": proj, "returncode": rc}
        if rc == 0:
            m = HEADLINE_RE.search(out)
            if m:
                vrow["certain_precision_pct"] = float(m.group(1))
                vrow["certain_recall_pct"] = float(m.group(2))
                vrow["certain_recall_frac"] = f"{m.group(3)}/{m.group(4)}"
                vrow["overall_recall_pct"] = float(m.group(5))
            else:
                vrow["parse_error"] = "headline regex did not match"
                vrow["tail"] = out[-800:]
        else:
            vrow["error"] = (err or "").strip()[-300:]
        rows.append(vrow)
    return rows


def main():
    t0 = time.time()
    all_rows = []

    print("=== malware corpus ===", flush=True)
    all_rows += malware_rows()

    print("=== benign_shipped ===", flush=True)
    all_rows += benign_shipped_rows()

    print("=== nonrust ===", flush=True)
    all_rows += nonrust_rows()

    print("=== variants/matrix ===", flush=True)
    all_rows += variant_rows()

    (HERE / "rows.json").write_text(json.dumps(all_rows, indent=2))

    print("=== DWARF validate pairs ===", flush=True)
    vrows = validate_rows()
    (HERE / "validate_rows.json").write_text(json.dumps(vrows, indent=2))

    dt = time.time() - t0
    print(f"done: {len(all_rows)} rows, {len(vrows)} validate rows, {dt:.0f}s", flush=True)


if __name__ == "__main__":
    main()

"""
unhusk-poc -- recover author-written functions from a stripped Rust PE binary.

Rust's compiler embeds a `core::panic::Location { file, line, col }` struct at
every reachable panic site (`.unwrap()`, slice indexing, `panic!`, integer
overflow checks, ...) so a crash can print `panicked at src/main.rs:42`. Those
structs live in read-only data, not in the symbol table, so `strip` leaves them
intact. This script:

  1. reads every `Location` struct out of `.rdata`;
  2. classifies each struct's embedded source path as author / std / dependency;
  3. disassembles every function (bounds come from `.pdata`) and records which
     functions load a *user* `Location` through a RIP-relative address;
  4. ranks those functions -- STRONG if a function references >= N distinct user
     Locations, SINGLE if exactly one.

The ranking rests on one observation: a function that references several of its
own panic sites is almost certainly hand-written. A single user closure inlined
into a library generic (`slice::sort_by`, a rayon iterator) references exactly
one -- hence the multiplicity threshold.

This is a teaching reimplementation of the PE path of `unhusk`. It keeps the
mechanism and drops the hardening: no packed-input detection, no call-graph
propagation to unanchored functions, no relocation-table string discovery, and a
deliberately small path taxonomy.

--------------------------------------------------------------------------------
Install:  pip install pefile iced-x86

Run:      python unhusk_pe_poc.py PROGRAM.exe
          python unhusk_pe_poc.py PROGRAM.exe --crate mytool --min-anchors 2
          python unhusk_pe_poc.py PROGRAM.exe --json

Output:   one line per author-attributed function --

            0x14000123f..0x140001480  [STRONG]  anchors=3  src/main.rs, src/scan.rs

          `--crate NAME` promotes a `cargo install`-style build's registry paths
          to author code (repeatable); omit it and the script guesses the crate
          name from the file name.

Scope:    x86-64 PE32+ (`.exe` / `.dll`) only. Binaries built with
          `-Z build-std panic_immediate_abort` or `--remap-path-prefix` carry no
          usable Location data and will report nothing.
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import argparse
import bisect
import json
import re
import struct
import sys
from dataclasses import dataclass

import pefile
from iced_x86 import Decoder

LOCATION_SIZE = 24  # file ptr (8) + file len (8) + line (u32) + col (u32)
MAX_PATH_LEN = 512
MAX_LINE = 200_000

# Modern (`library/core/src/...`) and pre-2018 (`src/libcore/...`) stdlib layouts.
_STD_PATH = re.compile(
    r"(^|/)(rustc/|library/(core|alloc|std|proc_macro|test|panic_unwind|panic_abort|backtrace)/)"
)
_OLD_STD_PATH = re.compile(
    r"(^|/)src/lib(core|alloc|std|proc_macro|test|panic_unwind|panic_abort|unwind|backtrace)/"
)
# `.../registry/src/<host>/<crate>-<version>/...` or a vendored `.../crates.io/<crate>-<version>/...`.
_REGISTRY_CRATE = re.compile(
    r"(?:cargo/registry/src/[^/]+|crates\.io(?:-[^/]+)?)/([A-Za-z0-9_-]+?)-\d[^/]*/"
)
_WINDOWS_ABS = re.compile(r"^[A-Za-z]:/")


def classify_path(path: str, root_crates: set[str]) -> str:
    """Classify one embedded source path as 'user', 'std', 'dep', or 'unknown'."""
    # Windows builds embed backslash paths; every rule below keys on '/', so this
    # must run first or a dependency path falls through to the 'user' branch.
    p = path.replace("\\", "/")

    if _STD_PATH.search(p) or _OLD_STD_PATH.search(p):
        return "std"

    crate = _REGISTRY_CRATE.search(p)
    if crate:
        # `cargo install` builds ship the author's own crate from the registry.
        return "user" if crate.group(1) in root_crates else "dep"
    if "/rust/deps/" in p or "/cargo/git/" in p:
        return "dep"

    # A relative path that escaped every library rule is author code.
    if not p.startswith("/") and not _WINDOWS_ABS.match(p):
        return "user"
    return "unknown"


@dataclass(frozen=True)
class Location:
    struct_rva: int
    file: str
    line: int
    col: int
    origin: str  # 'user' | 'std' | 'dep' | 'unknown'


def section_by_name(pe: pefile.PE, name: bytes):
    for section in pe.sections:
        if section.Name.rstrip(b"\x00") == name:
            return section
    return None


def read_rva(pe: pefile.PE, rva: int, length: int) -> bytes | None:
    """`length` bytes at `rva`, or None if the range is unmapped or truncated."""
    try:
        data = pe.get_data(rva, length)
    except pefile.PEFormatError:
        return None
    return data if len(data) == length else None


def function_ranges(pe: pefile.PE) -> list[tuple[int, int]]:
    """`(begin_rva, end_rva)` for every function with unwind info, from `.pdata`.

    `.pdata` is a packed array of 12-byte RUNTIME_FUNCTION records. Every
    function that can panic makes a call, and every function that makes a call
    has an entry here, so this misses nothing the rest of the script needs.
    """
    section = section_by_name(pe, b".pdata")
    if section is None:
        return []
    blob = section.get_data()
    ranges = []
    for offset in range(0, len(blob) - 11, 12):
        begin, end, _unwind = struct.unpack_from("<III", blob, offset)
        if end > begin:
            ranges.append((begin, end))
    return ranges


def dir64_reloc_rvas(pe: pefile.PE) -> list[int]:
    """RVAs of every slot holding an absolute 64-bit pointer (IMAGE_REL_BASED_DIR64).

    On PE the `Location.file` pointer is stored as a real address, so this list
    only tells us which `.rdata` words are pointers worth decoding as a struct.
    """
    if not hasattr(pe, "DIRECTORY_ENTRY_BASERELOC"):
        return []
    return [
        entry.rva
        for block in pe.DIRECTORY_ENTRY_BASERELOC
        for entry in block.entries
        if entry.type == 10
    ]


def recover_locations(pe: pefile.PE, root_crates: set[str]) -> list[Location]:
    """Every `core::panic::Location` struct reachable from a `.rdata` pointer slot."""
    image_base = pe.OPTIONAL_HEADER.ImageBase
    rdata = section_by_name(pe, b".rdata")

    def in_rdata(rva: int) -> bool:
        if rdata is None:
            return True
        return rdata.VirtualAddress <= rva < rdata.VirtualAddress + rdata.Misc_VirtualSize

    found: dict[int, Location] = {}
    for struct_rva in dir64_reloc_rvas(pe):
        if struct_rva in found or not in_rdata(struct_rva):
            continue
        raw = read_rva(pe, struct_rva, LOCATION_SIZE)
        if raw is None:
            continue
        ptr_va, file_len, line, col = struct.unpack("<QQII", raw)

        # Shape check -- reject the many DIR64 slots that are ordinary pointers.
        if not 0 < file_len <= MAX_PATH_LEN:
            continue
        if not 0 < line <= MAX_LINE or col == 0:
            continue
        if ptr_va < image_base:
            continue
        path_bytes = read_rva(pe, ptr_va - image_base, file_len)
        if path_bytes is None:
            continue
        try:
            path = path_bytes.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if not path.endswith(".rs"):
            continue

        found[struct_rva] = Location(
            struct_rva, path, line, col, classify_path(path, root_crates)
        )

    return sorted(found.values(), key=lambda loc: (loc.origin, loc.file, loc.line, loc.col))


def user_locations_referenced(
    code: bytes, base_rva: int, location_starts: list[int]
) -> set[int]:
    """Struct RVAs of every Location this function loads via `lea reg, [rip+disp]`.

    iced-x86 resolves the RIP-relative target for us. The decoder's IP is set to
    the function's RVA, so the target lands in RVA space with no fixup. A load of
    a field in the middle of a struct still attributes to the struct -- hence the
    24-byte containment window rather than an exact match.
    """
    hits: set[int] = set()
    for instr in Decoder(64, code, ip=base_rva):
        if not instr.is_ip_rel_memory_operand:
            continue
        target = instr.ip_rel_memory_address
        i = bisect.bisect_right(location_starts, target)
        if i and target < location_starts[i - 1] + LOCATION_SIZE:
            hits.add(location_starts[i - 1])
    return hits


def guess_root_crate(paths: list[str], binary_stem: str) -> set[str]:
    """Best-effort root-crate name for `cargo install`-style layouts.

    There, author code sits under `registry/src/...` like any dependency; the
    only tell is a crate name that matches the binary's file name.
    """
    stem = binary_stem.replace("-", "_")
    crates = set()
    for path in paths:
        m = _REGISTRY_CRATE.search(path.replace("\\", "/"))
        if m:
            crates.add(m.group(1))
    return {c for c in crates if c.replace("-", "_") == stem}


def emit(binary: str, results: list[tuple], min_anchors: int, as_json: bool) -> None:
    if as_json:
        # start/end are hex strings: a 64-bit address does not round-trip
        # through a JSON number (which is an f64).
        print(json.dumps(
            {
                "binary": binary,
                "format": "pe",
                "min_anchors": min_anchors,
                "functions": [
                    {
                        "start": hex(begin),
                        "end": hex(end),
                        "size": end - begin,
                        "tier": tier,
                        "anchor_count": count,
                        "anchor_files": files,
                    }
                    for begin, end, tier, count, files in results
                ],
            },
            indent=2,
        ))
        return

    print(f"unhusk-poc (PE): {binary} -- {len(results)} author-attributed function(s)")
    for begin, end, tier, count, files in results:
        print(f"  {hex(begin)}..{hex(end)}  [{tier.upper()}]  anchors={count}  {', '.join(files)}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recover author-written functions from a stripped Rust PE binary."
    )
    parser.add_argument("binary")
    parser.add_argument(
        "--crate",
        action="append",
        default=[],
        help="promote this crate's registry paths to author code (repeatable)",
    )
    parser.add_argument(
        "--min-anchors",
        type=int,
        default=2,
        help="distinct user Locations a function needs for the STRONG tier (default 2)",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = parser.parse_args()

    try:
        pe = pefile.PE(args.binary)
    except (OSError, pefile.PEFormatError) as exc:
        print(f"cannot read PE: {exc}", file=sys.stderr)
        return 2
    if pe.OPTIONAL_HEADER.Magic != 0x20B:
        print("only x86-64 PE32+ is supported", file=sys.stderr)
        return 2

    stem = re.sub(r"\.(exe|dll)$", "", args.binary.rsplit("/", 1)[-1], flags=re.IGNORECASE)

    root_crates = set(args.crate)
    locations = recover_locations(pe, root_crates)
    if not root_crates:
        guessed = guess_root_crate([loc.file for loc in locations], stem)
        if guessed:
            root_crates = guessed
            locations = recover_locations(pe, root_crates)

    user_rvas = {loc.struct_rva for loc in locations if loc.origin == "user"}
    file_of = {loc.struct_rva: loc.file for loc in locations}
    location_starts = sorted(loc.struct_rva for loc in locations)

    min_anchors = max(args.min_anchors, 1)
    results = []
    for begin, end in sorted(function_ranges(pe)):
        code = read_rva(pe, begin, end - begin)
        if code is None:
            continue
        anchors = user_locations_referenced(code, begin, location_starts) & user_rvas
        if not anchors:
            continue
        tier = "strong" if len(anchors) >= min_anchors else "single"
        files = sorted({file_of[a] for a in anchors})
        results.append((begin, end, tier, len(anchors), files))

    emit(args.binary, results, min_anchors, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())

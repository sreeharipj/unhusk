//! rulemine_extract — dump **raw per-function observables** from one stripped
//! x86-64 ELF Rust binary, for `bench/rulemine/`'s from-first-principles rule
//! search.
//!
//! Design rule for this program: **emit observations, never decisions.**
//! `bench/origin/`'s `origin_probe` already emits per-FDE counts bucketed into
//! unhusk's seven-way path taxonomy — which pre-commits the analysis to that
//! taxonomy being the right one. This extractor deliberately does not. It emits
//! the raw `Location` records (path string verbatim, line, column, address),
//! the raw reference edges from functions to those records, the raw call
//! graph, the raw reference edges to source-path *strings* that are not reached
//! through a `Location` struct at all, and a per-function instruction-shape
//! summary. Every bucket, threshold, class and rule is then defined downstream
//! in Python, where an alternative taxonomy can be tested against the same
//! bytes without re-running this program.
//!
//! Three parsing steps are taken from the `unhusk` library rather than
//! rewritten, because they are load-bearing, audited, and orthogonal to the
//! question being asked: ELF/relocation loading (`elf::ParsedElf`), source-path
//! string recovery (`strings::classify`), `.eh_frame` FDE recovery
//! (`frame::parse_eh_frame`), and `core::panic::Location` reconstruction
//! (`locate::find_locations`). `strings::classify` is called with an **empty**
//! `root_crates` list, exactly as `origin_probe` does: feeding the tool the
//! authorship answer would measure the root-detection heuristic instead of the
//! mechanism under test.
//!
//! The instruction scan is this program's own, not `unhusk::xref::scan`, because
//! xref collects precisely what unhusk's rules need (user-Location hits, dep
//! boundaries, call edges) and discards the rest. Here every RIP-relative
//! effective address is resolved and bucketed by *target section*, so that
//! "references a Location", "references a source-path string directly",
//! "references some other read-only constant" and "references mutable data" are
//! four separately-countable channels rather than one.

use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::path::PathBuf;

use anyhow::{Context, Result};
use clap::Parser;
use iced_x86::{Decoder, DecoderOptions, FlowControl, Instruction, OpKind, Register};
use rayon::prelude::*;
use serde::Serialize;
use sha2::{Digest, Sha256};

use unhusk::elf::ParsedElf;

#[derive(Parser)]
#[command(name = "rulemine_extract", about = "Raw per-function observables from a stripped ELF")]
struct Args {
    /// Stripped ELF binary to analyse.
    binary: PathBuf,
    /// Write JSON here (default: stdout).
    #[arg(short, long)]
    out: Option<PathBuf>,
    /// Free-form provenance tags recorded verbatim in the output header.
    #[arg(long)]
    crate_name: Option<String>,
    #[arg(long)]
    config: Option<String>,
}

// ── Output schema ─────────────────────────────────────────────────────────────

#[derive(Serialize)]
struct SectionInfo {
    name: String,
    vaddr: u64,
    size: u64,
}

/// One reconstructed `core::panic::Location`. `file` is the path string
/// **verbatim**, uninterpreted — classification happens downstream.
#[derive(Serialize)]
struct LocOut {
    id: u32,
    va: u64,
    file: String,
    line: u32,
    col: u32,
}

/// One source-path-looking string in read-only data, whether or not any
/// `Location` struct points at it.
#[derive(Serialize)]
struct StrOut {
    id: u32,
    va: u64,
    len: u32,
    s: String,
}

/// One function, as delimited by its `.eh_frame` FDE.
#[derive(Serialize)]
struct FnOut {
    s: u64,
    e: u64,
    /// Instruction-shape summary. Counts, not decisions.
    n_insn: u32,
    n_call: u32,
    n_icall: u32,
    n_cond_br: u32,
    n_uncond_br: u32,
    n_ibr: u32,
    n_ret: u32,
    n_exception: u32,
    /// Distinct RIP-relative effective addresses referenced, by target region.
    n_rip_ref: u32,
    n_ref_rodata: u32,
    n_ref_relro: u32,
    n_ref_data: u32,
    n_ref_text: u32,
    n_ref_other: u32,
    /// Distinct `Location` structs whose 24-byte body this function references.
    locs: Vec<u32>,
    /// Distinct source-path strings referenced **directly** (a pointer to the
    /// string bytes themselves, not to a `Location` struct that names it).
    strs: Vec<u32>,
    /// Direct near-call targets that are themselves FDE starts.
    callees: Vec<u64>,
}

#[derive(Serialize)]
struct Report {
    schema: &'static str,
    binary: String,
    sha256: String,
    crate_name: Option<String>,
    config: Option<String>,
    arch: &'static str,
    is_pie: bool,
    /// `eh_frame` (intact), `eh_frame_hdr` (recovered), or
    /// `call_target_fallback` (approximate). Recorded because `panic=abort`
    /// builds can lose `.eh_frame`, and a coverage loss must stay visible.
    fde_source: &'static str,
    n_relative_relocs: usize,
    sections: Vec<SectionInfo>,
    locations: Vec<LocOut>,
    strings: Vec<StrOut>,
    functions: Vec<FnOut>,
    warnings: Vec<String>,
}

// ── Address lookup tables ─────────────────────────────────────────────────────

/// A half-open `[start, end)` address range carrying an id, searched by one
/// `partition_point`. Used for both the 24-byte `Location` bodies and the
/// source-path string bodies.
struct RangeTable {
    starts: Vec<u64>,
    ends: Vec<u64>,
    ids: Vec<u32>,
}

impl RangeTable {
    fn build(mut items: Vec<(u64, u64, u32)>) -> Self {
        items.sort_unstable_by_key(|&(s, _, _)| s);
        RangeTable {
            starts: items.iter().map(|i| i.0).collect(),
            ends: items.iter().map(|i| i.1).collect(),
            ids: items.iter().map(|i| i.2).collect(),
        }
    }
    #[inline]
    fn lookup(&self, addr: u64) -> Option<u32> {
        let idx = self.starts.partition_point(|&s| s <= addr);
        if idx == 0 {
            return None;
        }
        if addr < self.ends[idx - 1] {
            Some(self.ids[idx - 1])
        } else {
            None
        }
    }
}

/// Which section an address falls in, coarsened to the four regions that carry
/// different meaning for a Rust binary: read-only constants, relocated
/// read-only data (vtables and `Location` structs live here), mutable data, and
/// code.
#[derive(Clone, Copy, PartialEq, Eq)]
enum Region {
    RoData,
    Relro,
    Data,
    Text,
    Other,
}

struct RegionMap {
    bounds: Vec<(u64, u64, Region)>,
}

impl RegionMap {
    fn build(elf: &ParsedElf) -> Self {
        let mut bounds = Vec::new();
        for (name, sec) in &elf.sections {
            let region = match name.as_str() {
                ".rodata" | ".rodata.cst16" | ".gcc_except_table" => Region::RoData,
                ".data.rel.ro" | ".got" | ".got.plt" => Region::Relro,
                ".data" | ".bss" | ".tdata" | ".tbss" => Region::Data,
                ".text" | ".init" | ".fini" | ".plt" | ".plt.sec" => Region::Text,
                _ => Region::Other,
            };
            if sec.size() > 0 {
                bounds.push((sec.vaddr, sec.vaddr + sec.size(), region));
            }
        }
        bounds.sort_unstable_by_key(|b| b.0);
        RegionMap { bounds }
    }
    #[inline]
    fn region(&self, addr: u64) -> Region {
        let idx = self.bounds.partition_point(|b| b.0 <= addr);
        if idx == 0 {
            return Region::Other;
        }
        let b = &self.bounds[idx - 1];
        if addr < b.1 {
            b.2
        } else {
            Region::Other
        }
    }
}

// ── Per-function scan ─────────────────────────────────────────────────────────

#[allow(clippy::too_many_lines)]
fn scan_one(
    text: &unhusk::elf::Section,
    text_base: u64,
    fn_start: u64,
    fn_end: u64,
    loc_tab: &RangeTable,
    str_tab: &RangeTable,
    regions: &RegionMap,
    fde_starts: &BTreeSet<u64>,
) -> FnOut {
    let mut out = FnOut {
        s: fn_start,
        e: fn_end,
        n_insn: 0,
        n_call: 0,
        n_icall: 0,
        n_cond_br: 0,
        n_uncond_br: 0,
        n_ibr: 0,
        n_ret: 0,
        n_exception: 0,
        n_rip_ref: 0,
        n_ref_rodata: 0,
        n_ref_relro: 0,
        n_ref_data: 0,
        n_ref_text: 0,
        n_ref_other: 0,
        locs: Vec::new(),
        strs: Vec::new(),
        callees: Vec::new(),
    };

    let off = match usize::try_from(fn_start.saturating_sub(text_base)) {
        Ok(v) => v,
        Err(_) => return out,
    };
    let len = match usize::try_from(fn_end.saturating_sub(fn_start)) {
        Ok(v) => v,
        Err(_) => return out,
    };
    if len == 0 || off + len > text.data.len() {
        return out;
    }

    let mut decoder = Decoder::with_ip(64, &text.data[off..off + len], fn_start, DecoderOptions::NONE);
    let mut instr = Instruction::default();

    let mut rip_targets: BTreeSet<u64> = BTreeSet::new();
    let mut locs: BTreeSet<u32> = BTreeSet::new();
    let mut strs: BTreeSet<u32> = BTreeSet::new();
    let mut callees: BTreeSet<u64> = BTreeSet::new();

    while decoder.can_decode() {
        decoder.decode_out(&mut instr);
        out.n_insn += 1;

        match instr.flow_control() {
            FlowControl::Call => out.n_call += 1,
            FlowControl::IndirectCall => out.n_icall += 1,
            FlowControl::ConditionalBranch => out.n_cond_br += 1,
            FlowControl::UnconditionalBranch => out.n_uncond_br += 1,
            FlowControl::IndirectBranch => out.n_ibr += 1,
            FlowControl::Return => out.n_ret += 1,
            FlowControl::Exception => out.n_exception += 1,
            _ => {}
        }

        if instr.memory_base() == Register::RIP {
            // iced-x86 pre-adds next-IP for RIP-relative operands: this is the
            // absolute effective address already, do not add IP again.
            let ea = instr.memory_displacement64();
            if ea != 0 {
                rip_targets.insert(ea);
            }
        }

        if instr.flow_control() == FlowControl::Call
            && instr.op_count() == 1
            && instr.op_kind(0) == OpKind::NearBranch64
        {
            let target = instr.near_branch64();
            if fde_starts.contains(&target) {
                callees.insert(target);
            }
        }
    }

    for &ea in &rip_targets {
        if let Some(id) = loc_tab.lookup(ea) {
            locs.insert(id);
        }
        if let Some(id) = str_tab.lookup(ea) {
            strs.insert(id);
        }
        match regions.region(ea) {
            Region::RoData => out.n_ref_rodata += 1,
            Region::Relro => out.n_ref_relro += 1,
            Region::Data => out.n_ref_data += 1,
            Region::Text => out.n_ref_text += 1,
            Region::Other => out.n_ref_other += 1,
        }
    }

    out.n_rip_ref = u32::try_from(rip_targets.len()).unwrap_or(u32::MAX);
    out.locs = locs.into_iter().collect();
    out.strs = strs.into_iter().collect();
    out.callees = callees.into_iter().collect();
    out
}

// ── main ──────────────────────────────────────────────────────────────────────

fn main() -> Result<()> {
    let args = Args::parse();

    let bytes = std::fs::read(&args.binary).context("reading binary")?;
    let sha256 = format!("{:x}", Sha256::digest(&bytes));
    drop(bytes);

    let elf = ParsedElf::load(&args.binary).context("loading ELF")?;

    // Empty root_crates: no authorship hint is fed to the extractor.
    let root_crates: Vec<String> = Vec::new();
    let strings = unhusk::strings::classify(&elf, &root_crates);
    let locations = unhusk::locate::find_locations(&elf, &strings);

    let (mut fn_map, mut fde_source) = match unhusk::frame::parse_eh_frame(&elf) {
        Ok(m) if !m.is_empty() => (m, "eh_frame"),
        _ => (unhusk::frame::FunctionMap::default(), ""),
    };
    if fn_map.is_empty() {
        fn_map = unhusk::frame::fallback_function_map(&elf);
        fde_source = if elf.section(".eh_frame_hdr").is_some() {
            "eh_frame_hdr"
        } else {
            "call_target_fallback"
        };
    }

    // Location bodies are 24 bytes: ptr(8) + len(8) + line(4) + col(4).
    let loc_tab = RangeTable::build(
        locations
            .iter()
            .enumerate()
            .map(|(i, l)| (l.struct_vaddr, l.struct_vaddr + 24, u32::try_from(i).unwrap_or(u32::MAX)))
            .collect(),
    );
    let str_tab = RangeTable::build(
        strings
            .iter()
            .enumerate()
            .map(|(i, s)| {
                (
                    s.vaddr,
                    s.vaddr + s.content.len() as u64,
                    u32::try_from(i).unwrap_or(u32::MAX),
                )
            })
            .collect(),
    );
    let regions = RegionMap::build(&elf);

    let functions: Vec<FnOut> = if let Some(text) = elf.section(".text") {
        let text_base = text.vaddr;
        let text_limit = text_base + text.data.len() as u64;
        let fde_starts: BTreeSet<u64> = fn_map.keys().copied().collect();
        let mut ranges: Vec<(u64, u64)> = fn_map
            .values()
            .filter(|f| f.start >= text_base && f.start < text_limit && f.end > f.start)
            .map(|f| (f.start, f.end.min(text_limit)))
            .collect();
        ranges.sort_unstable();
        ranges
            .par_iter()
            .map(|&(s, e)| scan_one(text, text_base, s, e, &loc_tab, &str_tab, &regions, &fde_starts))
            .collect()
    } else {
        Vec::new()
    };

    let mut sections: Vec<SectionInfo> = elf
        .sections
        .iter()
        .map(|(name, sec)| SectionInfo { name: name.clone(), vaddr: sec.vaddr, size: sec.size() })
        .collect();
    sections.sort_by_key(|s| s.vaddr);

    // Emit only the strings some function actually points at, plus every string
    // a Location names — the rest are unreferenced constants that no per-function
    // feature can ever see, and keeping them would inflate the output tenfold.
    let referenced: BTreeSet<u32> = functions.iter().flat_map(|f| f.strs.iter().copied()).collect();
    let str_va_to_id: HashMap<u64, u32> = strings
        .iter()
        .enumerate()
        .map(|(i, s)| (s.vaddr, u32::try_from(i).unwrap_or(u32::MAX)))
        .collect();
    let mut keep: BTreeSet<u32> = referenced;
    for l in &locations {
        if let Some(&id) = str_va_to_id.get(&l.file_vaddr) {
            keep.insert(id);
        }
    }

    let string_out: Vec<StrOut> = keep
        .iter()
        .filter_map(|&id| {
            let s = strings.get(id as usize)?;
            Some(StrOut {
                id,
                va: s.vaddr,
                len: u32::try_from(s.content.len()).unwrap_or(u32::MAX),
                s: s.content.clone(),
            })
        })
        .collect();

    let location_out: Vec<LocOut> = locations
        .iter()
        .enumerate()
        .map(|(i, l)| LocOut {
            id: u32::try_from(i).unwrap_or(u32::MAX),
            va: l.struct_vaddr,
            file: l.file.clone(),
            line: l.line,
            col: l.col,
        })
        .collect();

    let report = Report {
        schema: "rulemine.raw.v1",
        binary: args.binary.display().to_string(),
        sha256,
        crate_name: args.crate_name,
        config: args.config,
        arch: elf.arch,
        is_pie: elf.is_pie,
        fde_source,
        n_relative_relocs: elf.rela_relative.len(),
        sections,
        locations: location_out,
        strings: string_out,
        functions,
        warnings: elf.warnings.clone(),
    };

    let json = serde_json::to_string(&report).context("serializing")?;
    match args.out {
        Some(p) => std::fs::write(p, json).context("writing output")?,
        None => println!("{json}"),
    }
    Ok(())
}

// A BTreeMap import is needed only for the type alias re-export check below;
// keeping it silences an unused-import warning if FunctionMap's alias changes.
#[allow(dead_code)]
type _AssertMapKind = BTreeMap<u64, unhusk::frame::FunctionRange>;

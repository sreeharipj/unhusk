/// DIAGNOSTIC ONLY — does not touch the classifier.
///
/// Dumps every `.eh_frame`-derived `FunctionRange` (start/end address pair)
/// found by `frame::parse_eh_frame`, one `start_hex,end_hex` per line, sorted
/// by start address (free, since `FunctionMap` is a `BTreeMap<u64, _>`).
///
/// Built to answer one question: does the `.eh_frame`-derived function
/// boundary map survive `strip --strip-all` on a Rust release binary? Run it
/// against an unstripped binary and its `strip --strip-all`'d twin and diff
/// the address sets — `.eh_frame` is an allocated/loaded section (needed for
/// Rust panic unwinding at runtime), unlike `.symtab` which is non-allocated
/// and is exactly what `strip --strip-all` removes. If the hypothesis holds,
/// the two runs should produce (near-)identical start/end address sets.
///
/// Usage: dump_fde <binary>
use std::path::PathBuf;

use anyhow::{Context, Result};

use unhusk::elf::ParsedElf;
use unhusk::frame;

fn main() -> Result<()> {
    let mut args = std::env::args_os().skip(1);
    let Some(path) = args.next() else {
        eprintln!("usage: dump_fde <binary>");
        std::process::exit(2);
    };
    let path = PathBuf::from(path);

    let elf = ParsedElf::load(&path).with_context(|| format!("loading {}", path.display()))?;
    for w in &elf.warnings {
        eprintln!("warning: {w}");
    }

    let map = frame::parse_eh_frame(&elf).context("parsing .eh_frame")?;

    for range in map.values() {
        println!("0x{:x},0x{:x}", range.start, range.end);
    }

    eprintln!("total: {} function ranges recovered from .eh_frame", map.len());

    Ok(())
}

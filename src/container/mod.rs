//! Container seam (design §8).
//!
//! The conceptual core (ranking, STRONG-tier selection) and all of winnow are
//! format-blind: they depend only on `BinaryImage`. ELF and PE each implement
//! the trait with format-specific plumbing. Adding a format is adding an impl,
//! not touching the core — and the ELF impl doubles as the regression oracle
//! for the PE port.
//!
//! Address convention: the trait speaks one address space per image. On PE that
//! is the **RVA** (image-base-relative); on ELF it is the **vaddr**. Whatever
//! `function_ranges` yields, `xref_locations_in`, `locations().struct_addr`, and
//! `bytes_at` all speak the same space for that image.
use std::ops::Range;

use crate::strings::Origin;

pub mod elf_image;
pub mod pe;

/// One `core::panic::Location` recovered from a binary's read-only data, in a
/// format-independent shape the ranking/classification core consumes.
///
/// `struct_addr` is the address of the struct's first field (the `file` pointer
/// at offset 0), in the image's address space (RVA on PE, vaddr on ELF).
#[derive(Debug, Clone)]
pub struct RawLocation {
    /// Address of the Location struct itself (its offset-0 `file` pointer field).
    pub struct_addr: u64,
    /// Resolved source-path string the `file` field points at.
    pub file: String,
    pub line: u32,
    pub col: u32,
    /// Classification of `file` (User / Std / Dep / Unknown). The multiplicity
    /// heuristic ranks on the count of distinct in-range *User* locations.
    pub origin: Origin,
}

/// The container seam. Everything downstream — ranking, STRONG selection, winnow
/// — depends only on this trait, never on ELF/PE specifics.
pub trait BinaryImage {
    /// `[start, end)` ranges of real functions. RVA on PE (from `.pdata`),
    /// vaddr on ELF (from `.eh_frame`).
    fn function_ranges(&self) -> Vec<Range<u64>>;

    /// All `Location` structs recovered from read-only data.
    fn locations(&self) -> Vec<RawLocation>;

    /// Decode `[range)` and yield the addresses of the `Location` structs it
    /// references (via RIP-relative `lea`).
    fn xref_locations_in(&self, range: Range<u64>) -> Vec<u64>;

    /// Read raw bytes at an address, for winnow's code atom and struct reads.
    /// The address is in the image's space (RVA on PE, vaddr on ELF).
    fn bytes_at(&self, addr: u64, len: usize) -> Option<&[u8]>;
}

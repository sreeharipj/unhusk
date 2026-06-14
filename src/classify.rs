/// Four-way function attribution.
///
/// Given the set of "certain" functions (direct RIP-relative references to user
/// Location structs) and the call graph, we propagate attribution:
///
/// - **Certain**: function has a direct reference to a user panic Location.
///   Precision confirmed at 100% by DWARF ground truth.
/// - **Inferred**: no direct reference, but reachable from a certain-user
///   function via call edges, AND all its identified callers are also user
///   (certain or inferred).
/// - **Indeterminate**: reachable from user code but also called from library
///   code — shared utility function; NOT counted as user-attributed.
///   DWARF ground truth shows 0% precision for this bucket (all shared
///   functions resolve to std/dep by DWARF). Kept as a diagnostic label only.
/// - **Library**: reached only from library functions, or not reached at all.
///
/// Attribution is propagated with a BFS from the certain set.  We keep a
/// "taint" pass that marks functions called from known library code so we can
/// downgrade BFS candidates to Indeterminate.
use std::collections::{HashMap, HashSet, VecDeque};

use crate::frame::FunctionMap;
use crate::xref::{CallGraph, CertainSet};

// ── Types ─────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum Attribution {
    Certain,
    Inferred,
    Indeterminate,
    Library,
}

impl Attribution {
    pub fn label(&self) -> &'static str {
        match self {
            Attribution::Certain => "certain",
            Attribution::Inferred => "inferred",
            Attribution::Indeterminate => "indeterminate",
            Attribution::Library => "library",
        }
    }
}

#[derive(Debug, Clone)]
pub struct AttributedFn {
    pub start: u64,
    pub end: u64,
    pub attribution: Attribution,
}

// ── Public API ────────────────────────────────────────────────────────────────

/// Attribute every function in `fns` and return the full list.
///
/// The `dep_boundary` set contains functions anchored to dep Locations — these
/// act as hard barriers in the BFS, stopping propagation of "inferred" attribution.
///
/// `max_infer_depth`: if Some(n), the BFS stops after `n` hops from certain.
/// Depth 1 = direct callees of certain only. None = unlimited (current default).
pub fn attribute(
    fns: &FunctionMap,
    certain: &CertainSet,
    calls: &CallGraph,
    dep_boundary: &crate::xref::DepBoundarySet,
    max_infer_depth: Option<usize>,
) -> Vec<AttributedFn> {
    // ── Step 1: build reverse call graph (callee → set of callers) ───────────
    let mut callers: HashMap<u64, HashSet<u64>> = HashMap::new();
    for (&caller, callees) in calls {
        for &callee in callees {
            callers.entry(callee).or_default().insert(caller);
        }
    }

    // ── Step 2: seed the BFS from certain functions ──────────────────────────
    let mut result: HashMap<u64, Attribution> = HashMap::new();
    let mut queue: VecDeque<u64> = VecDeque::new();

    for &start in certain {
        if fns.contains_key(&start) {
            result.insert(start, Attribution::Certain);
            queue.push_back(start);
        }
    }

    // ── Step 3: BFS — propagate "inferred" through callees ───────────────────
    // We follow CALL edges: if a user-attributed function calls F, and F has
    // not yet been attributed as certain, mark it as inferred (tentatively).
    // HARD BARRIER: stop BFS propagation at dep_boundary functions (they are
    // dependency boundaries — don't propagate user attribution through them).
    // DEPTH LIMIT: if max_infer_depth is Some(n), stop BFS after n hops from certain.
    let mut tentative_inferred: HashSet<u64> = HashSet::new();
    let mut visited_in_bfs: HashSet<u64> = HashSet::new();

    // Seed BFS: (function_start, depth_from_certain)
    let mut frontier: VecDeque<(u64, usize)> = VecDeque::new();
    for &start in certain {
        if fns.contains_key(&start) {
            frontier.push_back((start, 0));
            visited_in_bfs.insert(start);
        }
    }

    while let Some((caller_start, depth)) = frontier.pop_front() {
        // Honour depth limit: don't expand further if we've hit the cap.
        if max_infer_depth.map_or(false, |max| depth >= max) {
            continue;
        }
        if let Some(callees) = calls.get(&caller_start) {
            for &callee in callees {
                if !fns.contains_key(&callee) {
                    continue; // callee not in .eh_frame; skip
                }
                if visited_in_bfs.contains(&callee) {
                    continue;
                }
                visited_in_bfs.insert(callee);
                // HARD BARRIER: functions with dep Location anchors are dependency boundaries.
                // Do NOT mark as inferred; do NOT propagate. They block the inference wave.
                if dep_boundary.contains(&callee) {
                    continue;
                }
                tentative_inferred.insert(callee);
                frontier.push_back((callee, depth + 1));
            }
        }
    }

    // ── Step 4: Indeterminate check ──────────────────────────────────────────
    // A tentative-inferred function is downgraded to Indeterminate if it also
    // has callers that are NOT in the user set (certain + inferred).
    let user_set: HashSet<u64> = {
        let mut s: HashSet<u64> = certain.iter().cloned().collect();
        s.extend(tentative_inferred.iter().cloned());
        s
    };

    for &fn_start in &tentative_inferred {
        if let Some(caller_set) = callers.get(&fn_start) {
            let has_non_user_caller = caller_set.iter().any(|c| !user_set.contains(c));
            if has_non_user_caller {
                result.insert(fn_start, Attribution::Indeterminate);
            } else {
                result.insert(fn_start, Attribution::Inferred);
            }
        } else {
            // No callers found in the call graph (tail-call or stripped).
            // Treat as Inferred — the BFS reached it from a user caller.
            result.insert(fn_start, Attribution::Inferred);
        }
    }

    // ── Step 5: Everything else is Library ───────────────────────────────────
    for (&start, range) in fns {
        result.entry(start).or_insert(Attribution::Library);
        let _ = range; // used below
    }

    // ── Assemble output ───────────────────────────────────────────────────────
    let mut out: Vec<AttributedFn> = fns
        .iter()
        .map(|(&start, range)| AttributedFn {
            start,
            end: range.end,
            attribution: *result.get(&start).unwrap_or(&Attribution::Library),
        })
        .collect();

    out.sort_by_key(|f| f.start);
    out
}

// ── Scoring helpers ───────────────────────────────────────────────────────────

#[derive(Debug, Default)]
pub struct Score {
    pub certain: usize,
    pub inferred: usize,
    pub indeterminate: usize,
    pub library: usize,
}

impl Score {
    pub fn from(attributed: &[AttributedFn]) -> Self {
        let mut s = Score::default();
        for f in attributed {
            match f.attribution {
                Attribution::Certain => s.certain += 1,
                Attribution::Inferred => s.inferred += 1,
                Attribution::Indeterminate => s.indeterminate += 1,
                Attribution::Library => s.library += 1,
            }
        }
        s
    }

    pub fn total(&self) -> usize {
        self.certain + self.inferred + self.indeterminate + self.library
    }

    /// Count of functions validated as user-authored.
    ///
    /// Only `certain` qualifies: 100% precision confirmed by DWARF ground truth.
    /// `inferred` is excluded — DWARF shows ~5% precision on real binaries (mostly
    /// dep/std glue reachable from user call sites). It is a call-closure annotation,
    /// not a user-code attribution.
    pub fn user_total(&self) -> usize {
        self.certain
    }
}

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
use crate::xref::{CallGraph, CertainSet, DepBoundarySet};

// ── Types ─────────────────────────────────────────────────────────────────────

/// Reverse call graph: callee → set of callers.
pub type RevCallGraph = HashMap<u64, HashSet<u64>>;

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
        if max_infer_depth.is_some_and(|max| depth >= max) {
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
    pub certain_by_backtrace: usize,
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

// ── Reverse call graph + backward BFS ────────────────────────────────────────

/// Build the reverse call graph (callee → callers) from a forward call graph.
pub fn build_rev_call_graph(calls: &CallGraph) -> RevCallGraph {
    let mut rev: RevCallGraph = HashMap::new();
    for (&caller, callees) in calls {
        for &callee in callees {
            rev.entry(callee).or_default().insert(caller);
        }
    }
    rev
}

/// Walk backward from the certain set, returning callers reachable within
/// `depth` hops via the reverse call graph.
///
/// The returned set is STRICTLY separate from `certain`:
/// - Functions already in `certain` are the BFS seeds and are never returned.
/// - Functions in `dep_boundary` are hard barriers: not added, not recursed through.
///   This mirrors the forward dep-boundary barrier exactly.
/// - Returns an empty set when `depth == 0`.
pub fn backtrace_walk(
    fns: &FunctionMap,
    certain: &CertainSet,
    rev: &RevCallGraph,
    dep_boundary: &DepBoundarySet,
    depth: usize,
) -> HashSet<u64> {
    if depth == 0 {
        return HashSet::new();
    }
    let mut result: HashSet<u64> = HashSet::new();
    // visited is seeded with certain so we never re-enqueue or add them.
    let mut visited: HashSet<u64> = certain.iter().cloned().collect();
    let mut frontier: VecDeque<(u64, usize)> = VecDeque::new();
    for &start in certain {
        if fns.contains_key(&start) {
            frontier.push_back((start, 0));
        }
    }
    while let Some((node, d)) = frontier.pop_front() {
        if d >= depth {
            continue;
        }
        let callers = match rev.get(&node) {
            Some(s) => s,
            None => continue,
        };
        for &caller in callers {
            if !fns.contains_key(&caller) {
                continue;
            }
            if visited.contains(&caller) {
                continue;
            }
            visited.insert(caller);
            // dep-boundary barrier: stop here, don't add, don't recurse.
            if dep_boundary.contains(&caller) {
                continue;
            }
            result.insert(caller);
            frontier.push_back((caller, d + 1));
        }
    }
    result
}

// ── Tests ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use crate::frame::FunctionRange;

    fn make_fns(addrs: &[u64]) -> FunctionMap {
        addrs
            .iter()
            .map(|&a| {
                (
                    a,
                    FunctionRange {
                        start: a,
                        end: a + 16,
                    },
                )
            })
            .collect()
    }

    #[test]
    fn build_rev_graph_empty() {
        let calls: CallGraph = HashMap::new();
        let rev = build_rev_call_graph(&calls);
        assert!(rev.is_empty());
    }

    #[test]
    fn build_rev_graph_simple() {
        // A → B, A → C
        let mut calls: CallGraph = HashMap::new();
        calls.entry(0xA).or_default().insert(0xB);
        calls.entry(0xA).or_default().insert(0xC);
        let rev = build_rev_call_graph(&calls);
        assert_eq!(rev[&0xB], [0xA].into_iter().collect());
        assert_eq!(rev[&0xC], [0xA].into_iter().collect());
        assert!(!rev.contains_key(&0xA));
    }

    #[test]
    fn backtrace_walk_depth_zero_returns_empty() {
        let fns = make_fns(&[0x10, 0x20, 0x30]);
        let certain: CertainSet = [0x10].into_iter().collect();
        let mut calls: CallGraph = HashMap::new();
        calls.entry(0x20).or_default().insert(0x10);
        let rev = build_rev_call_graph(&calls);
        let dep: DepBoundarySet = HashSet::new();
        assert!(backtrace_walk(&fns, &certain, &rev, &dep, 0).is_empty());
    }

    #[test]
    fn backtrace_walk_depth_one() {
        // caller 0x20 → certain 0x10; grandcaller 0x30 → 0x20
        let fns = make_fns(&[0x10, 0x20, 0x30]);
        let certain: CertainSet = [0x10].into_iter().collect();
        let mut calls: CallGraph = HashMap::new();
        calls.entry(0x20).or_default().insert(0x10);
        calls.entry(0x30).or_default().insert(0x20);
        let rev = build_rev_call_graph(&calls);
        let dep: DepBoundarySet = HashSet::new();
        let bt = backtrace_walk(&fns, &certain, &rev, &dep, 1);
        assert!(
            bt.contains(&0x20),
            "direct caller should be in depth-1 result"
        );
        assert!(
            !bt.contains(&0x30),
            "grandcaller should NOT be in depth-1 result"
        );
        assert!(!bt.contains(&0x10), "certain seed must never be in result");
    }

    #[test]
    fn backtrace_walk_depth_two() {
        let fns = make_fns(&[0x10, 0x20, 0x30]);
        let certain: CertainSet = [0x10].into_iter().collect();
        let mut calls: CallGraph = HashMap::new();
        calls.entry(0x20).or_default().insert(0x10);
        calls.entry(0x30).or_default().insert(0x20);
        let rev = build_rev_call_graph(&calls);
        let dep: DepBoundarySet = HashSet::new();
        let bt = backtrace_walk(&fns, &certain, &rev, &dep, 2);
        assert!(bt.contains(&0x20));
        assert!(bt.contains(&0x30));
    }

    #[test]
    fn backtrace_walk_dep_boundary_is_barrier() {
        // 0x30 (dep) → certain 0x10; 0x40 → 0x30
        let fns = make_fns(&[0x10, 0x30, 0x40]);
        let certain: CertainSet = [0x10].into_iter().collect();
        let mut calls: CallGraph = HashMap::new();
        calls.entry(0x30).or_default().insert(0x10);
        calls.entry(0x40).or_default().insert(0x30);
        let rev = build_rev_call_graph(&calls);
        let dep: DepBoundarySet = [0x30].into_iter().collect();
        let bt = backtrace_walk(&fns, &certain, &rev, &dep, 10);
        assert!(!bt.contains(&0x30), "dep barrier must not be added");
        assert!(
            !bt.contains(&0x40),
            "caller of dep barrier must not recurse through"
        );
    }
}

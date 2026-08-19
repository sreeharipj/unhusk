## Per-binary inventory

| binary | stratum B | domain | certain | STRONG | author crates | dep crates (metadata) | dep crates (DEPCRATE) |
|---|---|---|---:|---:|---:|---:|---:|
| bandwhich | async | async | 24 | 11 | 1 | 399 | 56 |
| bat | sync | cli | 141 | 10 | 1 | 305 | 88 |
| bottom | sync | framework | 46 | 25 | 2 | 216 | 46 |
| dprint | sync | macro | 388 | 195 | 5 | 352 | 107 |
| dufs | async | async | 37 | 14 | 1 | 311 | 61 |
| dust | sync | cli | 17 | 7 | 2 | 126 | 29 |
| eza | sync | cli | 34 | 22 | 1 | 208 | 38 |
| fclones | async | parallel | 98 | 26 | 2 | 172 | 59 |
| fd | sync | cli | 17 | 7 | 2 | 125 | 27 |
| gping | async | async | 7 | 4 | 2 | 198 | 36 |
| grex | sync | cli | 23 | 5 | 1 | 163 | 21 |
| hexyl | sync | cli | 16 | 3 | 1 | 66 | 12 |
| hyperfine | sync | cli | 15 | 6 | 1 | 151 | 25 |
| just | sync | cli | 168 | 51 | 3 | 152 | 41 |
| miniserve | async | async | 27 | 14 | 1 | 418 | 114 |
| oha | async | async | 160 | 107 | 1 | 456 | 80 |
| ouch | sync | crypto | 23 | 14 | 1 | 242 | 52 |
| pastel | sync | cli | 27 | 16 | 1 | 111 | 12 |
| procs | sync | cli | 26 | 7 | 1 | 285 | 65 |
| rage | sync | crypto | 73 | 37 | 6 | 358 | 68 |
| ripgrep | sync | cli | 344 | 203 | 11 | 49 | 22 |
| rustscan | async | async | 5 | 4 | 1 | 267 | 63 |
| sd | sync | cli | 5 | 5 | 3 | 92 | 19 |
| starship | sync | macro | 50 | 17 | 1 | 389 | 129 |
| taplo | sync | macro | 224 | 113 | 6 | 295 | 94 |
| tealdeer | sync | cli | 7 | 5 | 2 | 163 | 35 |
| tokei | sync | cli | 39 | 15 | 1 | 193 | 43 |
| trippy | async | async | 58 | 38 | 9 | 379 | 79 |
| typos | sync | macro | 30 | 17 | 10 | 206 | 45 |
| xh | async | async | 39 | 12 | 1 | 345 | 89 |
| xsv | sync | cli | 49 | 16 | 1 | 57 | 28 |
| zoxide | sync | cli | 8 | 3 | 1 | 123 | 11 |

## STRONG tier — stratified (Rule B, pre-registered)


**STRONG (>= 2 anchors) — SYNC** — 23 binaries: 23 binaries

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 797 | 763 | 34 | 2 | 95.7% | [94.1, 96.9] | [93.4, 97.4] |
| meta | unwrapped | 797 | 765 | 32 | 2 | 96.0% | [94.4, 97.1] | [93.8, 97.7] |
| depcrate | strict | 797 | 764 | 33 | 2 | 95.9% | [94.2, 97.0] | [93.4, 97.5] |
| depcrate | unwrapped | 797 | 766 | 31 | 2 | 96.1% | [94.5, 97.2] | [93.9, 97.8] |

**STRONG (>= 2 anchors) — ASYNC** — 9 binaries: bandwhich, dufs, fclones, gping, miniserve, oha, rustscan, trippy, xh

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 230 | 197 | 33 | 0 | 85.7% | [80.5, 89.6] | [70.9, 93.1] |
| meta | unwrapped | 230 | 202 | 28 | 0 | 87.8% | [83.0, 91.4] | [77.5, 95.5] |
| depcrate | strict | 230 | 197 | 33 | 0 | 85.7% | [80.5, 89.6] | [70.9, 93.1] |
| depcrate | unwrapped | 230 | 202 | 28 | 0 | 87.8% | [83.0, 91.4] | [77.5, 95.5] |

**STRONG (>= 2 anchors) — COMBINED** — 32 binaries: 32 binaries

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 1027 | 960 | 67 | 2 | 93.5% | [91.8, 94.8] | [89.5, 96.0] |
| meta | unwrapped | 1027 | 967 | 60 | 2 | 94.2% | [92.6, 95.4] | [90.7, 96.5] |
| depcrate | strict | 1027 | 961 | 66 | 2 | 93.6% | [91.9, 94.9] | [89.5, 96.1] |
| depcrate | unwrapped | 1027 | 968 | 59 | 2 | 94.3% | [92.7, 95.5] | [90.8, 96.6] |

## SINGLE tier — stratified (Rule B)


**SINGLE (1 anchor) — SYNC** — 23 binaries: 23 binaries

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 966 | 830 | 136 | 5 | 85.9% | [83.6, 88.0] | [78.0, 92.7] |
| meta | unwrapped | 966 | 832 | 134 | 5 | 86.1% | [83.8, 88.2] | [78.3, 92.8] |
| depcrate | strict | 969 | 834 | 135 | 2 | 86.1% | [83.7, 88.1] | [78.2, 92.8] |
| depcrate | unwrapped | 969 | 836 | 133 | 2 | 86.3% | [84.0, 88.3] | [78.5, 92.9] |

**SINGLE (1 anchor) — ASYNC** — 9 binaries: bandwhich, dufs, fclones, gping, miniserve, oha, rustscan, trippy, xh

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 223 | 126 | 97 | 2 | 56.5% | [49.9, 62.8] | [38.2, 89.7] |
| meta | unwrapped | 223 | 134 | 89 | 2 | 60.1% | [53.5, 66.3] | [41.5, 92.1] |
| depcrate | strict | 223 | 126 | 97 | 2 | 56.5% | [49.9, 62.8] | [38.2, 89.7] |
| depcrate | unwrapped | 223 | 134 | 89 | 2 | 60.1% | [53.5, 66.3] | [41.5, 92.1] |

**SINGLE (1 anchor) — COMBINED** — 32 binaries: 32 binaries

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 1189 | 956 | 233 | 7 | 80.4% | [78.1, 82.6] | [68.8, 89.4] |
| meta | unwrapped | 1189 | 966 | 223 | 7 | 81.2% | [78.9, 83.4] | [70.3, 89.8] |
| depcrate | strict | 1192 | 960 | 232 | 4 | 80.5% | [78.2, 82.7] | [68.9, 89.5] |
| depcrate | unwrapped | 1192 | 970 | 222 | 4 | 81.4% | [79.1, 83.5] | [70.4, 89.9] |

## Per-domain breakdown — `docs/local/validation.md`'s partition

Rule B folds `parallel` into async (the task defines async to include rayon generics). `docs/local/validation.md` keeps `parallel` as its own category, so its published async figure is the `async` row here, NOT the async stratum above. Quoted for comparison against the docs; both are the same underlying data cut differently.


**STRONG (>= 2) — domain `cli`** — 16 binaries: 16 binaries

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 379 | 369 | 10 | 2 | 97.4% | [95.2, 98.6] | [94.5, 98.5] |
| meta | unwrapped | 379 | 371 | 8 | 2 | 97.9% | [95.9, 98.9] | [95.8, 99.2] |
| depcrate | strict | 379 | 369 | 10 | 2 | 97.4% | [95.2, 98.6] | [94.5, 98.5] |
| depcrate | unwrapped | 379 | 371 | 8 | 2 | 97.9% | [95.9, 98.9] | [95.8, 99.2] |

**SINGLE (1) — domain `cli`** — 16 binaries: 16 binaries

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 553 | 506 | 47 | 2 | 91.5% | [88.9, 93.5] | [79.5, 96.2] |
| meta | unwrapped | 553 | 507 | 46 | 2 | 91.7% | [89.1, 93.7] | [80.0, 96.3] |
| depcrate | strict | 553 | 506 | 47 | 2 | 91.5% | [88.9, 93.5] | [79.5, 96.2] |
| depcrate | unwrapped | 553 | 507 | 46 | 2 | 91.7% | [89.1, 93.7] | [80.0, 96.3] |

**STRONG (>= 2) — domain `async`** — 8 binaries: bandwhich, dufs, gping, miniserve, oha, rustscan, trippy, xh

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 204 | 176 | 28 | 0 | 86.3% | [80.9, 90.3] | [67.2, 94.8] |
| meta | unwrapped | 204 | 181 | 23 | 0 | 88.7% | [83.7, 92.4] | [76.5, 97.7] |
| depcrate | strict | 204 | 176 | 28 | 0 | 86.3% | [80.9, 90.3] | [67.2, 94.8] |
| depcrate | unwrapped | 204 | 181 | 23 | 0 | 88.7% | [83.7, 92.4] | [76.5, 97.7] |

**SINGLE (1) — domain `async`** — 8 binaries: bandwhich, dufs, gping, miniserve, oha, rustscan, trippy, xh

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 153 | 107 | 46 | 0 | 69.9% | [62.3, 76.6] | [50.3, 93.9] |
| meta | unwrapped | 153 | 114 | 39 | 0 | 74.5% | [67.1, 80.8] | [57.2, 95.7] |
| depcrate | strict | 153 | 107 | 46 | 0 | 69.9% | [62.3, 76.6] | [50.3, 93.9] |
| depcrate | unwrapped | 153 | 114 | 39 | 0 | 74.5% | [67.1, 80.8] | [57.2, 95.7] |

**STRONG (>= 2) — domain `parallel`** — 1 binaries: fclones

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 26 | 21 | 5 | 0 | 80.8% | [62.1, 91.5] | n too small |
| meta | unwrapped | 26 | 21 | 5 | 0 | 80.8% | [62.1, 91.5] | n too small |
| depcrate | strict | 26 | 21 | 5 | 0 | 80.8% | [62.1, 91.5] | n too small |
| depcrate | unwrapped | 26 | 21 | 5 | 0 | 80.8% | [62.1, 91.5] | n too small |

**SINGLE (1) — domain `parallel`** — 1 binaries: fclones

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 70 | 19 | 51 | 2 | 27.1% | [18.1, 38.5] | n too small |
| meta | unwrapped | 70 | 20 | 50 | 2 | 28.6% | [19.3, 40.1] | n too small |
| depcrate | strict | 70 | 19 | 51 | 2 | 27.1% | [18.1, 38.5] | n too small |
| depcrate | unwrapped | 70 | 20 | 50 | 2 | 28.6% | [19.3, 40.1] | n too small |

**STRONG (>= 2) — domain `macro`** — 4 binaries: dprint, starship, taplo, typos

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 342 | 325 | 17 | 0 | 95.0% | [92.2, 96.9] | [91.2, 96.9] |
| meta | unwrapped | 342 | 325 | 17 | 0 | 95.0% | [92.2, 96.9] | [91.2, 96.9] |
| depcrate | strict | 342 | 326 | 16 | 0 | 95.3% | [92.5, 97.1] | [91.2, 97.7] |
| depcrate | unwrapped | 342 | 326 | 16 | 0 | 95.3% | [92.5, 97.1] | [91.2, 97.7] |

**SINGLE (1) — domain `macro`** — 4 binaries: dprint, starship, taplo, typos

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 348 | 267 | 81 | 2 | 76.7% | [72.0, 80.9] | [63.0, 84.4] |
| meta | unwrapped | 348 | 268 | 80 | 2 | 77.0% | [72.3, 81.1] | [65.2, 84.4] |
| depcrate | strict | 350 | 270 | 80 | 0 | 77.1% | [72.5, 81.2] | [63.0, 85.5] |
| depcrate | unwrapped | 350 | 271 | 79 | 0 | 77.4% | [72.8, 81.5] | [65.2, 85.5] |

**STRONG (>= 2) — domain `crypto`** — 2 binaries: ouch, rage

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 51 | 44 | 7 | 0 | 86.3% | [74.3, 93.2] | [78.6, 89.2] |
| meta | unwrapped | 51 | 44 | 7 | 0 | 86.3% | [74.3, 93.2] | [78.6, 89.2] |
| depcrate | strict | 51 | 44 | 7 | 0 | 86.3% | [74.3, 93.2] | [78.6, 89.2] |
| depcrate | unwrapped | 51 | 44 | 7 | 0 | 86.3% | [74.3, 93.2] | [78.6, 89.2] |

**SINGLE (1) — domain `crypto`** — 2 binaries: ouch, rage

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 44 | 38 | 6 | 1 | 86.4% | [73.3, 93.6] | [85.7, 88.9] |
| meta | unwrapped | 44 | 38 | 6 | 1 | 86.4% | [73.3, 93.6] | [85.7, 88.9] |
| depcrate | strict | 45 | 39 | 6 | 0 | 86.7% | [73.8, 93.7] | [86.1, 88.9] |
| depcrate | unwrapped | 45 | 39 | 6 | 0 | 86.7% | [73.8, 93.7] | [86.1, 88.9] |

**STRONG (>= 2) — domain `framework`** — 1 binaries: bottom

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 25 | 25 | 0 | 0 | 100.0% | [86.7, 100.0] | n too small |
| meta | unwrapped | 25 | 25 | 0 | 0 | 100.0% | [86.7, 100.0] | n too small |
| depcrate | strict | 25 | 25 | 0 | 0 | 100.0% | [86.7, 100.0] | n too small |
| depcrate | unwrapped | 25 | 25 | 0 | 0 | 100.0% | [86.7, 100.0] | n too small |

**SINGLE (1) — domain `framework`** — 1 binaries: bottom

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 21 | 19 | 2 | 0 | 90.5% | [71.1, 97.3] | n too small |
| meta | unwrapped | 21 | 19 | 2 | 0 | 90.5% | [71.1, 97.3] | n too small |
| depcrate | strict | 21 | 19 | 2 | 0 | 90.5% | [71.1, 97.3] | n too small |
| depcrate | unwrapped | 21 | 19 | 2 | 0 | 90.5% | [71.1, 97.3] | n too small |

## Exploratory stratification (Rule A-prime, POST-HOC — not a headline claim)

Rule A-prime: ASYNC iff a runtime generic is monomorphized over an author crate (i.e. the combinator actually inlines author code), not merely linked. Written after Rule A was refuted; reported for transparency only.


**[exploratory] STRONG — SYNC (A-prime)** — 19 binaries: 19 binaries

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 297 | 282 | 15 | 1 | 94.9% | [91.8, 96.9] | [91.6, 98.0] |
| meta | unwrapped | 297 | 284 | 13 | 1 | 95.6% | [92.7, 97.4] | [92.6, 98.5] |
| depcrate | strict | 297 | 282 | 15 | 1 | 94.9% | [91.8, 96.9] | [91.6, 98.0] |
| depcrate | unwrapped | 297 | 284 | 13 | 1 | 95.6% | [92.7, 97.4] | [92.6, 98.5] |

**[exploratory] STRONG — ASYNC (A-prime)** — 13 binaries: bandwhich, dprint, dufs, dust, fclones, miniserve, oha, ripgrep, rustscan, sd, starship, taplo, tokei

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 730 | 678 | 52 | 1 | 92.9% | [90.8, 94.5] | [84.8, 96.1] |
| meta | unwrapped | 730 | 683 | 47 | 1 | 93.6% | [91.5, 95.1] | [86.9, 96.6] |
| depcrate | strict | 730 | 679 | 51 | 1 | 93.0% | [90.9, 94.6] | [84.9, 96.3] |
| depcrate | unwrapped | 730 | 684 | 46 | 1 | 93.7% | [91.7, 95.2] | [87.0, 96.7] |

## Threshold ladder (`--min-anchors`), combined, cargo-metadata oracle / unwrapped

| min-anchors | n | precision | Wilson 95% | cluster bootstrap 95% | recall retained |
|---:|---:|---:|---|---|---:|
| >= 1 | 2216 | 87.2% | [85.8, 88.6] | [80.3, 92.5] | 99.6% |
| >= 2 | 1027 | 94.2% | [92.6, 95.4] | [90.7, 96.5] | 46.2% |
| >= 3 | 595 | 96.1% | [94.3, 97.4] | [92.3, 98.4] | 26.7% |
| >= 4 | 408 | 97.5% | [95.5, 98.7] | [94.3, 99.1] | 18.3% |

## Every false attribution — STRONG tier (>= 2 anchors)

Ruler: cargo-metadata oracle, **strict** (no wrapper unwrapping) — the most conservative reading, so this list is a superset. Rows marked *(rescued by unwrapped)* are forwarding wrappers whose body is the author's closure; the `unwrapped` ruler counts them as user, and that is a judgment call you can audit here rather than take on trust.

| binary | stratum | address | anchors | author-param? | why it is not user | demangled symbol |
|---|---|---|---:|---|---|---|
| bandwhich | async | `0x8f610` | 10 | **yes** | thread-trampoline (std generic over user fn) *(rescued by unwrapped)* | `std::sys::backtrace::__rust_begin_short_backtrace::<bandwhich::start<ratatui_crossterm::CrosstermBackend<std::io::stdio::Stdout>>::{closure#2}, ()>` |
| bandwhich | async | `0x874d0` | 3 | **yes** | unclassified library generic (no recognized adapter pattern) | `core::ptr::drop_glue::<core::option::Option<bandwhich::network::dns::client::Client>>` |
| bandwhich | async | `0x90630` | 6 | **yes** | thread-trampoline (std generic over user fn) *(rescued by unwrapped)* | `std::sys::backtrace::__rust_begin_short_backtrace::<bandwhich::start<ratatui_crossterm::CrosstermBackend<std::io::stdio::Stdout>>::{closure#1}, ()>` |
| bandwhich | async | `0x91f30` | 10 | **yes** | thread-trampoline (std generic over user fn) *(rescued by unwrapped)* | `std::sys::backtrace::__rust_begin_short_backtrace::<bandwhich::start<bandwhich::display::raw_terminal_backend::RawTerminalBackend>::{closure#2}, ()>` |
| bandwhich | async | `0x92f50` | 5 | **yes** | thread-trampoline (std generic over user fn) *(rescued by unwrapped)* | `std::sys::backtrace::__rust_begin_short_backtrace::<bandwhich::start<bandwhich::display::raw_terminal_backend::RawTerminalBackend>::{closure#1}, ()>` |
| bat | sync | `0x3dda90` | 2 | **yes** | core generic (iter/sort/fn-shim over user closure) | `<core::iter::adapters::GenericShunt<core::iter::adapters::map::Map<core::iter::adapters::map::Map<core::str::iter::Split<&str>, <bat::style::Component…` |
| dprint | sync | `0x8a3580` | 2 | *undeterminable (legacy mangling)* | futures combinator (inlines user closure) | `<futures_util::stream::futures_ordered::OrderWrapper<T> as core::future::future::Future>::poll` |
| dprint | sync | `0x6a6e70` | 2 | *undeterminable (legacy mangling)* | futures combinator (inlines user closure) | `<core::future::poll_fn::PollFn<F> as core::future::future::Future>::poll` |
| dprint | sync | `0x95c510` | 2 | *undeterminable (legacy mangling)* | unclassified library generic (no recognized adapter pattern) | `once_cell::imp::OnceCell<T>::initialize::{{closure}}` |
| dprint | sync | `0xa55be0` | 2 | *undeterminable (legacy mangling)* | unclassified library generic (no recognized adapter pattern) | `<alloc::vec::into_iter::IntoIter<T,A> as core::iter::traits::iterator::Iterator>::fold` |
| dprint | sync | `0x6f7010` | 2 | *undeterminable (legacy mangling)* | core generic (iter/sort/fn-shim over user closure) | `core::ops::function::impls::<impl core::ops::function::FnMut<A> for &mut F>::call_mut` |
| dprint | sync | `0x7ad150` | 2 | *undeterminable (legacy mangling)* | futures combinator (inlines user closure) | `<futures_util::future::maybe_done::MaybeDone<Fut> as core::future::future::Future>::poll` |
| dprint | sync | `0x8be110` | 2 | *undeterminable (legacy mangling)* | futures combinator (inlines user closure) | `tokio::runtime::park::CachedParkThread::block_on` |
| dprint | sync | `0xa551a0` | 2 | *undeterminable (legacy mangling)* | unclassified library generic (no recognized adapter pattern) | `<alloc::vec::into_iter::IntoIter<T,A> as core::iter::traits::iterator::Iterator>::fold` |
| dprint | sync | `0xabb140` | 2 | *undeterminable (legacy mangling)* | unclassified library generic (no recognized adapter pattern) | `<alloc::vec::Vec<T> as alloc::vec::spec_from_iter::SpecFromIter<T,I>>::from_iter` |
| dprint | sync | `0xac0b80` | 2 | *undeterminable (legacy mangling)* | unclassified library generic (no recognized adapter pattern) | `<alloc::vec::Vec<T> as alloc::vec::spec_from_iter::SpecFromIter<T,I>>::from_iter` |
| dust | sync | `0xdddd0` | 7 | **yes** | thread-trampoline (std generic over user fn) *(rescued by unwrapped)* | `std::sys::backtrace::__rust_begin_short_backtrace::<<dust::progress::PIndicator>::spawn::{closure#0}, ()>` |
| eza | sync | `0x953d0` | 3 | *undeterminable (legacy mangling)* | unclassified library generic (no recognized adapter pattern) | `std::sync::poison::once::Once::call_once_force::{{closure}}` |
| fclones | async | `0x26e6e0` | 2 | **yes** | unclassified library generic (no recognized adapter pattern) | `<nom::sequence::tuple<&str, (&str, &str), nom::error::Error<&str>, (nom::bytes::complete::tag<&str, &str, nom::error::Error<&str>>::{closure#0}, fclon…` |
| fclones | async | `0x209d90` | 2 | **yes** | unclassified library generic (no recognized adapter pattern) | `core::ptr::drop_glue::<fclones::cache::HashCache>` |
| fclones | async | `0x2bd290` | 2 | **yes** | rayon generic (data-parallel, inlines user closure) | `rayon::iter::plumbing::bridge_producer_consumer::helper::<rayon::vec::DrainProducer<fclones::dedupe::FsCommand>, rayon::iter::map::MapConsumer<rayon::…` |
| fclones | async | `0x204bc0` | 3 | **yes** | unclassified library generic (no recognized adapter pattern) | `<nom::branch::alt<&str, std::ffi::os_str::OsString, nom::error::Error<&str>, (nom::combinator::map<&str, (&str, &str), std::ffi::os_str::OsString, nom…` |
| fclones | async | `0x295260` | 2 | **yes** | rayon generic (data-parallel, inlines user closure) | `<rayon_core::job::HeapJob<rayon_core::spawn::spawn_job<fclones::group::rehash<fclones::group::group_by_prefix::{closure#0}, fclones::group::group_by_p…` |
| fd | sync | `0x108b60` | 3 | **yes** | thread-trampoline (std generic over user fn) *(rescued by unwrapped)* | `std::sys::backtrace::__rust_begin_short_backtrace::<<fd::walk::WorkerState>::scan::{closure#1}::{closure#0}, fd::exit_codes::ExitCode>` |
| gping | async | `0xe8800` | 6 | **yes** | unclassified library generic (no recognized adapter pattern) | `<ratatui_core::terminal::Terminal<ratatui_crossterm::CrosstermBackend<std::io::buffered::bufwriter::BufWriter<std::io::stdio::Stdout>>>>::try_draw::<<…` |
| gping | async | `0x1d3670` | 2 | **yes** | thread-trampoline (std generic over user fn) *(rescued by unwrapped)* | `std::sys::backtrace::__rust_begin_short_backtrace::<<pinger::linux::LinuxPinger as pinger::Pinger>::start::{closure#0}, ()>` |
| just | sync | `0x3610e0` | 4 | **yes** | core generic (iter/sort/fn-shim over user closure) | `<core::iter::adapters::GenericShunt<core::iter::adapters::map::Map<alloc::collections::btree::map::IntoIter<just::attribute::Attribute, just::name::Na…` |
| just | sync | `0x318650` | 2 | **yes** | serde generic (derive/monomorph over user type) | `<serde_json::ser::Compound<std::io::stdio::Stdout, serde_json::ser::CompactFormatter> as serde_core::ser::SerializeMap>::serialize_entry::<str, core::…` |
| just | sync | `0x35df70` | 2 | **yes** | core generic (iter/sort/fn-shim over user closure) | `<core::iter::adapters::copied::Copied<core::iter::adapters::skip_while::SkipWhile<core::slice::iter::Iter<&str>, <just::recipe_resolver::RecipeResolve…` |
| miniserve | async | `0x36ceee` | 2 | **yes** | framework handler-adapter (monomorphized over user handler) | `<actix_web_httpauth::middleware::AuthenticationMiddleware<actix_web::scope::ScopeService, miniserve::auth::handle_auth, actix_web_httpauth::extractors…` |
| miniserve | async | `0x34a077` | 8 | **yes** | futures combinator (inlines user closure) | `<tokio::task::local::LocalSet>::run_until::<miniserve::run::{closure#0}>::{closure#0}` |
| miniserve | async | `0x3ae87d` | 3 | **yes** | framework handler-adapter (monomorphized over user handler) | `<actix_web::middleware::logger::LoggerResponse<actix_web::middleware::from_fn::MiddlewareFnService<miniserve::errors::error_page_middleware<actix_http…` |
| miniserve | async | `0x354a6c` | 6 | **yes** | framework handler-adapter (monomorphized over user handler) | `actix_web::handler::handler_service::<miniserve::api, (actix_web::types::json::Json<miniserve::ApiCommand>, actix_web::data::Data<miniserve::config::M…` |
| miniserve | async | `0x35d79f` | 2 | **yes** | framework handler-adapter (monomorphized over user handler) | `actix_web::handler::handler_service::<miniserve::file_op::rm_file, (actix_web::request::HttpRequest, actix_web::types::query::Query<miniserve::file_op…` |
| miniserve | async | `0x358919` | 2 | **yes** | framework handler-adapter (monomorphized over user handler) | `actix_web::handler::handler_service::<miniserve::file_op::upload_file, (actix_web::request::HttpRequest, actix_web::types::query::Query<miniserve::fil…` |
| miniserve | async | `0x35e62f` | 2 | **yes** | framework handler-adapter (monomorphized over user handler) | `actix_web::handler::handler_service::<miniserve::listing::file_handler, (actix_web::request::HttpRequest,)>::{closure#0}::{closure#0}` |
| oha | async | `0x5b09c0` | 2 | **yes** | core generic (iter/sort/fn-shim over user closure) | `<core::iter::adapters::map::Map<core::iter::adapters::filter_map::FilterMap<core::ops::range::Range<usize>, oha::client::fast::work::{closure#0}::{clo…` |
| oha | async | `0x6f5fc0` | 3 | **yes** | futures combinator (inlines user closure) | `<tokio::time::timeout::Timeout<<oha::client::Client>::work_http1::{closure#0}::{closure#0}> as core::future::future::Future>::poll` |
| oha | async | `0x6683f0` | 3 | **yes** | futures combinator (inlines user closure) | `<tokio::time::timeout::Timeout<<oha::client::Client>::work_http1::{closure#0}::{closure#0}> as core::future::future::Future>::poll` |
| oha | async | `0x7ac7c0` | 2 | **yes** | futures combinator (inlines user closure) | `<core::pin::Pin<alloc::boxed::Box<oha::client::fast::work::{closure#0}::{closure#1}::{closure#0}::{closure#0}>> as core::future::future::Future>::poll` |
| oha | async | `0x7ab1b0` | 2 | **yes** | futures combinator (inlines user closure) | `<core::pin::Pin<alloc::boxed::Box<oha::client::fast::work_until::{closure#0}::{closure#1}::{closure#0}::{closure#0}>> as core::future::future::Future>…` |
| oha | async | `0x6fa230` | 3 | **yes** | futures combinator (inlines user closure) | `<tokio::time::timeout::Timeout<<oha::client::Client>::tls_client::{closure#0}> as core::future::future::Future>::poll` |
| oha | async | `0x5b0670` | 2 | **yes** | core generic (iter/sort/fn-shim over user closure) | `<core::iter::adapters::map::Map<core::iter::adapters::filter_map::FilterMap<core::ops::range::Range<usize>, oha::client::fast::work::{closure#0}::{clo…` |
| oha | async | `0x7abe80` | 3 | **yes** | futures combinator (inlines user closure) | `<core::pin::Pin<alloc::boxed::Box<oha::client::fast::work::{closure#0}::{closure#2}::{closure#0}::{closure#0}>> as core::future::future::Future>::poll` |
| oha | async | `0x5affe0` | 2 | **yes** | core generic (iter/sort/fn-shim over user closure) | `<core::iter::adapters::map::Map<core::iter::adapters::filter_map::FilterMap<core::ops::range::Range<usize>, oha::client::fast::work_until::{closure#0}…` |
| oha | async | `0x5b0330` | 2 | **yes** | core generic (iter/sort/fn-shim over user closure) | `<core::iter::adapters::map::Map<core::iter::adapters::filter_map::FilterMap<core::ops::range::Range<usize>, oha::client::fast::work_until::{closure#0}…` |
| oha | async | `0x66c390` | 2 | **yes** | futures combinator (inlines user closure) | `<tokio::time::timeout::Timeout<<oha::client::Client>::tls_client::{closure#0}> as core::future::future::Future>::poll` |
| oha | async | `0x5a01f0` | 11 | **yes** | unclassified library generic (no recognized adapter pattern) | `<ratatui_core::terminal::Terminal<ratatui_crossterm::CrosstermBackend<std::io::stdio::Stdout>>>::try_draw::<<ratatui_core::terminal::Terminal<ratatui_…` |
| oha | async | `0x7aa730` | 3 | **yes** | futures combinator (inlines user closure) | `<core::pin::Pin<alloc::boxed::Box<oha::client::fast::work_until::{closure#0}::{closure#2}::{closure#0}::{closure#0}>> as core::future::future::Future>…` |
| ouch | sync | `0x368380` | 13 | *undeterminable (legacy mangling)* | rayon generic (data-parallel, inlines user closure) | `<rayon::iter::map::MapFolder<C,F> as rayon::iter::plumbing::Folder<T>>::consume_iter` |
| ouch | sync | `0x24b680` | 3 | *undeterminable (legacy mangling)* | thread-trampoline (std generic over user fn) | `std::sys::backtrace::__rust_begin_short_backtrace` |
| ouch | sync | `0x205160` | 5 | *undeterminable (legacy mangling)* | unclassified library generic (no recognized adapter pattern) | `sevenz_rust2::util::decompress::decompress_impl::{{closure}}` |
| rage | sync | `0x286010` | 2 | *undeterminable (legacy mangling)* | unclassified library generic (no recognized adapter pattern) | `<nom::multi::ManyTill<F,G,E> as nom::internal::Parser<I>>::process` |
| rage | sync | `0x285b60` | 2 | *undeterminable (legacy mangling)* | unclassified library generic (no recognized adapter pattern) | `<nom::internal::MapOpt<F,G> as nom::internal::Parser<I>>::process` |
| rage | sync | `0x1a4e70` | 3 | *undeterminable (legacy mangling)* | unclassified library generic (no recognized adapter pattern) | `std::sync::poison::once::Once::call_once::{{closure}}` |
| rage | sync | `0x1c73d0` | 3 | *undeterminable (legacy mangling)* | unclassified library generic (no recognized adapter pattern) | `<nom::internal::MapOpt<F,G> as nom::internal::Parser<I>>::process` |
| ripgrep | sync | `0x2e3c90` | 2 | **yes** | core generic (iter/sort/fn-shim over user closure) | `<core::iter::adapters::filter_map::FilterMap<ignore::walk::Walk, rg::files::{closure#0}> as core::iter::traits::iterator::Iterator>::next` |
| ripgrep | sync | `0x27aa30` | 2 | **yes** | core generic (iter/sort/fn-shim over user closure) | `<core::iter::adapters::filter_map::FilterMap<ignore::walk::Walk, rg::search::{closure#0}> as core::iter::traits::iterator::Iterator::advance_by::SpecA…` |
| ripgrep | sync | `0x282c80` | 2 | **yes** | core generic (iter/sort/fn-shim over user closure) | `<core::iter::adapters::filter_map::FilterMap<ignore::walk::Walk, rg::files::{closure#0}> as core::iter::traits::iterator::Iterator>::next` |
| rustscan | async | `0x372b60` | 10 | **yes** | futures combinator (inlines user closure) | `<futures_util::stream::futures_unordered::FuturesUnordered<<rustscan::scanner::Scanner>::scan_socket::{closure#0}> as futures_core::stream::Stream>::p…` |
| starship | sync | `0x910ec0` | 2 | **yes** | unclassified library generic (no recognized adapter pattern) | `<std::sync::once::Once>::call_once_force::<<std::sync::once_lock::OnceLock<core::option::Option<usize>>>::initialize<<std::sync::once_lock::OnceLock<c…` |
| starship | sync | `0x84d780` | 4 | **yes** | rayon generic (data-parallel, inlines user closure) | `rayon::iter::plumbing::bridge_producer_consumer::helper::<rayon::vec::DrainProducer<(&alloc::string::String, &mut core::option::Option<core::result::R…` |
| starship | sync | `0x81b750` | 2 | **yes** | rayon generic (data-parallel, inlines user closure) | `rayon::iter::plumbing::bridge_producer_consumer::helper::<rayon::vec::DrainProducer<(&alloc::string::String, &mut core::option::Option<core::result::R…` |
| taplo | sync | `0x867280` | 2 | **yes** | framework handler-adapter (monomorphized over user handler) | `<core::iter::adapters::filter::Filter<core::iter::adapters::map::Map<core::iter::adapters::filter_map::FilterMap<rowan::cursor::PreorderWithTokens, <r…` |
| taplo | sync | `0x7eb720` | 3 | **yes** | futures combinator (inlines user closure) | `tokio::runtime::task::raw::poll::<<lsp_async_stub::Server<alloc::sync::Arc<taplo_lsp::world::WorldState<taplo_common::environment::native::NativeEnvir…` |
| taplo | sync | `0x78a110` | 2 | **yes** | framework handler-adapter (monomorphized over user handler) | `<either::Either<taplo::util::iter::ExactIter<core::iter::adapters::map::Map<core::iter::adapters::filter::Filter<rowan::api::SyntaxElementChildren<tap…` |
| taplo | sync | `0x9bd530` | 4 | **yes** | serde generic (derive/monomorph over user type) | `<serde_json::value::Value as serde::de::Deserializer>::deserialize_any::<taplo::dom::serde::TomlVisitor>` |

**67 STRONG false attributions total.** By cause:

- 18 — unclassified library generic (no recognized adapter pattern)
- 15 — futures combinator (inlines user closure)
- 11 — core generic (iter/sort/fn-shim over user closure)
- 8 — thread-trampoline (std generic over user fn)
- 8 — framework handler-adapter (monomorphized over user handler)
- 5 — rayon generic (data-parallel, inlines user closure)
- 2 — serde generic (derive/monomorph over user type)

**By author-parameterization** (see `author_parameterized()` — this split, not the cause split above, is what decides the *cost* of a false attribution):

- **49** are library generics *monomorphized over author code* — these bytes exist only because the author's code does, so the instantiation is specific to this binary and stays author-discriminative as a signature seed.
- **0** are **stock dependency code** — bytes present in anything linking that crate. These are the ones that would put a cross-project false positive into a generated rule.
- **18** are **undeterminable**: legacy-mangled binaries do not encode generic arguments, so whether the generic was instantiated over author code is not recoverable from the symbol. Counted, never guessed.

## Unknown-authorship functions (excluded from both numerator and denominator)

| binary | count | note |
|---|---:|---|
| pastel | 1 | 0 with no symbol at all; rest: leading crate absent from cargo metadata |
| tokei | 1 | 0 with no symbol at all; rest: leading crate absent from cargo metadata |
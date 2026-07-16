## Per-binary inventory

| binary | stratum B | domain | certain | STRONG | author crates | dep crates (metadata) | dep crates (DEPCRATE) |
|---|---|---|---:|---:|---:|---:|---:|
| bandwhich | async | async | 24 | 11 | 1 | 399 | 56 |
| dufs | async | async | 37 | 14 | 1 | 311 | 61 |
| fclones | async | parallel | 98 | 26 | 2 | 172 | 59 |
| gping | async | async | 7 | 4 | 2 | 198 | 36 |
| miniserve | async | async | 27 | 14 | 1 | 418 | 114 |
| oha | async | async | 160 | 107 | 1 | 456 | 80 |
| rage | sync | crypto | 73 | 37 | 6 | 358 | 68 |
| rustscan | async | async | 5 | 4 | 1 | 267 | 63 |
| trippy | async | async | 58 | 38 | 9 | 379 | 79 |
| xh | async | async | 39 | 12 | 1 | 345 | 89 |

## STRONG tier — stratified (Rule B, pre-registered)


**STRONG (>= 2 anchors) — SYNC** — 1 binaries: rage

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 37 | 33 | 4 | 0 | 89.2% | [75.3, 95.7] | n too small |
| meta | unwrapped | 37 | 33 | 4 | 0 | 89.2% | [75.3, 95.7] | n too small |
| depcrate | strict | 37 | 33 | 4 | 0 | 89.2% | [75.3, 95.7] | n too small |
| depcrate | unwrapped | 37 | 33 | 4 | 0 | 89.2% | [75.3, 95.7] | n too small |

**STRONG (>= 2 anchors) — ASYNC** — 9 binaries: bandwhich, dufs, fclones, gping, miniserve, oha, rustscan, trippy, xh

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 230 | 197 | 33 | 0 | 85.7% | [80.5, 89.6] | [70.9, 93.1] |
| meta | unwrapped | 230 | 202 | 28 | 0 | 87.8% | [83.0, 91.4] | [77.5, 95.5] |
| depcrate | strict | 230 | 197 | 33 | 0 | 85.7% | [80.5, 89.6] | [70.9, 93.1] |
| depcrate | unwrapped | 230 | 202 | 28 | 0 | 87.8% | [83.0, 91.4] | [77.5, 95.5] |

**STRONG (>= 2 anchors) — COMBINED** — 10 binaries: bandwhich, dufs, fclones, gping, miniserve, oha, rage, rustscan, trippy, xh

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 267 | 230 | 37 | 0 | 86.1% | [81.5, 89.8] | [75.0, 92.5] |
| meta | unwrapped | 267 | 235 | 32 | 0 | 88.0% | [83.6, 91.4] | [79.9, 94.2] |
| depcrate | strict | 267 | 230 | 37 | 0 | 86.1% | [81.5, 89.8] | [75.0, 92.5] |
| depcrate | unwrapped | 267 | 235 | 32 | 0 | 88.0% | [83.6, 91.4] | [79.9, 94.2] |

## SINGLE tier — stratified (Rule B)


**SINGLE (1 anchor) — SYNC** — 1 binaries: rage

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 35 | 30 | 5 | 1 | 85.7% | [70.6, 93.7] | n too small |
| meta | unwrapped | 35 | 30 | 5 | 1 | 85.7% | [70.6, 93.7] | n too small |
| depcrate | strict | 36 | 31 | 5 | 0 | 86.1% | [71.3, 93.9] | n too small |
| depcrate | unwrapped | 36 | 31 | 5 | 0 | 86.1% | [71.3, 93.9] | n too small |

**SINGLE (1 anchor) — ASYNC** — 9 binaries: bandwhich, dufs, fclones, gping, miniserve, oha, rustscan, trippy, xh

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 223 | 126 | 97 | 2 | 56.5% | [49.9, 62.8] | [38.2, 89.7] |
| meta | unwrapped | 223 | 134 | 89 | 2 | 60.1% | [53.5, 66.3] | [41.5, 92.1] |
| depcrate | strict | 223 | 126 | 97 | 2 | 56.5% | [49.9, 62.8] | [38.2, 89.7] |
| depcrate | unwrapped | 223 | 134 | 89 | 2 | 60.1% | [53.5, 66.3] | [41.5, 92.1] |

**SINGLE (1 anchor) — COMBINED** — 10 binaries: bandwhich, dufs, fclones, gping, miniserve, oha, rage, rustscan, trippy, xh

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 258 | 156 | 102 | 3 | 60.5% | [54.4, 66.2] | [41.9, 88.9] |
| meta | unwrapped | 258 | 164 | 94 | 3 | 63.6% | [57.5, 69.2] | [45.1, 90.6] |
| depcrate | strict | 259 | 157 | 102 | 2 | 60.6% | [54.6, 66.4] | [41.9, 89.0] |
| depcrate | unwrapped | 259 | 165 | 94 | 2 | 63.7% | [57.7, 69.3] | [45.2, 90.7] |

## Exploratory stratification (Rule A-prime, POST-HOC — not a headline claim)

Rule A-prime: ASYNC iff a runtime generic is monomorphized over an author crate (i.e. the combinator actually inlines author code), not merely linked. Written after Rule A was refuted; reported for transparency only.


**[exploratory] STRONG — SYNC (A-prime)** — 4 binaries: gping, rage, trippy, xh

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 91 | 85 | 6 | 0 | 93.4% | [86.4, 96.9] | [79.6, 100.0] |
| meta | unwrapped | 91 | 86 | 5 | 0 | 94.5% | [87.8, 97.6] | [87.5, 100.0] |
| depcrate | strict | 91 | 85 | 6 | 0 | 93.4% | [86.4, 96.9] | [79.6, 100.0] |
| depcrate | unwrapped | 91 | 86 | 5 | 0 | 94.5% | [87.8, 97.6] | [87.5, 100.0] |

**[exploratory] STRONG — ASYNC (A-prime)** — 6 binaries: bandwhich, dufs, fclones, miniserve, oha, rustscan

| oracle | ruler | n | TP | FP | unknown | precision | Wilson 95% | cluster bootstrap 95% |
|---|---|---:|---:|---:|---:|---:|---|---|
| meta | strict | 176 | 145 | 31 | 0 | 82.4% | [76.1, 87.3] | [61.4, 88.4] |
| meta | unwrapped | 176 | 149 | 27 | 0 | 84.7% | [78.6, 89.2] | [68.6, 90.5] |
| depcrate | strict | 176 | 145 | 31 | 0 | 82.4% | [76.1, 87.3] | [61.4, 88.4] |
| depcrate | unwrapped | 176 | 149 | 27 | 0 | 84.7% | [78.6, 89.2] | [68.6, 90.5] |

## Threshold ladder (`--min-anchors`), combined, cargo-metadata oracle / unwrapped

| min-anchors | n | precision | Wilson 95% | cluster bootstrap 95% | recall retained |
|---:|---:|---:|---|---|---:|
| >= 1 | 525 | 76.0% | [72.2, 79.5] | [61.2, 91.7] | 99.4% |
| >= 2 | 267 | 88.0% | [83.6, 91.4] | [79.9, 94.2] | 50.6% |
| >= 3 | 146 | 89.7% | [83.7, 93.7] | [81.1, 94.4] | 27.7% |
| >= 4 | 98 | 94.9% | [88.6, 97.8] | [84.8, 98.6] | 18.6% |

## Every false attribution — STRONG tier (>= 2 anchors)

Ruler: cargo-metadata oracle, **strict** (no wrapper unwrapping) — the most conservative reading, so this list is a superset. Rows marked *(rescued by unwrapped)* are forwarding wrappers whose body is the author's closure; the `unwrapped` ruler counts them as user, and that is a judgment call you can audit here rather than take on trust.

| binary | stratum | address | anchors | author-param? | why it is not user | demangled symbol |
|---|---|---|---:|---|---|---|
| bandwhich | async | `0x874d0` | 3 | **yes** | unclassified library generic (no recognized adapter pattern) | `core::ptr::drop_glue::<core::option::Option<bandwhich::network::dns::client::Client>>` |
| bandwhich | async | `0x8f610` | 10 | **yes** | thread-trampoline (std generic over user fn) *(rescued by unwrapped)* | `std::sys::backtrace::__rust_begin_short_backtrace::<bandwhich::start<ratatui_crossterm::CrosstermBackend<std::io::stdio::Stdout>>::{closure#2}, ()>` |
| bandwhich | async | `0x92f50` | 5 | **yes** | thread-trampoline (std generic over user fn) *(rescued by unwrapped)* | `std::sys::backtrace::__rust_begin_short_backtrace::<bandwhich::start<bandwhich::display::raw_terminal_backend::RawTerminalBackend>::{closure#1}, ()>` |
| bandwhich | async | `0x90630` | 6 | **yes** | thread-trampoline (std generic over user fn) *(rescued by unwrapped)* | `std::sys::backtrace::__rust_begin_short_backtrace::<bandwhich::start<ratatui_crossterm::CrosstermBackend<std::io::stdio::Stdout>>::{closure#1}, ()>` |
| bandwhich | async | `0x91f30` | 10 | **yes** | thread-trampoline (std generic over user fn) *(rescued by unwrapped)* | `std::sys::backtrace::__rust_begin_short_backtrace::<bandwhich::start<bandwhich::display::raw_terminal_backend::RawTerminalBackend>::{closure#2}, ()>` |
| fclones | async | `0x204bc0` | 3 | **yes** | unclassified library generic (no recognized adapter pattern) | `<nom::branch::alt<&str, std::ffi::os_str::OsString, nom::error::Error<&str>, (nom::combinator::map<&str, (&str, &str), std::ffi::os_str::OsString, nom…` |
| fclones | async | `0x295260` | 2 | **yes** | rayon generic (data-parallel, inlines user closure) | `<rayon_core::job::HeapJob<rayon_core::spawn::spawn_job<fclones::group::rehash<fclones::group::group_by_prefix::{closure#0}, fclones::group::group_by_p…` |
| fclones | async | `0x209d90` | 2 | **yes** | unclassified library generic (no recognized adapter pattern) | `core::ptr::drop_glue::<fclones::cache::HashCache>` |
| fclones | async | `0x26e6e0` | 2 | **yes** | unclassified library generic (no recognized adapter pattern) | `<nom::sequence::tuple<&str, (&str, &str), nom::error::Error<&str>, (nom::bytes::complete::tag<&str, &str, nom::error::Error<&str>>::{closure#0}, fclon…` |
| fclones | async | `0x2bd290` | 2 | **yes** | rayon generic (data-parallel, inlines user closure) | `rayon::iter::plumbing::bridge_producer_consumer::helper::<rayon::vec::DrainProducer<fclones::dedupe::FsCommand>, rayon::iter::map::MapConsumer<rayon::…` |
| gping | async | `0x1d3670` | 2 | **yes** | thread-trampoline (std generic over user fn) *(rescued by unwrapped)* | `std::sys::backtrace::__rust_begin_short_backtrace::<<pinger::linux::LinuxPinger as pinger::Pinger>::start::{closure#0}, ()>` |
| gping | async | `0xe8800` | 6 | **yes** | unclassified library generic (no recognized adapter pattern) | `<ratatui_core::terminal::Terminal<ratatui_crossterm::CrosstermBackend<std::io::buffered::bufwriter::BufWriter<std::io::stdio::Stdout>>>>::try_draw::<<…` |
| miniserve | async | `0x35e62f` | 2 | **yes** | framework handler-adapter (monomorphized over user handler) | `actix_web::handler::handler_service::<miniserve::listing::file_handler, (actix_web::request::HttpRequest,)>::{closure#0}::{closure#0}` |
| miniserve | async | `0x35d79f` | 2 | **yes** | framework handler-adapter (monomorphized over user handler) | `actix_web::handler::handler_service::<miniserve::file_op::rm_file, (actix_web::request::HttpRequest, actix_web::types::query::Query<miniserve::file_op…` |
| miniserve | async | `0x354a6c` | 6 | **yes** | framework handler-adapter (monomorphized over user handler) | `actix_web::handler::handler_service::<miniserve::api, (actix_web::types::json::Json<miniserve::ApiCommand>, actix_web::data::Data<miniserve::config::M…` |
| miniserve | async | `0x36ceee` | 2 | **yes** | framework handler-adapter (monomorphized over user handler) | `<actix_web_httpauth::middleware::AuthenticationMiddleware<actix_web::scope::ScopeService, miniserve::auth::handle_auth, actix_web_httpauth::extractors…` |
| miniserve | async | `0x358919` | 2 | **yes** | framework handler-adapter (monomorphized over user handler) | `actix_web::handler::handler_service::<miniserve::file_op::upload_file, (actix_web::request::HttpRequest, actix_web::types::query::Query<miniserve::fil…` |
| miniserve | async | `0x34a077` | 8 | **yes** | futures combinator (inlines user closure) | `<tokio::task::local::LocalSet>::run_until::<miniserve::run::{closure#0}>::{closure#0}` |
| miniserve | async | `0x3ae87d` | 3 | **yes** | framework handler-adapter (monomorphized over user handler) | `<actix_web::middleware::logger::LoggerResponse<actix_web::middleware::from_fn::MiddlewareFnService<miniserve::errors::error_page_middleware<actix_http…` |
| oha | async | `0x7aa730` | 3 | **yes** | futures combinator (inlines user closure) | `<core::pin::Pin<alloc::boxed::Box<oha::client::fast::work_until::{closure#0}::{closure#2}::{closure#0}::{closure#0}>> as core::future::future::Future>…` |
| oha | async | `0x7ab1b0` | 2 | **yes** | futures combinator (inlines user closure) | `<core::pin::Pin<alloc::boxed::Box<oha::client::fast::work_until::{closure#0}::{closure#1}::{closure#0}::{closure#0}>> as core::future::future::Future>…` |
| oha | async | `0x6f5fc0` | 3 | **yes** | futures combinator (inlines user closure) | `<tokio::time::timeout::Timeout<<oha::client::Client>::work_http1::{closure#0}::{closure#0}> as core::future::future::Future>::poll` |
| oha | async | `0x6683f0` | 3 | **yes** | futures combinator (inlines user closure) | `<tokio::time::timeout::Timeout<<oha::client::Client>::work_http1::{closure#0}::{closure#0}> as core::future::future::Future>::poll` |
| oha | async | `0x66c390` | 2 | **yes** | futures combinator (inlines user closure) | `<tokio::time::timeout::Timeout<<oha::client::Client>::tls_client::{closure#0}> as core::future::future::Future>::poll` |
| oha | async | `0x6fa230` | 3 | **yes** | futures combinator (inlines user closure) | `<tokio::time::timeout::Timeout<<oha::client::Client>::tls_client::{closure#0}> as core::future::future::Future>::poll` |
| oha | async | `0x5b0330` | 2 | **yes** | core generic (iter/sort/fn-shim over user closure) | `<core::iter::adapters::map::Map<core::iter::adapters::filter_map::FilterMap<core::ops::range::Range<usize>, oha::client::fast::work_until::{closure#0}…` |
| oha | async | `0x5a01f0` | 11 | **yes** | unclassified library generic (no recognized adapter pattern) | `<ratatui_core::terminal::Terminal<ratatui_crossterm::CrosstermBackend<std::io::stdio::Stdout>>>::try_draw::<<ratatui_core::terminal::Terminal<ratatui_…` |
| oha | async | `0x5affe0` | 2 | **yes** | core generic (iter/sort/fn-shim over user closure) | `<core::iter::adapters::map::Map<core::iter::adapters::filter_map::FilterMap<core::ops::range::Range<usize>, oha::client::fast::work_until::{closure#0}…` |
| oha | async | `0x5b0670` | 2 | **yes** | core generic (iter/sort/fn-shim over user closure) | `<core::iter::adapters::map::Map<core::iter::adapters::filter_map::FilterMap<core::ops::range::Range<usize>, oha::client::fast::work::{closure#0}::{clo…` |
| oha | async | `0x7ac7c0` | 2 | **yes** | futures combinator (inlines user closure) | `<core::pin::Pin<alloc::boxed::Box<oha::client::fast::work::{closure#0}::{closure#1}::{closure#0}::{closure#0}>> as core::future::future::Future>::poll` |
| oha | async | `0x5b09c0` | 2 | **yes** | core generic (iter/sort/fn-shim over user closure) | `<core::iter::adapters::map::Map<core::iter::adapters::filter_map::FilterMap<core::ops::range::Range<usize>, oha::client::fast::work::{closure#0}::{clo…` |
| oha | async | `0x7abe80` | 3 | **yes** | futures combinator (inlines user closure) | `<core::pin::Pin<alloc::boxed::Box<oha::client::fast::work::{closure#0}::{closure#2}::{closure#0}::{closure#0}>> as core::future::future::Future>::poll` |
| rage | sync | `0x1a4e70` | 3 | *undeterminable (legacy mangling)* | unclassified library generic (no recognized adapter pattern) | `std::sync::poison::once::Once::call_once::{{closure}}` |
| rage | sync | `0x286010` | 2 | *undeterminable (legacy mangling)* | unclassified library generic (no recognized adapter pattern) | `<nom::multi::ManyTill<F,G,E> as nom::internal::Parser<I>>::process` |
| rage | sync | `0x1c73d0` | 3 | *undeterminable (legacy mangling)* | unclassified library generic (no recognized adapter pattern) | `<nom::internal::MapOpt<F,G> as nom::internal::Parser<I>>::process` |
| rage | sync | `0x285b60` | 2 | *undeterminable (legacy mangling)* | unclassified library generic (no recognized adapter pattern) | `<nom::internal::MapOpt<F,G> as nom::internal::Parser<I>>::process` |
| rustscan | async | `0x372b60` | 10 | **yes** | futures combinator (inlines user closure) | `<futures_util::stream::futures_unordered::FuturesUnordered<<rustscan::scanner::Scanner>::scan_socket::{closure#0}> as futures_core::stream::Stream>::p…` |

**37 STRONG false attributions total.** By cause:

- 10 — unclassified library generic (no recognized adapter pattern)
- 10 — futures combinator (inlines user closure)
- 6 — framework handler-adapter (monomorphized over user handler)
- 5 — thread-trampoline (std generic over user fn)
- 4 — core generic (iter/sort/fn-shim over user closure)
- 2 — rayon generic (data-parallel, inlines user closure)

**By author-parameterization** (see `author_parameterized()` — this split, not the cause split above, is what decides the *cost* of a false attribution):

- **33** are library generics *monomorphized over author code* — these bytes exist only because the author's code does, so the instantiation is specific to this binary and stays author-discriminative as a signature seed.
- **0** are **stock dependency code** — bytes present in anything linking that crate. These are the ones that would put a cross-project false positive into a generated rule.
- **4** are **undeterminable**: legacy-mangled binaries do not encode generic arguments, so whether the generic was instantiated over author code is not recoverable from the symbol. Counted, never guessed.

## Unknown-authorship functions (excluded from both numerator and denominator)

| binary | count | note |
|---|---:|---|
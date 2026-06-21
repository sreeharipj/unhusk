#!/usr/bin/env bash
# turbo-bench/run_bench.sh
#
# Clones, builds, and benchmarks 5 real-world Rust binaries against
# two unhusk builds supplied on the command line.
#
# Usage:
#   ./run_bench.sh <path/to/unhusk-orig> <path/to/unhusk-turbo> [runs]
#
# Example:
#   cargo build --release
#   cp ../target/release/unhusk /tmp/unhusk_turbo
#   git stash && cargo build --release && cp ../target/release/unhusk /tmp/unhusk_orig && git stash pop
#   ./run_bench.sh /tmp/unhusk_orig /tmp/unhusk_turbo 10

set -euo pipefail

ORIG=${1:?usage: $0 <orig-binary> <turbo-binary> [runs]}
TURBO=${2:?usage: $0 <orig-binary> <turbo-binary> [runs]}
RUNS=${3:-10}
DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Clone + build targets ────────────────────────────────────────────────────

declare -A REPOS=(
  [ripgrep]="https://github.com/BurntSushi/ripgrep.git"
  [bat]="https://github.com/sharkdp/bat.git"
  [fd]="https://github.com/sharkdp/fd.git"
  [tokei]="https://github.com/XAMPPRocky/tokei.git"
  [just]="https://github.com/casey/just.git"
)

declare -A BIN_NAME=(
  [ripgrep]="rg" [bat]="bat" [fd]="fd" [tokei]="tokei" [just]="just"
)

echo "── cloning & building ──────────────────────────────────────────────────"
for name in "${!REPOS[@]}"; do
  if [[ ! -d "$DIR/$name" ]]; then
    echo "  cloning $name..."
    git clone --depth=1 "${REPOS[$name]}" "$DIR/$name" -q
  fi
  bin="$DIR/$name/target/release/${BIN_NAME[$name]}"
  if [[ ! -f "$bin" ]]; then
    echo "  building $name..."
    cargo build --release --manifest-path "$DIR/$name/Cargo.toml" -q
  else
    echo "  $name already built"
  fi
done

# ── Benchmark ────────────────────────────────────────────────────────────────

avg_ms() {
  local tool=$1 target=$2 total=0
  for _ in $(seq 1 "$RUNS"); do
    local ms
    ms=$({ time "$tool" "$target" >/dev/null 2>&1; } 2>&1 \
      | awk '/real/{split($2,a,"m"); printf "%.0f",(a[1]*60+a[2])*1000}')
    total=$(( total + ms ))
  done
  echo $(( total / RUNS ))
}

echo ""
echo "── results (${RUNS} runs each) ────────────────────────────────────────────────"
printf "  %-10s  %5s  %9s  %8s  %8s  %8s  %7s\n" \
  "binary" "size" "user_locs" "orig" "turbo" "saved" "speedup"
printf "  %-10s  %5s  %9s  %8s  %8s  %8s  %7s\n" \
  "----------" "-----" "---------" "--------" "--------" "--------" "-------"

total_orig=0; total_turbo=0

for name in ripgrep bat fd tokei just; do
  bin="$DIR/$name/target/release/${BIN_NAME[$name]}"
  size=$(ls -lh "$bin" | awk '{print $5}')
  user_locs=$("$TURBO" "$bin" 2>/dev/null | grep -oP '(?<=user=)\d+' | head -1)
  user_locs=${user_locs:-0}

  o=$(avg_ms "$ORIG"  "$bin")
  t=$(avg_ms "$TURBO" "$bin")
  saved=$(( o - t ))
  sx=$(awk "BEGIN{printf \"%.1fx\", $o/$t}")

  total_orig=$(( total_orig + o ))
  total_turbo=$(( total_turbo + t ))

  printf "  %-10s  %5s  %9s  %7sms  %7sms  %7sms  %7s\n" \
    "$name" "$size" "$user_locs" "$o" "$t" "$saved" "$sx"
done

echo ""
total_saved=$(( total_orig - total_turbo ))
total_sx=$(awk "BEGIN{printf \"%.1fx\", $total_orig/$total_turbo}")
printf "  %-10s  %5s  %9s  %7sms  %7sms  %7sms  %7s\n" \
  "TOTAL" "" "" "$total_orig" "$total_turbo" "$total_saved" "$total_sx"
echo ""
echo "  user_locs = user-code panic/assert Location structs in the binary"

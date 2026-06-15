#!/usr/bin/env bash
ROOT=/home/user/Videos/unhusk/realval
cd "$ROOT"
# name url binary
run() { bash "$ROOT/run.sh" "$1" "$2" "$3"; }

run ripgrep   https://github.com/BurntSushi/ripgrep      rg
run fd        https://github.com/sharkdp/fd              fd
run bat       https://github.com/sharkdp/bat             bat
run hyperfine https://github.com/sharkdp/hyperfine       hyperfine
run hexyl     https://github.com/sharkdp/hexyl           hexyl
run tokei     https://github.com/XAMPPRocky/tokei        tokei
run xsv       https://github.com/BurntSushi/xsv          xsv
run sd        https://github.com/chmln/sd                sd
run just      https://github.com/casey/just             just
run grex      https://github.com/pemistahl/grex          grex
run pastel    https://github.com/sharkdp/pastel          pastel
run zoxide    https://github.com/ajeetdsouza/zoxide      zoxide
run dust      https://github.com/bootandy/dust           dust
echo "ALL DONE" > "$ROOT/out/BATCH_DONE"

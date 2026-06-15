#!/usr/bin/env bash
ROOT=/home/user/Videos/unhusk/realval
cd "$ROOT"
r() { bash "$ROOT/run2.sh" "$1" "$2" "$3"; }
r ripgrep   https://github.com/BurntSushi/ripgrep      rg
r fd        https://github.com/sharkdp/fd              fd
r bat       https://github.com/sharkdp/bat             bat
r hyperfine https://github.com/sharkdp/hyperfine       hyperfine
r hexyl     https://github.com/sharkdp/hexyl           hexyl
r tokei     https://github.com/XAMPPRocky/tokei        tokei
r xsv       https://github.com/BurntSushi/xsv          xsv
r sd        https://github.com/chmln/sd                sd
r just      https://github.com/casey/just             just
r grex      https://github.com/pemistahl/grex          grex
r pastel    https://github.com/sharkdp/pastel          pastel
r zoxide    https://github.com/ajeetdsouza/zoxide      zoxide
r dust      https://github.com/bootandy/dust           dust
echo DONE > "$ROOT/out2/BATCH2_DONE"

#!/usr/bin/env bash
# Run the deployed firmware (default build vars, or override via extra args) on the streaming
# evaluation corpora and score real hit-rate / false-accepts-per-hour (spec 4.1/4.5).
#   bash tools/run_phase6_eval.sh [make vars...]      e.g. KWS_P_ON=0.7 (not a real flag; see below)
# To sweep P_ON/INFER_EVERY, pass Makefile vars directly, e.g.:
#   bash tools/run_phase6_eval.sh CFLAGS_EXTRA=-DKWS_P_ON=0.8f   (not supported by the Makefile yet;
#   the Makefile's own KWS_P_ON is baked via inference.c default; simplest is to edit and rebuild.)
set -euo pipefail
cd "$(dirname "$0")/.."
EVAL=sim/wav_corpus/eval
mkdir -p build
[ -f "$EVAL/negative.s16le.pcm" ] || python tools/make_eval_streams.py
(cd firmware && mingw32-make -j8 "$@" > ../build/fw_build.log 2>&1) || { tail -30 build/fw_build.log; exit 1; }

UART_LOG="$(pwd -W)/build/uart0.log"   # must be absolute: CreateFileBackend does not resolve relative/@ paths
run() {  # name pcm runtime_s
  local name=$1 pcm=$2 rt=$3
  echo "=== $name ($rt s)"
  taskkill //F //IM Renode.exe > /dev/null 2>&1 || true   # a prior run can leave an orphan holding uart0.log open
  rm -f build/uart0.log
  timeout 1800 "${RENODE_BIN:-/c/Program Files/Renode/bin/Renode.exe}" --disable-xwt --plain --console \
    -e "\$pcm=@$pcm; \$runtime=\"$rt\"; \$uartlog=\"$UART_LOG\"; include @sim/boot.resc" \
    > "build/renode_$name.out" 2>&1 < /dev/null || true
  [ -s build/uart0.log ] || { echo "Renode produced no uart0.log; see build/renode_$name.out:" >&2; tail -20 "build/renode_$name.out" >&2; exit 1; }
  cp build/uart0.log "build/uart0_$name.log"
}

run positive_clean "$EVAL/positive_clean.s16le.pcm" 165
python tools/crosscheck_eval.py positive build/uart0_positive_clean.log "$EVAL/positive_clean.json"

run positive_noisy "$EVAL/positive_noisy.s16le.pcm" 165
python tools/crosscheck_eval.py positive build/uart0_positive_noisy.log "$EVAL/positive_noisy.json"

run negative "$EVAL/negative.s16le.pcm" 1805
python tools/crosscheck_eval.py negative build/uart0_negative.log 1800

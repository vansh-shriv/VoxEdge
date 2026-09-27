#!/usr/bin/env bash
# Build with a deliberate task stall injected, run in Renode, check overrun/drop/recovery behaviour.
#   bash tools/run_phase5_stall.sh dsp|inference <seq> <ms> [wdt_ms=2000] [runtime_s=16.5]
# ms=0 means an unrecoverable stall: the watchdog must reset the system (checked via a second boot
# banner). <seq> must be a hop number capture actually reaches; for `inference` it must additionally
# be a multiple of INFER_EVERY (default 40) or the stall will never trigger.
set -euo pipefail
cd "$(dirname "$0")/.."
TASK_NAME=$1; SEQ=$2; MS=$3; WDT=${4:-2000}; RUNTIME=${5:-16.5}
case "$TASK_NAME" in dsp) TID=1 ;; inference) TID=2 ;; *) echo "task must be dsp or inference" >&2; exit 2 ;; esac
MODE=finite; [ "$MS" = "0" ] && MODE=infinite

mkdir -p build
(cd firmware && mingw32-make -j8 STALL_TASK=$TID STALL_AT_SEQ=$SEQ STALL_MS=$MS WDT_TIMEOUT_MS=$WDT \
  > ../build/fw_build.log 2>&1) || { tail -30 build/fw_build.log; exit 1; }
rm -f build/uart0.log
timeout 180 "${RENODE_BIN:-/c/Program Files/Renode/bin/Renode.exe}" --disable-xwt --plain --console \
  -e "\$pcm=@sim/wav_corpus/kws/demo.s16le.pcm; \$runtime=\"$RUNTIME\"; include @sim/boot.resc" \
  > build/renode.out 2>&1 < /dev/null || true
python tools/crosscheck_stall.py build/uart0.log "$MODE" "$TASK_NAME"

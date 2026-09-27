#!/usr/bin/env bash
# Build the FreeRTOS firmware, run it headless in Renode on the burst test signal, validate.
# Requires Renode, Arm GNU toolchain, mingw32-make, python+numpy (Git Bash on Windows).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build
UART_LOG="$(pwd -W)/build/uart0.log"   # must be absolute: CreateFileBackend does not resolve relative/@ paths
[ -f sim/wav_corpus/synthetic/burst_3s.s16le.pcm ] || python tools/make_burst_wav.py
(cd firmware && mingw32-make -j8)
rm -f build/uart0.log
timeout 300 "${RENODE_BIN:-/c/Program Files/Renode/bin/Renode.exe}" --disable-xwt --plain --console \
  -e "\$uartlog=\"$UART_LOG\"; include @sim/boot.resc" > build/renode.out 2>&1 < /dev/null || true
[ -s build/uart0.log ] || { echo "Renode produced no uart0.log; see build/renode.out:" >&2; tail -20 build/renode.out >&2; exit 1; }
python tools/validate_phase1.py build/uart0.log

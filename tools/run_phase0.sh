#!/usr/bin/env bash
# Build Phase 0 firmware, run it in headless Renode, validate the UART capture against the source PCM.
# Run from anywhere; uses Git Bash. Requires Renode, Arm GNU toolchain, mingw32-make, python+numpy.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build
UART_LOG="$(pwd -W)/build/uart0.log"   # must be absolute: CreateFileBackend does not resolve relative/@ paths
(cd firmware/phase0 && mingw32-make -B)
rm -f build/uart0.log
timeout 180 "${RENODE_BIN:-/c/Program Files/Renode/bin/Renode.exe}" --disable-xwt --plain --console \
  -e "\$elf=@firmware/phase0/phase0.elf; \$pcm=@sim/wav_corpus/synthetic/tone1k_1s.s16le.pcm; \$runtime=\"1.5\"; \$uartlog=\"$UART_LOG\"; include @sim/boot.resc" > build/renode.out 2>&1 < /dev/null || true
[ -s build/uart0.log ] || { echo "Renode produced no uart0.log; see build/renode.out:" >&2; tail -20 build/renode.out >&2; exit 1; }
python tools/validate_capture.py build/uart0.log sim/wav_corpus/synthetic/tone1k_1s.s16le.pcm

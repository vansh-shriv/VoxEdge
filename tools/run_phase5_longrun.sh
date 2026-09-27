#!/usr/bin/env bash
# Build the default firmware, run it on several minutes of concatenated negative audio (Renode runs
# faster than real time), and check stack/heap watermarks + overrun/drop counters for drift.
#   bash tools/run_phase5_longrun.sh [minutes=8]
set -euo pipefail
cd "$(dirname "$0")/.."
MIN=${1:-8}
PCM=sim/wav_corpus/longrun/negative_${MIN%.*}min.s16le.pcm
mkdir -p build
[ -f "$PCM" ] || python tools/make_longrun_wav.py "$MIN"
(cd firmware && mingw32-make -j8 STALL_TASK=0 > ../build/fw_build.log 2>&1) || { tail -30 build/fw_build.log; exit 1; }
rm -f build/uart0.log
RUNTIME=$(python -c "print($MIN*60+1)")
timeout 900 "${RENODE_BIN:-/c/Program Files/Renode/bin/Renode.exe}" --disable-xwt --plain --console \
  -e "\$pcm=@$PCM; \$runtime=\"$RUNTIME\"; include @sim/boot.resc" \
  > build/renode.out 2>&1 < /dev/null || true
python tools/crosscheck_longrun.py build/uart0.log

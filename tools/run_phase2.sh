#!/usr/bin/env bash
# Regenerate DSP tables, build firmware with the feature dump on, run it in headless Renode on the
# features_2s signal, and cross-check every on-device log-mel vector against the Python reference.
# Usage: bash tools/run_phase2.sh [tolerance]
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build
PCM=sim/wav_corpus/synthetic/features_2s.s16le.pcm
[ -f "$PCM" ] || python tools/make_feature_test_wav.py
python tools/gen_dsp_tables.py
# INFER_EVERY huge = model never runs: the debug dump is the lowest-priority task and would drop vectors
# while a 200 ms inference is executing; this test isolates the DSP path.
(cd firmware && mingw32-make -j8 DUMP_FEATURES=1 INFER_EVERY=1000000)
rm -f build/uart0.log
timeout 300 "${RENODE_BIN:-/c/Program Files/Renode/bin/Renode.exe}" --disable-xwt --plain --console \
  -e '$pcm=@sim/wav_corpus/synthetic/features_2s.s16le.pcm; $runtime="2.6"; include @sim/boot.resc' \
  > build/renode.out 2>&1 < /dev/null || true
python tools/crosscheck_features.py build/uart0.log "$PCM" ${1:-0.02}

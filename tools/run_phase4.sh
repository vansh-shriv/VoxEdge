#!/usr/bin/env bash
# Build the firmware for a model, run it headless in Renode on an audio stream, then run the
# on-device-vs-Python parity check and print cycle statistics.
#
#   bash tools/run_phase4.sh [model=s] [runtime_s=16.5] [pcm] [make vars...]
# Defaults to a stress configuration (inference every 50 ms, i.e. as fast as the model allows, and every
# input tensor dumped) to collect many parity samples. Override with e.g. INFER_EVERY=40 KERNELS=ref.
# e.g. bash tools/run_phase4.sh xs 16.5 sim/wav_corpus/kws/demo.s16le.pcm KERNELS=ref
set -euo pipefail
cd "$(dirname "$0")/.."
MODEL=${1:-s}; RUNTIME=${2:-16.5}; PCM=${3:-sim/wav_corpus/kws/demo.s16le.pcm}
shift $(( $# < 3 ? $# : 3 ))
mkdir -p build
[ -f firmware/src/model/model_$MODEL.c ] || python tools/tflite_to_c.py
(cd firmware && mingw32-make -j8 MODEL=$MODEL DUMP_INFER=1 INFER_EVERY=5 DUMP_INPUT_EVERY=1 "$@" size > ../build/fw_build.log 2>&1) \
  || { tail -30 build/fw_build.log; exit 1; }
grep -E "^ +[0-9]+ +[0-9]+ +[0-9]+ +[0-9]+" build/fw_build.log | tail -1 || true
rm -f build/uart0.log
timeout 900 "${RENODE_BIN:-/c/Program Files/Renode/bin/Renode.exe}" --disable-xwt --plain --console \
  -e "\$pcm=@$PCM; \$runtime=\"$RUNTIME\"; include @sim/boot.resc" > build/renode.out 2>&1 < /dev/null || true
KERN=cmsis; for a in "$@"; do [ "$a" = "KERNELS=ref" ] && KERN=ref; done
python tools/crosscheck_model.py build/uart0.log "$PCM" "$MODEL" "$KERN" 2>&1 | grep -v -E "oneDNN|absl|I0000|E0000|W0000|Warning|warn|deprecated|TF 2|migration|details|^ *$|AVX|instructions|XNNPACK"

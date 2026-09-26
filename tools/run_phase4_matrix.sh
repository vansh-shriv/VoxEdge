#!/usr/bin/env bash
# Re-measure the Phase 4 latency/parity matrix from clean object trees and print one summary block per
# configuration. Slow (each configuration rebuilds TFLite-Micro): about 3 min per row.
#   bash tools/run_phase4_matrix.sh > build/phase4_matrix.log
set -uo pipefail
cd "$(dirname "$0")/.."
DEMO=sim/wav_corpus/kws/demo.s16le.pcm
row() {  # label model runtime make-vars...
  local label=$1 model=$2 runtime=$3; shift 3
  echo "=== $label"
  bash tools/run_phase4.sh "$model" "$runtime" "$DEMO" "$@" 2>&1 \
    | grep -E "^ +[0-9]+ +[0-9]+|^variant|inexact|PASS A|PASS B|PASS C|FAIL|kws_infer|model runs" | cut -c1-220
}
row "xs cmsis -Os"  xs 16.5
row "s  cmsis -Os"  s  16.5
row "m  cmsis -Os"  m  16.5
row "s  cmsis -O2"  s  16.5 OPT=-O2
row "s  ref   -Os"  s  10   KERNELS=ref

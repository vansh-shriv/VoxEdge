#!/usr/bin/env bash
# Run the default firmware on each pathological clip and check for crashes/hangs/NaNs (spec 4.4).
#   bash tools/run_phase5_pathological.sh
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build
[ -f sim/wav_corpus/pathological/mixed.s16le.pcm ] || python tools/make_pathological_wav.py
(cd firmware && mingw32-make -j8 STALL_TASK=0 > ../build/fw_build.log 2>&1) || { tail -30 build/fw_build.log; exit 1; }

status=0
for name in silence clipped noise_max mixed; do
  PCM=sim/wav_corpus/pathological/$name.s16le.pcm
  DUR=$(python -c "import wave; w=wave.open('sim/wav_corpus/pathological/$name.wav'); print(w.getnframes()/w.getframerate())")
  HOPS=$(python -c "print(int($DUR*100))")
  echo "=== $name (${DUR}s, ~$HOPS hops)"
  rm -f build/uart0.log
  timeout 180 "/c/Program Files/Renode/bin/Renode.exe" --disable-xwt --plain --console \
    -e "\$pcm=@$PCM; \$runtime=\"$(python -c "print($DUR+0.5)")\"; include @sim/boot.resc" \
    > build/renode.out 2>&1 < /dev/null || true
  python tools/crosscheck_pathological.py build/uart0.log "$HOPS" || status=1
done
exit $status

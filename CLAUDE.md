# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

Phases 0-4 are done: Renode PDM capture, FreeRTOS pipeline, log-mel features (CMSIS-DSP), DS-CNN keyword model for "marvin" (Speech Commands v0.02), and on-device int8 inference with TFLite-Micro + CMSIS-NN, verified against the Python model. Phase 5 (robustness/overload suite) is next, then Phase 6 (streaming evaluation corpus, CI, README). **Read `docs/PROGRESS.md` first and update it whenever a milestone, decision, or gotcha lands.** The original design is in `voxedge-spec-simulator.md`. Git remote: https://github.com/vansh-shriv/VoxEdge.git (branch `main`).

## Commands (Git Bash on Windows)

- After `git clone`: `git submodule update --init` (FreeRTOS-Kernel, CMSIS-DSP, CMSIS_6, tflite-micro in `third_party/`), then `bash tools/fetch_tflm_deps.sh` (flatbuffers, gemmlowp, ruy, CMSIS-NN into git-ignored `third_party/tflm_deps/`, MD5-verified). Python deps: numpy, scipy, librosa, soundfile, tensorflow (`ml/requirements.txt`).
- Model on device: `bash tools/run_phase4.sh [xs|s|m] [runtime_s] [pcm] [make vars]` builds, runs headless Renode on `sim/wav_corpus/kws/demo.s16le.pcm` (create with `python tools/make_kws_demo.py`), and checks parity against the Python int8 model plus cycle cost. Defaults to a stress configuration (`INFER_EVERY=5`, all input tensors dumped); override e.g. `KERNELS=ref`.
- Regressions: `bash tools/run_phase0.sh` (bare-metal capture equals source PCM), `bash tools/run_phase1.sh` (pipeline plumbing, no drops), `bash tools/run_phase2.sh` (on-device log-mel vs `ml/features.py`, inference disabled in that build).
- Firmware build only: `cd firmware && mingw32-make -j8 [MODEL=xs|s|m] [KERNELS=cmsis|ref] [DUMP_FEATURES=1] [DUMP_INFER=1] [INFER_EVERY=n] [ARENA_KB=n] [OPT=-Os]` (variables documented at the top of `firmware/Makefile`; `firmware/phase0` has its own). Each configuration has its own object dir; `voxedge.elf` is copied from it on every build. The Arm GNU Toolchain is not on PATH; `TOOLCHAIN` in the Makefile points at it.
- Model pipeline (host, long-running): `python ml/prepare_data.py` (needs `speech_commands_v0.02.tar.gz` in `D:\EmbeddedProjects\datasets`, outside the repo; writes an 858 MB feature cache), `python ml/train.py [xs|s|m]`, `python ml/quantize.py [xs|s|m]`, `python tools/tflite_to_c.py` (embeds `ml/artifacts/*.tflite` as C arrays), `python tools/gen_dsp_tables.py` (feature tables).
- Run Renode by hand from the repo root: `Renode.exe --disable-xwt --plain --console -e '$pcm=@<file>.s16le.pcm; $runtime="16.5"; include @sim/boot.resc' < /dev/null`. `boot.resc` takes `$elf`, `$pcm`, `$uartlog`, `$runtime`, loads `sim/platform.repl`, sets `cpu PerformanceInMips 64`. Input is raw s16le PCM, not WAV. The UART log path must be absolute and quoted (`$ORIGIN` does not expand); `boot.resc` hardcodes `D:/EmbeddedProjects/Voxedge/build/uart0.log`.
- Write multi-file or long scripts with the Write tool, not shell heredocs (the shell tool mis-parses long ones). Write Makefiles with Edit/Write, not Python string replacement.

## Architecture

Signal path: PCM file → Renode PDM model → PDM ISR (double buffer) → FreeRTOS tasks. Priorities: ISR > capture (5) > DSP (4) > inference (3) > telemetry (1) > idle (WFI hook).
- **ISR** (`src/pdm_capture.c`): re-arms the next EasyDMA buffer, copies the finished 10 ms hop into a stream buffer, or drops the whole hop and counts an overrun.
- **Capture** (`tasks/capture.c`): hops → overlapping 30 ms windows on a queue.
- **DSP** (`tasks/dsp.c`, `dsp/features.c`): float32 CMSIS-DSP 512-pt rfft → 40 log-mel values. It also **owns the feature ring** (`dsp/feature_ring.c`: last 98 vectors, normalised and int8-quantised) and every `INFER_EVERY` hops snapshots it and notifies the inference task, or skips and counts if inference is still busy. Features are never lost; overload only lowers the inference rate.
- **Inference** (`tasks/inference.c`, `model/kws.cc`): TFLite-Micro with a static arena, model chosen at link time (`MODEL=`), threshold `KWS_P_ON` → wake GPIO + `E` event.
- **Telemetry**: lowest-priority UART reporter (`T` stats each second, `E` events, and `F`/`L`/`Q` debug dumps behind build flags) via a queue set. Debug dumps can drop while inference runs; that is expected.
- `sim/platform.repl` = stock Nano 33 BLE plus SysTick at 64 MHz and a DWT shim. `ml/` = features reference, data prep, model, training, quantization, eval. `tools/` = generators, cross-checks, runners.

## Constraints that must hold across changes

- **Feature definition lives in `ml/feature_config.py` + `ml/features.py`.** Firmware tables (`firmware/src/dsp/dsp_tables.*`) and `firmware/src/model/model_*.c`/`model_meta.h` are generated (`tools/gen_dsp_tables.py`, `tools/tflite_to_c.py`); never hand-edit them. Training must reuse `ml/features.py` so train and deploy inputs match.
- **Cycle numbers in Renode are instruction counts** (DWT shim serves `CYCCNT` from executed instructions at an assumed 64 MIPS / 1 IPC), so they are lower bounds. Use PDM hop `seq` for audio time; Renode's SysTick starts about 262 ms late.
- **Cross-checks are mandatory before trusting results**: features vs Python (`run_phase2.sh`, spec 4.2) and model output vs the Python int8 model (`run_phase4.sh`, spec 4.3). CMSIS-NN may differ by 1 LSB in rare inferences; reference kernels must be exact.
- **Verify what actually ran**: a stale ELF once produced false passes. After changing build variables, check the size/telemetry line (`arena`, `runs`, `infcyc_*`).
- **Robustness requirement**: capture must never miss a PDM handoff even when DSP/inference is stalled; overruns are detected, reported, and recovered from without corruption (demonstrated so far with overloaded inference; systematic tests are Phase 5).
- **Honest metrics**: latency in simulated time or emulated instruction counts, never wall-clock; real-time margin = cycles per stage relative to one 10 ms hop; **power/current is not measured** and docs must say so; hit rate (clean and noisy) and false accepts per hour on streaming audio are the evaluation metrics (spec asks 50+ clean, 50+ noisy positives, 30+ min negatives; clip-level numbers so far are not streaming numbers).

## Resolved decisions

PDM path: built-in Renode model. Features: log-mel (not MFCC). Keyword: "marvin" from Speech Commands. Model: `s` DS-CNN (4.1k params, 1.67 M MACs) with CMSIS-NN, inference every 400 ms, P_ON 0.9 (from the Phase 3 table, not yet tuned). Details and numbers are in `docs/PROGRESS.md`.

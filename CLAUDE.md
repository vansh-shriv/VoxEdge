# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

Phase 0 (environment + simulated PDM audio ingestion) and Phase 1 (FreeRTOS task skeleton with stub DSP/inference) are done; Phase 2 (real features) is next. **Read `docs/PROGRESS.md` first and update it whenever a milestone, decision, or gotcha lands.** The original design is in `voxedge-spec-simulator.md`. Git remote: https://github.com/vansh-shriv/VoxEdge.git (branch `main`).

## Commands (Git Bash on Windows)

- Main firmware (FreeRTOS): `bash tools/run_phase1.sh` builds `firmware/`, runs headless Renode on `burst_3s`, and validates `build/uart0.log`. Artifacts go to `build/` (`uart0.log`, `renode.out`).
- Phase 0 bare-metal capture regression: `bash tools/run_phase0.sh` (builds `firmware/phase0`, checks UART samples equal the source PCM).
- Build only: `cd firmware && mingw32-make -B` (`firmware/phase0` has its own Makefile). The Arm GNU Toolchain is not on PATH; the Makefile's `TOOLCHAIN` variable points at its `bin/`.
- Run Renode by hand from the repo root: `Renode.exe --disable-xwt --plain --console -e '$pcm=@sim/wav_corpus/synthetic/<file>.s16le.pcm; include @sim/boot.resc' < /dev/null`. `boot.resc` takes `$elf`, `$pcm`, `$uartlog`, `$runtime`, loads `sim/platform.repl`, and sets `cpu PerformanceInMips 64`.
- Generate test signals: `python tools/make_test_wav.py` (1 kHz ramp tone), `python tools/make_burst_wav.py` (silence/tone/silence).
- After `git clone`, run `git submodule update --init` (FreeRTOS-Kernel V11.1.0 in `third_party/`).
- Renode input is raw s16le PCM (`pdm SetInputFile`), not WAV. In `.resc` files the UART log path must be absolute and quoted (`$ORIGIN` does not expand); `boot.resc` hardcodes `D:/EmbeddedProjects/Voxedge/build/uart0.log`.

## Project

VoxEdge is an on-device wake-word (keyword spotting) audio pipeline that runs **entirely under Renode**. There is no physical board or microphone. Renode executes the real compiled ARM binary, and only the microphone is simulated, by playing back WAV files.

- Target: nRF52840 (Arduino Nano 33 BLE Sense) under Renode. Renode's simulated PDM peripheral plays WAV files as mic input at 16 kHz. Renode's `micro_speech` demo for this board is the reference to build from.
- Fallback if the PDM model has gaps: a custom Python Renode peripheral (memory-mapped "sample ready" and data registers, fed from a WAV on a timer). Try the built-in PDM first and document which path was used.

## Architecture (from the spec)

Signal path: WAV → Renode PDM playback → PDM data-ready ISR → ring buffer (double-buffer pattern) → FreeRTOS tasks.

Tasks and priorities (highest to lowest): ISR > Capture/Framer > DSP > Inference > Telemetry.
- ISR does the minimum (hand off the pointer, signal, return) and sends to the Capture task via `xStreamBufferSendFromISR`.
- DSP task: 30 ms window / 10 ms hop at 16 kHz, pre-emphasis, Hamming window, CMSIS-DSP FFT, mel filterbank, log-mel or MFCC.
- Inference task: int8 TFLite-Micro keyword-spotting model (DS-CNN or similar) with a static tensor arena.
- Decision logic (threshold, debounce) then toggles a GPIO that Renode watches or logs. Telemetry task reports UART stats plus heap/stack watermarks.

Planned layout: `firmware/` (C, `src/dsp`, `src/model`, `src/tasks`), `ml/` (train/quantize/eval in Python), `sim/` (`platform.repl`, `boot.resc`, `wav_corpus/`, `robot/` Robot Framework suites), `tools/`, `tests/unit/` (host-run), `docs/`, `.github/workflows/ci.yml`.

## Constraints that must hold across changes

- **Correctness cross-checks are mandatory before trusting end-to-end results**: on-device CMSIS-DSP features must match the Python/librosa reference on identical samples (§4.2), and on-device TFLite-Micro int8 output must match the Python quantized model on identical feature vectors (§4.3).
- **Robustness requirement**: the capture task must never miss a PDM buffer handoff even when DSP/inference is stalled. Overruns must be detected, reported, and recovered from without data corruption. Test with a debug build that injects a busy-loop, and with pathological WAVs (clipped, silence, max-amplitude white noise).
- **Honest metrics**:
  - Latency is reported in *simulated time* or CPU cycles from the emulated cycle counter, never wall-clock.
  - Real-time margin means cycles per DSP frame or inference call relative to the budget of one 10 ms hop.
  - **Power/current is not measured.** Docs and README must say so explicitly. Do not invent power numbers.
  - Sleep-mode (WFI) logic is optional (Option A: implement it and verify via Renode's trace; Option B: drop it and say so).
- Evaluation metrics: hit rate (clean and noisy positives) and false-accepts per hour of negative audio. The spec calls for 50+ clean positives, 50+ noisy positives, and 30+ min of negatives, all versioned and re-run in CI.

## Open decisions (spec §8)

Not yet resolved: the Renode PDM model's completeness for WAV playback, the keyword (Speech Commands word vs custom-recorded, custom preferred), and log-mel vs MFCC features. Check the repo and docs for a recorded decision before assuming one.

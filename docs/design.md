# VoxEdge design notes

This is the short design reference the spec's repo layout (§6) asks for. It states the scope and
architecture decisions once, precisely; `docs/PROGRESS.md` has the full narrative (every phase's
reasoning, results, and gotchas) and `voxedge-spec-simulator.md` is the original brief.

## Scope note

**This is a simulator-only project.** There is no physical nRF52840 board and no physical
microphone anywhere in this project. Renode emulates the nRF52840 and its PDM (microphone)
peripheral; the "microphone" is a WAV/PCM file played into that emulated peripheral. Everything
downstream of the PDM interrupt — the FreeRTOS task architecture, the DSP feature pipeline, the
quantised model, the watchdog, the decision logic — is the real firmware Renode executes
instruction-by-instruction; none of it is mocked or stubbed.

**Power and current draw are not measured, and no number is reported for them.** There is no
meaningful way to measure power from a simulated microphone with no physical board, and estimating
one would be dishonest. The firmware's idle task does execute `WFI` between interrupts — verified
via the emulated instruction-count trace showing the core otherwise idle except during real work —
which is the behaviour a power-aware build would rely on, but that is as far as this project goes on
power. This project's scope is DSP correctness, RTOS scheduling correctness, on-device inference
correctness, and detection accuracy/robustness under a simulated microphone input.

**All cycle/latency numbers are emulated instruction counts, not hardware cycle measurements.**
Renode has no DWT (cycle-counter) peripheral model; `sim/platform.repl` serves the `DWT_CYCCNT`
register from Renode's own executed-instruction counter, at an assumed 64 MIPS / 1
instruction-per-cycle (`cpu PerformanceInMips 64` in `sim/boot.resc`). Real silicon has flash wait
states, load-use stalls, and multi-cycle FPU operations that this does not model, so every cycle
figure in this project (feature-extraction cost, inference cost, CPU load) is a lower bound on real
hardware time, not a measurement of it.

## Architecture

```
 PCM file (host) → Renode PDM peripheral → PDM ISR (double buffer) → FreeRTOS tasks
```

Task priorities (highest to lowest): ISR > Capture (5) > DSP (4) > Inference (3) > Telemetry (1) >
idle (`WFI`). This ordering is the load-bearing design decision of the whole pipeline:

- **Capture** sits above DSP and inference, so neither can ever block it. The PDM ISR hands one
  10 ms hop to a FreeRTOS stream buffer per interrupt; if capture can't keep up (which nothing below
  it in priority can cause), the ISR drops the whole hop and counts an overrun rather than writing a
  partial one.
- **DSP** owns a ring buffer of the last 98 (980 ms) log-mel feature vectors, already normalised and
  int8-quantised. Every 400 ms (`KWS_INFER_EVERY` hops) it snapshots the ring for inference — but
  only if inference isn't still busy with the previous snapshot; otherwise the trigger is skipped
  and counted. Features are never lost to a slow model; an overloaded model only lowers the
  effective inference rate.
- **Inference** runs the int8 TFLite-Micro model (CMSIS-NN kernels), converts logits to P(marvin)
  via softmax, and raises/drops a "wake" GPIO + UART event on a single threshold crossing (no
  multi-hit debounce at the 400 ms cadence — see `docs/PROGRESS.md` Phase 4 for why).
- **Telemetry**, the lowest priority, is the only steady UART writer and the *only* feeder of the
  hardware watchdog (fed once per second). That is deliberate: a stall in DSP or inference that
  never blocks will starve telemetry — including the watchdog feed — and after
  `WDT_TIMEOUT_MS - 1000` ms (telemetry's period) in the worst case, the watchdog forces a reset.
  This is the recovery mechanism for an unbounded hang in any task above telemetry; Phase 5 verifies
  it directly (`tools/run_phase5_stall.sh`).

Feature and model definitions are generated, not hand-written, so the firmware and the Python
reference/training pipeline cannot silently drift apart:

- `ml/feature_config.py` + `ml/features.py` define the log-mel features once;
  `tools/gen_dsp_tables.py` compiles them into `firmware/src/dsp/dsp_tables.{h,c}`.
- `ml/train.py` / `ml/quantize.py` produce the int8 `.tflite` models; `tools/tflite_to_c.py` embeds
  them as C arrays (`firmware/src/model/model_*.c`) along with the training normalisation constants.

## Key decisions (with the phase that made them)

- PDM path: Renode's built-in `NRF52840_PDM` model (Phase 0) — no custom peripheral was needed.
- Features: log-mel, not MFCC (Phase 2) — simpler, no on-device DCT, standard input for a small
  DS-CNN.
- Keyword: "marvin" from Speech Commands v0.02 (Phase 3) — multi-syllable and distinctive.
- Deployed model: `s` (4,083 params, 1.67 M MACs) with CMSIS-NN kernels at `-O2` (Phase 4) — `xs` is
  too weak (55% noisy hit rate), `m` costs 3.9x the compute for ~4 points of hit rate.
- Watchdog timeout 2000 ms, fed once/second by telemetry only; deliberate-stall injection is
  compile-time gated off by default (Phase 5).
- Wake threshold P(marvin) ≥ 0.9, single-hit decision, inference every 400 ms (from the Phase 3
  clip-level table; the honest streaming numbers that validate this choice are in Phase 6 /
  `docs/results.md`).

See `docs/PROGRESS.md` for the reasoning behind each and everything that didn't make this summary.

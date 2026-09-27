# VoxEdge results

This is the results summary the spec's repo layout (§6) asks for. It is a compact index into
`docs/PROGRESS.md`, which has the full context, methodology, and caveats for every number below —
read that file before citing anything here out of context.

## Model (Phase 3, clip-level — each 1 s clip scored in isolation, keyword centred)

Trained on Speech Commands v0.02, keyword "marvin", features identical to the firmware
(`ml/features.py`, cross-checked in Phase 2). Test set: 195 marvin clips (never trained/validated
on) + all held-out unknown-word clips + silence, each in a clean and a 10 dB-SNR noisy version.

| model | params | MACs | int8 size | hit rate clean/noisy | 3-class acc clean/noisy |
|---|---|---|---|---|---|
| xs | 1,811 | 0.72 M | 9.6 KB | 72.3 / 54.9 % | 98.10 / 97.85 % |
| **s** (deployed) | 4,083 | 1.67 M | 15.6 KB | 87.7 / 84.6 % | 98.60 / 98.05 % |
| m | 14,739 | 6.43 M | 34.0 KB | 91.3 / 89.2 % | 99.18 / 98.67 % |

Full threshold sweeps: `ml/artifacts/marvin_results_{float,int8}.json`.

## On-device inference (Phase 4)

Deployed model `s`, CMSIS-NN int8 kernels, `-O2`. Parity against the Python int8 TFLite
interpreter, fed the device's own quantised input tensor: bit-exact for reference kernels (all
sizes); CMSIS-NN differs by at most 1 LSB in under 1% of inferences (checker threshold).

| model | reference kernels | CMSIS-NN | speed-up |
|---|---|---|---|
| xs | 89.97 M instr (1,406 ms) | 7.10 M instr (111.0 ms) | 12.7x |
| **s** | 199.49 M instr (3,117 ms) | 10.46 M instr (163.4 ms, `-O2`) | 19.1x |
| m | 722.56 M instr (11,290 ms) | 33.04 M instr (516.2 ms) | 21.9x |

(Instruction counts from Renode's DWT shim, assumed 64 MIPS / 1 IPC — a lower bound on real-hardware
cycles; see the caveat in `docs/PROGRESS.md` Phase 2/4.) Deployed pipeline: ≈46% of a 64 MHz core,
129.7 KB flash, 136 KB RAM (64 KB TFLite-Micro arena, 48 KB FreeRTOS heap).

## Robustness (Phase 5)

| test | result |
|---|---|
| 600 ms stall, DSP task | 1 boot, 0 PDM overruns, backlog counted (`dspdrop`), resumes cleanly |
| 600 ms stall, inference task | 1 boot, 0 PDM overruns, backlog counted (`skipped`), resumes cleanly |
| unbounded stall, either task | watchdog resets the system (2nd boot banner); 0 overruns pre-reset |
| pathological audio (silence/clipped/max-noise/mixed) | no crash/hang; P(keyword) stays in valid range |
| 4 min long run, concatenated negative audio | 0 overruns/drops; every stack/heap watermark settles and holds flat |

## Streaming evaluation (Phase 6 — spec §4.1/§4.5)

Deployed firmware (`s`, CMSIS-NN, `-O2`, inference every 400 ms, wake at P(marvin) ≥ 0.9) run
against continuous streams built from the Speech Commands *test split only*
(`tools/make_eval_streams.py`, `tools/run_phase6_eval.sh`).

| stream | content | result |
|---|---|---|
| positive, clean | 80 marvin clips, 1 s silence gaps | 81.2% hit rate (65/80) |
| positive, noisy | same clips + background noise, 5 dB SNR | 61.3% hit rate (49/80) |
| negative | 30 min of unknown words + background noise | 2.00 false accepts/hour (1 event in 30 min) |

This is the honest streaming number, as distinct from the Phase 3 clip-level table above: real
continuous audio, the actual 400 ms inference cadence and 980 ms ring window, and the deployed
threshold — not an idealised 1 s window with the word centred.

## What was not measured

**Power/current draw.** There is no physical board and no meaningful way to measure it from a
simulated microphone; inventing a number would be dishonest. This project targets DSP correctness,
RTOS scheduling, on-device inference correctness, and detection accuracy/robustness under a
simulated microphone input.

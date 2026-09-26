# VoxEdge progress log

Newest entries at the bottom of each phase. Update this file whenever a milestone or decision lands.

## Phase 0 — Environment + simulated audio ingestion

**Status: functionally complete (2026-09-26).** Exit criterion from the spec is met: firmware ISR fires from Renode's emulated PDM, samples are dumped over UART, and they match the source audio bit-for-bit.

### Environment (Windows 11)
| Tool | Version / location | Installed via |
|---|---|---|
| Renode | 1.16.0.6726, `C:\Program Files\Renode` | `winget install Renode.Renode` |
| Arm GNU Toolchain | 12.2.MPACBTI-Rel1 (gcc 12.2.1), `C:\Program Files (x86)\Arm GNU Toolchain arm-none-eabi\12.2 mpacbti-rel1\bin` | `winget install Arm.ArmGnuToolchain` (not on PATH; Makefile references it via `TOOLCHAIN`) |
| make | `mingw32-make` (`C:\MinGW\bin`) | pre-existing |
| Python | 3.12 (conda env `tf_env`) | pre-existing |

### Decisions
- **PDM path: built-in Renode model** (spec §2 / open decision 1). `NRF52840_PDM` exists in `platforms/cpus/nrf52840.repl` at 0x4001D000, IRQ 29, and is fed with `pdm SetInputFile <raw s16le pcm>`. No custom Python peripheral needed so far. Renode's own `micro_speech` test uses the same mechanism.
- Platform: `platforms/boards/arduino_nano_33_ble.repl` (stock, no custom `.repl` yet).
- Input format is **raw s16le PCM at 16 kHz**, not WAV. `tools/make_test_wav.py` emits both.
- Phase 0 firmware is bare-metal (no RTOS, no CMSIS); FreeRTOS arrives in Phase 1. Toolchain flags already target Cortex-M4F hard-float.

### Results
- Test signal: 1 s, 1 kHz tone with amplitude ramp (`sim/wav_corpus/synthetic/tone1k_1s.*`).
- 100 x 160-sample frames captured (10 ms hop), sequence numbers contiguous, firmware overrun count 0.
- `tools/validate_capture.py`: 16000/16000 samples identical to source at offset 0 (no gain applied by the model despite GAINL/GAINR writes).
- Footprint: 832 B flash, 1324 B RAM.

### How to reproduce
`bash tools/run_phase0.sh` (builds, runs headless Renode, validates). Artifacts land in `build/` (`uart0.log`, `renode.out`).

### Gotchas found
- Renode 1.16 hangs with `--console` alone under a non-interactive shell; use `--plain --console --disable-xwt`, `-e "...; quit"` (the script ends with `quit`), and redirect stdin from `/dev/null`.
- `CreateFileBackend` needs an **absolute, quoted** path, and `$ORIGIN` does not expand inside `@...`. `sim/boot.resc` hardcodes `D:/EmbeddedProjects/Voxedge/build/uart0.log`, so it must change if the repo moves. `build/` must exist first.
- Paths with spaces break `.resc` tokenization unless quoted. The repo was originally under `D:\Embedded Projects`; it now lives at `D:\EmbeddedProjects\Voxedge` (space removed).
- The link script marks `.bss` as `NOLOAD`; without it Renode logs a bogus flash-resident block.
- Renode logs `pdm: Unhandled write to offset 0x544 ... PORT/CONNECT` (PSEL.DIN) and similar for other PSEL fields. Cosmetic; the model ignores pin selection.

### Not yet verified / open
- Real-time behavior: the model delivers samples at Renode's virtual PDM rate. Confirmed 100 frames in the run but the actual sample-rate timing against virtual time is not measured yet (needed for Phase 5 latency numbers).
- Cycle counter (DWT) availability under Renode, needed for CPU-load metrics.
- The UART dump is synchronous and hex-encoded; fine for Phase 0 but will be replaced by the telemetry task.
- Repo initialised and pushed to https://github.com/vansh-shriv/VoxEdge.git (branch `main`).

## Phase 1 — FreeRTOS task skeleton

**Status: functionally complete (2026-09-26).** `bash tools/run_phase1.sh` builds, runs headless Renode on `burst_3s` (1 s silence, 1 s 1 kHz tone, 1 s silence), and all 13 checks in `tools/validate_phase1.py` pass.

### What was built (`firmware/`, spec §6 layout; `firmware/phase0/` kept as the bare-metal reference)
- FreeRTOS-Kernel V11.1.0 as a git submodule (`third_party/FreeRTOS-Kernel`), `ARM_CM4F` port, `heap_4`, 1 kHz tick, 64 MHz clock assumed in `FreeRTOSConfig.h`.
- Data path: PDM ISR -> stream buffer (8 hops, trigger = 1 hop) -> **capture** (prio 5) builds 30 ms windows on a 10 ms hop -> queue (depth 2) -> **dsp** (prio 4, stub: mean-square energy + threshold VAD) -> queue (depth 4) -> **inference** (prio 3, stub score + threshold/debounce, drives GPIO P0.24 = `led_red`) -> event queue -> **telemetry** (prio 1, UART `E`/`T` lines).
- ISR runs at the highest FromISR-safe priority (5<<5), copies one finished 320 B hop into the stream buffer, and drops the whole hop (counted in `pdm_overruns`) if there is no room, so the stream never holds a partial hop.
- Every queue drop is counted (`dspdrop`, `infdrop`, `evtdrop`). Idle hook executes `WFI` (spec §3.5 Option A; verification against the Renode execution trace still to do).
- Stack overflow (check level 2), malloc failure and `configASSERT` all print `FATAL ...` and halt.
- Sim: `sim/platform.repl` overrides the stock board with `nvic.systickFrequency: 64000000`. `boot.resc` sets `cpu PerformanceInMips 64`. `boot.resc` now defaults to the Phase 1 ELF and `burst_3s` input, and `run_phase0.sh` overrides them.

### Results
- Wake-on at hop 102 (tone starts at hop 100), wake-off at hop 204 (tone ends at hop 200). The 2-hop lag is the 30 ms window; the off lag also includes 3-frame debounce.
- 326 PDM frames = 326 hops = 324 windows/inferences; zero overruns and zero drops.
- Footprint: 10.3 KB flash, 44.3 KB RAM (40 KB is the FreeRTOS heap; 9.3 KB still free after tasks/queues). Stack high-water marks: about 213–217 of 256 words free per task, so 256 words is generous and can shrink later.

### Gotchas found
- **Renode SysTick startup skew:** `xTickCount` stays at 0 for about 262 ms after the scheduler starts (2^24 counts / 64 MHz), because Renode's SysTick model does not reset its current value when firmware writes it. Ticks then run at exactly 1000/s. Consequence: **use PDM hop sequence numbers (audio time), not ticks, for latency numbers**. Tick timestamps are offset by about 261 ms relative to audio time.
- Mixed positional and designated initialisers in the vector table silently overwrote entries. All entries are now designated (`[n] = ...`) and `-Wno-override-init` is set for the intentional default-fill.
- Long multi-file heredocs in one Bash call failed to parse in this shell. Write files individually.
- Renode still logs harmless `Unhandled write` warnings for PSEL registers (uart0 0x50C, pdm 0x540/0x544).

### Not yet verified / open
- Instruction throughput: `cpu PerformanceInMips 64` is an assumption (about 1 instruction per cycle at 64 MHz), not a measurement. It affects every real-time-margin claim in Phase 5, so state it wherever CPU-load numbers are reported.
- DWT cycle counter under Renode is still untested.
- Stub DSP/inference are placeholders (Phase 2/4). The final task priorities and queue depths are provisional until real per-frame costs are known.
- Overrun/overload behavior is not yet exercised (Phase 5).

## Phase 2 — real feature extraction

**Status: functionally complete (2026-09-26).** `bash tools/run_phase2.sh` regenerates tables, builds with `DUMP_FEATURES=1`, runs Renode on `features_2s`, and cross-checks every on-device log-mel vector against the Python reference.

### Decisions
- **Log-mel, not MFCC** (spec open decision 3): simpler, no DCT on-device, and the usual input for small DS-CNN keyword-spotting models.
- Parameters (single source of truth `ml/feature_config.py`): 16 kHz, 480-sample (30 ms) window, 160 hop, 512-pt FFT, pre-emphasis 0.97 (window-local, `y[0] = x[0]`), symmetric Hamming, 40 HTK-mel filters 20 Hz–8 kHz with no area normalisation, `log(mel + 1.0)` on raw int16 units (floor = 1 LSB²).
- `tools/gen_dsp_tables.py` generates `firmware/src/dsp/dsp_tables.{h,c}` (config `#define`s, Hamming window, sparse mel filterbank: 40 filters, 493 weights) from the Python reference, so the firmware and reference can't drift. **Regenerate after touching `ml/feature_config.py` or `ml/features.py`** (`run_phase2.sh` does it).
- Reference (`ml/features.py`) is float64 numpy FFT plus `librosa.filters.mel` and `librosa.feature.melspectrogram(S=power)`. Window `k` covers hops k-2..k, so the reference index equals the firmware `seq` (first window is 2).
- Firmware (`firmware/src/dsp/features.c`): float32 `arm_rfft_fast_f32` from CMSIS-DSP (submodules `third_party/CMSIS-DSP` + `third_party/CMSIS_6` for core headers), only the needed sources compiled (see `firmware/Makefile`). Calls `arm_rfft_fast_init_512_f32` directly, because the generic init pulled every FFT size's tables (99 KB flash vs 24 KB now).
- Debug path: `DUMP_FEATURES=1` makes inference forward each feature vector to telemetry through a queue set (event queue + dump queue); telemetry prints `F <seq> <40 x float32 hex>`. Off (0) in normal builds.

### Results (`features_2s`: silence, chirp+noise, hard-clipped sine, sigma=3000 white noise)
- 198 reference windows, all present on device, no duplicates, zero overruns/drops (including the dump path).
- Log-mel values span 0.000–30.924. **Max abs diff 1.1e-4**, mean 2e-6, p99 2e-5. Silence windows match exactly. Pass tolerance is 0.02 (about 200x margin; tighten if a later change needs it).
- `features_compute` costs **avg 40.4 k / max 40.7 k instructions per window = 6.3 % of one 10 ms hop at 64 MHz** (budget 640 k). Whole pipeline (capture + DSP + stub inference + kernel, dump off): about 6.2 M instructions per virtual second, roughly 10 % of a 64 MHz core. The core is halted in idle WFI the rest of the time, which is the spec's §3.5 Option A evidence.
- Footprint (dump off): 24.4 KB flash, 50 KB RAM (40 KB is the FreeRTOS heap; about 28.7 KB free). DSP task stack high-water 166 of 256 words free.

### Gotchas / caveats
- **Renode has no DWT.** Reads of 0xE0001004 hit "non existing peripheral" and return 0. `sim/platform.repl` now has a Python peripheral at 0xE0001000 that serves `CYCCNT` from `ExecutedInstructions`. With `cpu PerformanceInMips 64` that is **instructions, treated as cycles (1 IPC)**. It ignores flash wait states, FPU/multiplier latency and bus stalls, so every cycle figure is a lower bound; real-time-margin claims must say so. The firmware DWT code is unchanged and works on real hardware.
- Python-peripheral scripts get `self.GetMachine()` (not `self.Machine`). A bad attribute is an unhandled exception that kills Renode.
- Renode `AddHook` Python snippets cannot see functions defined in a separate `python` block, so per-function counting through hooks did not work. The DWT shim replaced it.
- The PDM keeps producing frames after the input file ends (59 extra windows on device beyond the 198 reference windows). The cross-check ignores them; their content is unverified.
- Heredocs containing `\` line continuations through `python - <<PY` corrupted the Makefile. Write Makefiles with the Write tool.

### Not yet verified / open
- Only synthetic signals so far. No real speech, so no statement about feature quality for KWS (Phase 3 data).
- `float32` vs `float64` agreement is excellent on these signals. A worst case such as a strong low-frequency tone plus very quiet high bands has not been tried.
- 1 IPC and 64 MIPS remain assumptions (see above).
- The stub inference score still comes from raw energy, not the log-mel vector.

## Phase 3 — model training (off-device)

**Status: complete (2026-09-27).** Three DS-CNN sizes trained on the exact on-device features, quantised to full int8, and compared float vs int8. Run order: `python ml/prepare_data.py`, `python ml/train.py [v ...]`, `python ml/quantize.py [v ...]` (env: `tf_env`, TF 2.21 / Keras 3.15; see `ml/requirements.txt`).

### Decisions
- **Keyword: "marvin"** from Speech Commands v0.02 (spec open decision 2; user chose a Speech Commands word, I picked marvin because it is multi-syllable and distinctive). Change `KEYWORD` in `ml/model_config.py` and re-run to switch.
- Classes: silence / unknown (the other 34 words) / marvin. Input is the 98x40 log-mel patch of a 1 s clip, computed by the same maths as the firmware; `ml/data.py:logmel_batch` (vectorised) matches the librosa-based `ml/features.py` to 9.5e-7, and `features.py` matches the firmware to 1.1e-4 (Phase 2).
- Normalisation `(x - 15.1394) / 5.2580` (train mean/std, `ml/artifacts/marvin_norm.json`) is applied outside the model. The firmware will do one affine op before int8 quantisation.
- Architecture (`ml/model.py`): strided 10x4 conv front end (98x40 -> 25x20), N x (3x3 depthwise + 1x1 pointwise), global average pool, dense logits. Only CONV_2D, DEPTHWISE_CONV_2D, MEAN, FULLY_CONNECTED remain after int8 conversion (BN folds into convs; softmax is applied outside, on logits). All have TFLite-Micro int8 kernels.
- Model sizes were chosen from the Phase 2 cost data: a stock-size DS-CNN (~18 M MACs) would need seconds per inference on an M4 without CMSIS-NN. Hence three small variants to measure the tradeoff the spec asks for.

### Data (`ml/prepare_data.py`, cache at `D:\EmbeddedProjects\datasets\kws_marvin_features.npz`, 858 MB, not in git)
- Dataset: `speech_commands_v0.02.tar.gz` (2.43 GB) in `D:\EmbeddedProjects\datasets`, outside the repo. **`download.tensorflow.org` failed TLS verification here (certificate name mismatch), so it was fetched from the same object on Google's storage host, `storage.googleapis.com/download.tensorflow.org/data/...`; verification was not bypassed.** No published checksum was found; `gzip -t` passed.
- Splits: the dataset's own `validation_list.txt` / `testing_list.txt` (speaker-disjoint). marvin clips: 1710 train / 195 val / 195 test. Unknown words: 83133 / 9786 / 10810.
- Train set (29,340 clips): each marvin clip x4 (original + 3 augmented: shift +-150 ms, gain 0.5-1.5x, background noise 5-30 dB SNR with p=0.8), 20,000 randomly sampled unknown-word clips (x1, noise p=0.5), 2,500 silence clips. Background-noise files are split 80/20 in time, so val/test noise is never seen in training.
- Test: 195 marvin + all 10,810 unknown + 400 silence, in a clean version and a noisy version (held-out noise at 10 dB SNR).

### Results (int8 = what will be deployed; test set, argmax decision unless noted)
| variant | params | MACs | int8 .tflite | hit clean / noisy (float) | hit clean / noisy (int8) | 3-class acc clean / noisy (int8) | float-int8 agreement |
|---|---|---|---|---|---|---|---|
| xs (16ch, 2 blocks) | 1,811 | 0.72 M | 9.6 KB | 75.9 / 57.4 % | 72.3 / 54.9 % | 98.10 / 97.85 % | 99.61 % |
| s (24ch, 3 blocks) | 4,083 | 1.67 M | 15.6 KB | 89.2 / 87.2 % | 87.7 / 84.6 % | 98.60 / 98.05 % | 99.74 % |
| m (48ch, 4 blocks) | 14,739 | 6.43 M | 34.0 KB | 91.8 / 89.7 % | 91.3 / 89.2 % | 99.18 / 98.67 % | 99.88 % |

Operating points (int8, clip-level false accepts per hour of 1 s clips): `m` at p(marvin) >= 0.9 gives 87.2 % / 84.1 % hit (clean/noisy) at 1.0 / 3.5 FA/h; full tables are in `ml/artifacts/marvin_results_{float,int8}.json`. Quantisation costs 0.5-3.6 points of hit rate, most for the smallest model.
- **Choice for Phase 4: `s`** (1.67 M MACs, 15.6 KB). `xs` is clearly too weak (55 % noisy hit rate). `m` buys about 4 points of hit rate for 3.9x the MACs. Phase 4 will measure real on-device cost of all three so the latency/accuracy table is complete, and the final pick can change if `s` misses its CPU budget.
- Input quant (all variants): scale 0.023016, zero-point -3. Output (logits) quant: xs 0.1813/45, s 0.2119/30, m 0.2169/24.

### Caveats (read before quoting numbers)
- **Only 195 marvin test clips**: a hit rate has roughly +-4 points of sampling uncertainty (95 %), so `s` vs `m` differences are not clearly significant.
- **False-accept-per-hour is clip-level** (fraction of non-keyword test clips that fire, x3600). Test negatives are 1 s clips of the other 34 words, which is harder than typical background audio but is not a streaming measurement. The real streaming figure (hours of concatenated negatives through Renode) is Phase 6.
- The model sees a 1 s window with the word roughly centred (dataset convention plus +-150 ms shift augmentation). Streaming detection will slide this window every hop, so behaviour at other alignments is untested until Phase 4/6. Threshold and debounce are not tuned yet.
- Unknown-word training uses 20,000 of 83,133 clips; more negatives may reduce false accepts.
- Test data was used for reporting only. The best-validation-accuracy checkpoint was kept per variant.

## Next: Phase 4 — on-device inference (TFLite-Micro)
Integrate TFLite-Micro (submodule, static tensor arena) with `marvin_s_int8.tflite` as a C array; keep a ring of the last 98 feature vectors; run inference every N hops; quantise input with the stored scale/zero-point; measure cycles per inference for xs/s/m; parity check against the Python int8 interpreter on the same features (spec §4.3). Open: TFLM build flags on this toolchain (reference kernels vs CMSIS-NN), arena size, inference cadence vs CPU budget.

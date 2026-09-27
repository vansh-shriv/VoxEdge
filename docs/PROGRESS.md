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
- **Object-sharing bug (found while committing; fixed, re-measurement pending)**: the Makefile helper was named `strip`, a make built-in, so `$(call strip,..)` never removed `../` and third-party objects (FreeRTOS, CMSIS-DSP/NN, TFLite-Micro) were written to `obj/third_party/`, shared by every configuration. Consequences: (a) the `-O2` experiment above reused `-Os` third-party objects, so it says nothing; (b) CMSIS-NN builds may have reused TFLM core objects built earlier for reference kernels. The core objects only differ by `-DCMSIS_NN`, which does not affect them, and the CMSIS-NN kernel objects are only compiled by cmsis builds, so the CMSIS numbers and parity results below are very probably right, but they were **not** measured from clean per-configuration trees. `tools/run_phase4_matrix.sh` re-measures the whole matrix from clean trees (output `build/phase4_matrix.log`); until it has been folded into this file, treat the CMSIS-NN rows as provisional. The reference-kernel rows were built before `KERNELS` existed and are unaffected.
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

## Phase 4 — on-device inference (TFLite-Micro)

**Status: complete (2026-09-27).** The int8 model runs on the emulated nRF52840 under TFLite-Micro, its output is verified against the Python int8 model, and the latency/accuracy tradeoff is measured for all three sizes with both kernel sets. Run: `bash tools/run_phase4.sh [xs|s|m] [runtime_s] [pcm] [make vars]` (needs `python tools/make_kws_demo.py` once for the demo stream).

### What was built
- **TFLite-Micro** (submodule `third_party/tflite-micro`, HEAD 2026-09-25) compiled by our own Makefile, not its generator: only the ~55 C++ files this model needs, `-fno-exceptions -fno-rtti`, static tensor arena, `MicroMutableOpResolver<4>` (Conv2D, DepthwiseConv2D, FullyConnected, Mean). `tools/fetch_tflm_deps.sh` downloads flatbuffers, gemmlowp, ruy and CMSIS-NN into `third_party/tflm_deps/` (git-ignored) at the exact versions TFLM pins, verifying each MD5.
- **Kernels** (`KERNELS=cmsis|ref`, default cmsis): CMSIS-NN via TFLM's own `kernels/cmsis_nn/{conv,depthwise_conv,fully_connected}.cc` (needs `-DCMSIS_NN`), or TFLM reference kernels.
- **Model embedding**: `tools/tflite_to_c.py` writes `firmware/src/model/model_{xs,s,m}.c` + `model_meta.h` (normalisation mean/std). Input/output quantisation params are read from the model at run time. Select with `MODEL=`.
- **Data path** (changed from Phases 1-3): the **DSP task owns a ring of the last 98 feature vectors, already normalised and quantised to int8** (`dsp/feature_ring.c`). Every `INFER_EVERY` hops (once the ring is full) it snapshots the ring and notifies the inference task. If inference is still running, the trigger is **skipped and counted** (`skipped`), never queued, so features are never lost and capture/DSP are never blocked. (The first design had inference own the ring, fed through a queue; a slow model would have dropped frames and silently corrupted every later input.)
- **Inference task** (prio 3, 1024-word stack): runs the model, softmax on dequantised logits, a single inference above `KWS_P_ON` = 0.90 raises wake (GPIO P0.24 + `E ... R` event), the first inference below drops it. Cost is measured with the DWT shim.
- Build system: per-configuration object dirs (`obj/<kernels><opt>-<model>-f..i..-e..-a..-q../`), link through a response file, `voxedge.elf` copied from the configuration's ELF on every build.
- Debug channel (`DUMP_INFER=1`): `L <seq> <3 int8 logits> <p_key x1000>` per inference and sampled `Q <seq> <3920 int8 hex>` input tensors.

### Parity against the Python int8 model (`tools/crosscheck_model.py`, spec 4.3)
Demo stream: 5 marvin + 5 other-word clips from the test split (never trained on), `tools/make_kws_demo.py`. Three checks:
- **A** device logits vs the Python TFLite interpreter (reference kernels, `BUILTIN_REF`) fed the *device's own* input tensor.
- **B** device input tensor vs Python quantisation of the float64 reference features (validates features, ring ordering and quantisation).
- **C** end-to-end logits/argmax vs Python from reference features.

| model | kernels | A exact | B input-tensor diffs | C argmax agree |
|---|---|---|---|---|
| xs | ref | 4/4 | 0/15,680 | pass |
| s | ref | 2/2 | 0/7,840 | pass |
| m | ref | 1/1 | 0/3,920 | pass |
| xs | CMSIS-NN | **102/103** (one logit off by 1 LSB at seq 805: device 52 vs Python 51) | 0/380,240 | 91/91 (6 near-ties) |
| s | CMSIS-NN | 62/62 | 0/227,360 | 58/58 |
| m | CMSIS-NN | 28/28 | 0/105,840 | 25/25 |
| s | CMSIS-NN, `-O2` | 77/77 | 0/286,160 | 72/72 |

Reference kernels are bit-exact but were tested on very few inferences (they take seconds each). CMSIS-NN shows one 1-LSB difference in 193 inferences. It is likely a rare requantisation rounding difference in CMSIS-NN, but that is **not proven** (the reference runs are too few to isolate it). The checker requires exactness for `KERNELS=ref` and allows at most 1 LSB in at most 1 % of inferences for `cmsis`, always printing the count.

### Latency / accuracy tradeoff (instructions per `kws_infer()`, treated as cycles; see caveat)
Re-measured from clean per-configuration object trees (`bash tools/run_phase4_matrix.sh`, log in `build/phase4_matrix.log`) after finding the build bug below; confirms the numbers first reported were correct (they matched to within simulation noise), except for `-O2`.

| model | MACs | int8 hit clean/noisy (Phase 3) | reference kernels | CMSIS-NN `-Os` | CMSIS-NN `-O2` | speed-up (`-Os`) | CMSIS-NN instr/MAC | arena used |
|---|---|---|---|---|---|---|---|---|
| xs | 0.72 M | 72 / 55 % | 89.97 M (1,406 ms) | **7.10 M (111.0 ms)** | - | 12.7x | 9.9 | 18.0 KB |
| s | 1.67 M | 88 / 85 % | 199.49 M (3,117 ms) | **12.91 M (201.6 ms)** | **10.46 M (163.4 ms)** | 15.5x | 7.7 | 27.0 KB |
| m | 6.43 M | 91 / 89 % | 722.56 M (11,290 ms) | **33.04 M (516.2 ms)** | - | 21.9x | 5.1 | 53.5 KB |

(ms = instructions / 64 MHz.) Reference kernels cost 112-125 instructions per MAC, unusable in real time. `-O2` cuts CMSIS-NN's `s` cost by 19 % (12.91 M -> 10.46 M); the first "-O2 gives no gain" reading was wrong (see the build bug below) — only `s` was re-measured under `-O2` so far.

### Operating point and load
- **Chosen and now the Makefile default: `MODEL=s`, `KERNELS=cmsis`, `OPT=-O2`, `INFER_EVERY=40` (one inference per 400 ms), `KWS_P_ON=0.9`, single hit.** At the 50 ms stress cadence `s` is overloaded (231-248 of ~310 triggers skipped depending on `-Os`/`-O2`), yet **capture and DSP were never starved: 0 overruns and 0 drops** in every run, including the 3-11 s reference-kernel inferences. That is the overload/degradation behaviour of spec 4.4, demonstrated.
- Re-measured end to end at the deployed setting: **29.6 M instr/s = 46 % of a 64 MHz core** (model 10.46 M instr / 0.4 s = 26.2 M/s + features about 4.0 M/s + kernel/idle overhead, consistent with the parts). Idle is WFI. Footprint: **129.7 KB flash, 136 KB RAM** (64 KB arena, 48 KB FreeRTOS heap) — `-O2` costs about 16 KB more flash than `-Os` (114 KB) for the 19 % instruction saving.
- Demo stream, deployed setting: wake raised for **5/5 marvin clips and 0/5 other-word clips** (rises at seq 120, 440, 720, 1000, 1320, all within 1-2 inferences of the clip start) — re-confirmed with `-O2`, same result as the earlier `-Os` run.
- Inference task stack high-water: 665 of 1024 words free, so 512 words would do.

### Gotchas found
- **Object-sharing build bug (found and fixed after the first measurement pass)**: the Makefile helper was named `strip`, which shadows a GNU Make built-in, so `$(call strip,..)` never stripped `../` and every configuration wrote third-party objects (FreeRTOS, CMSIS-DSP/NN, TFLite-Micro) to the same `obj/third_party/...` path, shared across `MODEL`/`KERNELS`/`OPT`. Renamed to `noup`. Re-measuring every row from clean per-configuration trees (`tools/run_phase4_matrix.sh`) reproduced the original xs/s/m `-Os` numbers almost exactly (parity results and cycle counts matched to within simulation noise) — those were fine because CMSIS-NN kernel objects are cmsis-only and `-DCMSIS_NN` doesn't change the shared core objects' code. The one reading that **was** wrong: "`-O2` gives no gain", because the `-O2` build had silently reused `-Os` third-party objects. Re-measured `-O2` shows a real 19 % instruction-count reduction for `s`. Lesson: a build-config bug can produce a plausible, self-consistent wrong answer instead of an error — the fix was found by suspicion of a too-convenient result, not a crash.
- **Windows command-line limit**: the link line exceeded it once CMSIS-NN was added. The tail was silently truncated and `ld` reported a bogus `crti.o` `_init` conflict plus a half path. Fixed with a linker response file (`@objs.rsp`; GNU Make 3.82 has no `$(file)`, so one `echo` per object).
- **Makefile bugs that produced false passes**: (1) `voxedge.elf` was not tied to the configuration, so a stale ELF from another `MODEL` was reused; (2) adding the response-file rule ahead of the ELF rule changed the default goal, so a bare `make` stopped linking and the Phase 1/2 scripts ran stale ELFs. Fixed with a per-configuration ELF, an always-copy phony `voxedge.elf`, and `.DEFAULT_GOAL`. Lesson: check the size/telemetry of what actually ran.
- TFLM needs `-DCMSIS_NN` when using its `cmsis_nn/` kernels (otherwise redefinition errors); `GetBuiltinCode` comes from `tensorflow/compiler/mlir/lite/schema/schema_utils.cc`; `_sbrk` is stubbed to fail so newlib `malloc` can never silently eat RAM; `.init_array` support plus empty `_init/_fini` are needed for C++ statics.
- The debug dumps (telemetry is priority 1) drop entries while a 200 ms inference runs. The feature cross-check (`run_phase2.sh`) therefore builds with `INFER_EVERY=1000000` so it measures DSP only. Normal builds are unaffected.
- `tools/run_phase1.sh` is now a pipeline-plumbing check with no wake expectations: the energy stub is gone.

### Caveats / not yet verified
- **Instructions are not cycles**: `kws_infer` numbers come from the DWT shim (`ExecutedInstructions`, assumed 64 MIPS at 1 IPC). A real M4 has flash wait states, load-use stalls and multi-cycle FPU ops, so real time is longer. CMSIS-NN's SIMD kernels may also have a different instruction-to-cycle ratio than the reference kernels, so the speed-up ratios are indicative only.
- Decision parameters (P_ON, single hit, cadence) come from the Phase 3 table, not tuning. Real hit rate and false accepts per hour on streaming audio come in Phase 6.
- 7.7 instr/MAC (`-Os`) / 6.3 instr/MAC (`-O2`, `s` only) is still high for CMSIS-NN; which layer dominates is not profiled (the 10x4 strided front-end conv is a suspect). `xs` and `m` have not been re-measured under `-O2` (not the deployed model, lower priority).
- Nothing yet skips inference during silence; a cheap energy gate could cut the load substantially.

## Next: Phase 5 — robustness and overload testing
Deliberate stalls (debug busy-loop in DSP/inference), pathological WAVs (clipped, silence, max-amplitude noise), watchdog, buffer-overrun recovery, long-run stack/heap watermarks (spec 4.4). Much of the overload behaviour is already demonstrated above; Phase 5 makes it a systematic test suite.

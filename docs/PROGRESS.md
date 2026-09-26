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

## Next: Phase 3 — model training (off-device, Python/TensorFlow)
Needs decisions: keyword (Speech Commands word vs custom recorded, spec open decision 2) and whether to train on the exact on-device features (recommended: reuse `ml/features.py`, so train and deploy see identical inputs). TensorFlow is already in the `tf_env` conda env; check versions and dataset availability before starting.

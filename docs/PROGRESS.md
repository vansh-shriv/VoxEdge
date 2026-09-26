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

## Next: Phase 1 — FreeRTOS task skeleton
Pull FreeRTOS-Kernel (Cortex-M4F port), replace the main-loop dump with ISR -> stream buffer -> capture task, stub DSP (energy/VAD) and inference, add telemetry task.

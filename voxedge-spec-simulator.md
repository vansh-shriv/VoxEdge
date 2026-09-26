# VoxEdge — On-Device Wake-Word Audio Pipeline
## Simulator-Only Specification (PRD + Technical Design + Build Roadmap)

---

## 0. Document purpose

This is the emulator-only version of VoxEdge. No microphone, no board — the entire pipeline (DMA-style audio ingestion, FreeRTOS task architecture, DSP feature extraction, quantized model inference) runs under **Renode** on your laptop, fed with pre-recorded WAV audio instead of a live MEMS mic.

This is not a stretch or a hack: Renode's own official demo set includes exactly this pattern — a simulated PDM microphone on an **Arduino Nano 33 BLE Sense (nRF52840)** feeding TensorFlow Lite Micro's `micro_speech` example, with WAV files played back as the "microphone" input for wake-word detection testing. VoxEdge follows that precedent, but with your own DSP pipeline, your own trained model, and your own RTOS task architecture, rather than using the stock demo as-is.

Target platform: **nRF52840 (Arduino Nano 33 BLE Sense)** under Renode, because Renode has first-class, maintained support for this exact chip plus a simulated PDM microphone peripheral. Using this platform saves you from having to hand-write a custom Renode peripheral just to get audio samples into the emulator.

---

## 1. Product requirements (PRD)

Same problem and goals as the hardware version:

1. Continuous audio ingestion, DMA-style, no CPU busy-waiting on the data path.
2. On-device feature extraction and a quantized neural network for keyword spotting, running with real-time margin.
3. A measured latency/accuracy tradeoff, with an honest, explicit note on what "real-time margin" means without physical timing.
4. A justified FreeRTOS task/priority architecture separating capture, DSP, inference, housekeeping.
5. Robustness: buffer overrun handling, watchdog, graceful degradation under overload — all fully testable in the emulator, in fact more easily than on hardware, since you can deterministically inject overload conditions.

**What changes because there's no hardware:** power/current draw numbers are dropped (see the honesty note in §5.4). Everything else — the real DSP math, the real quantized model, the real RTOS scheduling behavior, the real buffer-overrun edge cases — is unchanged and fully testable, because Renode executes your actual compiled ARM binary instruction-by-instruction; it is not a mock or a stub of your logic, only of the physical microphone.

---

## 2. How simulated audio input works

Renode models the nRF52840's PDM (Pulse Density Modulation) peripheral, which is what a real Nano 33 BLE Sense uses for its on-board MEMS microphone. Renode's simulated PDM peripheral can be configured to **play back a WAV file** as if it were live microphone input, sample by sample, at the correct simulated sample rate, triggering the same PDM data-ready interrupts your firmware would see on real hardware.

This means:
- Your firmware's interrupt handler, DMA-equivalent buffering, and everything downstream is **identical code** to what would run on a physical board.
- You control the test input precisely: record or source WAV clips of your wake word, of background noise, and of confusable speech, and feed each one through the identical pipeline, deterministically and repeatably — something that is actually harder to do rigorously with a live mic and a human saying words into it.
- You can also feed synthetic test signals (pure tones, noise, silence, clipped/corrupted audio) to test pipeline robustness in ways a live mic setup would struggle to reproduce on demand.

**Practical note:** if the nRF52840 PDM peripheral model in your Renode version has any gaps, the fallback is to write a small **custom Renode peripheral in Python** (Renode supports this directly) that exposes a memory-mapped "sample ready" register and a data register, and have a Python-side script push samples from a WAV file into it on a timer matching your target sample rate. This is more setup work but keeps you unblocked regardless of peripheral model completeness. Try the built-in PDM model first; only build the custom peripheral if you hit a real gap, and document which path you took.

---

## 3. System architecture

### 3.1 Simulated signal path
```
WAV file (host) --Renode PDM peripheral playback--> nRF52840 PDM peripheral (emulated)
   --PDM data-ready interrupt--> firmware ISR --> RAM ring buffer (same double-buffer
   pattern as the hardware design, just fed by the emulated peripheral instead of a
   physical I2S/PDM line)
```

Sample rate: 16 kHz, matching the PDM decimation filter's typical output on this chip (verify against the nRF52840 PDM peripheral's documented supported rates and configure Renode to match).

### 3.2 Software pipeline (FreeRTOS tasks) — unchanged from the hardware spec

```
[PDM data-ready ISR]  --xStreamBufferSendFromISR-->  [Capture/Framer Task]
                                                             |
                                                             v
                                         [DSP Task: pre-emphasis, windowing,
                                          FFT, mel filterbank, log, features]
                                                             |
                                                             v
                                         [Inference Task: TFLite-Micro int8
                                          keyword-spotting model]
                                                             |
                                                             v
                                         [Decision logic: threshold, debounce,
                                          trigger action]
                              -------------------------------------
                              |                                    |
                              v                                    v
                    [Wake action: toggle a GPIO         [Telemetry task: UART stats,
                     Renode can watch/log]                heap/stack watermarks]
```

Task priorities, unchanged: ISR (hardware) > Capture/Framer > DSP > Inference > Telemetry. The ISR does the minimum possible work (copy pointer, signal, return) — this matters just as much in simulation, because Renode will faithfully reproduce a priority-inversion bug or a missed deadline if you introduce one, which is exactly the point.

### 3.3 Feature extraction — unchanged
30 ms window / 10 ms hop at 16 kHz, pre-emphasis, Hamming window, FFT via CMSIS-DSP, mel filterbank, log-mel or MFCC features. This is pure math running on the emulated Cortex-M core; it behaves identically to real hardware because it doesn't touch any peripheral — only the *input* to this stage was simulated, not the stage itself.

### 3.4 Model — unchanged
Train a small DS-CNN or similar keyword-spotting architecture in Python/TensorFlow on Speech Commands or your own recorded keyword samples, quantize to int8, deploy via TensorFlow Lite for Microcontrollers with a static tensor arena. All of this happens on your PC regardless of hardware vs simulator — no change at all.

### 3.5 Power management — replaced

The hardware spec's sleep-mode power management (§2.5 of the original) is **dropped as a build goal**, since there is no meaningful emulated equivalent of measuring current draw, and inventing one would be dishonest. Two options, pick one and state it clearly:

- **Option A (recommended):** implement the sleep-mode logic anyway — entering a documented low-power mode between PDM buffer fills is still real firmware behavior worth writing and is still relevant code even if you can't measure its electrical effect. Report it as "implements CPU sleep between capture windows (WFI/low-power mode), verified via Renode's execution trace showing the core idle between interrupts" rather than a current number.
- **Option B:** drop sleep-mode work entirely from VoxEdge's scope and say so in the README, spending the time instead on making the DSP/inference/robustness work more thorough.

---

## 4. Test plan

### 4.1 Functional (via WAV playback)
- Record or source: 50+ clean positive (keyword) clips, 50+ noisy positive clips (keyword + background noise mixed), 30+ minutes of negative audio (other speech, silence, noise, music).
- Play each category through Renode, log detections, compute hit rate (clean, noisy) and false-accept rate (per hour of negative audio) — the same metrics as the hardware version, now with perfectly repeatable, versioned test inputs you can commit to your repo and re-run in CI on every change.

### 4.2 Cross-check DSP against Python
Same as the hardware spec: run the identical raw samples through a Python reference (librosa) and your on-device CMSIS-DSP pipeline, diff the feature vectors, and fix discrepancies before trusting live-audio results. This step is unchanged and just as important in simulation.

### 4.3 Model parity check
Confirm the on-device TFLite-Micro int8 inference produces the same output as the Python-side quantized model given the same feature vector inputs, before trusting end-to-end WAV-driven results. Log both and diff.

### 4.4 Robustness / overload testing — easier and more thorough in simulation
Because Renode gives you deterministic control over execution:
- Deliberately stall the DSP or inference task (e.g., have a debug build inject an artificial busy-loop) and confirm the capture task still never misses a PDM buffer handoff, and that the system reports and recovers from a buffer overrun rather than corrupting data — testable on-demand and repeatably, which is difficult to arrange reliably with live hardware.
- Feed pathological WAV inputs (clipped audio, silence, white noise at max amplitude) and confirm the pipeline doesn't crash, hang, or produce nonsensical detections.
- Run for a long emulated duration (Renode can run faster than real-time) feeding hours of concatenated negative audio, watching for memory leaks via stack/heap high-water marks over time.

### 4.5 Metrics to report (revised for no physical hardware)
- Detection latency, reported in **simulated time** (Renode tracks virtual time consistently, so "X ms of simulated audio to detection" is a real and meaningful number) and/or in CPU cycles via the DWT-equivalent cycle counter on the emulated core.
- Hit rate (%) and false-accept rate (per hour), from the WAV test sets — these are real, honest numbers regardless of simulation.
- CPU load: cycles spent per DSP frame and per inference call, relative to the cycle budget available in one hop period (10 ms of audio at your target clock speed) — this is a legitimate real-time margin metric even without physical timing, since it's derived from the actual instruction execution Renode performs.
- Flash/RAM footprint of the model and pipeline — real numbers, unaffected by simulation.
- Buffer overrun count under normal and deliberately-overloaded conditions.
- Explicitly state in the README: "power/current draw was not measured — this project targets DSP correctness, RTOS scheduling, and detection accuracy under a simulated microphone input, not power characterization," mirroring the same honest scoping note as SafeFlash.

---

## 5. Build roadmap (phased, simulator-only)

**Phase 0 — Environment + simulated audio ingestion (2–3 days)**
- Install Renode, confirm the nRF52840/Arduino Nano 33 BLE Sense platform boots a trivial firmware image.
- Get the PDM peripheral model playing back a WAV file and confirm your firmware's ISR fires and you can capture raw samples out to UART; validate in Python/Audacity that the samples you captured match the source WAV (this replaces the hardware spec's "record and inspect raw audio" milestone one-for-one).

**Phase 1 — FreeRTOS task skeleton (1–2 days)**
- Same as hardware spec: capture, DSP (stubbed as energy/VAD), inference (stubbed), telemetry tasks, wired with stream buffers/queues, validated end to end with the WAV-driven input in place of a live mic.

**Phase 2 — Real feature extraction (2–3 days)**
- CMSIS-DSP pre-emphasis/windowing/FFT/mel filterbank, cross-checked against the Python/librosa reference on the same WAV files (§4.2). Identical to the hardware spec.

**Phase 3 — Model training (2–3 days, off-device)**
- Train and quantize the KWS model in Python, validate accuracy against a held-out test set before deploying on-device. Identical to the hardware spec — this phase never depended on hardware in the first place.

**Phase 4 — On-device inference (2–3 days)**
- Integrate TFLite-Micro, wire in the real feature extractor, confirm parity with the Python quantized model (§4.3).

**Phase 5 — Robustness + overload testing (2–3 days)**
- Buffer overrun detection/handling, the deliberate-overload tests from §4.4, watchdog behavior. This phase is if anything more thorough than the hardware version because of Renode's determinism.

**Phase 6 — Full evaluation + CI + polish (2–3 days)**
- Assemble the WAV test corpora (positive/clean, positive/noisy, negative), run the full evaluation sweep from §4.1, produce hit-rate/false-accept tables.
- Wire unit tests (DSP cross-check, model parity) and the Renode-driven functional suite into GitHub Actions, running headlessly.
- README with architecture diagram, a spectrogram + detection-timeline plot (genuinely easy to produce well since your inputs are WAV files you already have in Python), results tables, and the explicit power-scope note from §4.5.

Total: roughly 2.5–3 weeks, similar to the hardware version, with the audio-ingestion setup (Phase 0) trading hardware/wiring debugging time for Renode/peripheral-model setup time.

---

## 6. Repo layout

```
voxedge/
├── firmware/
│   ├── src/
│   │   ├── pdm_capture.c/h     (PDM interrupt handling, ring buffer)
│   │   ├── dsp/                 (fft, mel filterbank, feature extraction)
│   │   ├── model/                (TFLite-Micro integration, generated model array)
│   │   └── tasks/                (capture, dsp, inference, telemetry)
│   └── CMakeLists.txt / Makefile
├── ml/
│   ├── train.py
│   ├── quantize.py
│   ├── eval.py                   (Python-side accuracy eval + reference feature extraction)
│   └── data/                     (dataset prep scripts, not raw audio)
├── sim/
│   ├── platform.repl             (Renode platform description, if customized)
│   ├── boot.resc                 (Renode script: load ELF, configure PDM playback, start)
│   ├── wav_corpus/                (positive-clean, positive-noisy, negative test WAVs)
│   └── robot/                    (.robot test suites for the evaluation sweep)
├── tools/
│   └── audio_dump_analyze.py     (plots waveforms/spectrograms, hit-rate reporting)
├── tests/
│   └── unit/                     (DSP cross-check tests, model parity tests, host-run)
├── docs/
│   ├── design.md                 (include the "no physical mic / no power measurement" scope note)
│   └── results.md
└── .github/workflows/ci.yml      (unit tests + headless Renode evaluation sweep)
```

---

## 7. Stretch goals (adjusted for simulator-only)

1. **Custom Renode peripheral for a synthetic two-mic array**, feeding two phase-shifted WAV streams to test beamforming logic — more setup than the hardware two-mic stretch, but fully controllable and repeatable.
2. **VAD gate** before DSP/inference — unchanged from the hardware spec, still real firmware logic worth adding and testing with the same WAV corpora.
3. **Simulated "wake" hand-off**: on detection, toggle a GPIO Renode logs, and treat that as the interface to a hypothetical next stage — you can still narrate a "post-wake" story in your design doc even without an actual radio/Wi-Fi path.
4. If you later get any board at all (even briefly, e.g., borrowed for a day), run the identical firmware image against a live mic for a short qualitative demo video — this is optional and not required for the project to be complete, but is a nice capstone if the opportunity arises.

---

## 8. Open decisions to make before Phase 0

1. Confirm your installed Renode version's nRF52840 PDM peripheral model completeness for your needs (sample rate, gain, WAV playback support) before committing — check Renode's demo repository for the `micro_speech`/Nano 33 BLE Sense example first, since it's a working reference to build from rather than starting blind.
2. Speech Commands dataset word vs a custom keyword recorded by you (into WAV files, no live-capture pipeline needed since everything is WAV-driven anyway — recording your own samples is arguably *easier* now, since you just need a phone/laptop mic to produce WAV files, not a wired-up board) — custom keyword is a stronger, more distinctive story and now has fewer hardware-related excuses not to attempt it.
3. Direct log-mel features vs full MFCC with DCT — unchanged tradeoff from the hardware spec.

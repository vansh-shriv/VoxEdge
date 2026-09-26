"""Generate the Phase 2 feature cross-check signal (2 s, 16 kHz, seeded, deterministic):

  0.0-0.3 s  digital silence            (log floor: exact zeros must match exactly)
  0.3-1.0 s  100->6000 Hz chirp + noise (broadband, sweeps across the mel bands)
  1.0-1.3 s  clipped 440 Hz sine        (full-scale, hard-clipped harmonics)
  1.3-2.0 s  white noise, sigma=3000    (high level, all bins populated)
"""
import wave, pathlib, sys
import numpy as np

out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "sim/wav_corpus/synthetic")
out.mkdir(parents=True, exist_ok=True)
fs = 16000
rng = np.random.default_rng(20260926)
x = np.zeros(2 * fs)

t = np.arange(int(0.7 * fs)) / fs
chirp = np.sin(2 * np.pi * (100 * t + 0.5 * (6000 - 100) / 0.7 * t ** 2))
x[int(0.3 * fs):fs] = 0.6 * 32767 * chirp + rng.normal(0, 0.02 * 32767, len(t))

t = np.arange(int(0.3 * fs)) / fs
x[fs:int(1.3 * fs)] = np.clip(3.0 * 32767 * np.sin(2 * np.pi * 440 * t), -32768, 32767)

x[int(1.3 * fs):] = rng.normal(0, 3000, len(x) - int(1.3 * fs))

x = np.clip(np.round(x), -32768, 32767).astype("<i2")
with wave.open(str(out / "features_2s.wav"), "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(fs); w.writeframes(x.tobytes())
(out / "features_2s.s16le.pcm").write_bytes(x.tobytes())
print("wrote", out / "features_2s.*", len(x), "samples")

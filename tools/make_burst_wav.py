"""Generate the Phase 1 pipeline test signal: 1 s silence, 1 s 1 kHz tone, 1 s silence (3 s total).

Hop k covers samples [160k, 160k+160), so the tone occupies hops 100..199 (of 300).
Writes WAV + raw s16le PCM (Renode's `pdm SetInputFile` takes raw PCM).
"""
import wave, pathlib, sys
import numpy as np

out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "sim/wav_corpus/synthetic")
out.mkdir(parents=True, exist_ok=True)
fs = 16000
x = np.zeros(3 * fs, dtype="<i2")
t = np.arange(fs) / fs
x[fs:2 * fs] = (0.5 * np.sin(2 * np.pi * 1000 * t) * 32767).astype("<i2")
with wave.open(str(out / "burst_3s.wav"), "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(fs); w.writeframes(x.tobytes())
(out / "burst_3s.s16le.pcm").write_bytes(x.tobytes())
print("wrote", out / "burst_3s.*", len(x), "samples")

"""Generate a deterministic 1 s, 16 kHz mono test signal as WAV + raw s16le PCM.

Renode's PDM model consumes raw s16le PCM (`pdm SetInputFile`), so we emit both.
The signal is a ramp-modulated 1 kHz tone so that dropped/duplicated/shifted samples are obvious.
"""
import wave, numpy as np, pathlib, sys

out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "sim/wav_corpus/synthetic")
out.mkdir(parents=True, exist_ok=True)
fs = 16000
t = np.arange(fs) / fs
x = (0.5 * np.sin(2 * np.pi * 1000 * t) * np.linspace(0.1, 1.0, fs) * 32767).astype("<i2")
with wave.open(str(out / "tone1k_1s.wav"), "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(fs); w.writeframes(x.tobytes())
(out / "tone1k_1s.s16le.pcm").write_bytes(x.tobytes())
print("wrote", out, len(x), "samples")

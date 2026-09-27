"""Generate pathological audio for Phase 5 robustness testing (spec 4.4): digital silence,
full-scale hard-clipped tones, and max-amplitude white noise. Deterministic (seeded).

python tools/make_pathological_wav.py
Writes sim/wav_corpus/pathological/{silence,clipped,noise_max,mixed}.{wav,s16le.pcm}, each 5 s / 16 kHz.
"""
import pathlib, wave
import numpy as np

out = pathlib.Path("sim/wav_corpus/pathological")
out.mkdir(parents=True, exist_ok=True)
fs = 16000
rng = np.random.default_rng(20260927)


def write(name, x):
    x = np.clip(np.round(x), -32768, 32767).astype("<i2")
    with wave.open(str(out / f"{name}.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(fs); w.writeframes(x.tobytes())
    (out / f"{name}.s16le.pcm").write_bytes(x.tobytes())
    print(f"wrote {name}: {len(x)} samples, min={x.min()} max={x.max()}")


n = 5 * fs
write("silence", np.zeros(n))                                   # exact digital silence throughout

t = np.arange(n) / fs
write("clipped", np.clip(4.0 * 32767 * np.sin(2 * np.pi * 300 * t), -32768, 32767))  # 4x overdrive, hard square-ish

write("noise_max", rng.uniform(-32768, 32767, n))                # full-scale white noise, worst case for every mel bin

# Alternating pathology every 1 s: silence / clipped / max noise / silence / clipped (edge transitions
# are the interesting part: an abrupt jump from full-scale noise to digital silence and back).
seg = fs
mixed = np.concatenate([
    np.zeros(seg),
    np.clip(4.0 * 32767 * np.sin(2 * np.pi * 300 * t[:seg]), -32768, 32767),
    rng.uniform(-32768, 32767, seg),
    np.zeros(seg),
    np.clip(4.0 * 32767 * np.sin(2 * np.pi * 300 * t[:seg]), -32768, 32767),
])
write("mixed", mixed)

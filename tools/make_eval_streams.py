"""Build the Phase 6 streaming evaluation corpora (spec 4.1): continuous audio streams fed through
the real running firmware, as opposed to the isolated 1 s clips used for the Phase 3 model table.
All clips come from the Speech Commands *test* split only (never trained or validated on).

python tools/make_eval_streams.py
Writes sim/wav_corpus/eval/{positive_clean,positive_noisy,negative}.{wav,s16le.pcm} + manifest .json
for the two positive streams (clip start/end sample -> for hit-rate scoring).

  positive_clean : 80 marvin test clips, 1 s gap of digital silence between each (spec: 50+ clean).
  positive_noisy : the same 80 clips mixed with held-out background noise at 5 dB SNR, same gaps
                    (spec: 50+ noisy; 5 dB is harder than the 10 dB used for the Phase 3 test set).
  negative       : 30 minutes of unknown-word clips and held-out background noise, interleaved,
                    covering "other speech, silence, noise" per spec 4.1 (no music in this dataset).
"""
import json, pathlib, sys, wave
import numpy as np
import soundfile as sf

root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "ml"))
import data
from model_config import DATASET_DIR, CACHE, CLIP_SAMPLES

SEED = 20260928
N_POS = 80
NOISY_SNR_DB = 5.0
NEG_MINUTES = 30
GAP_S = 1.0
FS = 16000

out = root / "sim" / "wav_corpus" / "eval"
out.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(SEED)


def write(name, x, manifest=None):
    x = np.clip(np.round(x), -32768, 32767).astype("<i2")
    with wave.open(str(out / f"{name}.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(FS); w.writeframes(x.tobytes())
    (out / f"{name}.s16le.pcm").write_bytes(x.tobytes())
    if manifest is not None:
        (out / f"{name}.json").write_text(json.dumps(manifest, indent=1))
    print(f"wrote {name}: {len(x)/FS/60:.1f} min, {len(x)} samples")


z = np.load(CACHE)
key_files = z["test_key_files"]
unk_files = z["test_unk_files"]
print(f"test split: {len(key_files)} marvin clips, {len(unk_files)} unknown-word clips")
assert len(key_files) >= N_POS

bg_train, bg_held = data.load_background()   # bg_held: last 20% in time, never used for training


def clip_stream(files, mix_noise_snr=None):
    gap = np.zeros(int(GAP_S * FS), np.int16)
    parts = [gap]
    manifest = []
    pos = len(gap)
    for rel in files:
        c = data.read_clip(DATASET_DIR / rel)
        if mix_noise_snr is not None:
            c = data.mix_noise(c, bg_held, mix_noise_snr, rng)
        parts += [c, gap]
        manifest.append({"start": pos, "end": pos + CLIP_SAMPLES, "source": str(rel)})
        pos += CLIP_SAMPLES + len(gap)
    return np.concatenate(parts).astype(np.float64), manifest


key_sel = rng.choice(key_files, N_POS, replace=False)
x, m = clip_stream(key_sel)
write("positive_clean", x, m)
x, m = clip_stream(key_sel, mix_noise_snr=NOISY_SNR_DB)
write("positive_noisy", x, m)

# Negative: alternate a random unknown-word clip (with its own gap) and a background-noise crop,
# until we reach NEG_MINUTES. Every unknown-word clip used at most once (falls back to reuse with a
# warning only if the test split is exhausted, which it won't be: len(unk_files) ~10,800).
target = int(NEG_MINUTES * 60 * FS)
unk_order = rng.permutation(unk_files)
gap = np.zeros(int(GAP_S * FS), np.int16)
parts, n, ui = [], 0, 0
while n < target:
    if ui < len(unk_order):
        c = data.read_clip(DATASET_DIR / unk_order[ui]); ui += 1
    else:
        c = data.silence_clip(bg_held, rng)   # exhausted (won't happen at 30 min), degrade gracefully
    parts += [c, gap]
    n += len(c) + len(gap)
    noise = data.noise_crop(bg_held, rng) * rng.uniform(0.2, 0.8)
    parts.append(noise)
    n += len(noise)
x = np.concatenate(parts)[:target]
write(f"negative", x)
print(f"negative stream used {ui} distinct unknown-word clips")

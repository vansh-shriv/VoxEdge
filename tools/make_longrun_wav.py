"""Generate a long concatenated-negative-audio clip for Phase 5 long-run stability (spec 4.4):
watch stack/heap high-water marks and overrun/drop counters over many minutes for leaks or slow
drift. Uses the Speech Commands background-noise files (needs the dataset; ml/prepare_data.py must
have been run at least once so DATASET_DIR exists).

python tools/make_longrun_wav.py [minutes=8]
Writes sim/wav_corpus/longrun/negative_<minutes>min.{wav,s16le.pcm}: the background-noise files
looped/concatenated back-to-back with independent random gain per segment, deterministic (seeded).
"""
import pathlib, sys, wave
import numpy as np
import soundfile as sf

root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "ml"))
from model_config import DATASET_DIR

minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0
fs = 16000
target = int(minutes * 60 * fs)
rng = np.random.default_rng(20260927)

bg_dir = DATASET_DIR / "_background_noise_"
files = sorted(bg_dir.glob("*.wav"))
if not files:
    sys.exit(f"no background noise files under {bg_dir}; run ml/prepare_data.py first")
clips = [sf.read(str(f), dtype="int16")[0] for f in files]
print(f"{len(clips)} background files, total {sum(len(c) for c in clips) / fs:.0f} s")

out = []
n = 0
while n < target:
    c = clips[rng.integers(len(clips))].astype(np.float64) * rng.uniform(0.3, 1.0)
    out.append(c)
    n += len(c)
x = np.clip(np.round(np.concatenate(out)[:target]), -32768, 32767).astype("<i2")

outdir = root / "sim" / "wav_corpus" / "longrun"
outdir.mkdir(parents=True, exist_ok=True)
name = f"negative_{int(minutes)}min"
with wave.open(str(outdir / f"{name}.wav"), "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(fs); w.writeframes(x.tobytes())
(outdir / f"{name}.s16le.pcm").write_bytes(x.tobytes())
print(f"wrote {outdir / name}.*: {len(x)} samples = {len(x) / fs / 60:.1f} min")

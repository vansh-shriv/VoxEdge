"""Build a demo audio stream from real Speech Commands *test-split* clips (never seen in training).

python tools/make_kws_demo.py   (needs the dataset + feature cache from ml/prepare_data.py)

Layout: 0.5 s silence, then N marvin clips and N other-word clips alternating (marvin first), each
1 s followed by 0.5 s digital silence. Clips are picked with a fixed seed, not cherry-picked.
Writes sim/wav_corpus/kws/demo.{wav,s16le.pcm} and demo.json (per-clip start sample, label, source).
"""
import json, pathlib, sys, wave
import numpy as np

root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "ml"))
import data
from model_config import *

N = 5
z = np.load(CACHE)
rng = np.random.default_rng(7)
key = rng.choice(z["test_key_files"], N, replace=False)
unk = rng.choice(z["test_unk_files"], N, replace=False)

fs, gap = 16000, np.zeros(8000, np.int16)
parts, manifest, pos = [gap], [], len(gap)
for k, u in zip(key, unk):
    for rel, label in ((k, KEYWORD), (u, "unknown")):
        parts += [data.read_clip(DATASET_DIR / rel), gap]
        manifest.append({"start": pos, "end": pos + fs, "label": label, "source": str(rel)})
        pos += fs + len(gap)
x = np.concatenate(parts).astype("<i2")

out = root / "sim" / "wav_corpus" / "kws"
out.mkdir(parents=True, exist_ok=True)
with wave.open(str(out / "demo.wav"), "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(fs); w.writeframes(x.tobytes())
(out / "demo.s16le.pcm").write_bytes(x.tobytes())
(out / "demo.json").write_text(json.dumps({"samples": len(x), "clips": manifest}, indent=1))
print(f"wrote {out}/demo.*  {len(x)/fs:.1f} s, {len(manifest)} clips")
for m in manifest: print(f"  {m['start']/fs:5.1f}s  {m['label']:8s} {m['source']}")

"""Build the KWS feature cache from Speech Commands v0.02 (run once; ~10-20 min).

  python ml/prepare_data.py            # extracts the tar if needed, writes DATA_ROOT/kws_<word>_features.npz

Splits use the dataset's own validation_list.txt / testing_list.txt (speaker-disjoint). Background
noise files are split 80/20 in time: train augmentation and train silence use the first 80 %,
validation/test noise and silence use the last 20 %.

Training set (augmented, features fixed offline): each keyword clip x4 (shift +-150 ms, gain
0.5-1.5, background noise at 5-30 dB SNR with p=0.8; the first copy is unmodified), unknown words
x1 (shift, gain, noise p=0.5), plus silence clips. Validation and test are unaugmented; the test
set also has a noisy copy (heldout noise at 10 dB SNR) for the clean-vs-noisy hit-rate report.
"""
import pathlib, sys, tarfile, time
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import data
from model_config import *  # noqa: F401,F403

SEED = 20260927
N_UNK_TRAIN, N_UNK_VAL = 20000, 2000
N_SIL_TRAIN, N_SIL_VAL, N_SIL_TEST = 2500, 300, 400
KEY_COPIES = 4
MAX_SHIFT = 2400            # 150 ms
NOISY_TEST_SNR_DB = 10.0


def ensure_dataset():
    if DATASET_DIR.exists() and (DATASET_DIR / "testing_list.txt").exists():
        return
    tar = DATA_ROOT / "speech_commands_v0.02.tar.gz"
    print(f"extracting {tar} ...", flush=True)
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar, "r:gz") as t:
        t.extractall(DATASET_DIR)


def list_files():
    words = sorted(d.name for d in DATASET_DIR.iterdir() if d.is_dir() and not d.name.startswith("_"))
    assert KEYWORD in words, f"{KEYWORD} not in dataset"
    val = set((DATASET_DIR / "validation_list.txt").read_text().split())
    test = set((DATASET_DIR / "testing_list.txt").read_text().split())
    out = {s: {"key": [], "unk": []} for s in ("train", "val", "test")}
    for w in words:
        for f in sorted((DATASET_DIR / w).glob("*.wav")):
            rel = f"{w}/{f.name}"
            split = "val" if rel in val else "test" if rel in test else "train"
            out[split]["key" if w == KEYWORD else "unk"].append(rel)
    return words, out


def featurize(clip_iter, n, label_iter=None, chunk=1000):
    """Consume an iterator of int16 clips, return float32 features [n, N_FRAMES, 40]."""
    feats, buf = [], []
    for i, c in enumerate(clip_iter):
        buf.append(c)
        if len(buf) == chunk:
            feats.append(data.logmel_batch(np.stack(buf))); buf = []
            print(f"    {i + 1}/{n}", end="\r", flush=True)
    if buf:
        feats.append(data.logmel_batch(np.stack(buf)))
    print(" " * 30, end="\r")
    return np.concatenate(feats)


def augment(clip, bank, rng, p_noise):
    c = data.shift(clip, int(rng.integers(-MAX_SHIFT, MAX_SHIFT + 1)))
    c = np.clip(np.round(c.astype(np.float64) * rng.uniform(0.5, 1.5)), -32768, 32767).astype(np.int16)
    if rng.random() < p_noise:
        c = data.mix_noise(c, bank, rng.uniform(5, 30), rng)
    return c


def main():
    t0 = time.time()
    ensure_dataset()
    rng = np.random.default_rng(SEED)
    words, files = list_files()
    bg_train, bg_held = data.load_background()
    print(f"{len(words)} words; keyword '{KEYWORD}' clips: " +
          ", ".join(f"{s}={len(files[s]['key'])}" for s in files) +
          "; unknown: " + ", ".join(f"{s}={len(files[s]['unk'])}" for s in files), flush=True)

    def sample(lst, n):
        return [lst[i] for i in rng.permutation(len(lst))[:n]]

    def read(rels):
        return [data.read_clip(DATASET_DIR / r) for r in rels]

    # ---- train (augmented)
    key_tr = read(files["train"]["key"])
    unk_tr_rel = sample(files["train"]["unk"], N_UNK_TRAIN)
    def train_clips():
        for c in key_tr:
            yield c
            for _ in range(KEY_COPIES - 1): yield augment(c, bg_train, rng, 0.8)
        for r in unk_tr_rel: yield augment(data.read_clip(DATASET_DIR / r), bg_train, rng, 0.5)
        for _ in range(N_SIL_TRAIN): yield data.silence_clip(bg_train, rng)
    n_tr = len(key_tr) * KEY_COPIES + len(unk_tr_rel) + N_SIL_TRAIN
    y_tr = np.array([KEY] * (len(key_tr) * KEY_COPIES) + [UNKNOWN] * len(unk_tr_rel) + [SILENCE] * N_SIL_TRAIN, np.int8)
    print(f"train: {n_tr} clips", flush=True)
    x_tr = featurize(train_clips(), n_tr)

    # ---- validation (clean)
    key_v = files["val"]["key"]; unk_v = sample(files["val"]["unk"], N_UNK_VAL)
    print(f"val: {len(key_v)} key + {len(unk_v)} unk + {N_SIL_VAL} sil", flush=True)
    def val_clips():
        for c in read(key_v): yield c
        for r in unk_v: yield data.read_clip(DATASET_DIR / r)
        for _ in range(N_SIL_VAL): yield data.silence_clip(bg_held, rng)
    y_v = np.array([KEY] * len(key_v) + [UNKNOWN] * len(unk_v) + [SILENCE] * N_SIL_VAL, np.int8)
    x_v = featurize(val_clips(), len(y_v))

    # ---- test (clean + noisy copy of identical clips; silence clips are identical in both)
    key_t = files["test"]["key"]; unk_t = files["test"]["unk"]
    print(f"test: {len(key_t)} key + {len(unk_t)} unk + {N_SIL_TEST} sil", flush=True)
    sil_t = [data.silence_clip(bg_held, rng) for _ in range(N_SIL_TEST)]
    rng_noise = np.random.default_rng(SEED + 1)
    def test_clips(noisy):
        for rel in key_t + unk_t:
            c = data.read_clip(DATASET_DIR / rel)
            yield data.mix_noise(c, bg_held, NOISY_TEST_SNR_DB, rng_noise) if noisy else c
        for c in sil_t: yield c
    y_t = np.array([KEY] * len(key_t) + [UNKNOWN] * len(unk_t) + [SILENCE] * N_SIL_TEST, np.int8)
    x_t = featurize(test_clips(False), len(y_t))
    x_tn = featurize(test_clips(True), len(y_t))

    # ---- sanity: vectorised features == librosa-based reference (and hence the firmware)
    probe = np.stack([data.read_clip(DATASET_DIR / key_t[i]) for i in range(3)])
    print(f"vectorised vs reference max abs diff: {data.check_against_reference(probe):.2e}")

    mean, std = float(x_tr.mean()), float(x_tr.std())
    print(f"train feature mean={mean:.4f} std={std:.4f}")
    np.savez(CACHE, x_train=x_tr, y_train=y_tr, x_val=x_v, y_val=y_v, x_test=x_t, x_test_noisy=x_tn,
             y_test=y_t, mean=mean, std=std, test_key_files=np.array(key_t), test_unk_files=np.array(unk_t))
    print(f"wrote {CACHE} ({CACHE.stat().st_size / 1e6:.0f} MB) in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()

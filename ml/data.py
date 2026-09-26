"""Speech Commands dataset preparation: WAVs -> log-mel arrays (same features as the firmware)."""
import pathlib, sys
import numpy as np
import soundfile as sf

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import features as ref
from feature_config import HOP, WIN, NFFT, PREEMPH, LOG_FLOOR, N_MELS
from model_config import *  # noqa: F401,F403

_MEL = ref.mel_matrix()                  # (N_MELS, N_BINS) float64
_HAM = ref.hamming()
_IDX = HOP * np.arange(N_FRAMES)[:, None] + np.arange(WIN)   # (N_FRAMES, WIN) sample indices


def logmel_batch(x, chunk=256):
    """int16 [N, CLIP_SAMPLES] -> float32 [N, N_FRAMES, N_MELS]. Identical maths to ml/features.py
    (which itself is cross-checked against the firmware), but vectorised and without librosa's
    per-call overhead. tests: see check_against_reference()."""
    x = np.asarray(x)
    out = np.empty((len(x), N_FRAMES, N_MELS), np.float32)
    for s in range(0, len(x), chunk):
        fr = x[s:s + chunk][:, _IDX].astype(np.float64)          # (c, frames, WIN)
        y = fr.copy()
        y[..., 1:] -= PREEMPH * fr[..., :-1]
        y *= _HAM
        p = np.abs(np.fft.rfft(y, n=NFFT, axis=-1)) ** 2
        out[s:s + chunk] = np.log(p @ _MEL.T + LOG_FLOOR)
    return out


def check_against_reference(x):
    """Max abs difference between logmel_batch and the librosa-based reference on a few clips."""
    got = logmel_batch(x)
    worst = 0.0
    for i in range(len(x)):
        seqs, want = ref.logmel(x[i])
        assert len(seqs) == N_FRAMES
        worst = max(worst, float(np.abs(got[i] - want).max()))
    return worst


def read_clip(path):
    a, sr = sf.read(str(path), dtype="int16")
    assert sr == 16000, path
    out = np.zeros(CLIP_SAMPLES, np.int16)
    out[:min(len(a), CLIP_SAMPLES)] = a[:CLIP_SAMPLES]           # zero-pad at the end
    return out


def load_background(root=None):
    """Background-noise files, each split into a train part (first 80 %) and val/test part (last 20 %)."""
    root = pathlib.Path(root or DATASET_DIR) / "_background_noise_"
    train, heldout = [], []
    for f in sorted(root.glob("*.wav")):
        a, sr = sf.read(str(f), dtype="int16")
        assert sr == 16000
        cut = int(len(a) * 0.8)
        train.append(a[:cut]); heldout.append(a[cut:])
    return train, heldout


def noise_crop(bank, rng):
    n = bank[rng.integers(len(bank))]
    s = rng.integers(0, len(n) - CLIP_SAMPLES)
    return n[s:s + CLIP_SAMPLES].astype(np.float64)


def rms(a):
    return float(np.sqrt(np.mean(np.square(a, dtype=np.float64)) + 1e-9))


def mix_noise(clip, bank, snr_db, rng):
    """Add background noise to `clip` at the given SNR (dB, relative to the clip's RMS)."""
    c = clip.astype(np.float64)
    n = noise_crop(bank, rng)
    g = rms(c) / (rms(n) * 10 ** (snr_db / 20.0))
    return np.clip(np.round(c + g * n), -32768, 32767).astype(np.int16)


def shift(clip, n):
    """Shift by n samples (positive = later), zero fill."""
    out = np.zeros_like(clip)
    if n >= 0: out[n:] = clip[:CLIP_SAMPLES - n]
    else:      out[:n] = clip[-n:]
    return out


def silence_clip(bank, rng):
    """Background-noise crop at random gain; ~10 % exact digital silence."""
    if rng.random() < 0.1:
        return np.zeros(CLIP_SAMPLES, np.int16)
    n = noise_crop(bank, rng) * rng.uniform(0.05, 1.0)
    return np.clip(np.round(n), -32768, 32767).astype(np.int16)

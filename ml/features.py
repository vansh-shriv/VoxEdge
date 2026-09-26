"""Float64 reference log-mel feature extractor (host side).

Window k covers hops k-2..k, i.e. samples [HOP*(k-2), HOP*(k-2)+WIN), matching the firmware's
capture task, so window index k here equals the firmware's `seq`. The first window is k = 2.
The mel filterbank comes from librosa (HTK mel scale, no area normalisation).
"""
import numpy as np
import librosa

from feature_config import *  # noqa: F401,F403


def hamming():
    return np.hamming(WIN)


def mel_matrix():
    """(N_MELS, N_BINS) float64 filterbank from librosa."""
    return librosa.filters.mel(sr=FS, n_fft=NFFT, n_mels=N_MELS, fmin=FMIN, fmax=FMAX,
                               htk=True, norm=None)


def frame_windows(x):
    """Overlapping windows [n_windows, WIN] and their firmware seq numbers (starting at 2)."""
    x = np.asarray(x, dtype=np.float64)
    n_hops = len(x) // HOP
    seqs = np.arange(2, n_hops)
    frames = np.stack([x[HOP * (k - 2):HOP * (k - 2) + WIN] for k in seqs])
    return seqs, frames


def power_spectra(frames):
    """Pre-emphasis (window-local), Hamming, zero-pad to NFFT, |rfft|^2 -> [n_windows, N_BINS]."""
    y = frames.copy()
    y[:, 1:] -= PREEMPH * frames[:, :-1]
    y *= hamming()
    return np.abs(np.fft.rfft(y, n=NFFT, axis=1)) ** 2


def logmel_from_power(p):
    # librosa applies the filterbank: melspectrogram(S=power) -> [N_MELS, n_windows]
    mel = librosa.feature.melspectrogram(S=p.T, sr=FS, n_fft=NFFT, n_mels=N_MELS,
                                         fmin=FMIN, fmax=FMAX, htk=True, norm=None)
    return np.log(mel.T + LOG_FLOOR)


def logmel(x):
    """int16/float samples -> (seqs, log-mel [n_windows, N_MELS])."""
    seqs, frames = frame_windows(x)
    return seqs, logmel_from_power(power_spectra(frames))

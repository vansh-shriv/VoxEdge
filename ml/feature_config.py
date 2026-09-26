"""Feature-extraction parameters: the single source of truth.

tools/gen_dsp_tables.py writes these into firmware/src/dsp/dsp_tables.h, so the firmware and the
Python reference cannot drift apart. Changing anything here requires regenerating the tables.
"""
FS = 16000           # sample rate, Hz
WIN = 480            # 30 ms analysis window
HOP = 160            # 10 ms hop
NFFT = 512           # zero-padded FFT length
N_BINS = NFFT // 2 + 1
PREEMPH = 0.97       # y[n] = x[n] - PREEMPH * x[n-1]; window-local, y[0] = x[0]
N_MELS = 40
FMIN = 20.0          # Hz
FMAX = 8000.0        # Hz (Nyquist)
LOG_FLOOR = 1.0      # log(mel_energy + LOG_FLOOR); samples are raw int16 units, so 1 = 1 LSB^2

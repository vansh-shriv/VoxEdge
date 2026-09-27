"""Spectrogram + detection-timeline plot for the README/docs (spec §6): shows the streaming audio
the firmware actually saw, the true keyword clip locations, and the wake events it produced.

python tools/plot_detection_timeline.py <uart.log> <pcm> <manifest.json> <out.png> [start_s] [dur_s]
"""
import json, re, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

log, pcm, manifest_path, out = sys.argv[1:5]
start_s = float(sys.argv[5]) if len(sys.argv) > 5 else 0.0
dur_s = float(sys.argv[6]) if len(sys.argv) > 6 else 30.0
FS = 16000

x = np.frombuffer(open(pcm, "rb").read(), dtype="<i2").astype(np.float64)
lo, hi = int(start_s * FS), int((start_s + dur_s) * FS)
seg = x[lo:hi]

manifest = json.loads(open(manifest_path).read())["clips"] if "clips" in json.loads(open(manifest_path).read()) else json.loads(open(manifest_path).read())
lines = [l.rstrip("\n") for l in open(log, errors="replace") if l.strip()]
rises = [(int(m[1]), int(m[2])) for l in lines if (m := re.fullmatch(r"E (\d+) R (\d+)", l))]
falls = [(int(m[1]), int(m[2])) for l in lines if (m := re.fullmatch(r"E (\d+) F (\d+)", l))]

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 5), sharex=True, height_ratios=[3, 1])
ax1.specgram(seg, NFFT=512, Fs=FS, noverlap=384, cmap="magma")
ax1.set_ylabel("Hz"); ax1.set_ylim(0, 8000)
ax1.set_title("VoxEdge streaming detection: spectrogram, true keyword windows, and wake events")

for c in manifest:
    s, e = c["start"] / FS, c["end"] / FS
    if e < start_s or s > start_s + dur_s: continue
    ax1.axvspan(s, e, color="lime", alpha=0.15)
    ax2.axvspan(s, e, color="lime", alpha=0.25)

for seq, tick in rises:
    t = seq * 0.01
    if start_s <= t <= start_s + dur_s:
        ax1.axvline(t, color="cyan", lw=1.2, ls="--")
        ax2.axvline(t, color="cyan", lw=1.2, ls="--")
for seq, tick in falls:
    t = seq * 0.01
    if start_s <= t <= start_s + dur_s:
        ax2.axvline(t, color="orangered", lw=1, ls=":")

ax2.set_yticks([]); ax2.set_xlabel("time (s)")
ax2.set_ylabel("wake")
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
ax1.legend(handles=[Patch(color="lime", alpha=0.3, label="true keyword clip"),
                     Line2D([0], [0], color="cyan", ls="--", label="wake ON"),
                     Line2D([0], [0], color="orangered", ls=":", label="wake OFF")],
          loc="upper right", fontsize=8)
plt.tight_layout()
plt.savefig(out, dpi=130)
print(f"wrote {out}")

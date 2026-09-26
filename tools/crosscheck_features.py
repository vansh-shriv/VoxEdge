"""Phase 2 cross-check: on-device log-mel (UART `F` lines) vs the float64 Python reference.

Usage: python tools/crosscheck_features.py build/uart0.log sim/wav_corpus/synthetic/features_2s.s16le.pcm [tol]
Exit 0 iff every reference window is present exactly once on the device and max |diff| <= tol.
Also reports DWT cycle cost of features_compute() against the 10 ms hop budget.
"""
import re, sys, pathlib
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "ml"))
import features as ref
from feature_config import N_MELS, HOP

log, pcm = sys.argv[1], sys.argv[2]
tol = float(sys.argv[3]) if len(sys.argv) > 3 else 0.02
CPU_HZ = 64_000_000   # assumed core clock (FreeRTOSConfig.h, sim/boot.resc)

dev, dup, tel = {}, 0, []
for line in open(log, errors="replace"):
    line = line.strip()
    m = re.fullmatch(r"F (\d+) ([0-9a-f]{%d})" % (8 * N_MELS), line)
    if m:
        seq = int(m[1])
        dup += seq in dev
        dev[seq] = np.frombuffer(bytes.fromhex(m[2]), dtype=">u4").astype(np.uint32).view(np.float32)
    elif line.startswith("T "):
        tel.append({k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", line)})

x = np.frombuffer(open(pcm, "rb").read(), dtype="<i2")
seqs, want = ref.logmel(x)
missing = [int(s) for s in seqs if s not in dev]
extra = sorted(set(dev) - set(int(s) for s in seqs))
print(f"reference windows={len(seqs)} device windows={len(dev)} missing={len(missing)} "
      f"extra={len(extra)} duplicates={dup}")

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)

check(not missing, f"every reference window present on device (missing: {missing[:8]})")
check(dup == 0, "no duplicate windows")
if len(dev) - len(extra):
    idx = [i for i, s in enumerate(seqs) if int(s) in dev]
    got = np.stack([dev[int(seqs[i])] for i in idx]).astype(np.float64)
    d = np.abs(got - want[idx])
    worst = np.unravel_index(np.argmax(d), d.shape)
    print(f"log-mel range: {want.min():.3f}..{want.max():.3f}")
    print(f"abs diff: max={d.max():.5f} (window seq {int(seqs[idx[worst[0]]])}, mel {worst[1]})  "
          f"mean={d.mean():.6f}  p99={np.percentile(d, 99):.5f}")
    for name, lo, hi in [("silence", 2, 28), ("chirp+noise", 32, 95), ("clipped sine", 102, 126), ("noise", 132, 198)]:
        sel = [j for j, i in enumerate(idx) if lo <= seqs[i] <= hi]
        if sel: print(f"  {name:13s} windows {lo:3d}-{hi:3d}: max diff {d[sel].max():.5f}")
    check(d.max() <= tol, f"max abs diff {d.max():.5f} <= tol {tol}")

if tel:
    t = tel[-1]
    print("last telemetry:", t)
    check(t["dspcyc_max"] > 0, "DWT cycle counter works under Renode")
    if t["dspcyc_max"]:
        budget = CPU_HZ * HOP // 16000
        print(f"features_compute cycles: avg={t['dspcyc_avg']} max={t['dspcyc_max']}  "
              f"hop budget={budget}  -> avg {100 * t['dspcyc_avg'] / budget:.1f}% / max {100 * t['dspcyc_max'] / budget:.1f}% of one hop")
    for k in ("ovr", "dspdrop", "evtdrop", "dumpdrop"):
        check(t[k] == 0, f"{k} == 0")

sys.exit(1 if fails else 0)

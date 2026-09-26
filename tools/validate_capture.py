"""Phase 0 validation: compare samples dumped over UART by firmware with the source PCM.

Usage: python tools/validate_capture.py build/uart0.log sim/wav_corpus/synthetic/tone1k_1s.s16le.pcm
Parses 'S:<seq>:<hex>' lines, concatenates frames, finds the best offset into the source,
and reports match statistics. Exit code 0 only if the captured stream equals the source
(at some constant offset) sample-for-sample and frame sequence numbers are contiguous.
"""
import re, sys
import numpy as np

log, pcm = sys.argv[1], sys.argv[2]
frames, seqs, overruns = [], [], None
for line in open(log, errors="replace"):
    line = line.strip()
    m = re.fullmatch(r"S:([0-9a-f]{4}):([0-9a-f]+)", line)
    if m:
        seqs.append(int(m[1], 16))
        frames.append(np.frombuffer(bytes.fromhex(m[2]), dtype="<i2"))
    elif line.startswith("D:"):
        overruns = int(line[2:], 16)
cap = np.concatenate(frames)
src = np.frombuffer(open(pcm, "rb").read(), dtype="<i2")
print(f"frames={len(frames)} samples={len(cap)} src_samples={len(src)} overruns_reported={overruns}")
print("sequence contiguous:", seqs == list(range(len(seqs))))

# find constant offset: cap[i] == src[i + off]
best = None
probe = cap[400:480]
for off in range(-400, len(src) - 480):
    j = 400 + off
    if j < 0 or j + 80 > len(src): continue
    if np.array_equal(src[j:j + 80], probe):
        best = off; break
print("offset (cap index -> src index):", best)
if best is None:
    print("no exact alignment; correlation-based check:")
    n = min(len(cap), len(src))
    print("  max abs diff (no offset):", int(np.abs(cap[:n].astype(int) - src[:n]).max()))
    sys.exit(1)
lo, hi = max(0, -best), min(len(cap), len(src) - best)
seg_cap, seg_src = cap[lo:hi], src[lo + best:hi + best]
mism = int(np.count_nonzero(seg_cap != seg_src))
print(f"compared {hi - lo} samples, mismatches={mism}, max abs diff={int(np.abs(seg_cap.astype(int) - seg_src).max())}")
sys.exit(0 if mism == 0 and seqs == list(range(len(seqs))) else 1)

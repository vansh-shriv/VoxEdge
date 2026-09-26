"""Phase 4 parity check (spec 4.3): on-device TFLite-Micro int8 inference vs the Python int8 model.

python tools/crosscheck_model.py <uart.log> <input.s16le.pcm> [variant=s] [kernels=cmsis|ref]

Three checks on the `L` (logits per inference) and `Q` (sampled input tensor) lines:
  A. Model parity: feed the *device's own* quantised input tensor (Q line) to the Python TFLite
     interpreter with reference kernels and compare with the device's L line. Reference-kernel
     firmware must be bit-exact. CMSIS-NN firmware may differ by 1 LSB in at most 1 % of inferences
     (its requantisation rounds slightly differently in rare cases); the count is always reported.
  B. Feature/ring parity: the device input tensor vs Python's quantisation of the float64
     reference features for the same window range. Differences come only from the float32 vs
     float64 feature gap (Phase 2, ~1e-4) flipping a rounding, so they must be rare and +-1 LSB.
  C. End to end: device logits vs Python (reference features -> int8 model) for every inference.
Prints cycle statistics from the last telemetry line. Exit 0 iff A is exact, B differs by <= 1 LSB
in <= 0.5 % of elements, and C agrees on argmax in every inference whose margin exceeds 1 LSB.
"""
import json, pathlib, re, sys
import numpy as np

root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "ml"))
import features as ref
import model_config as mc
import tensorflow as tf

log, pcm = sys.argv[1], sys.argv[2]
variant = sys.argv[3] if len(sys.argv) > 3 else "s"
kernels = sys.argv[4] if len(sys.argv) > 4 else "cmsis"
CPU_HZ = 64_000_000

it = tf.lite.Interpreter(model_path=str(mc.ARTIFACTS / f"{mc.KEYWORD}_{variant}_int8.tflite"),
                         experimental_op_resolver_type=tf.lite.experimental.OpResolverType.BUILTIN_REF)
it.allocate_tensors()
inp, out = it.get_input_details()[0], it.get_output_details()[0]
s_in, z_in = inp["quantization"]
norm = json.loads((mc.ARTIFACTS / f"{mc.KEYWORD}_norm.json").read_text())


def run(q):  # q: int8 [98, 40] -> int8 logits
    it.set_tensor(inp["index"], q.reshape(inp["shape"]).astype(np.int8))
    it.invoke()
    return it.get_tensor(out["index"])[0].astype(int)


L, Q, tel = {}, {}, []
for line in open(log, errors="replace"):
    t = line.split()
    if not t: continue
    if t[0] == "L" and len(t) == 6:
        L[int(t[1])] = ([int(v) for v in t[2:5]], int(t[5]))
    elif t[0] == "Q" and len(t) == 3 and len(t[2]) == mc.N_FRAMES * 40 * 2:
        Q[int(t[1])] = np.frombuffer(bytes.fromhex(t[2]), dtype=np.int8).reshape(mc.N_FRAMES, 40)
    elif t[0] == "T":
        tel.append({k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", line)})
print(f"variant {variant}: {len(L)} inferences (L lines), {len(Q)} input tensors (Q lines)")

x = np.frombuffer(open(pcm, "rb").read(), dtype="<i2")
seqs, feats = ref.logmel(x)
by_seq = {int(s): i for i, s in enumerate(seqs)}
q_all = np.clip(np.round(((feats - norm["mean"]) / norm["std"]) / s_in + z_in), -128, 127).astype(np.int8)

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)

def in_ref(seq):
    """True if the reference has every window of this input (the emulated mic keeps producing frames after the file ends)."""
    return seq in by_seq and seq - mc.N_FRAMES + 1 in by_seq

def ref_input(seq):
    return q_all[by_seq[seq - mc.N_FRAMES + 1]:by_seq[seq] + 1]

# A. model parity on the device's own input tensors
inexact, worst_a, nA = [], 0, 0
for seq, q in Q.items():
    if seq not in L: continue
    nA += 1
    d = np.abs(run(q) - np.array(L[seq][0]))
    if d.max() > 0:
        inexact.append(seq); worst_a = max(worst_a, int(d.max()))
        print(f"   A inexact seq {seq}: device {L[seq][0]} python {run(q).tolist()}")
if kernels == "ref":
    ok_a = nA > 0 and not inexact
else:
    ok_a = nA > 0 and worst_a <= 1 and len(inexact) <= 0.01 * nA
check(ok_a, f"A ({kernels} kernels): {nA - len(inexact)}/{nA} inferences bit-exact vs Python reference kernels"
            + (f"; {len(inexact)} differ, max {worst_a} LSB" if inexact else ""))

# B. device input tensor vs Python quantisation of reference features
tot = diff = worst = 0
for seq, q in Q.items():
    if not in_ref(seq): continue
    d = np.abs(q.astype(int) - ref_input(seq).astype(int))
    tot += d.size; diff += int((d > 0).sum()); worst = max(worst, int(d.max()))
if tot:
    check(worst <= 1 and diff / tot <= 0.005,
          f"B: input tensors differ in {diff}/{tot} elements ({100 * diff / tot:.3f} %), max |diff| = {worst} LSB")

# C. end-to-end logits
maxd, agree, n_c, close = 0, 0, 0, 0
for seq, (lg, pk) in sorted(L.items()):
    if not in_ref(seq): continue
    p = run(ref_input(seq)); lg = np.array(lg)
    maxd = max(maxd, int(np.abs(p - lg).max())); n_c += 1
    top2 = np.sort(p)[-2:]
    if top2[1] - top2[0] <= 1: close += 1; continue          # near-tie: argmax not meaningful
    agree += int(p.argmax() == lg.argmax())
check(n_c > 0 and agree == n_c - close, f"C: argmax agrees on {agree}/{n_c - close} inferences (max |logit diff| = {maxd} LSB, {close} near-ties)")

if tel:
    t = tel[-1]
    if t["runs"]:
        print(f"model runs={t['runs']} due={t['due']} skipped={t['skipped']}  arena={t['arena']} B")
        print(f"kws_infer cycles: avg={t['infcyc_avg']:,} max={t['infcyc_max']:,}  "
              f"= {t['infcyc_avg'] / CPU_HZ * 1000:.1f} ms at {CPU_HZ // 10**6} MHz; "
              f"features_compute avg={t['dspcyc_avg']:,}")
    for k in ("ovr", "dspdrop", "evtdrop"):
        check(t[k] == 0, f"{k} == 0 (capture/DSP never starved)")
sys.exit(1 if fails else 0)

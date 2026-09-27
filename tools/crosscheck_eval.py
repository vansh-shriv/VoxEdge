"""Phase 6 streaming evaluation scoring (spec 4.1/4.5): real hit-rate / false-accept metrics from
wake events (`E ... R`) the running firmware actually produced on continuous audio, as opposed to
the Phase 3 clip-level numbers (each 1 s window scored independently, keyword perfectly centred).

python tools/crosscheck_eval.py positive <uart.log> <manifest.json>   -> hit rate
python tools/crosscheck_eval.py negative <uart.log> <duration_s>      -> false accepts / hour
"""
import json, re, sys

mode, log = sys.argv[1], sys.argv[2]
lines = [l.rstrip("\n") for l in open(log, errors="replace") if l.strip()]
rises = [(int(m[1]), int(m[2])) for l in lines if (m := re.fullmatch(r"E (\d+) R (\d+)", l))]   # (seq, tick)
tel = [{k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", l)} for l in lines if l.startswith("T ")]

print(f"boots={sum(l.startswith('VOXEDGE') for l in lines)} FATAL={sum(l.startswith('FATAL') for l in lines)} "
      f"wake-on events={len(rises)} telemetry lines={len(tel)}")
if tel:
    last = tel[-1]
    print(f"final: pdm={last['pdm']} ovr={last['ovr']} dspdrop={last['dspdrop']}")

FS, HOP = 16000, 160

if mode == "positive":
    manifest = json.loads(open(sys.argv[3]).read())
    # A rise's seq is the hop whose 980 ms ring snapshot ended there; count it as belonging to a clip
    # if that ring window overlaps the clip at all (seq-97..seq hops vs [start,end) samples).
    hits = 0
    for c in manifest:
        c_lo, c_hi = c["start"] // HOP, c["end"] // HOP
        hit = any(seq - 97 <= c_hi and seq >= c_lo for seq, _ in rises)
        c["hit"] = hit
        hits += hit
    rate = hits / len(manifest)
    print(f"hit rate: {hits}/{len(manifest)} = {rate*100:.1f}%")
    # multiple rises inside one clip's window would double count wake events relative to clips; report separately
    extra = len(rises) - hits
    if extra: print(f"note: {len(rises)} total wake-on events for {hits} hit clips ({extra} extra, likely re-triggers)")
    sys.exit(0)
elif mode == "negative":
    duration_s = float(sys.argv[3])
    fa = len(rises)
    per_hour = fa / (duration_s / 3600)
    print(f"false accepts: {fa} in {duration_s/60:.1f} min = {per_hour:.2f} / hour")
    sys.exit(0)
else:
    sys.exit(f"unknown mode {mode!r}")

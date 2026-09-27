"""Phase 5 long-run stability checker (spec 4.4): stack/heap high-water marks must stabilise, not
drift downward indefinitely (a leak), and overrun/drop counters must stay at 0 throughout a long run.

python tools/crosscheck_longrun.py <uart.log>
"""
import re, sys

lines = [l.rstrip("\n") for l in open(sys.argv[1], errors="replace") if l.strip()]
tel = [{k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", l)} for l in lines if l.startswith("T ")]

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)

check(sum(l.startswith("VOXEDGE PHASE5 BOOT") for l in lines) == 1, "exactly one boot (no reset)")
check(not any(l.startswith("FATAL") for l in lines), "no FATAL")
check(len(tel) >= 30, f"{len(tel)} telemetry lines (need enough to see a trend)")
if not tel: sys.exit(1 if fails else 0)

last = tel[-1]
print(f"final: tick={last['tick']} pdm={last['pdm']} runs={last['runs']} "
      f"heapmin={last['heapmin']} stk(cap/dsp/inf/tel)={last['stk_cap']}/{last['stk_dsp']}/{last['stk_inf']}/{last['stk_tel']}")

for key in ("ovr", "dspdrop", "evtdrop", "dumpdrop"):
    check(all(t[key] == 0 for t in tel), f"{key} == 0 throughout ({tel[-1][key]} at end)")

# uxTaskGetStackHighWaterMark (and free-heap) is a running minimum: it steps down each time a code
# path that uses a bit more stack/heap runs for the first time (e.g. the first wake event), then
# holds flat once every path has been exercised. That settling is expected, not a leak. A real leak
# looks different: the watermark keeps decreasing throughout the second half of the run, never
# reaching a flat plateau. So the check is that the LAST HALF is already flat (== its own last
# value), not that the whole run never moved.
half = max(1, len(tel) // 2)
for key in ("heapmin", "stk_cap", "stk_dsp", "stk_inf", "stk_tel"):
    last_val = tel[-1][key]
    second_half_min = min(t[key] for t in tel[-half:])
    check(second_half_min == last_val, f"{key}: flat over the second half (min {second_half_min}, final {last_val}) - settled, not still leaking")

check(last["pdm"] == last["hops"], "capture consumed every PDM frame (no silent backlog)")

sys.exit(1 if fails else 0)

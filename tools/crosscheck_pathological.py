"""Phase 5 pathological-audio checker (spec 4.4): confirm the pipeline never crashes, hangs, or
produces a nonsensical (NaN/Inf/out-of-range) detection when fed clipped audio, digital silence, or
max-amplitude white noise.

python tools/crosscheck_pathological.py <uart.log> <expected_hops>
"""
import re, sys

log, expected_hops = sys.argv[1], int(sys.argv[2])
lines = [l.rstrip("\n") for l in open(log, errors="replace") if l.strip()]

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)

check(lines and lines[0].startswith("VOXEDGE PHASE5 BOOT"), "boot banner")
check(sum(l.startswith("VOXEDGE PHASE5 BOOT") for l in lines) == 1, "no unexpected reset (exactly one boot)")
check(not any(l.startswith("FATAL") for l in lines), "no FATAL (no stack overflow, malloc failure or assert)")

tel = [{k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", l)} for l in lines if l.startswith("T ")]
check(len(tel) >= 2, f"{len(tel)} telemetry lines (pipeline kept running)")
if tel:
    last = tel[-1]
    print("last telemetry:", last)
    check(last["pdm"] >= expected_hops * 0.9, f"pdm frames {last['pdm']} (expected ~{expected_hops})")
    check(last["ovr"] == 0, "no PDM overruns")
    check(last["dspdrop"] == 0, "no DSP drops (real-time margin held even on worst-case input)")
    check(0 <= last["pkey"] <= 1000, f"P(keyword) in range (pkey={last['pkey']})")

pkeys = sorted(set(t["pkey"] for t in tel))
print(f"P(keyword) values seen: {pkeys[:8]}{'...' if len(pkeys) > 8 else ''}")  # informational only:
# constant input (exact digital silence) legitimately gives a constant output, so this is not itself
# a pass/fail signal; the range check above is what would catch a NaN-corrupted softmax.

events = [l for l in lines if re.fullmatch(r"E \d+ [RF] \d+", l)]
print(f"wake events: {len(events)}")

sys.exit(1 if fails else 0)

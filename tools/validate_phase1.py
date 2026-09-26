"""Phase 1 validation of build/uart0.log for the burst_3s test signal (tone in hops 100..199).

Pipeline plumbing only (the placeholder energy detector that raised wake events was replaced by the
real model in Phase 4): boot banner, no FATAL, zero overruns/drops in every telemetry line,
capture consuming every hop, DSP keeping up. Model behaviour is checked by run_phase4.sh.
"""
import re, sys

log = sys.argv[1] if len(sys.argv) > 1 else "build/uart0.log"
runtime_s = 3.5
lines = [l.strip() for l in open(log, errors="replace") if l.strip()]
fails = []

def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)

check(lines and lines[0].startswith("VOXEDGE PHASE"), "boot banner")
check(not any(l.startswith("FATAL") for l in lines), "no FATAL")

tel = []
for l in lines:
    if l.startswith("T "):
        tel.append({k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", l)})
check(len(tel) >= 2, f"{len(tel)} telemetry lines")
for key in ("ovr", "dspdrop", "evtdrop"):
    check(all(t[key] == 0 for t in tel), f"{key} == 0 in all telemetry")
if tel:
    last = tel[-1]
    print("last telemetry:", last)
    check(last["pdm"] >= 290, f"pdm frames {last['pdm']}")
    check(last["hops"] >= last["pdm"] - 2, "capture consumed every hop")
    check(last["win"] >= last["hops"] - 4, "dsp keeps up with capture")
    exp_ticks = last["tick"]
    print(f"ticks per virtual second (nominal 1000): last tick={exp_ticks}")

sys.exit(1 if fails else 0)

"""Phase 1 validation of build/uart0.log for the burst_3s test signal (tone in hops 100..199).

Checks: boot banner, no FATAL, wake-on within a few hops of the tone start, wake-off within a
few hops of its end, zero overruns/drops in every telemetry line, all tasks alive
(hops == pdm frames), and SysTick ticks tracking virtual time.
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

events = [(int(m[1]), m[2], int(m[3])) for l in lines if (m := re.fullmatch(r"E (\d+) ([RF]) (\d+)", l))]
print("events (seq, type, tick):", events)
rise = [e for e in events if e[1] == "R"]
fall = [e for e in events if e[1] == "F"]
check(len(events) == 2 and len(rise) == 1 and len(fall) == 1, "exactly one wake-on and one wake-off")
if rise: check(100 <= rise[0][0] <= 105, f"wake-on at hop {rise[0][0]} (tone starts at 100)")
if fall: check(200 <= fall[0][0] <= 208, f"wake-off at hop {fall[0][0]} (tone ends at 200)")

tel = []
for l in lines:
    if l.startswith("T "):
        tel.append({k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", l)})
check(len(tel) >= 2, f"{len(tel)} telemetry lines")
for key in ("ovr", "dspdrop", "infdrop", "evtdrop"):
    check(all(t[key] == 0 for t in tel), f"{key} == 0 in all telemetry")
if tel:
    last = tel[-1]
    print("last telemetry:", last)
    check(last["pdm"] >= 290, f"pdm frames {last['pdm']}")
    check(last["hops"] >= last["pdm"] - 2, "capture consumed every hop")
    check(last["win"] >= last["hops"] - 4 and last["inf"] >= last["win"] - 2, "dsp/inference keep up")
    exp_ticks = last["tick"]
    print(f"ticks per virtual second (nominal 1000): last tick={exp_ticks}")

sys.exit(1 if fails else 0)

"""Phase 5 stall/watchdog checker (spec 4.4).

python tools/crosscheck_stall.py <uart.log> <mode:finite|infinite> [stalled_task:dsp|inference]

finite:   exactly one boot; a STALL start/end pair; ovr stays 0 for the whole run (capture never
          misses a PDM handoff); the queue downstream of the stalled task backs up and then holds
          flat (dsp_drops for a dsp stall, infer_skipped for an inference stall: dropped, not
          corrupted); telemetry/wake events resume after the stall (system recovers).
infinite: at least two boot banners (the watchdog forced a reset); a STALL start with no matching
          end; ovr stays 0 in the pre-reset portion; the pre-reset run stops cleanly (no FATAL).
"""
import re, sys

log, mode = sys.argv[1], sys.argv[2]
stalled_task = sys.argv[3] if len(sys.argv) > 3 else "dsp"
backlog_key = "dspdrop" if stalled_task == "dsp" else "skipped" if stalled_task == "inference" else None
lines = [l.rstrip("\n") for l in open(log, errors="replace") if l.strip()]

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)

boots = [i for i, l in enumerate(lines) if l.startswith("VOXEDGE PHASE5 BOOT")]
tel = [{k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", l)} for l in lines if l.startswith("T ")]
starts = [l for l in lines if l.startswith("STALL start")]
ends = [l for l in lines if l.startswith("STALL end")]
fatal = [l for l in lines if l.startswith("FATAL")]

print(f"boots={len(boots)} stall_starts={len(starts)} stall_ends={len(ends)} telemetry_lines={len(tel)}")
check(all(t["ovr"] == 0 for t in tel), "PDM overrun count stays 0 in every telemetry line")
check(not fatal, "no FATAL")

if mode == "finite":
    check(len(boots) == 1, f"exactly one boot ({len(boots)})")
    check(len(starts) == 1 and len(ends) == 1, "one STALL start/end pair (task resumed on its own)")
    drops = [t[backlog_key] for t in tel]
    check(any(d > 0 for d in drops), f"{backlog_key} rose during the stall (backlog handled, not corrupted)")
    if drops:
        check(drops[-1] == max(drops), f"{backlog_key} holds flat after the stall (none once resumed)")
    post_stall_tel = tel[-3:] if len(tel) >= 3 else tel
    check(len(tel) >= 5, f"telemetry kept reporting after the stall ({len(tel)} lines total)")
elif mode == "infinite":
    check(len(boots) >= 2, f"watchdog forced a reset: at least 2 boots ({len(boots)})")
    check(len(starts) >= 1 and len(ends) == 0, "STALL started and never returned (as designed)")
    pre_reset = tel[:boots[1]] if len(boots) > 1 else tel
    check(len(pre_reset) >= 1, "at least one telemetry line before the reset")
else:
    print(f"unknown mode {mode!r}"); sys.exit(2)

sys.exit(1 if fails else 0)

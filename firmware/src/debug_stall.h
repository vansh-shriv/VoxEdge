#ifndef DEBUG_STALL_H
#define DEBUG_STALL_H

#include <stdint.h>

/* Deliberate busy-loop injection for Phase 5 robustness testing (spec 4.4). Compile-time only, so
 * a normal build can never accidentally stall: STALL_TASK selects which task's call site fires
 * (STALL_TASK_DSP / STALL_TASK_INFERENCE, 0 = never), STALL_AT_SEQ is the hop sequence number that
 * triggers it (fires once), STALL_MS is how long to busy-spin with interrupts enabled (0 = forever,
 * i.e. simulates an unrecoverable hang; the watchdog is the only way out of that one).
 *
 * The call sites are in the DSP and inference tasks specifically because they sit above telemetry
 * in priority: a stall there starves telemetry's watchdog feed and its UART output, but never the
 * higher-priority PDM ISR or capture task, which is exactly the scenario spec 4.4 asks to test. */

#define STALL_TASK_NONE       0
#define STALL_TASK_DSP        1
#define STALL_TASK_INFERENCE  2

#ifndef STALL_TASK
#define STALL_TASK STALL_TASK_NONE
#endif
#ifndef STALL_AT_SEQ
#define STALL_AT_SEQ 0xFFFFFFFFu
#endif
#ifndef STALL_MS
#define STALL_MS 0
#endif

/* No-op unless task_id == STALL_TASK && seq == STALL_AT_SEQ; fires at most once per boot. */
void debug_stall_maybe(int task_id, uint32_t seq);

#endif

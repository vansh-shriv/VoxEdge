#include "debug_stall.h"
#include "voxedge.h"

#define REG(a) (*(volatile uint32_t *)(a))
#define DEMCR       REG(0xE000EDFCUL)
#define DWT_CTRL    REG(0xE0001000UL)
#define DWT_CYCCNT  REG(0xE0001004UL)
#define CYCLES_PER_MS 64000u   /* matches the 64 MHz assumption used everywhere else (sim/boot.resc) */

void debug_stall_maybe(int task_id, uint32_t seq)
{
#if STALL_TASK != STALL_TASK_NONE
    static uint8_t fired;
    if (fired || task_id != STALL_TASK || seq != STALL_AT_SEQ) return;
    fired = 1;

    DEMCR |= 1u << 24;
    DWT_CTRL |= 1u;

    uart_puts("STALL start task="); uart_puti(task_id);
    uart_puts(" seq="); uart_putu(seq); uart_puts(" ms="); uart_putu(STALL_MS); uart_puts("\n");

#if STALL_MS == 0
    for (;;) { __asm volatile(""); }   /* never returns: only the watchdog recovers from this */
#else
    /* DWT_CYCCNT is served by a Python-scripted Renode peripheral (sim/platform.repl); reading it
     * every spin iteration would invoke that script millions of times and make the simulation
     * itself hang for minutes. Spin on a cheap register-only counter and poll DWT_CYCCNT rarely. */
    uint32_t t0 = DWT_CYCCNT;
    uint32_t target = (uint32_t)STALL_MS * CYCLES_PER_MS;
    for (;;) {
        for (volatile uint32_t k = 0; k < 200000u; k++) { }
        if (DWT_CYCCNT - t0 >= target) break;
    }
    uart_puts("STALL end task="); uart_puti(task_id); uart_puts(" seq="); uart_putu(seq); uart_puts("\n");
#endif
#else
    (void)task_id; (void)seq;
#endif
}

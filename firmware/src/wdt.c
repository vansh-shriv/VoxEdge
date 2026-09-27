#include "wdt.h"

#define REG(a) (*(volatile uint32_t *)(a))

#define WDT_BASE 0x40010000UL
#define WDT_TASKS_START     REG(WDT_BASE + 0x000)
#define WDT_EVENTS_TIMEOUT  REG(WDT_BASE + 0x100)
#define WDT_INTENSET        REG(WDT_BASE + 0x304)
#define WDT_RUNSTATUS       REG(WDT_BASE + 0x400)
#define WDT_CRV             REG(WDT_BASE + 0x504)   /* reload value, LFCLK (32768 Hz) ticks */
#define WDT_RREN            REG(WDT_BASE + 0x508)   /* reload-request-register enable, bitmask */
#define WDT_CONFIG          REG(WDT_BASE + 0x50C)
#define WDT_RR0             REG(WDT_BASE + 0x600)
#define WDT_RR_MAGIC        0x6E524635UL
#define WDT_IRQn            16

#define POWER_RESETREAS     REG(0x40000400UL)
#define RESETREAS_DOG_BIT   (1u << 1)

#define NVIC_ISER0          REG(0xE000E100UL)
#define AIRCR               REG(0xE000ED0CUL)
#define AIRCR_SYSRESETREQ   0x05FA0004UL             /* VECTKEY | SYSRESETREQ */

static int s_was_dog;

void wdt_init(uint32_t timeout_ms)
{
    /* Latch and clear the reset reason before anything else can reset the chip again. */
    s_was_dog = (POWER_RESETREAS & RESETREAS_DOG_BIT) != 0;
    POWER_RESETREAS = 0xFFFFFFFFu;   /* write-1-to-clear */

    WDT_CONFIG = 1u;                 /* SLEEP=Run: keep counting through the idle-hook WFI */
    WDT_CRV = (uint32_t)(((uint64_t)timeout_ms * 32768u) / 1000u) - 1u;
    WDT_RREN = 1u;                   /* enable reload register 0 */
    WDT_INTENSET = 1u;               /* EVENTS_TIMEOUT interrupt */
    NVIC_ISER0 = 1u << WDT_IRQn;
    WDT_TASKS_START = 1u;
    wdt_feed();
}

void wdt_feed(void) { WDT_RR0 = WDT_RR_MAGIC; }

int wdt_was_reset_cause(void) { return s_was_dog; }

/* Belt and braces: force a full core reset from the ISR itself, regardless of whether the
 * simulated/real WDT peripheral also resets the chip on timeout. */
void WDT_IRQHandler(void)
{
    WDT_EVENTS_TIMEOUT = 0;
    AIRCR = AIRCR_SYSRESETREQ;
    for (;;) ;
}

#ifndef WDT_H
#define WDT_H

#include <stdint.h>

/* nRF52840 hardware watchdog (WDT), 32.768 kHz LFCLK-clocked, runs through CPU sleep (WFI). Only
 * telemetry_task feeds it, once per second, so any task at or above telemetry's priority that
 * never blocks (a stall/deadlock) starves telemetry and lets the watchdog fire. */
void wdt_init(uint32_t timeout_ms);
void wdt_feed(void);

/* True if the last reset was caused by the watchdog (RESETREAS.DOG), read once at boot before
 * this or any later reset clears it. */
int wdt_was_reset_cause(void);

#endif

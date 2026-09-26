/*
 * Telemetry: lowest-priority task, the only steady-state UART user. Emits
 *   E <seq> <R|F> <tick>   on wake on/off events
 *   T key=value ...        every second
 */
#include "voxedge.h"
#include "task.h"

static void kv(const char *k, uint32_t v) { uart_puts(" "); uart_puts(k); uart_puts("="); uart_putu(v); }

void telemetry_task(void *arg)
{
    (void)arg;
    event_msg_t e;
    TickType_t next = xTaskGetTickCount() + pdMS_TO_TICKS(1000);

    for (;;) {
        TickType_t now = xTaskGetTickCount();
        TickType_t wait = (next > now) ? next - now : 0;
        if (xQueueReceive(g_evt_q, &e, wait) == pdPASS) {
            char t[2] = { (char)e.type, 0 };
            uart_puts("E "); uart_putu(e.seq); uart_puts(" "); uart_puts(t);
            uart_puts(" "); uart_putu(e.tick); uart_puts("\n");
        }
        if (xTaskGetTickCount() >= next) {
            next += pdMS_TO_TICKS(1000);
            uart_puts("T");
            kv("tick", xTaskGetTickCount());
            kv("pdm", g_stats.pdm_frames);   kv("hops", g_stats.hops);
            kv("win", g_stats.windows);      kv("inf", g_stats.inferences);
            kv("ovr", g_stats.pdm_overruns); kv("dspdrop", g_stats.dsp_drops);
            kv("infdrop", g_stats.inf_drops); kv("evtdrop", g_stats.evt_drops);
            kv("stk_cap", uxTaskGetStackHighWaterMark(g_capture_h));
            kv("stk_dsp", uxTaskGetStackHighWaterMark(g_dsp_h));
            kv("stk_inf", uxTaskGetStackHighWaterMark(g_inf_h));
            kv("stk_tel", uxTaskGetStackHighWaterMark(NULL));
            kv("heap", xPortGetFreeHeapSize()); kv("heapmin", xPortGetMinimumEverFreeHeapSize());
            uart_puts("\n");
        }
    }
}

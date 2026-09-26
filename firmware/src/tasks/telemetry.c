/*
 * Telemetry: lowest-priority task, the only steady-state UART user. Waits on a queue set
 * (event queue + debug feature-dump queue) with a 1 s timeout. Emits
 *   E <seq> <R|F> <tick>        wake on/off events
 *   F <seq> <40 x float32 hex>  one log-mel vector (only when VOXEDGE_DUMP_FEATURES=1)
 *   T key=value ...             every second
 */
#include "voxedge.h"
#include "task.h"

static void kv(const char *k, uint32_t v) { uart_puts(" "); uart_puts(k); uart_puts("="); uart_putu(v); }

void telemetry_task(void *arg)
{
    (void)arg;
    static event_msg_t e;
    static feature_msg_t f;
    TickType_t next = xTaskGetTickCount() + pdMS_TO_TICKS(1000);

    for (;;) {
        TickType_t now = xTaskGetTickCount();
        TickType_t wait = (next > now) ? next - now : 0;
        QueueSetMemberHandle_t m = xQueueSelectFromSet(g_tel_set, wait);
        if (m == g_evt_q && xQueueReceive(g_evt_q, &e, 0) == pdPASS) {
            char t[2] = { (char)e.type, 0 };
            uart_puts("E "); uart_putu(e.seq); uart_puts(" "); uart_puts(t);
            uart_puts(" "); uart_putu(e.tick); uart_puts("\n");
        } else if (m == g_dump_q && xQueueReceive(g_dump_q, &f, 0) == pdPASS) {
            uart_puts("F "); uart_putu(f.seq); uart_puts(" ");
            for (int i = 0; i < FEAT_N_MELS; i++) {
                union { float f; uint32_t u; } c = { .f = f.logmel[i] };
                uart_puthex32(c.u);
            }
            uart_puts("\n");
        }
        if (xTaskGetTickCount() >= next) {
            next += pdMS_TO_TICKS(1000);
            uart_puts("T");
            kv("tick", xTaskGetTickCount());
            kv("pdm", g_stats.pdm_frames);   kv("hops", g_stats.hops);
            kv("win", g_stats.windows);      kv("inf", g_stats.inferences);
            kv("ovr", g_stats.pdm_overruns); kv("dspdrop", g_stats.dsp_drops);
            kv("infdrop", g_stats.inf_drops); kv("evtdrop", g_stats.evt_drops);
            kv("dumpdrop", g_stats.dump_drops);
            kv("dspcyc_last", g_stats.dsp_cyc_last); kv("dspcyc_max", g_stats.dsp_cyc_max);
            kv("dspcyc_avg", g_stats.windows ? g_stats.dsp_cyc_sum / g_stats.windows : 0);
            kv("stk_cap", uxTaskGetStackHighWaterMark(g_capture_h));
            kv("stk_dsp", uxTaskGetStackHighWaterMark(g_dsp_h));
            kv("stk_inf", uxTaskGetStackHighWaterMark(g_inf_h));
            kv("stk_tel", uxTaskGetStackHighWaterMark(NULL));
            kv("heap", xPortGetFreeHeapSize()); kv("heapmin", xPortGetMinimumEverFreeHeapSize());
            uart_puts("\n");
        }
    }
}

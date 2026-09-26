/*
 * Telemetry: lowest-priority task, the only steady-state UART user. Waits on a queue set with a
 * 1 s timeout. Emits
 *   E <seq> <R|F> <tick>          wake on/off events
 *   F <seq> <40 x float32 hex>    log-mel vector          (VOXEDGE_DUMP_FEATURES=1)
 *   L <seq> <l0> <l1> <l2> <pk>   int8 logits, P(key) x1000 per inference (VOXEDGE_DUMP_INFER=1)
 *   Q <seq> <3920 x int8 hex>     model input tensor, sampled            (VOXEDGE_DUMP_INFER=1)
 *   T key=value ...               every second
 */
#include "voxedge.h"
#include "task.h"

static void kv(const char *k, uint32_t v) { uart_puts(" "); uart_puts(k); uart_puts("="); uart_putu(v); }

void telemetry_task(void *arg)
{
    (void)arg;
    static event_msg_t e;
    static feature_msg_t f;
    static infl_msg_t l;
    static infq_msg_t q;
    TickType_t next = xTaskGetTickCount() + pdMS_TO_TICKS(1000);

    for (;;) {
        TickType_t now = xTaskGetTickCount();
        TickType_t wait = (next > now) ? next - now : 0;
        QueueSetMemberHandle_t m = xQueueSelectFromSet(g_tel_set, wait);
        if (m && m == g_evt_q && xQueueReceive(g_evt_q, &e, 0) == pdPASS) {
            char t[2] = { (char)e.type, 0 };
            uart_puts("E "); uart_putu(e.seq); uart_puts(" "); uart_puts(t);
            uart_puts(" "); uart_putu(e.tick); uart_puts("\n");
        } else if (m && m == g_dump_q && xQueueReceive(g_dump_q, &f, 0) == pdPASS) {
            uart_puts("F "); uart_putu(f.seq); uart_puts(" ");
            for (int i = 0; i < FEAT_N_MELS; i++) {
                union { float f; uint32_t u; } c = { .f = f.logmel[i] };
                uart_puthex32(c.u);
            }
            uart_puts("\n");
        } else if (m && m == g_infl_q && xQueueReceive(g_infl_q, &l, 0) == pdPASS) {
            uart_puts("L "); uart_putu(l.seq);
            for (int i = 0; i < KWS_N_CLASSES; i++) { uart_puts(" "); uart_puti(l.logits[i]); }
            uart_puts(" "); uart_putu(l.pkey_permille); uart_puts("\n");
        } else if (m && m == g_infq_q && xQueueReceive(g_infq_q, &q, 0) == pdPASS) {
            uart_puts("Q "); uart_putu(q.seq); uart_puts(" ");
            uart_puthex_bytes((const uint8_t *)q.input, KWS_INPUT_BYTES);
            uart_puts("\n");
        }
        if (xTaskGetTickCount() >= next) {
            next += pdMS_TO_TICKS(1000);
            uart_puts("T");
            kv("tick", xTaskGetTickCount());
            kv("pdm", g_stats.pdm_frames);   kv("hops", g_stats.hops);
            kv("win", g_stats.windows);
            kv("ovr", g_stats.pdm_overruns); kv("dspdrop", g_stats.dsp_drops);
            kv("evtdrop", g_stats.evt_drops); kv("dumpdrop", g_stats.dump_drops);
            kv("due", g_stats.infer_due);    kv("skipped", g_stats.infer_skipped);
            kv("runs", g_stats.model_runs);  kv("pkey", g_stats.pkey_permille);
            kv("dspcyc_last", g_stats.dsp_cyc_last); kv("dspcyc_max", g_stats.dsp_cyc_max);
            kv("dspcyc_avg", g_stats.windows ? g_stats.dsp_cyc_sum / g_stats.windows : 0);
            kv("infcyc_last", g_stats.infer_cyc_last); kv("infcyc_max", g_stats.infer_cyc_max);
            kv("infcyc_avg", g_stats.model_runs ? g_stats.infer_cyc_sum / g_stats.model_runs : 0);
            kv("arena", g_stats.arena_used);
            kv("stk_cap", uxTaskGetStackHighWaterMark(g_capture_h));
            kv("stk_dsp", uxTaskGetStackHighWaterMark(g_dsp_h));
            kv("stk_inf", uxTaskGetStackHighWaterMark(g_inf_h));
            kv("stk_tel", uxTaskGetStackHighWaterMark(NULL));
            kv("heap", xPortGetFreeHeapSize()); kv("heapmin", xPortGetMinimumEverFreeHeapSize());
            uart_puts("\n");
        }
    }
}

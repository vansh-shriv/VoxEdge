/*
 * Inference task: runs the int8 TFLite-Micro model on the ring snapshot handed over by the DSP
 * task, converts logits to P(keyword), and applies threshold + debounce + the wake GPIO action.
 * kws_infer() is timed with the DWT cycle counter.
 */
#include <math.h>
#include <string.h>
#include "voxedge.h"
#include "task.h"

#define REG(a) (*(volatile uint32_t *)(a))
#define DWT_CYCCNT  REG(0xE0001004UL)

#ifndef KWS_DUMP_INPUT_EVERY
#define KWS_DUMP_INPUT_EVERY 8
#endif

/* Decision logic (Phase 6 will tune these on the streaming corpus). */
/* At the default 400 ms cadence a multi-hit debounce would add whole seconds of latency, so a single
 * inference above P_ON raises wake. P_ON=0.9 is the operating point from the Phase 3 table. */
#ifndef KWS_P_ON
#define KWS_P_ON        0.90f     /* P(keyword) needed for a "hit" inference */
#endif
#define P_ON            KWS_P_ON
#define ON_STREAK       1         /* consecutive hits to raise wake */
#define OFF_STREAK      1         /* consecutive misses to drop it */

int8_t g_snap[KWS_INPUT_BYTES];
volatile uint32_t g_snap_seq;
volatile uint8_t g_infer_busy;

static float p_keyword(const int8_t *logits)
{
    float l[KWS_N_CLASSES], m = -1e30f, sum = 0.0f;
    const float s = kws_output_scale();
    const int z = kws_output_zero_point();
    for (int i = 0; i < KWS_N_CLASSES; i++) { l[i] = ((int)logits[i] - z) * s; if (l[i] > m) m = l[i]; }
    for (int i = 0; i < KWS_N_CLASSES; i++) { l[i] = expf(l[i] - m); sum += l[i]; }
    return l[KWS_CLASS_KEY] / sum;
}

void inference_task(void *arg)
{
    (void)arg;
    int8_t logits[KWS_N_CLASSES];
    int active = 0;
    uint32_t streak = 0, runs = 0;
#if VOXEDGE_DUMP_INFER
    static infq_msg_t qm;
#endif

    for (;;) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        uint32_t seq = g_snap_seq;

        uint32_t t0 = DWT_CYCCNT;
        int rc = kws_infer(g_snap, logits);
        uint32_t dt = DWT_CYCCNT - t0;
        if (rc != 0) { g_infer_busy = 0; continue; }

        float p = p_keyword(logits);
        g_stats.pkey_permille = (uint32_t)(p * 1000.0f + 0.5f);
        g_stats.infer_cyc_last = dt;
        g_stats.infer_cyc_sum += dt;
        if (dt > g_stats.infer_cyc_max) g_stats.infer_cyc_max = dt;
        g_stats.model_runs++;

#if VOXEDGE_DUMP_INFER
        {
            infl_msg_t lm = { seq, { logits[0], logits[1], logits[2] }, (uint16_t)g_stats.pkey_permille };
            if (xQueueSend(g_infl_q, &lm, 0) != pdPASS) g_stats.dump_drops++;
            if (runs % KWS_DUMP_INPUT_EVERY == 0) {    /* sampled full input tensors for bit-exact parity checks */
                qm.seq = seq;
                memcpy(qm.input, g_snap, KWS_INPUT_BYTES);
                if (xQueueSend(g_infq_q, &qm, 0) != pdPASS) g_stats.dump_drops++;
            }
        }
#endif
        runs++;
        g_infer_busy = 0;       /* snapshot consumed; DSP may hand over the next one */

        int hit = p >= P_ON;
        streak = (hit != active) ? streak + 1 : 0;
        if (streak >= (active ? OFF_STREAK : ON_STREAK)) {
            active = hit;
            streak = 0;
            wake_gpio_set(active);
            event_msg_t e = { seq, xTaskGetTickCount(), active ? EVT_WAKE_ON : EVT_WAKE_OFF };
            if (xQueueSend(g_evt_q, &e, 0) != pdPASS) g_stats.evt_drops++;
        }
    }
}

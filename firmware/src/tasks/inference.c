/*
 * Inference task (Phase 1 stub) + decision logic. The "model" is a placeholder score derived
 * from energy; threshold + debounce + GPIO action are the real interface the TFLite model
 * will plug into in Phase 4.
 */
#include "voxedge.h"
#include "task.h"

#ifndef VOXEDGE_DUMP_FEATURES
#define VOXEDGE_DUMP_FEATURES 0   /* 1: forward every feature vector to telemetry for host cross-checking */
#endif

#define SCORE_ON_PERMILLE   500
#define DEBOUNCE_FRAMES     3

static uint32_t stub_score_permille(const feature_msg_t *f)
{
    uint32_t s = f->energy / 1000u;
    return s > 1000u ? 1000u : s;
}

void inference_task(void *arg)
{
    (void)arg;
    static feature_msg_t f;
    int active = 0;
    uint32_t streak = 0;

    for (;;) {
        if (xQueueReceive(g_inf_q, &f, portMAX_DELAY) != pdPASS) continue;
        g_stats.inferences++;
#if VOXEDGE_DUMP_FEATURES
        if (xQueueSend(g_dump_q, &f, 0) != pdPASS) g_stats.dump_drops++;
#endif
        int hit = stub_score_permille(&f) >= SCORE_ON_PERMILLE;
        streak = (hit != active) ? streak + 1 : 0;
        if (streak >= DEBOUNCE_FRAMES) {
            active = hit;
            streak = 0;
            wake_gpio_set(active);
            event_msg_t e = { f.seq, xTaskGetTickCount(), active ? EVT_WAKE_ON : EVT_WAKE_OFF };
            if (xQueueSend(g_evt_q, &e, 0) != pdPASS) g_stats.evt_drops++;
        }
    }
}

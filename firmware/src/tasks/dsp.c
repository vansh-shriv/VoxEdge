/*
 * DSP task: log-mel features (dsp/features.c) per 30 ms window, pushed into the int8 feature ring.
 * Every KWS_INFER_EVERY hops (once the ring holds a full clip) it snapshots the ring for the
 * inference task. The ring lives here so that features are never lost when inference is slow:
 * if the inference task is still busy the trigger is skipped and counted, not queued.
 * features_compute() is timed with the DWT cycle counter.
 */
#include "voxedge.h"
#include "dsp/features.h"
#include "dsp/feature_ring.h"
#include "task.h"

#define REG(a) (*(volatile uint32_t *)(a))
#define DEMCR       REG(0xE000EDFCUL)
#define DWT_CTRL    REG(0xE0001000UL)
#define DWT_CYCCNT  REG(0xE0001004UL)

#ifndef KWS_INFER_EVERY
#define KWS_INFER_EVERY 5
#endif

void dsp_task(void *arg)
{
    (void)arg;
    static window_msg_t win;
    static float logmel[FEAT_N_MELS];

    features_init();
    DEMCR |= 1u << 24;       /* TRCENA */
    DWT_CTRL |= 1u;          /* CYCCNTENA */

    for (;;) {
        if (xQueueReceive(g_dsp_q, &win, portMAX_DELAY) != pdPASS) continue;
        debug_stall_maybe(STALL_TASK_DSP, win.seq);

        uint32_t t0 = DWT_CYCCNT;
        features_compute(win.samples, logmel);
        uint32_t dt = DWT_CYCCNT - t0;
        g_stats.dsp_cyc_last = dt;
        g_stats.dsp_cyc_sum += dt;
        if (dt > g_stats.dsp_cyc_max) g_stats.dsp_cyc_max = dt;
        g_stats.windows++;

#if VOXEDGE_DUMP_FEATURES
        static feature_msg_t fm;
        fm.seq = win.seq;
        for (int i = 0; i < FEAT_N_MELS; i++) fm.logmel[i] = logmel[i];
        if (xQueueSend(g_dump_q, &fm, 0) != pdPASS) g_stats.dump_drops++;
#endif

        ring_push(logmel);
        if (ring_full() && win.seq % KWS_INFER_EVERY == 0) {
            g_stats.infer_due++;
            if (g_infer_busy) {
                g_stats.infer_skipped++;
            } else {
                ring_snapshot(g_snap);
                g_snap_seq = win.seq;
                g_infer_busy = 1;
                xTaskNotifyGive(g_inf_h);
            }
        }
    }
}

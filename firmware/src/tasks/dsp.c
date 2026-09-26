/*
 * DSP task: log-mel features (dsp/features.c) per 30 ms window. The window energy + threshold VAD
 * from Phase 1 is kept as a cheap gate/stub signal for the placeholder inference task.
 * features_compute() is timed with the DWT cycle counter.
 */
#include "voxedge.h"
#include "dsp/features.h"

#define REG(a) (*(volatile uint32_t *)(a))
#define DEMCR       REG(0xE000EDFCUL)
#define DWT_CTRL    REG(0xE0001000UL)
#define DWT_CYCCNT  REG(0xE0001004UL)

#define VAD_MEAN_SQ_THRESHOLD 250000u    /* ~500 RMS on int16 samples */

void dsp_task(void *arg)
{
    (void)arg;
    static window_msg_t win;
    static feature_msg_t f;

    features_init();
    DEMCR |= 1u << 24;       /* TRCENA */
    DWT_CTRL |= 1u;          /* CYCCNTENA */

    for (;;) {
        if (xQueueReceive(g_dsp_q, &win, portMAX_DELAY) != pdPASS) continue;

        uint64_t acc = 0;
        for (int i = 0; i < WINDOW_SAMPLES; i++) acc += (int32_t)win.samples[i] * win.samples[i];
        f.seq = win.seq;
        f.energy = (uint32_t)(acc / WINDOW_SAMPLES);
        f.vad = f.energy > VAD_MEAN_SQ_THRESHOLD;

        uint32_t t0 = DWT_CYCCNT;
        features_compute(win.samples, f.logmel);
        uint32_t dt = DWT_CYCCNT - t0;
        g_stats.dsp_cyc_last = dt;
        g_stats.dsp_cyc_sum += dt;
        if (dt > g_stats.dsp_cyc_max) g_stats.dsp_cyc_max = dt;

        g_stats.windows++;
        if (xQueueSend(g_inf_q, &f, 0) != pdPASS) g_stats.inf_drops++;
    }
}

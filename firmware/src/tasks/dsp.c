/* DSP task (Phase 1 stub): window energy + energy-threshold VAD. Real features arrive in Phase 2. */
#include "voxedge.h"

#define VAD_MEAN_SQ_THRESHOLD 250000u    /* ~500 RMS on int16 samples */

void dsp_task(void *arg)
{
    (void)arg;
    static window_msg_t win;
    feature_msg_t f;

    for (;;) {
        if (xQueueReceive(g_dsp_q, &win, portMAX_DELAY) != pdPASS) continue;
        uint64_t acc = 0;
        for (int i = 0; i < WINDOW_SAMPLES; i++) acc += (int32_t)win.samples[i] * win.samples[i];
        f.seq = win.seq;
        f.energy = (uint32_t)(acc / WINDOW_SAMPLES);
        f.vad = f.energy > VAD_MEAN_SQ_THRESHOLD;
        g_stats.windows++;
        if (xQueueSend(g_inf_q, &f, 0) != pdPASS) g_stats.inf_drops++;
    }
}

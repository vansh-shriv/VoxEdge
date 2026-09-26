/* Capture/framer: 10 ms hops from the ISR -> overlapping 30 ms windows (10 ms hop). */
#include <string.h>
#include "voxedge.h"

void capture_task(void *arg)
{
    (void)arg;
    static int16_t hop[HOP_SAMPLES];
    static window_msg_t win;
    uint32_t seq = 0;

    for (;;) {
        if (xStreamBufferReceive(g_pdm_stream, hop, HOP_BYTES, portMAX_DELAY) != HOP_BYTES)
            continue;
        memmove(win.samples, win.samples + HOP_SAMPLES, (WINDOW_SAMPLES - HOP_SAMPLES) * 2);
        memcpy(win.samples + WINDOW_SAMPLES - HOP_SAMPLES, hop, HOP_BYTES);
        g_stats.hops++;
        if (seq >= WINDOW_SAMPLES / HOP_SAMPLES - 1) {   /* window is full */
            win.seq = seq;
            if (xQueueSend(g_dsp_q, &win, 0) != pdPASS) g_stats.dsp_drops++;
        }
        seq++;
    }
}

#include "voxedge.h"
#include "task.h"
#include "dsp/feature_ring.h"

stats_t g_stats;
StreamBufferHandle_t g_pdm_stream;
QueueHandle_t g_dsp_q, g_evt_q, g_dump_q, g_infl_q, g_infq_q;
QueueSetHandle_t g_tel_set;
TaskHandle_t g_capture_h, g_dsp_h, g_inf_h, g_tel_h;

static void fatal(const char *what)
{
    taskDISABLE_INTERRUPTS();
    uart_puts("FATAL "); uart_puts(what); uart_puts("\n");
    for (;;) ;
}

void vAssertCalled(const char *file, int line) { (void)file; (void)line; fatal("assert"); }
void vApplicationMallocFailedHook(void) { fatal("malloc"); }
void vApplicationStackOverflowHook(TaskHandle_t t, char *name) { (void)t; (void)name; fatal("stack"); }
void vApplicationIdleHook(void) { __asm volatile("wfi"); }   /* CPU sleeps between interrupts */

int main(void)
{
    uart_init();
    uart_puts("VOXEDGE PHASE5 BOOT\n");
    if (wdt_was_reset_cause()) uart_puts("RESET_CAUSE=WDT\n");
    wake_gpio_init();

    int rc = kws_init();
    if (rc != 0) { uart_puts("kws_init rc="); uart_puti(rc); uart_puts("\n"); fatal("model"); }
    ring_init(kws_input_scale(), kws_input_zero_point());
    g_stats.arena_used = kws_arena_used();

    g_pdm_stream = xStreamBufferCreate(PDM_STREAM_HOPS * HOP_BYTES, HOP_BYTES);
    g_dsp_q = xQueueCreate(2, sizeof(window_msg_t));
    g_evt_q = xQueueCreate(8, sizeof(event_msg_t));
    g_tel_set = xQueueCreateSet(8 + 8 + 16 + 2);
    if (!g_pdm_stream || !g_dsp_q || !g_evt_q || !g_tel_set) fatal("alloc");
    xQueueAddToSet(g_evt_q, g_tel_set);
#if VOXEDGE_DUMP_FEATURES
    g_dump_q = xQueueCreate(8, sizeof(feature_msg_t));
    if (!g_dump_q) fatal("alloc");
    xQueueAddToSet(g_dump_q, g_tel_set);
#endif
#if VOXEDGE_DUMP_INFER
    g_infl_q = xQueueCreate(16, sizeof(infl_msg_t));
    g_infq_q = xQueueCreate(2, sizeof(infq_msg_t));
    if (!g_infl_q || !g_infq_q) fatal("alloc");
    xQueueAddToSet(g_infl_q, g_tel_set);
    xQueueAddToSet(g_infq_q, g_tel_set);
#endif

    xTaskCreate(capture_task,   "capture", 256,  NULL, PRIO_CAPTURE,   &g_capture_h);
    xTaskCreate(dsp_task,       "dsp",     256,  NULL, PRIO_DSP,       &g_dsp_h);
    xTaskCreate(inference_task, "infer",   1024, NULL, PRIO_INFERENCE, &g_inf_h);
    xTaskCreate(telemetry_task, "telem",   256,  NULL, PRIO_TELEMETRY, &g_tel_h);
    if (!g_capture_h || !g_dsp_h || !g_inf_h || !g_tel_h) fatal("task");

    pdm_init(g_pdm_stream);
    pdm_start();
    wdt_init(WDT_TIMEOUT_MS);
    vTaskStartScheduler();
    fatal("scheduler");
    return 0;
}

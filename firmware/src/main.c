#include "voxedge.h"
#include "task.h"

stats_t g_stats;
StreamBufferHandle_t g_pdm_stream;
QueueHandle_t g_dsp_q, g_inf_q, g_evt_q, g_dump_q;
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
    uart_puts("VOXEDGE PHASE2 BOOT\n");
    wake_gpio_init();

    g_pdm_stream = xStreamBufferCreate(PDM_STREAM_HOPS * HOP_BYTES, HOP_BYTES);
    g_dsp_q = xQueueCreate(2, sizeof(window_msg_t));
    g_inf_q = xQueueCreate(4, sizeof(feature_msg_t));
    g_evt_q = xQueueCreate(8, sizeof(event_msg_t));
    g_dump_q = xQueueCreate(8, sizeof(feature_msg_t));
    g_tel_set = xQueueCreateSet(8 + 8);
    if (!g_pdm_stream || !g_dsp_q || !g_inf_q || !g_evt_q || !g_dump_q || !g_tel_set) fatal("alloc");
    xQueueAddToSet(g_evt_q, g_tel_set);
    xQueueAddToSet(g_dump_q, g_tel_set);

    xTaskCreate(capture_task,   "capture", 256, NULL, PRIO_CAPTURE,   &g_capture_h);
    xTaskCreate(dsp_task,       "dsp",     256, NULL, PRIO_DSP,       &g_dsp_h);
    xTaskCreate(inference_task, "infer",   256, NULL, PRIO_INFERENCE, &g_inf_h);
    xTaskCreate(telemetry_task, "telem",   256, NULL, PRIO_TELEMETRY, &g_tel_h);
    if (!g_capture_h || !g_dsp_h || !g_inf_h || !g_tel_h) fatal("task");

    pdm_init(g_pdm_stream);
    pdm_start();
    vTaskStartScheduler();
    fatal("scheduler");
    return 0;
}

/*
 * PDM capture: EasyDMA double buffer. The ISR only re-arms the next buffer and copies the
 * finished one into a stream buffer for the capture task. It never blocks, and drops a whole
 * frame (counted as an overrun) rather than writing a partial one.
 */
#include "voxedge.h"

#define REG(a) (*(volatile uint32_t *)(a))
#define PDM_BASE 0x4001D000UL
#define PDM_TASKS_START     REG(PDM_BASE + 0x000)
#define PDM_EVENTS_STARTED  REG(PDM_BASE + 0x100)
#define PDM_EVENTS_END      REG(PDM_BASE + 0x108)
#define PDM_INTENSET        REG(PDM_BASE + 0x304)
#define PDM_ENABLE          REG(PDM_BASE + 0x500)
#define PDM_MODE            REG(PDM_BASE + 0x508)
#define PDM_GAINL           REG(PDM_BASE + 0x518)
#define PDM_GAINR           REG(PDM_BASE + 0x51C)
#define PDM_RATIO           REG(PDM_BASE + 0x520)
#define PDM_PSEL_CLK        REG(PDM_BASE + 0x540)
#define PDM_PSEL_DIN        REG(PDM_BASE + 0x544)
#define PDM_SAMPLE_PTR      REG(PDM_BASE + 0x560)
#define PDM_SAMPLE_MAXCNT   REG(PDM_BASE + 0x564)
#define PDM_IRQn            29
#define NVIC_ISER0          REG(0xE000E100UL)
#define NVIC_IPR(n)         (*(volatile uint8_t *)(0xE000E400UL + (n)))

static int16_t s_buf[2][HOP_SAMPLES];
static uint32_t s_started, s_ended;
static StreamBufferHandle_t s_sink;

void pdm_init(StreamBufferHandle_t sink)
{
    s_sink = sink;
    PDM_PSEL_CLK = 26;
    PDM_PSEL_DIN = 25;
    PDM_MODE = 1;                       /* mono */
    PDM_GAINL = 0x28; PDM_GAINR = 0x28;
    PDM_RATIO = 0;
    PDM_SAMPLE_MAXCNT = HOP_SAMPLES;
    PDM_SAMPLE_PTR = (uint32_t)s_buf[0];
    PDM_ENABLE = 1;
    PDM_INTENSET = (1u << 0) | (1u << 2);            /* STARTED, END */
    NVIC_IPR(PDM_IRQn) = configMAX_SYSCALL_INTERRUPT_PRIORITY;  /* may call FromISR APIs */
    NVIC_ISER0 = 1u << PDM_IRQn;
}

void pdm_start(void) { PDM_TASKS_START = 1; }

void PDM_IRQHandler(void)
{
    BaseType_t woken = pdFALSE;
    if (PDM_EVENTS_STARTED) {
        PDM_EVENTS_STARTED = 0;
        s_started++;
        PDM_SAMPLE_PTR = (uint32_t)s_buf[s_started & 1];   /* arm the next buffer */
    }
    if (PDM_EVENTS_END) {
        PDM_EVENTS_END = 0;
        g_stats.pdm_frames++;
        if (xStreamBufferSpacesAvailable(s_sink) >= HOP_BYTES)
            xStreamBufferSendFromISR(s_sink, s_buf[s_ended & 1], HOP_BYTES, &woken);
        else
            g_stats.pdm_overruns++;
        s_ended++;
    }
    portYIELD_FROM_ISR(woken);
}

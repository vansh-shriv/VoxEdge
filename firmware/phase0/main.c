/*
 * VoxEdge Phase 0: PDM capture -> UART dump.
 * The ISR only flips double-buffer pointers and flags a ready buffer; main() dumps
 * ready buffers to UART as hex lines "S:<seq>:<hex little-endian int16 samples>".
 */
#include <stdint.h>

#define REG(a) (*(volatile uint32_t *)(a))

#define PDM_BASE 0x4001D000UL
#define PDM_TASKS_START     REG(PDM_BASE + 0x000)
#define PDM_EVENTS_STARTED  REG(PDM_BASE + 0x100)
#define PDM_EVENTS_STOPPED  REG(PDM_BASE + 0x104)
#define PDM_EVENTS_END      REG(PDM_BASE + 0x108)
#define PDM_INTENSET        REG(PDM_BASE + 0x304)
#define PDM_ENABLE          REG(PDM_BASE + 0x500)
#define PDM_PDMCLKCTRL      REG(PDM_BASE + 0x504)
#define PDM_MODE            REG(PDM_BASE + 0x508)
#define PDM_GAINL           REG(PDM_BASE + 0x518)
#define PDM_GAINR           REG(PDM_BASE + 0x51C)
#define PDM_RATIO           REG(PDM_BASE + 0x520)
#define PDM_PSEL_CLK        REG(PDM_BASE + 0x540)
#define PDM_PSEL_DIN        REG(PDM_BASE + 0x544)
#define PDM_SAMPLE_PTR      REG(PDM_BASE + 0x560)
#define PDM_SAMPLE_MAXCNT   REG(PDM_BASE + 0x564)

#define UART_BASE 0x40002000UL
#define UART_TASKS_STARTTX  REG(UART_BASE + 0x008)
#define UART_EVENTS_ENDTX   REG(UART_BASE + 0x120)
#define UART_ENABLE         REG(UART_BASE + 0x500)
#define UART_PSEL_TXD       REG(UART_BASE + 0x50C)
#define UART_BAUDRATE       REG(UART_BASE + 0x524)
#define UART_TXD_PTR        REG(UART_BASE + 0x544)
#define UART_TXD_MAXCNT     REG(UART_BASE + 0x548)

#define NVIC_ISER0          REG(0xE000E100UL)

#define FRAME_SAMPLES 160   /* 10 ms @ 16 kHz */
#define DUMP_FRAMES   100   /* 1 s of audio, then stop dumping */

static int16_t buf[2][FRAME_SAMPLES];
static volatile uint32_t started_count;   /* STARTED events seen (selects next buffer) */
static volatile uint32_t end_count;       /* buffers completed */
static volatile uint32_t overruns;

void PDM_IRQHandler(void)
{
    if (PDM_EVENTS_STARTED) {
        PDM_EVENTS_STARTED = 0;
        started_count++;
        PDM_SAMPLE_PTR = (uint32_t)buf[started_count & 1];  /* arm the *next* buffer */
    }
    if (PDM_EVENTS_END) {
        PDM_EVENTS_END = 0;
        end_count++;
    }
}

static char tx[FRAME_SAMPLES * 4 + 32];

static void uart_send(const char *p, uint32_t n)
{
    UART_EVENTS_ENDTX = 0;
    UART_TXD_PTR = (uint32_t)p;
    UART_TXD_MAXCNT = n;
    UART_TASKS_STARTTX = 1;
    while (!UART_EVENTS_ENDTX) ;
}

static uint32_t put_hex(char *o, uint32_t v, int digits)
{
    static const char h[] = "0123456789abcdef";
    for (int i = digits - 1; i >= 0; i--) *o++ = h[(v >> (4 * i)) & 0xF];
    return digits;
}

int main(void)
{
    UART_PSEL_TXD = 6;               /* P0.06, arbitrary in emulation */
    UART_BAUDRATE = 0x10000000;      /* 1 Mbaud */
    UART_ENABLE = 8;
    uart_send("VOXEDGE PHASE0 BOOT\n", 20);

    PDM_PSEL_CLK = 26;               /* P0.26 */
    PDM_PSEL_DIN = 25;               /* P0.25 */
    PDM_MODE = 1;                    /* mono, left on falling edge */
    PDM_GAINL = 0x28; PDM_GAINR = 0x28;
    PDM_RATIO = 0;                   /* Ratio64 */
    PDM_SAMPLE_MAXCNT = FRAME_SAMPLES;
    PDM_SAMPLE_PTR = (uint32_t)buf[0];
    PDM_ENABLE = 1;
    PDM_INTENSET = (1u << 0) | (1u << 2);   /* STARTED, END */
    NVIC_ISER0 = 1u << 29;           /* PDM IRQ */
    PDM_TASKS_START = 1;

    uint32_t seen = 0;
    while (seen < DUMP_FRAMES) {
        __asm volatile("wfi");
        while (seen < end_count) {
            /* buffer completed by END #seen+1 is buf[seen & 1] */
            if (end_count - seen > 1) overruns++;
            uint32_t n = 0;
            tx[n++] = 'S'; tx[n++] = ':';
            n += put_hex(tx + n, seen, 4);
            tx[n++] = ':';
            const uint8_t *b = (const uint8_t *)buf[seen & 1];
            for (int i = 0; i < FRAME_SAMPLES * 2; i++) n += put_hex(tx + n, b[i], 2);
            tx[n++] = '\n';
            uart_send(tx, n);
            seen++;
        }
    }
    uint32_t n = 0;
    tx[n++] = 'D'; tx[n++] = ':'; n += put_hex(tx + n, overruns, 4); tx[n++] = '\n';
    uart_send(tx, n);
    for (;;) __asm volatile("wfi");
}

#include "voxedge.h"

#define REG(a) (*(volatile uint32_t *)(a))
#define UART_BASE 0x40002000UL
#define UART_TASKS_STARTTX  REG(UART_BASE + 0x008)
#define UART_EVENTS_ENDTX   REG(UART_BASE + 0x120)
#define UART_ENABLE         REG(UART_BASE + 0x500)
#define UART_PSEL_TXD       REG(UART_BASE + 0x50C)
#define UART_BAUDRATE       REG(UART_BASE + 0x524)
#define UART_TXD_PTR        REG(UART_BASE + 0x544)
#define UART_TXD_MAXCNT     REG(UART_BASE + 0x548)

void uart_init(void)
{
    UART_PSEL_TXD = 6;
    UART_BAUDRATE = 0x10000000;   /* 1 Mbaud */
    UART_ENABLE = 8;
}

/* EasyDMA needs RAM, so copy through a small buffer. Only telemetry (and fatal hooks) print. */
void uart_puts(const char *s)
{
    static char buf[96];
    while (*s) {
        uint32_t n = 0;
        while (*s && n < sizeof buf) buf[n++] = *s++;
        UART_EVENTS_ENDTX = 0;
        UART_TXD_PTR = (uint32_t)buf;
        UART_TXD_MAXCNT = n;
        UART_TASKS_STARTTX = 1;
        while (!UART_EVENTS_ENDTX) ;
    }
}

void uart_putu(uint32_t v)
{
    char t[11]; int i = 10;
    t[i] = 0;
    do { t[--i] = '0' + v % 10; v /= 10; } while (v);
    uart_puts(&t[i]);
}

void uart_puthex32(uint32_t v)
{
    static const char h[] = "0123456789abcdef";
    char t[9];
    for (int i = 0; i < 8; i++) t[i] = h[(v >> (28 - 4 * i)) & 0xF];
    t[8] = 0;
    uart_puts(t);
}

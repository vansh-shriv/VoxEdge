#include <stdint.h>

extern uint32_t _estack, _sidata, _sdata, _edata, _sbss, _ebss;
extern int main(void);
extern void __libc_init_array(void);
void _init(void) {}
/* No newlib heap: all memory is static or FreeRTOS heap_4. Any malloc() fails loudly instead of eating RAM. */
void *_sbrk(int incr) { (void)incr; return (void *)-1; }
void _fini(void) {}

void Default_Handler(void) { for (;;) ; }
#define WEAK_DEFAULT __attribute__((weak, alias("Default_Handler")))

void Reset_Handler(void);
void NMI_Handler(void) WEAK_DEFAULT;
void HardFault_Handler(void) WEAK_DEFAULT;
void MemManage_Handler(void) WEAK_DEFAULT;
void BusFault_Handler(void) WEAK_DEFAULT;
void UsageFault_Handler(void) WEAK_DEFAULT;
void SVC_Handler(void) WEAK_DEFAULT;        /* FreeRTOS: vPortSVCHandler */
void PendSV_Handler(void) WEAK_DEFAULT;     /* FreeRTOS: xPortPendSVHandler */
void SysTick_Handler(void) WEAK_DEFAULT;    /* FreeRTOS: xPortSysTickHandler */
void PDM_IRQHandler(void) WEAK_DEFAULT;
void WDT_IRQHandler(void) WEAK_DEFAULT;

void Reset_Handler(void)
{
    uint32_t *src = &_sidata, *dst = &_sdata;
    while (dst < &_edata) *dst++ = *src++;
    for (dst = &_sbss; dst < &_ebss; ) *dst++ = 0;
    *(volatile uint32_t *)0xE000ED88 |= (0xFu << 20);   /* CPACR: enable FPU (CP10/CP11) */
    __asm volatile("dsb; isb");
    __libc_init_array();
    main();
    for (;;) __asm volatile("wfi");
}

/* Core exceptions (16) + nRF52840 IRQs 0..47. PDM is IRQ 29 (matches Renode nvic@29). */
__attribute__((section(".isr_vector"), used))
void (* const vectors[16 + 48])(void) = {
    [0 ... 16 + 47] = Default_Handler,
    [0] = (void (*)(void))&_estack, [1] = Reset_Handler, [2] = NMI_Handler,
    [3] = HardFault_Handler, [4] = MemManage_Handler, [5] = BusFault_Handler,
    [6] = UsageFault_Handler, [7] = 0, [8] = 0, [9] = 0, [10] = 0,
    [11] = SVC_Handler, [12] = 0, [13] = 0, [14] = PendSV_Handler, [15] = SysTick_Handler,
    [16 + 16] = WDT_IRQHandler,
    [16 + 29] = PDM_IRQHandler,
};

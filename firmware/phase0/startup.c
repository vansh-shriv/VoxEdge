#include <stdint.h>

extern uint32_t _estack, _sidata, _sdata, _edata, _sbss, _ebss;
extern int main(void);
void PDM_IRQHandler(void);

void Reset_Handler(void)
{
    uint32_t *src = &_sidata, *dst = &_sdata;
    while (dst < &_edata) *dst++ = *src++;
    for (dst = &_sbss; dst < &_ebss; ) *dst++ = 0;
    main();
    for (;;) __asm volatile("wfi");
}

void Default_Handler(void) { for (;;) ; }

/* Core exceptions (16) + nRF52840 IRQs 0..47. PDM is IRQ 29 (matches Renode nvic@29). */
__attribute__((section(".isr_vector"), used))
void (* const vectors[16 + 48])(void) = {
    (void (*)(void))&_estack, Reset_Handler,
    Default_Handler, Default_Handler, Default_Handler, Default_Handler, Default_Handler,
    0, 0, 0, 0,
    Default_Handler, Default_Handler, 0, Default_Handler, Default_Handler,
    [16 + 29] = PDM_IRQHandler,
    [16 + 47] = Default_Handler,
};

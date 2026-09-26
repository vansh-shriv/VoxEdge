#include "voxedge.h"

#define REG(a) (*(volatile uint32_t *)(a))
#define P0_OUTSET REG(0x50000508UL)
#define P0_OUTCLR REG(0x5000050CUL)
#define P0_DIRSET REG(0x50000518UL)
#define WAKE_PIN  24    /* led_red on the Renode Nano 33 BLE platform */

void wake_gpio_init(void) { P0_DIRSET = 1u << WAKE_PIN; wake_gpio_set(0); }
void wake_gpio_set(int on) { if (on) P0_OUTSET = 1u << WAKE_PIN; else P0_OUTCLR = 1u << WAKE_PIN; }

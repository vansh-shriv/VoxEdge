# Phase 0 build. Override TOOLCHAIN if arm-none-eabi-gcc is not on PATH.
TOOLCHAIN ?= C:/Program Files (x86)/Arm GNU Toolchain arm-none-eabi/12.2 mpacbti-rel1/bin/
CC := "$(TOOLCHAIN)arm-none-eabi-gcc"
SIZE := "$(TOOLCHAIN)arm-none-eabi-size"
CFLAGS := -mcpu=cortex-m4 -mthumb -mfloat-abi=hard -mfpu=fpv4-sp-d16 -Os -g -Wall -Wextra -ffreestanding -fno-common
LDFLAGS := -nostartfiles -nostdlib -Tlink.ld -Wl,--gc-sections -Wl,-Map=phase0.map

phase0.elf: main.c startup.c link.ld
	$(CC) $(CFLAGS) main.c startup.c $(LDFLAGS) -lgcc -o $@
	$(SIZE) $@

clean:
	rm -f phase0.elf phase0.map

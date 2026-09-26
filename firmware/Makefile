# Firmware build (Phase 1+). Override TOOLCHAIN if arm-none-eabi-gcc is not on PATH.
TOOLCHAIN ?= C:/Program Files (x86)/Arm GNU Toolchain arm-none-eabi/12.2 mpacbti-rel1/bin/
CC   := "$(TOOLCHAIN)arm-none-eabi-gcc"
SIZE := "$(TOOLCHAIN)arm-none-eabi-size"
RTOS := ../third_party/FreeRTOS-Kernel

SRCS := startup.c $(wildcard src/*.c) $(wildcard src/tasks/*.c) \
        $(RTOS)/tasks.c $(RTOS)/queue.c $(RTOS)/list.c $(RTOS)/stream_buffer.c \
        $(RTOS)/portable/GCC/ARM_CM4F/port.c $(RTOS)/portable/MemMang/heap_4.c

CFLAGS  := -mcpu=cortex-m4 -mthumb -mfloat-abi=hard -mfpu=fpv4-sp-d16 -Os -g -Wall -Wextra -Wno-override-init \
           -ffunction-sections -fdata-sections -fno-common \
           -I. -Isrc -I$(RTOS)/include -I$(RTOS)/portable/GCC/ARM_CM4F
LDFLAGS := -nostartfiles --specs=nano.specs --specs=nosys.specs -Tlink.ld -Wl,--gc-sections -Wl,-Map=voxedge.map

voxedge.elf: $(SRCS) link.ld $(wildcard src/*.h) FreeRTOSConfig.h
	$(CC) $(CFLAGS) $(SRCS) $(LDFLAGS) -o $@
	$(SIZE) $@

clean:
	rm -f voxedge.elf voxedge.map

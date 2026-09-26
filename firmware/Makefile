# Firmware build. Override TOOLCHAIN if arm-none-eabi-gcc is not on PATH.
TOOLCHAIN ?= C:/Program Files (x86)/Arm GNU Toolchain arm-none-eabi/12.2 mpacbti-rel1/bin/
CC   := "$(TOOLCHAIN)arm-none-eabi-gcc"
SIZE := "$(TOOLCHAIN)arm-none-eabi-size"
RTOS := ../third_party/FreeRTOS-Kernel
CMSIS_DSP := ../third_party/CMSIS-DSP
CMSIS_CORE := ../third_party/CMSIS_6/CMSIS/Core/Include

# 1 dumps every feature vector over UART (used by tools/run_phase2.sh); 0 for normal builds.
DUMP_FEATURES ?= 0

# Only the pieces needed for arm_rfft_fast_f32 (512-pt) and its twiddle/bit-reversal tables.
DSPSRC := $(CMSIS_DSP)/Source/TransformFunctions/arm_rfft_fast_f32.c \
          $(CMSIS_DSP)/Source/TransformFunctions/arm_rfft_fast_init_f32.c \
          $(CMSIS_DSP)/Source/TransformFunctions/arm_cfft_f32.c \
          $(CMSIS_DSP)/Source/TransformFunctions/arm_cfft_init_f32.c \
          $(CMSIS_DSP)/Source/TransformFunctions/arm_cfft_radix8_f32.c \
          $(CMSIS_DSP)/Source/TransformFunctions/arm_bitreversal2.c \
          $(CMSIS_DSP)/Source/CommonTables/arm_common_tables.c \
          $(CMSIS_DSP)/Source/CommonTables/arm_const_structs.c

SRCS := startup.c $(wildcard src/*.c) $(wildcard src/tasks/*.c) $(wildcard src/dsp/*.c) $(DSPSRC) \
        $(RTOS)/tasks.c $(RTOS)/queue.c $(RTOS)/list.c $(RTOS)/stream_buffer.c \
        $(RTOS)/portable/GCC/ARM_CM4F/port.c $(RTOS)/portable/MemMang/heap_4.c

CFLAGS  := -mcpu=cortex-m4 -mthumb -mfloat-abi=hard -mfpu=fpv4-sp-d16 -Os -g -Wall -Wextra -Wno-override-init \
           -ffunction-sections -fdata-sections -fno-common \
           -I. -Isrc -Isrc/dsp -I$(RTOS)/include -I$(RTOS)/portable/GCC/ARM_CM4F \
           -I$(CMSIS_DSP)/Include -I$(CMSIS_DSP)/PrivateInclude -I$(CMSIS_CORE) \
           -DVOXEDGE_DUMP_FEATURES=$(DUMP_FEATURES)
LDFLAGS := -nostartfiles --specs=nano.specs --specs=nosys.specs -Tlink.ld -Wl,--gc-sections -Wl,-Map=voxedge.map -lm

voxedge.elf: $(SRCS) link.ld $(wildcard src/*.h src/dsp/*.h) FreeRTOSConfig.h
	$(CC) $(CFLAGS) $(SRCS) $(LDFLAGS) -o $@
	$(SIZE) $@

clean:
	rm -f voxedge.elf voxedge.map

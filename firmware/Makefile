# Firmware build (C + C++, per-file objects in obj/). Override TOOLCHAIN if the Arm GNU toolchain
# is not at the default path.  Variables:
#   MODEL=xs|s|m        which int8 model to link (default s)
#   DUMP_FEATURES=1     forward every feature vector to telemetry (tools/run_phase2.sh)
#   DUMP_INFER=1        forward every inference (logits, sampled input tensors) to telemetry
#   KERNELS=cmsis|ref   CMSIS-NN optimised int8 kernels (default) or TFLM reference kernels
#   OPT=-Os|-O2|-O3     compiler optimisation level for everything
#   ARENA_KB=<n>        TFLite-Micro tensor arena size
#   INFER_EVERY=<hops>  run the model every N hops (10 ms each)
#   DUMP_INPUT_EVERY=<n> with DUMP_INFER=1, dump the full input tensor every n-th run
#   WDT_TIMEOUT_MS=<n>  hardware watchdog timeout (default 2000; fed once/second by telemetry)
#   STALL_TASK=0|1|2    Phase 5 debug stall: 0 none, 1 dsp, 2 inference (see src/debug_stall.h)
#   STALL_AT_SEQ=<n>    hop sequence number that triggers the stall
#   STALL_MS=<n>        stall duration in ms (0 = forever; only the watchdog recovers from that)
.DEFAULT_GOAL := voxedge.elf
TOOLCHAIN ?= C:/Program Files (x86)/Arm GNU Toolchain arm-none-eabi/12.2 mpacbti-rel1/bin/
CC   := "$(TOOLCHAIN)arm-none-eabi-gcc"
CXX  := "$(TOOLCHAIN)arm-none-eabi-g++"
SIZE := "$(TOOLCHAIN)arm-none-eabi-size"

MODEL         ?= s
DUMP_FEATURES ?= 0
DUMP_INFER    ?= 0
ARENA_KB      ?= 64
KERNELS       ?= cmsis
OPT           ?= -O2
INFER_EVERY   ?= 40
DUMP_INPUT_EVERY ?= 8
WDT_TIMEOUT_MS ?= 2000
STALL_TASK    ?= 0
STALL_AT_SEQ  ?= 0xFFFFFFFF
STALL_MS      ?= 0

RTOS       := ../third_party/FreeRTOS-Kernel
CMSIS_DSP  := ../third_party/CMSIS-DSP
CMSIS_CORE := ../third_party/CMSIS_6/CMSIS/Core/Include
TFLM       := ../third_party/tflite-micro
TFLM_DEPS  := ../third_party/tflm_deps
TFL        := $(TFLM)/tensorflow/lite
CMSIS_NN   := $(TFLM_DEPS)/cmsis_nn

# ---- C sources
DSPSRC := $(CMSIS_DSP)/Source/TransformFunctions/arm_rfft_fast_f32.c \
          $(CMSIS_DSP)/Source/TransformFunctions/arm_rfft_fast_init_f32.c \
          $(CMSIS_DSP)/Source/TransformFunctions/arm_cfft_f32.c \
          $(CMSIS_DSP)/Source/TransformFunctions/arm_cfft_init_f32.c \
          $(CMSIS_DSP)/Source/TransformFunctions/arm_cfft_radix8_f32.c \
          $(CMSIS_DSP)/Source/TransformFunctions/arm_bitreversal2.c \
          $(CMSIS_DSP)/Source/CommonTables/arm_common_tables.c \
          $(CMSIS_DSP)/Source/CommonTables/arm_const_structs.c
CSRCS := startup.c $(wildcard src/*.c) $(wildcard src/tasks/*.c) $(wildcard src/dsp/*.c) $(DSPSRC) \
         src/model/model_$(MODEL).c \
         $(RTOS)/tasks.c $(RTOS)/queue.c $(RTOS)/list.c $(RTOS)/stream_buffer.c \
         $(RTOS)/portable/GCC/ARM_CM4F/port.c $(RTOS)/portable/MemMang/heap_4.c

# ---- C++ sources: our glue + the parts of TFLite-Micro this model needs (reference kernels)
TFLM_CORE := debug_log flatbuffer_utils memory_helpers micro_allocation_info micro_allocator micro_context \
             micro_interpreter micro_interpreter_context micro_interpreter_graph micro_log micro_op_resolver \
             micro_resource_variable micro_time micro_utils
TFLM_KERN := conv_common depthwise_conv_common fully_connected_common kernel_util reduce reduce_common
ifeq ($(KERNELS),cmsis)
# TFLM's CMSIS-NN kernel variants (SIMD int8) replace the reference conv / depthwise / fully-connected.
KERN_OPT_SRCS := $(addprefix $(TFL)/micro/kernels/cmsis_nn/,conv.cc depthwise_conv.cc fully_connected.cc)
KERN_DEFS := -DCMSIS_NN
CMSIS_NN_SRCS := $(filter-out %_f16.c %_f32.c,$(wildcard $(CMSIS_NN)/Source/ConvolutionFunctions/*.c \
                   $(CMSIS_NN)/Source/FullyConnectedFunctions/*.c $(CMSIS_NN)/Source/NNSupportFunctions/*.c))
else
KERN_OPT_SRCS := $(addprefix $(TFL)/micro/kernels/,conv.cc depthwise_conv.cc fully_connected.cc)
KERN_DEFS :=
CMSIS_NN_SRCS :=
endif
CSRCS += $(CMSIS_NN_SRCS)
CXXSRCS := $(wildcard src/model/*.cc) \
           $(addprefix $(TFL)/micro/,$(addsuffix .cc,$(TFLM_CORE))) \
           $(addprefix $(TFL)/micro/kernels/,$(addsuffix .cc,$(TFLM_KERN))) $(KERN_OPT_SRCS) \
           $(wildcard $(TFL)/micro/arena_allocator/*allocator.cc) \
           $(TFL)/micro/memory_planner/greedy_memory_planner.cc $(TFL)/micro/memory_planner/linear_memory_planner.cc \
           $(TFL)/micro/memory_planner/non_persistent_buffer_planner_shim.cc \
           $(TFL)/micro/tflite_bridge/flatbuffer_conversions_bridge.cc $(TFL)/micro/tflite_bridge/micro_error_reporter.cc \
           $(TFL)/core/api/flatbuffer_conversions.cc $(TFL)/core/api/tensor_utils.cc $(TFL)/core/c/common.cc \
           $(TFLM)/tensorflow/compiler/mlir/lite/schema/schema_utils.cc $(TFL)/kernels/kernel_util.cc \
           $(TFL)/kernels/internal/common.cc $(TFL)/kernels/internal/portable_tensor_utils.cc \
           $(TFL)/kernels/internal/quantization_util.cc $(TFL)/kernels/internal/runtime_shape.cc \
           $(TFL)/kernels/internal/tensor_ctypes.cc $(TFL)/kernels/internal/tensor_utils.cc
CXXSRCS := $(filter-out %/recording_single_arena_buffer_allocator.cc,$(CXXSRCS))

# One object tree per configuration: the -D flags change the code, so objects must not be shared.
OBJDIR := obj/$(KERNELS)$(OPT)-$(MODEL)-f$(DUMP_FEATURES)i$(DUMP_INFER)-e$(INFER_EVERY)-a$(ARENA_KB)-q$(DUMP_INPUT_EVERY)-w$(WDT_TIMEOUT_MS)-s$(STALL_TASK).$(STALL_AT_SEQ).$(STALL_MS)
# (not named 'strip': that is a make built-in and $(call strip,..) would silently call it)
noup    = $(subst ../,,$(1))
OBJS    := $(addprefix $(OBJDIR)/,$(addsuffix .o,$(call noup,$(CSRCS) $(CXXSRCS))))

vpath %.c  . ..
vpath %.cc . ..

ARCH     := -mcpu=cortex-m4 -mthumb -mfloat-abi=hard -mfpu=fpv4-sp-d16
INC      := -I. -Isrc -Isrc/dsp -Isrc/model -I$(RTOS)/include -I$(RTOS)/portable/GCC/ARM_CM4F \
            -I$(CMSIS_DSP)/Include -I$(CMSIS_DSP)/PrivateInclude -I$(CMSIS_CORE)
TFLM_INC := -I$(TFLM) -I$(CMSIS_NN) -I$(CMSIS_NN)/Include -I$(TFLM_DEPS)/flatbuffers/include -I$(TFLM_DEPS)/gemmlowp -I$(TFLM_DEPS)/ruy
DEFS     := -DVOXEDGE_DUMP_FEATURES=$(DUMP_FEATURES) -DVOXEDGE_DUMP_INFER=$(DUMP_INFER) \
            -DARM_NN_ENABLE_F16=0 -DARM_NN_ENABLE_F32=0 -DKWS_MODEL=$(MODEL) -DKWS_ARENA_BYTES=$(ARENA_KB)*1024 -DKWS_INFER_EVERY=$(INFER_EVERY) -DKWS_DUMP_INPUT_EVERY=$(DUMP_INPUT_EVERY) \
            -DWDT_TIMEOUT_MS=$(WDT_TIMEOUT_MS) -DSTALL_TASK=$(STALL_TASK) -DSTALL_AT_SEQ=$(STALL_AT_SEQ) -DSTALL_MS=$(STALL_MS)
COMMON   := $(ARCH) $(OPT) -g -ffunction-sections -fdata-sections -fno-common -MMD -MP
CFLAGS   := $(COMMON) -Wall -Wextra -Wno-override-init $(INC) -I$(CMSIS_NN) -I$(CMSIS_NN)/Include $(DEFS)
CXXFLAGS := $(COMMON) -std=c++17 -fno-exceptions -fno-rtti -fno-threadsafe-statics -fno-use-cxa-atexit \
            $(KERN_DEFS) -DTF_LITE_STATIC_MEMORY -DTF_LITE_DISABLE_X86_NEON -DTF_LITE_STRIP_ERROR_STRINGS \
            -Wno-psabi -Wno-unused-parameter -Wno-type-limits -Wno-sign-compare $(INC) $(TFLM_INC) $(DEFS)
LDFLAGS  := $(ARCH) -nostartfiles --specs=nano.specs --specs=nosys.specs -Tlink.ld -Wl,--gc-sections \
            -Wl,-Map=voxedge.map -lm

# The object list is too long for a Windows command line (~8-32 KB limit), so pass it to the linker
# through a response file. GNU Make 3.82 has no $(file ...), hence one short echo per object.
define NL


endef
RSP := $(OBJDIR)/objs.rsp

$(RSP): $(OBJS)
	@mkdir -p $(dir $@)
	@rm -f $@
	$(foreach o,$(OBJS),@echo $(o) >> $@$(NL))

# Link into the per-configuration object dir, then always copy to voxedge.elf (phony), so a stale
# ELF from another MODEL/KERNELS/... configuration can never be picked up as "up to date".
$(OBJDIR)/voxedge.elf: $(RSP) link.ld
	$(CXX) @$(RSP) $(LDFLAGS) -o $@

voxedge.elf: $(OBJDIR)/voxedge.elf
	cp -f $< $@

$(OBJDIR)/%.c.o: %.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c $< -o $@

$(OBJDIR)/%.cc.o: %.cc
	@mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) -c $< -o $@

.PHONY: voxedge.elf size clean

size: voxedge.elf
	$(SIZE) voxedge.elf

clean:
	rm -rf $(OBJDIR) voxedge.elf voxedge.map

-include $(OBJS:.o=.d)

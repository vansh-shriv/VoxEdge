// TFLite-Micro glue: one static interpreter over the linked int8 model, reference kernels.
#include <new>
#include <cstring>

#include "kws.h"
#include "model_data.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"

#define KWS_CAT2(a, b) a##b
#define KWS_CAT(a, b) KWS_CAT2(a, b)
#define KWS_MODEL_DATA KWS_CAT(g_model_, KWS_MODEL)

namespace {

constexpr int kArenaBytes = KWS_ARENA_BYTES;
alignas(16) uint8_t g_arena[kArenaBytes];

// Placement-new storage so nothing depends on C++ static-init ordering.
alignas(tflite::MicroMutableOpResolver<4>) uint8_t g_resolver_mem[sizeof(tflite::MicroMutableOpResolver<4>)];
alignas(tflite::MicroInterpreter) uint8_t g_interp_mem[sizeof(tflite::MicroInterpreter)];
tflite::MicroInterpreter* g_interp = nullptr;
TfLiteTensor* g_in = nullptr;
TfLiteTensor* g_out = nullptr;

}  // namespace

extern "C" int kws_init(void) {
  const tflite::Model* model = tflite::GetModel(KWS_MODEL_DATA);
  if (model->version() != TFLITE_SCHEMA_VERSION) return -1;

  auto* resolver = new (g_resolver_mem) tflite::MicroMutableOpResolver<4>();
  if (resolver->AddConv2D() != kTfLiteOk) return -2;
  if (resolver->AddDepthwiseConv2D() != kTfLiteOk) return -2;
  if (resolver->AddFullyConnected() != kTfLiteOk) return -2;
  if (resolver->AddMean() != kTfLiteOk) return -2;

  g_interp = new (g_interp_mem) tflite::MicroInterpreter(model, *resolver, g_arena, kArenaBytes);
  if (g_interp->AllocateTensors() != kTfLiteOk) return -3;

  g_in = g_interp->input(0);
  g_out = g_interp->output(0);
  if (g_in->type != kTfLiteInt8 || g_out->type != kTfLiteInt8) return -4;
  if (static_cast<int>(g_in->bytes) != KWS_INPUT_BYTES) return -5;
  if (static_cast<int>(g_out->bytes) != KWS_N_CLASSES) return -6;
  return 0;
}

extern "C" float kws_input_scale(void) { return g_in->params.scale; }
extern "C" int kws_input_zero_point(void) { return g_in->params.zero_point; }
extern "C" float kws_output_scale(void) { return g_out->params.scale; }
extern "C" int kws_output_zero_point(void) { return g_out->params.zero_point; }

extern "C" int kws_infer(const int8_t* input, int8_t* logits) {
  std::memcpy(g_in->data.int8, input, KWS_INPUT_BYTES);
  if (g_interp->Invoke() != kTfLiteOk) return -1;
  std::memcpy(logits, g_out->data.int8, KWS_N_CLASSES);
  return 0;
}

extern "C" uint32_t kws_arena_used(void) { return static_cast<uint32_t>(g_interp->arena_used_bytes()); }

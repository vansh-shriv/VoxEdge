#ifndef KWS_H
#define KWS_H

#include <stdint.h>
#include "model_meta.h"

#define KWS_N_MELS      40
#define KWS_INPUT_BYTES (KWS_N_FRAMES * KWS_N_MELS)

#ifdef __cplusplus
extern "C" {
#endif

/* Build the TFLite-Micro interpreter over the linked int8 model. Returns 0 on success. */
int kws_init(void);

/* Input tensor quantisation (read from the model): q = round(x / scale) + zero_point. */
float kws_input_scale(void);
int   kws_input_zero_point(void);
float kws_output_scale(void);
int   kws_output_zero_point(void);

/* Run one inference. `input` is KWS_INPUT_BYTES int8 (frame-major: [frame][mel]) already
 * quantised; `logits` receives KWS_N_CLASSES raw int8 outputs. Returns 0 on success. */
int kws_infer(const int8_t *input, int8_t *logits);

/* Bytes of the tensor arena actually used (after kws_init). */
uint32_t kws_arena_used(void);

#ifdef __cplusplus
}
#endif

#endif

#ifndef FEATURE_RING_H
#define FEATURE_RING_H

#include <stdint.h>
#include "model/kws.h"

/* Ring of the last KWS_N_FRAMES log-mel vectors, stored already normalised and int8-quantised
 * with the model's input parameters. Single writer (the DSP task). */
void ring_init(float input_scale, int input_zero_point);
void ring_push(const float *logmel);              /* KWS_N_MELS floats */
int  ring_full(void);
void ring_snapshot(int8_t *dst);                  /* oldest frame first, KWS_INPUT_BYTES */

#endif

#ifndef FEATURES_H
#define FEATURES_H

#include <stdint.h>
#include "dsp_tables.h"

void features_init(void);

/* One FEAT_WIN-sample int16 window -> FEAT_N_MELS log-mel values.
 * Pre-emphasis (window-local) -> Hamming -> zero-pad -> CMSIS-DSP rfft (f32) -> power
 * -> sparse mel filterbank -> log(x + FEAT_LOG_FLOOR). Mirrors ml/features.py. */
void features_compute(const int16_t *win, float *logmel_out);

#endif

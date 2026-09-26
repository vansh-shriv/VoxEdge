#include <math.h>
#include <string.h>
#include "feature_ring.h"

static int8_t s_ring[KWS_N_FRAMES][KWS_N_MELS];
static uint32_t s_head, s_count;
static float s_a, s_b;      /* q = x * s_a + s_b, folds ((x - mean) / std) / scale + zero_point */

void ring_init(float input_scale, int input_zero_point)
{
    s_a = 1.0f / (KWS_NORM_STD * input_scale);
    s_b = (float)input_zero_point - KWS_NORM_MEAN * s_a;
    s_head = s_count = 0;
}

void ring_push(const float *logmel)
{
    for (int i = 0; i < KWS_N_MELS; i++) {
        int q = (int)floorf(logmel[i] * s_a + s_b + 0.5f);
        s_ring[s_head][i] = (int8_t)(q > 127 ? 127 : q < -128 ? -128 : q);
    }
    s_head = (s_head + 1) % KWS_N_FRAMES;
    if (s_count < KWS_N_FRAMES) s_count++;
}

int ring_full(void) { return s_count >= KWS_N_FRAMES; }

void ring_snapshot(int8_t *dst)
{
    for (uint32_t i = 0; i < KWS_N_FRAMES; i++)
        memcpy(dst + i * KWS_N_MELS, s_ring[(s_head + i) % KWS_N_FRAMES], KWS_N_MELS);
}

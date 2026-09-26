#include <math.h>
#include "arm_math.h"
#include "features.h"

static arm_rfft_fast_instance_f32 s_rfft;
static float s_buf[FEAT_NFFT];     /* time-domain input; the rfft uses it as scratch */
static float s_spec[FEAT_NFFT];    /* packed rfft output: [Re0, ReN/2, Re1, Im1, Re2, Im2, ...] */
static float s_pow[FEAT_N_BINS];

void features_init(void)
{
    /* Direct 512-pt init (not the generic one) so the linker drops every other FFT size's tables. */
    _Static_assert(FEAT_NFFT == 512, "features.c is hard-wired to the 512-point RFFT");
    arm_rfft_fast_init_512_f32(&s_rfft);
}

void features_compute(const int16_t *win, float *out)
{
    s_buf[0] = (float)win[0] * g_hamming[0];
    for (int i = 1; i < FEAT_WIN; i++)
        s_buf[i] = ((float)win[i] - FEAT_PREEMPH * (float)win[i - 1]) * g_hamming[i];
    for (int i = FEAT_WIN; i < FEAT_NFFT; i++) s_buf[i] = 0.0f;

    arm_rfft_fast_f32(&s_rfft, s_buf, s_spec, 0);

    s_pow[0] = s_spec[0] * s_spec[0];
    s_pow[FEAT_NFFT / 2] = s_spec[1] * s_spec[1];
    for (int k = 1; k < FEAT_NFFT / 2; k++) {
        float re = s_spec[2 * k], im = s_spec[2 * k + 1];
        s_pow[k] = re * re + im * im;
    }

    const float *w = g_mel_w;
    for (int m = 0; m < FEAT_N_MELS; m++) {
        const float *p = &s_pow[g_mel_start[m]];
        float acc = 0.0f;
        for (int j = 0; j < g_mel_len[m]; j++) acc += *w++ * p[j];
        out[m] = logf(acc + FEAT_LOG_FLOOR);
    }
}

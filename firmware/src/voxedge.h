#ifndef VOXEDGE_H
#define VOXEDGE_H

#include <stdint.h>
#include "FreeRTOS.h"
#include "queue.h"
#include "stream_buffer.h"
#include "dsp/dsp_tables.h"
#include "model/kws.h"

#define SAMPLE_RATE_HZ   16000
#define HOP_SAMPLES      160                    /* 10 ms hop = one PDM buffer */
#define WINDOW_SAMPLES   480                    /* 30 ms analysis window */
#define HOP_BYTES        (HOP_SAMPLES * 2)
#define PDM_STREAM_HOPS  8                      /* stream-buffer depth in hops */

#ifndef VOXEDGE_DUMP_FEATURES
#define VOXEDGE_DUMP_FEATURES 0
#endif
#ifndef VOXEDGE_DUMP_INFER
#define VOXEDGE_DUMP_INFER 0
#endif

/* Task priorities: ISR > capture > dsp > inference > telemetry > idle (0). */
#define PRIO_CAPTURE     5
#define PRIO_DSP         4
#define PRIO_INFERENCE   3
#define PRIO_TELEMETRY   1

/* Window handed capture -> dsp. seq = index of the newest hop in the window. */
typedef struct { uint32_t seq; int16_t samples[WINDOW_SAMPLES]; } window_msg_t;
/* Debug feature dump (dsp -> telemetry, VOXEDGE_DUMP_FEATURES). */
typedef struct { uint32_t seq; float logmel[FEAT_N_MELS]; } feature_msg_t;
/* Wake events (inference -> telemetry). */
typedef enum { EVT_WAKE_ON = 'R', EVT_WAKE_OFF = 'F' } event_type_t;
typedef struct { uint32_t seq; uint32_t tick; uint8_t type; } event_msg_t;
/* Debug inference dump (VOXEDGE_DUMP_INFER): every run's logits; the full input tensor for a sample of runs. */
typedef struct { uint32_t seq; int8_t logits[KWS_N_CLASSES]; uint16_t pkey_permille; } infl_msg_t;
typedef struct { uint32_t seq; int8_t input[KWS_INPUT_BYTES]; } infq_msg_t;

/* Pipeline counters; written by their owning task/ISR, read by telemetry. */
typedef struct {
    volatile uint32_t pdm_frames;      /* buffers completed by PDM (ISR) */
    volatile uint32_t pdm_overruns;    /* ISR could not hand a buffer to capture (stream full) */
    volatile uint32_t hops;            /* hops consumed by capture task */
    volatile uint32_t dsp_drops;       /* windows dropped: dsp queue full */
    volatile uint32_t evt_drops;       /* events dropped: telemetry queue full */
    volatile uint32_t windows;         /* windows processed by dsp */
    volatile uint32_t dump_drops;      /* debug dumps dropped: dump queue full */
    volatile uint32_t dsp_cyc_last;    /* DWT cycles for the last features_compute() */
    volatile uint32_t dsp_cyc_max;
    volatile uint32_t dsp_cyc_sum;     /* over `windows` calls */
    volatile uint32_t infer_due;       /* inference triggers (ring full and seq % KWS_INFER_EVERY == 0) */
    volatile uint32_t infer_skipped;   /* triggers skipped because the previous inference was still running */
    volatile uint32_t model_runs;      /* completed model invocations */
    volatile uint32_t infer_cyc_last;  /* DWT cycles for the last kws_infer() */
    volatile uint32_t infer_cyc_max;
    volatile uint32_t infer_cyc_sum;   /* over `model_runs` calls */
    volatile uint32_t pkey_permille;   /* last P(keyword) x 1000 */
    volatile uint32_t arena_used;      /* TFLite-Micro arena bytes in use */
} stats_t;
extern stats_t g_stats;

extern StreamBufferHandle_t g_pdm_stream;
extern QueueHandle_t g_dsp_q, g_evt_q, g_dump_q, g_infl_q, g_infq_q;
extern QueueSetHandle_t g_tel_set;
extern TaskHandle_t g_capture_h, g_dsp_h, g_inf_h, g_tel_h;

/* dsp -> inference hand-off: DSP copies the feature ring into g_snap and notifies the inference
 * task, but only while g_infer_busy == 0 (DSP sets it, inference clears it when done). */
extern int8_t g_snap[KWS_INPUT_BYTES];
extern volatile uint32_t g_snap_seq;
extern volatile uint8_t g_infer_busy;

/* pdm_capture.c */
void pdm_init(StreamBufferHandle_t sink);
void pdm_start(void);
/* uart.c (polled UARTE0 TX) */
void uart_init(void);
void uart_puts(const char *s);
void uart_putu(uint32_t v);
void uart_puti(int32_t v);
void uart_puthex32(uint32_t v);                  /* 8 lowercase hex digits */
void uart_puthex_bytes(const uint8_t *p, uint32_t n);
/* gpio.c */
void wake_gpio_init(void);
void wake_gpio_set(int on);
/* tasks */
void capture_task(void *arg);
void dsp_task(void *arg);
void inference_task(void *arg);
void telemetry_task(void *arg);

#endif

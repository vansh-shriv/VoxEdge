#ifndef VOXEDGE_H
#define VOXEDGE_H

#include <stdint.h>
#include "FreeRTOS.h"
#include "queue.h"
#include "stream_buffer.h"
#include "queue.h"
#include "dsp/dsp_tables.h"

#define SAMPLE_RATE_HZ   16000
#define HOP_SAMPLES      160                    /* 10 ms hop = one PDM buffer */
#define WINDOW_SAMPLES   480                    /* 30 ms analysis window */
#define HOP_BYTES        (HOP_SAMPLES * 2)
#define PDM_STREAM_HOPS  8                      /* stream-buffer depth in hops */

/* Task priorities: ISR > capture > dsp > inference > telemetry > idle (0). */
#define PRIO_CAPTURE     5
#define PRIO_DSP         4
#define PRIO_INFERENCE   3
#define PRIO_TELEMETRY   1

/* Window handed capture -> dsp. seq = index of the newest hop in the window. */
typedef struct { uint32_t seq; int16_t samples[WINDOW_SAMPLES]; } window_msg_t;
/* Features handed dsp -> inference. energy = mean square of the window. */
typedef struct { uint32_t seq; uint32_t energy; uint8_t vad; float logmel[FEAT_N_MELS]; } feature_msg_t;
/* Events handed inference -> telemetry. */
typedef enum { EVT_WAKE_ON = 'R', EVT_WAKE_OFF = 'F' } event_type_t;
typedef struct { uint32_t seq; uint32_t tick; uint8_t type; } event_msg_t;

/* Pipeline counters; written by their owning task/ISR, read by telemetry. */
typedef struct {
    volatile uint32_t pdm_frames;      /* buffers completed by PDM (ISR) */
    volatile uint32_t pdm_overruns;    /* ISR could not hand a buffer to capture (stream full) */
    volatile uint32_t hops;            /* hops consumed by capture task */
    volatile uint32_t dsp_drops;       /* windows dropped: dsp queue full */
    volatile uint32_t inf_drops;       /* features dropped: inference queue full */
    volatile uint32_t evt_drops;       /* events dropped: telemetry queue full */
    volatile uint32_t windows;         /* windows processed by dsp */
    volatile uint32_t inferences;      /* feature vectors processed by inference */
    volatile uint32_t dump_drops;      /* debug feature dumps dropped: dump queue full */
    volatile uint32_t dsp_cyc_last;    /* DWT cycles for the last features_compute() */
    volatile uint32_t dsp_cyc_max;
    volatile uint32_t dsp_cyc_sum;     /* over `windows` calls */
} stats_t;
extern stats_t g_stats;

extern StreamBufferHandle_t g_pdm_stream;
extern QueueHandle_t g_dsp_q, g_inf_q, g_evt_q, g_dump_q;
extern QueueSetHandle_t g_tel_set;
extern TaskHandle_t g_capture_h, g_dsp_h, g_inf_h, g_tel_h;

/* pdm_capture.c */
void pdm_init(StreamBufferHandle_t sink);
void pdm_start(void);
/* uart.c (polled UARTE0 TX) */
void uart_init(void);
void uart_puts(const char *s);
void uart_putu(uint32_t v);
void uart_puthex32(uint32_t v);   /* 8 lowercase hex digits */
/* gpio.c */
void wake_gpio_init(void);
void wake_gpio_set(int on);
/* tasks */
void capture_task(void *arg);
void dsp_task(void *arg);
void inference_task(void *arg);
void telemetry_task(void *arg);

#endif

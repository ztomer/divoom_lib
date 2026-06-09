/* downsample_kernel.c — LANCZOS3 1-D kernel precompute (split from
 * downsample.c, REVIEW §1). Pure libm math; no pixel/alpha helpers. */
#include "downsample_kernel.h"
#include <stdlib.h>
#include <math.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

/* LANCZOS3 parameters + PIL sampling conventions (see downsample.c header). */
#define LANCZOS_A          3.0
#define LANCZOS_A_INV      (1.0 / LANCZOS_A)
#define CENTER_OFFSET      0.5
#define INPUT_PIXEL_CENTER 0.5
#define ROUND_HALF_POS     0.5

/* LANCZOS3 kernel. Returns 0 outside the support, 1 at x=0. */
static inline double lanczos3_kernel(double x) {
    if (x == 0.0) return 1.0;
    double ax = fabs(x);
    if (ax >= LANCZOS_A) return 0.0;
    double pix  = M_PI * ax;
    double pixA = M_PI * ax * LANCZOS_A_INV;
    return (sin(pix) / pix) * (sin(pixA) / pixA);
}

/* Map output coordinate to input coordinate (PIL convention).
 * center = in0 + (out + 0.5) * scale. For our calls in0=0, so
 * center = (out + 0.5) * scale. */
static inline double out_to_in(int out_coord, int in_size, int out_size) {
    double scale = (double)in_size / (double)out_size;
    return ((double)out_coord + CENTER_OFFSET) * scale;
}

/* PIL's filterscale: stretches the LANCZOS support for downscaling
 * (so the filter covers the full output cell) and clamps to 1.0 for
 * upscaling. The kernel argument is then multiplied by ss = 1/filterscale
 * to compress the filter back to its natural width. */
static inline void compute_filterscale(
    int in_size, int out_size,
    double *filterscale_out, double *ss_out
) {
    double scale = (double)in_size / (double)out_size;
    double filterscale = scale < 1.0 ? 1.0 : scale;
    *filterscale_out = filterscale;
    *ss_out = 1.0 / filterscale;
}

/* Kernel1D + PRECISION_* come from downsample_kernel.h. Weights are stored as
 * int32_t in PIL's fixed-point format: w_q = (int)(w * PRECISION_SCALE + 0.5).
 * The un-normalized kernel sums to >1.0 for downscaling (the filterscale
 * stretch), so PIL divides by the sum first; after normalization the quantized
 * weights sum to ~PRECISION_SCALE (= 1.0 in fixed-point). */
int kernel1d_init(Kernel1D *k, int out_coord, int in_size, int out_size) {
    double center = out_to_in(out_coord, in_size, out_size);
    double filterscale, ss;
    compute_filterscale(in_size, out_size, &filterscale, &ss);
    double support = LANCZOS_A * filterscale;
    int xmin = (int)floor(center - support);
    int xmax = (int)ceil(center + support);
    if (xmin < 0) xmin = 0;
    if (xmax > in_size) xmax = in_size;
    k->left = xmin;
    k->right = xmax - 1;
    k->n = k->right - k->left + 1;
    if (k->n <= 0) return -1;
    k->weights = (int32_t*)malloc(sizeof(int32_t) * (size_t)k->n);
    if (!k->weights) return -1;

    /* Step 1: compute un-normalized double weights and their quantized sum. */
    double *w_d = (double*)malloc(sizeof(double) * (size_t)k->n);
    if (!w_d) { free(k->weights); k->weights = NULL; return -1; }
    int32_t *w_q = (int32_t*)malloc(sizeof(int32_t) * (size_t)k->n);
    if (!w_q) { free(k->weights); k->weights = NULL; free(w_d); return -1; }
    int64_t sum_q = 0;
    for (int i = 0; i < k->n; i++) {
        int in_idx = xmin + i;
        double w = lanczos3_kernel(
            ((double)in_idx - center + INPUT_PIXEL_CENTER) * ss
        );
        w_d[i] = w;
        int32_t q = (int32_t)(w * (double)PRECISION_SCALE + (w >= 0.0 ? ROUND_HALF_POS : -ROUND_HALF_POS));
        w_q[i] = q;
        sum_q += q;
    }

    /* Step 2: normalize quantized weights using PIL's round-half-up
     * on the integer ratio: (w_q * PRECISION_SCALE + sum_q/2) / sum_q.
     * For negative: -(((-w_q) * PRECISION_SCALE + sum_q/2) / sum_q).
     * Return the actual sum of normalized weights for the accumulator bias. */
    int64_t actual_sum = 0;
    if (sum_q != 0) {
        for (int i = 0; i < k->n; i++) {
            int64_t q = w_q[i];
            int64_t half = sum_q / 2;
            if (q >= 0) {
                k->weights[i] = (int32_t)((q * (int64_t)PRECISION_SCALE + half) / sum_q);
            } else {
                k->weights[i] = (int32_t)(-(((-q) * (int64_t)PRECISION_SCALE + half) / sum_q));
            }
            actual_sum += k->weights[i];
        }
    } else {
        for (int i = 0; i < k->n; i++) k->weights[i] = 0;
        actual_sum = 0;
    }
    return (int32_t)actual_sum;

    free(w_q);
    free(w_d);
    return 0;
}

void kernel1d_free(Kernel1D *k) {
    if (k->weights) { free(k->weights); k->weights = NULL; }
}

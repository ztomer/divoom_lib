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
    int xmin = (int)(center - support + CENTER_OFFSET);
    int xmax_raw = (int)(center + support + CENTER_OFFSET);
    if (xmin < 0) xmin = 0;
    if (xmax_raw > in_size) xmax_raw = in_size;
    int right = xmax_raw - 1;
    k->left = xmin;
    k->right = right;
    k->n = right - xmin + 1;
    if (k->n <= 0) return -1;
    k->weights = (int32_t*)malloc(sizeof(int32_t) * (size_t)k->n);
    if (!k->weights) return -1;

    /* Step 1: compute un-normalized double weights and their sum. */
    double *w_d = (double*)malloc(sizeof(double) * (size_t)k->n);
    if (!w_d) { free(k->weights); k->weights = NULL; return -1; }
    double sum = 0.0;
    for (int i = 0; i < k->n; i++) {
        int in_idx = xmin + i;
        double w = lanczos3_kernel(
            ((double)in_idx - center + INPUT_PIXEL_CENTER) * ss
        );
        w_d[i] = w;
        sum += w;
    }

    /* Step 2: normalize by sum, then quantize to int32. PIL's
     * normalize_coeffs_8bpc uses round-half-away-from-zero (different bias
     * for positive vs negative values). LANCZOS3 has negative side-lobe
     * weights, so this matters. The two cases are:
     *   positive w: (int)(0.5 + w * PRECISION_SCALE)   // round-half-up
     *   negative w: (int)(-0.5 + w * PRECISION_SCALE)  // round-half-down (away from 0)
     * The (int) cast truncates toward zero, so the explicit sign of the
     * bias is what determines the rounding direction. */
    if (sum != 0.0) {
        double inv_sum = 1.0 / sum;
        for (int i = 0; i < k->n; i++) {
            double w_norm = w_d[i] * inv_sum;
            if (w_norm >= 0.0) {
                k->weights[i] = (int32_t)(w_norm * (double)PRECISION_SCALE + ROUND_HALF_POS);
            } else {
                k->weights[i] = (int32_t)(w_norm * (double)PRECISION_SCALE - ROUND_HALF_POS);
            }
        }
    } else {
        for (int i = 0; i < k->n; i++) k->weights[i] = 0;
    }

    free(w_d);
    return 0;
}

void kernel1d_free(Kernel1D *k) {
    if (k->weights) { free(k->weights); k->weights = NULL; }
}

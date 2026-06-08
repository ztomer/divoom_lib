/* downsample_kernel.h — shared LANCZOS3 fixed-point precision + the 1-D kernel
 * precompute API. Split from downsample.c (REVIEW §1, 500-LOC rule). The
 * pixel-resampling passes in downsample.c consume Kernel1D + PRECISION_*. */
#ifndef DIVOOM_DOWNSAMPLE_KERNEL_H
#define DIVOOM_DOWNSAMPLE_KERNEL_H
#include <stdint.h>

/* PIL fixed-point precision (src/libImaging/Resample.c): 22 fractional bits,
 * half-scale bias for round-to-nearest. Shared by the kernel quantization and
 * the passes' accumulator. */
#define PRECISION_BITS   22
#define PRECISION_SCALE  (1 << PRECISION_BITS)
#define PRECISION_HALF   (1 << (PRECISION_BITS - 1))

/* Precomputed 1-D kernel for one output coordinate (normalized, quantized to
 * int32 fixed-point). */
typedef struct {
    int     left;       /* leftmost input index (clamped to [0, in_size-1]) */
    int     right;      /* rightmost (inclusive) */
    int     n;          /* right - left + 1 */
    int32_t *weights;   /* normalized quantized weights[n] */
} Kernel1D;

int  kernel1d_init(Kernel1D *k, int out_coord, int in_size, int out_size);
void kernel1d_free(Kernel1D *k);

#endif /* DIVOOM_DOWNSAMPLE_KERNEL_H */

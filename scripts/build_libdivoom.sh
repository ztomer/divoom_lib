#!/usr/bin/env bash
# Build script for the native libdivoom_compact shared library.
# Combines four C sources into a single shared library (all under divoom_lib — R17):
#   - divoom_lib/native_src/compact.c          (tile compacting + framing — encode_basic/ios_le)
#   - divoom_lib/native_src/downsample.c       (LANCZOS3 downscale — used by the library)
#   - divoom_lib/native_src/image_encode.c     (16x16 palette encoder for 0x44/0x49)
#   - divoom_lib/native_src/image_encode_32.c  (32x32 encoder + 0x8B 3-phase chunker — Round 4)
#
# compact.c exports encode_basic_payload + encode_ios_le_payload used by
# divoom_lib/framing.py.
#
# Cross-platform (R20): produces a .dylib on macOS and a .so on Linux. The
# Python loaders resolve the right name via divoom_lib/native_lib.py.
#
# Usage:  ./scripts/build_libdivoom.sh
# Output: ./divoom_lib/libdivoom_compact.{dylib|so} (overwrites existing)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LIB_DIR="${PROJECT_ROOT}/divoom_lib"
NATIVE_SRC_DIR="${LIB_DIR}/native_src"

OS="$(uname -s)"
ARCH="$(uname -m)"

# -ffp-contract=off: forbid FMA contraction of `a*b+c` into a single fused op.
# At -O3 with SIMD, clang contracts differently across versions/arches, which
# made the LANCZOS3 downscaler byte-exact locally but 1 LSB off PIL on the CI
# runner's clang (the test_native_downscaler::test_stress_random flake). Off =
# IEEE-strict separate multiply+add everywhere, matching PIL's scalar math.
CFLAGS=(-O3 -ffp-contract=off -fPIC -Wall -Wextra -Wno-unused-parameter)
ARCH_FLAGS=()
LD_FLAGS=()

case "${OS}" in
  Darwin)
    CC="${CC:-clang}"
    OUT="${LIB_DIR}/libdivoom_compact.dylib"
    CFLAGS+=(-dynamiclib)
    LD_FLAGS=(
      -dynamiclib
      -Wl,-install_name,@rpath/libdivoom_compact.dylib
      -Wl,-undefined,dynamic_lookup
    )
    ;;
  Linux)
    CC="${CC:-cc}"
    OUT="${LIB_DIR}/libdivoom_compact.so"
    CFLAGS+=(-shared)
    LD_FLAGS=(-shared -lm)
    ;;
  *)
    echo "Unsupported OS: ${OS}. Building a generic .so with -shared." >&2
    CC="${CC:-cc}"
    OUT="${LIB_DIR}/libdivoom_compact.so"
    CFLAGS+=(-shared)
    LD_FLAGS=(-shared)
    ;;
esac

# Detect arch — ARM gets NEON, x86_64 gets SSE2.
case "${ARCH}" in
  arm64|aarch64)
    ARCH_FLAGS=(-march=armv8-a+simd)
    ;;
  x86_64|amd64)
    ARCH_FLAGS=(-msse2)
    ;;
  *)
    echo "Unknown arch: ${ARCH}. Building with no SIMD flags." >&2
    ;;
esac

echo "Building ${OUT} for ${OS}/${ARCH} with ${CC}…"
"${CC}" "${CFLAGS[@]}" "${ARCH_FLAGS[@]}" \
  -I"${NATIVE_SRC_DIR}" \
  "${NATIVE_SRC_DIR}/compact.c" \
  "${NATIVE_SRC_DIR}/downsample.c" \
  "${NATIVE_SRC_DIR}/downsample_kernel.c" \
  "${NATIVE_SRC_DIR}/image_encode.c" \
  "${NATIVE_SRC_DIR}/image_encode_32.c" \
  "${LD_FLAGS[@]}" \
  -o "${OUT}"

echo "Done."
if command -v file >/dev/null 2>&1; then
  file "${OUT}"
fi

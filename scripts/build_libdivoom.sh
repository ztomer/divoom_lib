#!/usr/bin/env bash
# Build script for libdivoom_compact.dylib
# Combines four C sources into a single dylib (all under divoom_lib — R17):
#   - divoom_lib/native_src/compact.c          (tile compacting + framing — encode_basic/ios_le)
#   - divoom_lib/native_src/downsample.c       (LANCZOS3 downscale — used by the library)
#   - divoom_lib/native_src/image_encode.c     (16x16 palette encoder for 0x44/0x49)
#   - divoom_lib/native_src/image_encode_32.c  (32x32 encoder + 0x8B 3-phase chunker — Round 4)
#
# compact.c exports encode_basic_payload + encode_ios_le_payload used by
# divoom_lib/framing.py.
#
# Usage:  ./scripts/build_libdivoom.sh
# Output: ./divoom_lib/libdivoom_compact.dylib (overwrites existing)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LIB_DIR="${PROJECT_ROOT}/divoom_lib"
NATIVE_SRC_DIR="${LIB_DIR}/native_src"
OUT="${LIB_DIR}/libdivoom_compact.dylib"

CC="${CC:-clang}"
CFLAGS=(
  -O3
  -fPIC
  -dynamiclib
  -Wall
  -Wextra
  -Wno-unused-parameter
)
ARCH_FLAGS=()
LD_FLAGS=(
  -dynamiclib
  -Wl,-install_name,@rpath/libdivoom_compact.dylib
  -Wl,-undefined,dynamic_lookup
)

# Detect arch — M-series gets NEON, Intel gets SSE2.
ARCH="$(uname -m)"
case "${ARCH}" in
  arm64|aarch64)
    ARCH_FLAGS=(-march=armv8-a+simd)
    ;;
  x86_64)
    ARCH_FLAGS=(-msse2)
    ;;
  *)
    echo "Unknown arch: ${ARCH}. Building with no SIMD flags." >&2
    ;;
esac

echo "Building ${OUT} for ${ARCH}…"
"${CC}" "${CFLAGS[@]}" "${ARCH_FLAGS[@]}" \
  -I"${NATIVE_SRC_DIR}" \
  "${NATIVE_SRC_DIR}/compact.c" \
  "${NATIVE_SRC_DIR}/downsample.c" \
  "${NATIVE_SRC_DIR}/image_encode.c" \
  "${NATIVE_SRC_DIR}/image_encode_32.c" \
  "${LD_FLAGS[@]}" \
  -o "${OUT}"

echo "Done."
file "${OUT}"

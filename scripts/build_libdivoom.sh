#!/usr/bin/env bash
# Build script for libdivoom_compact.dylib
# Combines four C sources into a single dylib:
#   - gui/compact.c                            (tile compacting + framing — used by the GUI/framing)
#   - divoom_lib/native_src/downsample.c       (LANCZOS3 downscale — used by the library)
#   - divoom_lib/native_src/image_encode.c     (16x16 palette encoder for 0x44/0x49)
#   - divoom_lib/native_src/image_encode_32.c  (32x32 encoder + 0x8B 3-phase chunker — Round 4)
#
# gui/compact.c also exports encode_basic_payload + encode_ios_le_payload
# used by divoom_lib/framing.py.
#
# Usage:  ./scripts/build_libdivoom.sh
# Output: ./gui/libdivoom_compact.dylib (overwrites existing)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
GUI_DIR="${PROJECT_ROOT}/gui"
NATIVE_SRC_DIR="${PROJECT_ROOT}/divoom_lib/native_src"
OUT="${GUI_DIR}/libdivoom_compact.dylib"

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
  -I"${GUI_DIR}" \
  -I"${NATIVE_SRC_DIR}" \
  "${GUI_DIR}/compact.c" \
  "${NATIVE_SRC_DIR}/downsample.c" \
  "${NATIVE_SRC_DIR}/image_encode.c" \
  "${NATIVE_SRC_DIR}/image_encode_32.c" \
  "${LD_FLAGS[@]}" \
  -o "${OUT}"

echo "Done."
file "${OUT}"

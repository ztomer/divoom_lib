"""32×32 PixooMax / extended-LED Divoom device encoder.

Differences from the 16×16 encoder in `divoom_image_encode.py`:

  1. Two pre-frames at the start of any push (hass-divoom:348-350):
       [AA][LLLL][0x00, 0x00, 0x05, 0x00, 0x00]         5 bytes
       [AA][LLLL][0x00, 0x00, 0x06, 0x00, 0x00, 0x00]   6 bytes
  2. Palette flag = 0x03 (not 0x00) per frame (hass-divoom:445)
  3. Color count is 2 bytes LE u16 (not 1 byte u8)
  4. Chunked-frame header is u32 total_size + u16 index (not u16+u8)

This file deliberately stays separate from `divoom_image_encode.py` to
keep both files under the 500 LOC limit and to make the 16→32 split
explicit. Tests live in `tests/test_divoom_image_encode_32.py`.

Source of truth:
  hass-divoom/custom_components/divoom/devices/divoom.py:300-350
  hass-divoom/custom_components/divoom/devices/divoom.py:444-450
  hass-divoom/custom_components/divoom/devices/divoom.py:283-290
"""
from __future__ import annotations

import math
from typing import List, Tuple

from .divoom_image_encode import (
    Frame,
    build_palette_and_pixels,
    encode_palette,
    encode_pixels,
    _u16_le,
)


SCREENSIZE_32 = 32
PALETTE_FLAG_32 = 0x03
COLOR_COUNT_SIZE_32 = 2  # bytes (LE u16)
PIXEL_COUNT_32 = SCREENSIZE_32 * SCREENSIZE_32


# Pre-frames required at the start of every 32×32 push.
# hass-divoom:348-350.
PRE_FRAME_1 = bytes([0x00, 0x00, 0x05, 0x00, 0x00])
PRE_FRAME_2 = bytes([0x00, 0x00, 0x06, 0x00, 0x00, 0x00])


def _u16_be(n: int) -> bytes:
    """Pack an integer as 2 big-endian bytes."""
    return n.to_bytes(2, byteorder="big", signed=False)


def _pre_frame(payload: bytes) -> bytes:
    """Wrap a pre-frame body with [0xAA][LLLL LE] header. hass-divoom:277-281."""
    llll = len(payload) + 3  # AA(1) + LLLL(2) + payload
    return bytes([0xAA]) + llll.to_bytes(2, "little") + payload


def pre_frames() -> List[bytes]:
    """The two 32×32 pre-frames. Caller appends these to the start of
    any 0x44/0x49/0x8B push to a 32×32 device.

    Hass-divoom:348-350 says "Pixoo-Max expects two empty frames with
    flags 0x05 and 0x06 at the start".
    """
    return [_pre_frame(PRE_FRAME_1), _pre_frame(PRE_FRAME_2)]


def encode_animation_frame_32(
    rgb_bytes: bytes, w: int, h: int, time_ms: int,
) -> bytes:
    """Encode a single 32×32 animation frame.

    Layout (per hass-divoom:439-454 + frame.rs):
        0xAA         (frame data start marker)
        LLLL         (LE u16: byte count of (AA + LLLL + TTTT + RR + NN_NN
                      + COLOR_DATA + PIXEL_DATA), INCLUDING the 2 LLLL
                      bytes themselves)
        TTTT         (LE u16: frame duration in milliseconds; 0x0000 for static)
        RR=0x03      (palette flag: 0x03 for 32×32, 0x00 for 16×16)
        NN_NN        (LE u16: num colors; 0 means 256 per device protocol)
        COLOR_DATA   (palette: 3 bytes per color, first-seen order)
        PIXEL_DATA   (bit-packed pixel indices, LSB-first into LSB-first bytes)

    For 32×32 the TTTT is set to 0 for static frames (only used in
    multi-frame animations); for animation frames it carries the
    per-frame duration in ms.
    """
    if w != SCREENSIZE_32 or h != SCREENSIZE_32:
        raise ValueError(
            f"32x32 encoder requires w=h=32, got w={w} h={h}"
        )
    palette, pixels, nb_bits = build_palette_and_pixels(rgb_bytes, w, h)
    color_data = encode_palette(palette)
    pixel_data = encode_pixels(pixels, nb_bits)
    # LLLL = 1 (AA) + 2 (LLLL) + 2 (TTTT) + 1 (RR) + 2 (NN_NN) + 3N + p = 8 + 3N + p
    llll = 8 + len(color_data) + len(pixel_data)
    nn = len(palette) if len(palette) < 65536 else 0
    header = (
        bytes([0xAA])
        + _u16_le(llll)
        + _u16_le(time_ms)
        + bytes([PALETTE_FLAG_32])
        + (nn & 0xFFFF).to_bytes(2, "little")
    )
    return header + color_data + pixel_data


def encode_animation_32(frames: List[Frame]) -> List[bytes]:
    """Encode a 32×32 animation as a list of pre-frames + per-frame
    bodies, ready to be wrapped in 0x49 or 0x8B chunked packets.

    Returns:
        list of bytes. The first 2 are the pre-frames; the rest are
        the per-frame bodies. Caller chunks them at the SPP layer.
    """
    out: List[bytes] = pre_frames()
    for (rgb, w, h, t) in frames:
        out.append(encode_animation_frame_32(rgb, w, h, t))
    return out

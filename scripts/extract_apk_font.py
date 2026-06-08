#!/usr/bin/env python3
"""Extract the printable-ASCII subset of a Divoom APK bitmap font (R28).

The official Divoom Android app bundles 16x16 1-bpp bitmap fonts under
``assets/divoom_fond16_*.bin`` / ``FontLib_16_*.bin``. The matrix devices are
16/32/64px, so anti-aliased TrueType text turns to mush — the device-bound text
we rasterise must use these exact bitmap glyphs.

APK storage format (reverse-engineered from ``F2/d.smali``):
  * Each glyph is exactly 32 bytes = 16 rows x 16 cols, 1 bit/pixel.
  * Glyph for codepoint ``cp`` lives at byte offset ``(cp - 0x21) * 32`` for the
    printable-ASCII range ``0x21..0x7e`` (``'A'`` = 0x41 -> index 32, ``'0'`` =
    0x30 -> index 15). (Other Unicode ranges follow in the smali range table.)
  * Within a glyph: 2 bytes per row, little-endian 16-bit, MSB = leftmost pixel,
    but the whole glyph is stored ROTATED — applying a 270deg-CW transform yields
    the upright character.

This script bakes the rotation in at extraction time so the runtime
``BitmapFont`` reader is trivial (read 32 bytes, 2/row, MSB-left, upright). It
writes 95 glyphs for codepoints ``0x20..0x7e`` (space = blank) to
``divoom_lib/fonts/divoom_fond16_default_ascii.bin``.

Usage::

    python3 scripts/extract_apk_font.py            # default font
    python3 scripts/extract_apk_font.py <src.bin> <dst.bin>
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SRC = (
    REPO / "references" / "apk" / "decompiled_src" / "resources" / "assets"
    / "divoom_fond16_default.bin"
)
DEFAULT_DST = REPO / "divoom_lib" / "fonts" / "divoom_fond16_default_ascii.bin"

GLYPH_BYTES = 32          # 16x16 @ 1bpp
FIRST_CP = 0x20           # space (blank)
LAST_CP = 0x7E            # '~'


def _decode_apk_glyph(blob: bytes, cp: int) -> list[list[int]]:
    """Return an upright 16x16 0/1 matrix for ``cp`` from the raw APK blob."""
    idx = cp - 0x21
    g = blob[idx * GLYPH_BYTES : idx * GLYPH_BYTES + GLYPH_BYTES]
    # 2 bytes/row, little-endian 16-bit, MSB = leftmost — the *stored* (rotated)
    # orientation.
    raw = [
        [((g[r * 2] | (g[r * 2 + 1] << 8)) >> (15 - x)) & 1 for x in range(16)]
        for r in range(16)
    ]
    # 270deg-CW transform -> upright glyph.
    return [[raw[c][15 - r] for c in range(16)] for r in range(16)]


def _pack_upright(mat: list[list[int]]) -> bytes:
    """Pack a 16x16 0/1 matrix as 2 bytes/row, MSB = leftmost pixel."""
    out = bytearray()
    for row in mat:
        val = 0
        for x in range(16):
            if row[x]:
                val |= 1 << (15 - x)
        out.append((val >> 8) & 0xFF)   # high byte first (MSB-left, big-endian row)
        out.append(val & 0xFF)
    return bytes(out)


def extract(src: Path, dst: Path) -> int:
    blob = src.read_bytes()
    out = bytearray()
    for cp in range(FIRST_CP, LAST_CP + 1):
        if cp == FIRST_CP:  # space — blank cell
            out += b"\x00" * GLYPH_BYTES
            continue
        out += _pack_upright(_decode_apk_glyph(blob, cp))
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(out)
    return LAST_CP - FIRST_CP + 1


def main(argv: list[str]) -> int:
    src = Path(argv[1]) if len(argv) > 1 else DEFAULT_SRC
    dst = Path(argv[2]) if len(argv) > 2 else DEFAULT_DST
    if not src.exists():
        print(f"source font not found: {src}", file=sys.stderr)
        return 1
    n = extract(src, dst)
    print(f"wrote {n} glyphs ({dst.stat().st_size} bytes) -> {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

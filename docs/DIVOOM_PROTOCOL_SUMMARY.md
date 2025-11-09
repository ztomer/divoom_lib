# Divoom Protocol & References — Quick Summary

Date: 2025-11-09

This document summarizes the findings from reading the reference implementations in `references/` and the scraped API docs in `api_scraper/divoom_docs/`.

## Overview

- Sources reviewed:
  - `references/divoom-ditoo-pro-controller/` (Rust CLI + protocol implementation)
  - `references/node-divoom-timebox-evo/` (Node library and `PROTOCOL.md`)
  - `references/fhem-Divoom/` (Perl tools)
  - `api_scraper/divoom_docs/` — scraped ShowDoc pages; canonical JSON at `divoom_api_full.json`.
- Purpose: understand the packet framing, common command opcodes, and how images/animations are encoded and transferred.

## Protocol essentials

- Packet framing (SPP / RFCOMM standard pattern used by references):
  - Packet: `0x01 + LLLL (2 bytes, LSB-first) + PAYLOAD + CRC (2 bytes, LSB-first) + 0x02`.
  - `LLLL` = length in bytes of PAYLOAD + CRC (includes the length field itself in some docs); multi-byte values are LSB-first.
  - Checksum: 2-byte sum of the bytes (sum across length, command, data) packed LSB-first.
  - Header/footer bytes (0x01 / 0x02) must be escaped when they appear inside payloads in some implementations (see older Perl and node docs).
- BLE/LE variant (used by iOS): 4-byte header `0xFE 0xEF 0xAA 0x55`, then `len (2 bytes)`, `cmd identifier` and optional `packet number` before the payload; ACK behavior differs (ACK cmd 0x33).

## Important opcodes (examples)

- 0x44: Set image / display picture (divoom image-encoded payload). Example message header `44000A0A04 ...` used in references.
- 0x45: Set light mode / channel control.
- 0x49: Set phone gif (animation packet type for pre-LE method).
- 0x8B: App new send GIF / upgraded animation transfer protocol (control words: 0=start, 1=send data (256 bytes blocks), 2=terminate). Device may request resends via control responses.
- 0x74: Set brightness (1 byte 0–100).
- Many more: alarms (0x42/0x43/0x51), system settings, music commands; see `api_scraper/divoom_docs/divoom_api_full.json` for a full list.

## Image & animation encoding notes

- Image format: palette-based representation plus packed pixel data.
  - Build `colorArray` (RRGGBB hex), then `pixelArray` with indices into palette.
  - Bits-per-pixel = ceil(log2(#colors)) with minimum 1.
  - Pixel bits are packed LSB-first per pixel (the JS/node docs detail reversing bit-order in and out); final payload is bytes formed from these packed bits.
- Animations are sent as frames with a frame header and concatenated frames split into chunks the device expects (examples: `49 LLLL NN FRAME_DATA` or app-new `0x8B` with 256-byte chunks).
- Devices expect fixed-size blocks for streaming commands (200 or 256 byte payload blocks in several commands). The app must send control-word start and then chunked data with offset IDs.

## Reference implementations & important files

- Rust (RFCOMM approach; Linux/BlueZ): `references/divoom-ditoo-pro-controller/`
  - `src/lib.rs` and `src/main.rs` show how to serialize packets and send over RFCOMM with `bluetooth-serial-port`.
  - Useful for packet serialization examples and `0x8b` style send flow.
- Node (protocol composition): `references/node-divoom-timebox-evo/`
  - `PROTOCOL.md` explains message framing and image/animation packing in JS-friendly terms (useful for encoding logic).
  - `src/index.ts` creates typed request objects and channels.
- Perl (`references/fhem-Divoom/divoom.pl`): practical RFCOMM/escape examples and multiple image conversion helpers.
- Scraped docs: `api_scraper/divoom_docs/divoom_api_full.json` — consolidated ShowDoc content for each command.

## Key caveats & assumptions

- Several implementations assume RFCOMM/Spp (classic Bluetooth) and rely on platform-specific serial port support (Rust’s `bluetooth-serial-port` works on BlueZ/Linux). macOS might require different Bluetooth handling or use BLE characteristics.
- The app / LE path uses a different header and may need ACK handling; if implementing BLE, follow the iOS LE notes in `base.md`.
- Escaping header bytes (0x01/0x02) occurs in older code paths — ensure your encoder does the necessary escaping for the transport used.

## Suggested next steps (I can implement any of these)

1. Create a small Python helper module `divoom_api/packets.py` that:
   - builds framed packets (length, CRC),
   - encodes images (palette + pixel packing),
   - provides helpers for `set_brightness(0x74)`, `set_image(0x44)`, `send_animation_8b(0x8b)`.
2. Add unit tests that validate length/CRC and reproduce example frames from the Node/Rust encoders.
3. Provide a CLI example that composes and prints hex for a brightness or image command (safe, offline testing).

---
Files you may want to open next:

- `api_scraper/divoom_docs/divoom_api_full.json` — full scraped commands and docs.
- `references/divoom-ditoo-pro-controller/src/lib.rs` & `src/main.rs` — packet examples and RFCOMM usage.
- `references/node-divoom-timebox-evo/PROTOCOL.md` — detailed image/bit packing rules.

If you want, I'll implement option (1) above (a Python packet-builder + unit tests and a small README) next. If so, confirm whether to target RFCOMM (classic Bluetooth) or BLE/LE framing first.

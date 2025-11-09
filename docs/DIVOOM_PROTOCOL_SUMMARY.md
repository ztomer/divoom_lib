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

## BLE / macOS (Bleak) findings — probe results (2025-11-09)

Recent experimentation using `minimal_bleak.py` (Bleak + CoreBluetooth on macOS) produced a few important, practical findings that do not appear prominently in the older RFCOMM-focused docs. These are written so you can re-use the same approach on other Divoom devices.

- Common service namespace: many Divoom devices expose a service UUID in the `49535343-xxxx-...` family (for example `49535343-fe7d-4ae5-8fa9-9fafd205e455`). That service typically contains a small set of characteristics including at least one writeable and one notifiable characteristic.

- Characteristic discovery heuristics (how to find the right chars):
  - Scan and list all characteristics for the device's services. Prefer characteristics that expose `write` or `write-without-response` properties for sending commands. Prefer characteristics with `notify` for ACKs/responses.
  - In practice the following UUIDs were seen on a Timoo device during probe:
    - writeable candidates: `49535343-8841-43f4-a8d4-ecbe34729bb3` (['write-without-response','write']), `49535343-aca3-481c-91ec-d85e28a60318` (['write','notify'])
    - notify candidate (ACKs observed): `49535343-1e4d-4bd9-ba61-23c647249616` (['write-without-response','notify'])
  - Matching strategy: prefer an exact UUID saved from a prior run; if none, prefer a characteristic that belongs to the `49535343-` service and exposes `write` privileges; subscribe to all `notify` characteristics and watch for ACK patterns.

- iOS-LE outer framing (observed in the wild):
  - Header: 0xFE 0xEF 0xAA 0x55
  - Length: 2 bytes, little-endian (counts the remainder as implemented in the examples below)
  - Outer command ID (1 byte) — often 0x45 for light/channel-related operations
  - 4-byte packet number (little-endian)
  - Inner data bytes (application-specific payload)
  - 2-byte checksum (little-endian) computed as a simple sum over the bytes used by the device implementation (length bytes + command + packet number + data in our helper)

- Legacy inner 0x45 variant (critical finding):
  - Some devices accept a nested/legacy format where the iOS-LE outer command is 0x45 and the inner payload begins with 0x45 again, followed by a longer / legacy parameter block. In our probe the exact working inner payload was:

    [0x45, 0x01, 0xFF, 0xFF, 0xFF, 0x64, 0x00, 0x01, 0x00, 0x00, 0x00]

    - Interpretation (likely): outer/inner 0x45 = light/channel family, `0x01` = DIVOOM_DISP_LIGHT_MODE, `0xFF,0xFF,0xFF` = RGB (white), `0x64` = brightness 100, then a series of flags/ids (0x00,0x01,0x00,0x00,0x00) that the firmware expects in the legacy handler.
    - Outer (raw) iOS-LE packet we sent (hex):

      fe ef aa 55 12 00 45 00 00 00 00 45 01 ff ff ff 64 00 01 00 00 00 ff 03

    - In short: devices may silently ignore short/canonical 7-byte variants and only accept this longer legacy form for some light-mode operations.

- ACK detection pattern (useful when subscribing to notifications):
  - Two useful patterns emerged in notifications:
    - Compact/older pattern: a 3-byte fragment [0x04, <cmd>, 0x55] appears within some responses. This is a reliable marker for an ACK for `<cmd>` when seen.
    - iOS-LE style: notifications may contain the `FE EF AA 55` header followed by data; you need to search inside that payload for the same [0x04, <cmd>, 0x55] or directly for the command id bytes (e.g., 0x45).
  - In the test logs an ACK notification looked like: `01 06 00 04 45 55 01 a5 00 02` (the bytes around the 0x45 indicate an ACK was received). The helper in `minimal_bleak.py` looks for both forms.

- Practical testing workflow (recommended for other devices):
  1. Scan for device with a recognizable name (e.g., contains "Timoo" / "Divoom").

 2. Connect and enumerate services & characteristics.
 3. Subscribe to all characteristics with `notify` so you can receive ACKs.
 4. For each write-capable char discovered (prefer those in the `49535343-` service):
     - Try replaying any saved successful payload for that characteristic first (persisted payloads must be stored per-character). If it ACKs, persist the mapping and stop.
     - If no saved payload, try the canonical short/light payloads (7-byte) both as SPP-style framed packets and as iOS-LE framed packets.
     - If canonical attempts fail, try the legacy long inner 0x45 variant wrapped in iOS-LE (the probe found this to succeed).
 5. If you discover a working variant, save the exact inner bytes (not an outer wrapper) along with the characteristic UUID and the framing flag (use iOS-LE or not).

- Persistence & automation guidelines
  - Save: write characteristic UUID, notify/ack characteristic UUID, service UUID, characteristic properties, and a human-friendly description.
  - Also save: the exact last_successful_payload as a hex list, a boolean `last_successful_use_ios_le`, and the `last_successful_write_characteristic` so future runs attempt the correct payload on the correct char before probing.
  - Prefer per-character payload mapping (i.e., allow multiple saved payloads keyed by characteristic UUID). Device firmware variants and mobile OS BLE stacks sometimes require the same command to be issued on a specific characteristic.

- Implementation notes (what to implement in helpers):
  - construct_ios_le_packet(cmd, payload, pktnum=0): build outer header, compute length properly, include packet number, and compute checksum as the sum over length bytes + cmd + pktnum + data bytes, packaged as 2 bytes LSB-first.
  - construct_spp_packet(cmd, payload): build START(0x01) + len + escaped payload + CRC + END(0x02) as in RFCOMM/SPP-style references.
  - notification handler: search notifications for both the 3-byte [0x04, cmd, 0x55] pattern and for the `FE EF AA 55` header then scan inside.

## Troubleshooting & tips

- Timing: some devices need a short delay after subscribing to notifications before accepting writes. Add a configurable `post_connect_delay_ms` (100–500 ms) if you see flakiness.
- Escaping: when building SPP packets ensure you escape 0x01/0x02/0x03 inside payloads using the documented escape sequences to avoid corrupting framing bytes.
- MTU/chunking: firmware that accepts `0x8B` (animation upload) expects fixed-size chunks (e.g., 200 or 256 bytes) — follow the Rust/node examples for chunking and start/stop control words.

## Recommended next docs/tasks (I can implement any of these)

- Add a short `BLE-quickstart.md` describing the exact discover → subscribe → replay → persist workflow with terminal commands and minimal example outputs.
- Add examples in `docs/` showing:
  - The exact working legacy packet hex and how to build it from helper functions.
  - How to inspect `.divoom_last_working_char.json` and interpret saved payload entries.
  - How to use the new CLI flags in `minimal_bleak.py` such as `--replay-legacy` and `--skip-channel-switch`.
- Add verbose logging and a `--test-saved-only` mode for quick CI checks.

If you want, I'll add `BLE-quickstart.md` and update `DIVOOM_PROTOCOL_SUMMARY.md` further with step-by-step commands and copyable examples. Which two artifacts should I produce next? (suggestion: `BLE-quickstart.md` + `docs/EXAMPLES.md` with the constructed packet examples)

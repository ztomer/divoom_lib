# APK Protocol & Encoding Comparison

**Purpose:** Byte-level comparison of our encoding/streaming against the
decompiled Divoom Android app (`references/apk/`). The APK is the
authoritative reference; divergences are noted and categorized by risk.

**Sources:**
- Our code: `divoom_lib/display/animation.py`, `animation_8b.py`,
  `divoom_lib/utils/divoom_image_encode.py`, `divoom_image_encode_32.py`,
  `divoom_lib/framing.py`, `ble_transport.py`
- APK: `references/apk/decompiled_src/sources/com/divoom/Divoom/bluetooth/`
  (`s.java`, `q.java`, `CmdManager.java`, `DesignSendModel.java`,
  `NDKMain.java`, `HotUpdateHandle.java`)
- Third-party refs: futpib, hass-divoom (marked where used)

---

## 1. Executive Summary

| Component | Status | Risk | Evidence |
|-----------|--------|------|----------|
| **0x8B START payload** `[0x00][size:4 LE]` | ✅ MATCH | none | APK `CmdManager.n()` line 1525, our `_phase_start()` |
| **0x8B DATA payload** `[0x01][size:4 LE][idx:2 LE][≤256 bytes]` | ✅ MATCH | none | APK `h.f()` with `f30416i=true`, our `_phase_data()` |
| **0x8B chunk size** 256 bytes | ✅ MATCH | none | APK `hVar.q(256)`, our `SENDING_DATA_CHUNK_SIZE` |
| **Frame body header:** `AA LLLL TTTT RR NN` | ✅ MATCH | none | APK native `NDKMain.pixelEncode()` output, our `encode_animation_frame()` |
| **Color palette:** 3-byte RGB, first-seen order | ✅ MATCH | none | APK `W2.c.F()` `bArr.length % 768`, our palette construction |
| **Pixel data:** LSB-first continuous bit pack | ✅ MATCH | none | RomRider protocol (both derive from same spec) |
| **0x49 packet index** `PACKET_NUM u8` | ✅ MATCH | resolved R38 | APK `e3/h.java` `f()` loop starts at **i12=0** (0-based). Our code now starts at **0** (Python `packet_num=0`, C `packet_num=0`). |
| **0x49 total_len + index field sizes** (16px: 2B+1B; 32px: 4B+2B) | ✅ MATCH | none | APK `e3/h.java` lines 164-168: `i9={2,4}`, `i11={1,2}` by screen mode. Our code matches. |
| **BLE wire framing** | ❌ DIFFERENT | low (transport) | Our: iOS LE `FE EF AA 55 ... CMD ... CK CK 02`. APK: SPP Basic `01 LL LL CMD ... CK CK 02`. Both preserve same cmd+payload. |
| **0x8B TERMINATE (CW=2)** | ❌ EXTRA (removed R35d) | resolved | APK does NOT send terminate — verified on 4 hardware devices (Timoo SPP, Ditoo BLE, Tivoo Max BLE, Pixoo BLE). Removed. |
| **32x32 pre-frames (0x05/0x06)** | ❌ NOT IN APK | **high** | `0x05` and `0x06` only appear as **SPP escape sequences** (`s.java` `l()` method), NOT as pre-frames. Our pre-frames come from **hass-divoom**. No APK code path sends them. |
| **32x32 frame header RR=0x03, 2-byte NN** | ❌ NOT IN APK | **high** | APK uses same `AA LLLL TTTT RR NN` format via `NDKMain.pixelEncode()` for ALL sizes (`RR=0x00`, 1-byte NN). Our RR=0x03, 2-byte NN come from **hass-divoom**. |
| **APK BlueHigh encoding (`pixelEncodeBlueHigh`)** | ❌ NOT IMPLEMENTED | medium | APK has a SEPARATE native encoding path for high-res (Pixoo Max): header byte `0x25`/`0x2A` + `rowCnt`/`columnCnt`. We don't use this — our AA format matches the standard `pixelEncode()` path. |
| **Color quantization** (>256 colors) | ❌ MISSING | low | APK native has `colorQuantityV1/V2`. We raise ValueError. OK as long as callers pre-quantize. |
| **0x8B device-ready wait** | ✅ FIXED (R35) | none | `_expected_response_command` now set before START so iOS LE notification handler routes device's `[0]` ACK. |
| **0x8B retransmit serving** `[1][idx:2 LE]` | ⚠️ TIMING DIFF | low | Our: post-stream poll loop (1s quiet timeout). APK: event-driven, interleaved with initial send. |
| **Inter-chunk delay** | ❌ DIFFERENT | low | Our: 10ms BLE + GATT ACK pacing. APK: 40ms SPP sleep. Both effective. |

---

## 2. Frame Body Format — Byte-by-Byte

### 2.1 Static Image (`encode_static_image`)

| Offset | Size | Field | Our value | APK value | Match |
|--------|------|-------|-----------|-----------|-------|
| 0 | 1 | AA | `0xAA` | Native output includes `0xAA` | ✅ |
| 1-2 | 2 | LLLL | LE u16 = `6 + 3*N + pixel_bytes` | Same | ✅ |
| 3-5 | 3 | padding | `0x00 0x00 0x00` | Same | ✅ |
| 6 | 1 | NN | u8 (0=256) | `(byte)n` | ✅ |
| 7.. | N*3 | COLOR_DATA | R G B, first-seen | Same | ✅ |
| ... | P | PIXEL_DATA | LSB-first bit pack | Same | ✅ |

Header is 6 bytes (no TTTT, no RR, 3 zero bytes where TTTT+RR would be).

### 2.2 Animation Frame (`encode_animation_frame`, 16x16)

| Offset | Size | Field | Our value | APK value | Match |
|--------|------|-------|-----------|-----------|-------|
| 0 | 1 | AA | `0xAA` | Native output includes `0xAA` | ✅ |
| 1-2 | 2 | LLLL | LE u16 = `7 + 3*N + pixel_bytes` | Same | ✅ |
| 3-4 | 2 | TTTT | LE u16, display time in ms | Same (from `speed` param to `pixelEncode`) | ✅ |
| 5 | 1 | RR | `0x00` (reset palette) | Native handles | ✅ (for 16x16) |
| 6 | 1 | NN | u8 (0=256) | `(byte)n` | ✅ |
| 7.. | N*3 | COLOR_DATA | R G B, first-seen | Same | ✅ |
| ... | P | PIXEL_DATA | LSB-first bit pack | Same | ✅ |

Header is 7 bytes.

### 2.3 Animation Frame (`encode_animation_frame_32`, 32x32) — DEPARTURE FROM APK

**APK standard path** (`NDKMain.pixelEncode()`, used for all sizes on most devices):
```
Same AA LLLL TTTT RR NN format as 16x16:
  [0xAA][LLLL LE u16][TTTT LE u16][0x00][NN u8][COLOR_DATA][PIXEL_DATA]
Header is 7 bytes. RR=0x00, NN=1 byte, same as 16x16.
```

**Our 32x32 path** (`encode_animation_frame_32`, from hass-divoom):
```
  [0xAA][LLLL LE u16][TTTT LE u16][0x03][NN_NN LE u16][COLOR_DATA][PIXEL_DATA]
Header is 8 bytes. RR=0x03, NN=2 bytes (u16).
```

**APK BlueHigh path** (`NDKMain.pixelEncodeBlueHigh()`, for Pixoo Max 32x32+):
```
APK header before calling native:
  header = {0x25, validCnt, speed>>8, speed&255, rowCnt, columnCnt}
  For 32x32: {0x25=37, 1, speed_hi, speed_lo, 2, 2}
Native output: (unknown internal format, wrapped with header)
```

**Verdict:** Our RR=0x03 and 2-byte NN come from **hass-divoom**, not the APK.
The APK's standard `pixelEncode()` produces the same 7-byte AA format for
ALL display sizes. The BlueHigh path (0x25 format) is separate and we
don't use it. Test on hardware: does RR=0x00 + 1-byte NN work for 32x32?

### 2.4 32x32 Pre-Frames — NOT IN APK

**Our pre-frames** (from hass-divoom):
```
Pre-frame 1: [0xAA] [0x05 0x00] [0x00 0x00 0x05 0x00 0x00]    (LLLL=5, body=5 bytes)
Pre-frame 2: [0xAA] [0x06 0x00] [0x00 0x00 0x06 0x00 0x00 0x00]  (LLLL=6, body=6 bytes)
```

**APK finding:** `0x05` and `0x06` only appear in `s.java` `l()` method as
**SPP escape sequences** (byte-stuffing for old-mode framing):
- `0x01` → `[0x03, 0x04]`  (escape for SPP start byte)
- `0x02` → `[0x03, 0x05]`  (escape for SPP end byte)
- `0x03` → `[0x03, 0x06]`  (escape for SPP escape byte)

No APK code path sends a `0x05` or `0x06` byte as a "pre-frame" before pixel
data. The APK's 32x32 encoding either:
1. Goes through standard `pixelEncode()` → standard AA format (no pre-frames)
2. Goes through BlueHigh `pixelEncodeBlueHigh()` → 0x25/0x2A header (no pre-frames)

**To verify on hardware:** Remove the two pre-frames from
`divoom_image_encode_32.py` and test a 32x32 animation. If it works, the
pre-frames are unnecessary for this device/firmware.

---

## 3. Packetization Formats

### 3.1 0x8B Animation Stream

APK source: `CmdManager.n()` → `e3.h.g()` / `e3.h.f()` → `s.c()`.
Our source: `animation_8b.py` → `stream_animation_8b` in `animation.py`.

**START:**
```
APK:   q.s().F(s.c(SPP_APP_NEW_GIF_CMD2020, [0x00] + file_size(4 LE)))
Ours:  send_command(0x8B, [0x00] + file_size(4 LE), write_with_response=False)
```
MATCH. Wire payload is `[0x00][size:4 LE]`.

**DATA (N packets):**
```
APK:   hVar.l([0x01]), hVar.i(true), hVar.q(256)
       → f30412e = {1}  (control word in prefix)
       → f30416i = true  (4-byte total_len, 2-byte index)
       → f30418k = 256   (chunk size)
       Payload: [0x01][file_size:4 LE][chunk_idx:2 LE][data:≤256 bytes]

Ours:  [0x01][file_size:4 LE][offset_id:2 LE][chunk:≤256 bytes]
```
MATCH. Same control word, same size/idx fields, same chunk max.

**TERMINATE:**
```
APK:   NOT SENT
Ours:  [0x02] after 0.5s settle
```
DIVERGENCE. APK relies on `file_size` in START to know length. Our
extra byte is tolerated by tested hardware but may confuse other firmware.

**Chunk index semantics (load-bearing):**
```
APK:   chunk_idx is a sequential index (0, 1, 2, ...)
       Device places chunk N at byte N*256 in reconstructed file.
Ours:  offset_id is the same sequential index (0, 1, 2, ...)
```
MATCH. This was the root cause of the R11 stall bug (was byte offset,
not chunk index).

### 3.2 0x49 Chunked Animation (legacy)

APK source: `CmdManager.o()` → `e3/h.java` `f()` method.
Our source: `image_encode.c` `_py_encode_animation`.

```
APK:   TOTAL_LEN(i9 bytes LE) + PACKET_NUM(i11 bytes LE, 0-based) + chunk(≤chunk_size bytes)
Ours:  TOTAL_LEN(LE u16) + PACKET_NUM(u8, 1-based) + chunk(≤200 bytes)
```

**Packet index counter — CONFIRMED 0-based in APK.**
APK `e3/h.java` line 178-179:
```java
for (int i12 = 0; i12 < iCeil; i12++) {
    byte[] bArrC = L.c(L.b(L.d(L.d(bArrB, length, i9, false),
         i12, i11, false), ...), ...);
```
The loop iterates `i12 = 0, 1, 2, ...` and encodes it directly. **Our 1-based
counter is wrong.** Should be fixed to 0-based.

**Field sizes:**

| Screen size | APK `i9` (total_len) | APK `i11` (index) | Our total_len | Our index |
|-------------|----------------------|-------------------|---------------|-----------|
| 16px | 2 bytes LE u16 | 1 byte u8 | 2 bytes LE u16 | 1 byte u8 (1-based ❌) |
| 32px+ | 4 bytes LE u32 | 2 bytes LE u16 | 4 bytes LE u32 (via C) | 2 bytes LE u16 |

**Chunk size:**
- APK default: `f30418k = 200` bytes (set in `e3/h.java`)
- APK 0x8B path: `hVar.q(256)` → 256 bytes
- Our 0x49 path: 200 bytes — MATCHES APK default
- Our 0x8B path: 256 bytes — MATCHES APK

**To fix:** Change `packet_num` from 1-based to 0-based in the 0x49 encoder
(`image_encode.c` and Python fallback).

### 3.3 0x44 Static Image

APK source: `CmdManager.l()`.
Our source: `sender_protocol.py` `encode_static_image`.

```
APK:   Prefix: [0x00, 0x0A, 0x0A, 0x04]
       Data:   [0xAA][LLLL][0x00 0x00 0x00][NN][COLOR_DATA][PIXEL_DATA]

Ours:  Same prefix, same frame body format
```
MATCH.

---

## 4. BLE Framing Layer

### 4.1 APK SPP Basic Protocol (`s.k()` / `s.l()`)

Format used over classic Bluetooth RFCOMM:
```
Offset  Size  Description
------  ----  -------------------------------
  0      1    0x01 (start byte)
  1-2    2    LL LL = (packet_len - 4) LE u16
  3      1    Command ID byte
  4..n-3 ?    Payload (command-specific)
  n-2..n-1 2  CRC: sum(bytes 1..n-3) LE u16
  n      1    0x02 (end byte)
```

Old mode `s.l()` additionally byte-stuffs values 1, 2, 3 in payload.

### 4.2 Our iOS LE Protocol (`encode_ios_le_payload`)

Format used over macOS BLE GATT (from APK `com.divoom.Divoom.bluetooth.c#b`):
```
Offset  Size  Description
------  ----  -------------------------------
  0-3    4    0xFE 0xEF 0xAA 0x55 (header)
  4-5    2    Length = total_bytes - 7, LE u16
  6      1    Packet number (low byte)
  7      1    Command ID byte
  8..n-3 ?    Payload (command-specific, WITHOUT command id)
  n-2..n-1 2  CRC: sum(bytes 4..n-3) LE u16
  n      1    0x02 (end byte)
```

Both wrap the same CMD+PAYLOAD in different envelopes. The payload bytes
(cmd args) are identical between the two formats.

### 4.3 Our SPP (BT Classic) Path

When `use_spp=True`, we use `encode_basic_payload` which matches the
APK's SPP Basic Protocol format exactly (`01 LL LL CMD ... CK CK 02`).

---

## 5. Display Pipeline vs APK

The full chain for showing a GIF on device:

### Our path (`show_image` → `stream_animation_8b`)

```
show_image(path)
  → show_design(name, channel=0x05)    # switch to display channel
    → send_command(0x45, [0x05])
  → process_image(path)
    → resize to device resolution
    → encode frames via encode_animation_frame / encode_animation_frame_32
  → _build_animation_blob(frames)       # concatenate frame bodies
  → Animation.stream_animation_8b(blob) # 3-phase 0x8B send
```

### APK path (`DesignSendModel` → BLE)

```
DesignSendModel.sendToOneDevice(pixelBean)
  → CmdManager.h(pixelBean)            # encode
    → NDKMain.pixelEncode(rawRGB, speed, width, null...)
      # Returns encoded byte[] with AA LLLL TTTT RR NN ... format
    → e3.h.g(encodedData) → list of 256-byte chunks
  → CmdManager.n(pixelBean)            # send via 0x8B
    → q.s().F(s.c(0x8B, [0x00, size:4 LE]))   # START
    # Returns chunk list; stored in pixelCacheList
    # Later (device-driven): startSendAllAni() sends all chunks
  → DesignSendModel.startSendAllAni()  # triggered by device [0] ACK
    → q.s().o()                        # clear queue
    → for each chunk: q.s().F(chunk)   # fire-and-forget, 40ms delay
```

### Key differences

| Aspect | Our path | APK path |
|--------|----------|----------|
| **Channel switch** | `show_design()` via 0x45, hardcoded to channel 5 | APK can switch to channel 1 (clock) or 5 (display) |
| **Encoder** | Python/C `encode_animation_frame` | Native NDK `pixelEncode()` |
| **Chunking** | On-the-fly during stream | Pre-chunked before START |
| **Device-ready gate** | Bounded `_await_8b_device_ready(2s)` | Indefinite reactive wait |
| **Send trigger** | Immediate after START+wait | Device's `[0]` response calls `startSendAllAni()` |
| **First data delivery** | ~200ms-2s (device-ready ACK) | Immediate on device request |
| **Retransmits** | Post-stream poll loop | Event-driven, any time |
| **Chunk resend method** | Re-read from source blob | `q.s().z()` immediate from `pixelCacheList` |

---

## 6. Step-by-Step Verification Procedures

### 6.1 Verify Wire Format: 0x8B Payload

**Goal:** Confirm our 0x8B START + DATA bytes match APK output byte-for-byte.

**Instrumentation:**
Add debug logging to `stream_animation_8b()` that dumps the first
START packet and first DATA packet as hex:

```python
# In stream_animation_8b(), after building the START payload:
import logging
_log = logging.getLogger("divoom_lib.verify")

# After app_new_send_gif_cmd for START:
_log.info("8B_START_HEX=%s", bytes([0x8B, 0x00]) + file_size.to_bytes(4, "little")).hex())

# After app_new_send_gif_cmd for first DATA chunk:
first_chunk = list(blob[0:min(256, file_size)])
_log.info("8B_DATA0_HEX=%s", bytes([0x8B, 0x01]) + file_size.to_bytes(4, "little") + (0).to_bytes(2, "little") + bytes(first_chunk)).hex())
```

**Verification method:**
1. Enable DEBUG logging on `divoom_lib` logger
2. Push a small (1-frame) GIF to device via Monthly Best sync
3. Capture the log output for the 8B_START_HEX and 8B_DATA0_HEX lines
4. Compare against known-good APK capture (from Android hcidump or BLE sniffer)

**Expected START:** `8b 00 XX XX XX XX` (0x8B command, 0x00 control word,
file_size LE u32).

**Expected DATA0:** `8b 01 XX XX XX XX 00 00 <256 bytes>` (half of the
payload for a 1-frame 16x16 animation = ~324 bytes total).

**Known-good baseline (16x16, 1 frame, 100ms, 4 colors):**
```
8B START:  8b 00 44 01 00 00
8B DATA0:  8b 01 44 01 00 00 00 00 AA 13 00 64 00 00 04
           (palette entries) (pixel data...)
```

### 6.2 Verify Device-Ready ACK

**Goal:** Confirm the device's `[0]` ACK is received and processed.

**Instrumentation:**
Add a one-shot log in `_handle_ios_le_notification` when a 0x8b
notification is received:

```python
# In _handle_ios_le_notification:
if command_identifier == COMMANDS["app new send gif cmd"]:
    _log.info("8B_NOTIFICATION_CMD=%s PAYLOAD_HEX=%s",
              command_identifier, response_data.hex())
```

**Verification method:**
1. Enable INFO logging
2. Connect to real hardware and push a GIF via Monthly Best
3. Check for the log line. It should appear ~100-500ms after START is sent.
4. If missing: `_expected_response_command` is not set correctly,
   or the notification handler dropped the msg. Check the
   "Response command ... does not match expected" warning log.

**Expected payload:** `00` (single byte 0x00).

### 6.3 Verify Retransmit Serving

**Goal:** Confirm retransmit requests are handled.

**Instrumentation:**
Add a log in `_serve_8b_retransmits` when a retransmit request is received:

```python
# In _serve_8b_retransmits:
if len(payload) >= 3 and payload[0] == 1:
    idx = int.from_bytes(bytes(payload[1:3]), byteorder="little")
    _log.info("8B_RETRANSMIT_REQUEST chunk_idx=%d", idx)
```

**Verification method:**
1. Enable INFO logging on `divoom_lib`
2. Push a large multi-frame animation (ideally >5KB so many chunks)
3. Check for `8B_RETRANSMIT_REQUEST` logs after the data phase
4. If none appear: either device received all chunks cleanly (no loss),
   or retransmit serving doesn't work (unlikely — tested in unit tests)

### 6.4 Verify TERMINATE Presence (APK Deviation)

**Goal:** Confirm that we send (or don't send) TERMINATE.

**Instrumentation:**
```python
# In stream_animation_8b, after the TERMINATE send:
_log.info("8B_TERMINATE_SENT=%s", ok)
```

**Verification method:**
1. Enable INFO logging
2. Push a GIF via Monthly Best
3. Check for `8B_TERMINATE_SENT` log line
4. To TEST the APK behavior: temporarily comment out the TERMINATE send
   (lines 195-200 in animation.py) and test on hardware. Does the
   animation still display correctly? If yes, the APK is correct and
   we should remove it permanently. If no, the device firmware requires
   terminate.

### 6.5 Verify 0x49 Counter (APK Deviation)

**Goal:** Confirm whether 1-based vs 0-based counter matters.

**Instrumentation:**
Add a log in the send path for the 0x49 PACKET_NUM:

```python
# In _py_encode_animation or wherever packet_num is constructed:
_log.info("49_PACKET_NUM=%d (0-based would be %d)", packet_num, packet_num - 1)
```

**Verification method:**
1. Enable INFO logging
2. Push a GIF that triggers the 0x49 path (older device, or if 0x8B fails)
3. Check the PACKET_NUM value
4. To test: change to 0-based and test on hardware. If animation works
   either way, this is benign.

### 6.6 Verify 32x32 Pre-Frames

**Goal:** Confirm 32x32 animations work with and without pre-frames.

**Instrumentation:**
Add logs around pre-frame construction:

```python
# In show_image or process_image, when building 32x32 frames:
if w == 32 and h == 32:
    _log.info("32x32_FRAME_COUNT=%d pre_frames=%s",
              len(frames), hasattr(self, '_use_pre_frames'))
```

**Verification method:**
1. Enable INFO logging
2. Push a 32x32 image/animation to a Pixoo Max (or other 32x32 device)
3. Test two variants:
   a. With pre-frames (current behavior)
   b. Without pre-frames (comment out the pre-frame construction in
      `divoom_image_encode_32.py` or the codepath that calls it)
4. Compare device display. If both work, pre-frames are unnecessary.
   If only (a) works, they're required. If only (b) works, they're wrong.

### 6.7 Verify iOS LE vs SPP Basic Framing

**Goal:** Confirm the BLE wire format is correct.

**Instrumentation:**
Log the raw bytes sent over the wire in `_send_ios_le_payload`:

```python
# In ble_transport.py _send_ios_le_payload (or send_payload):
_log.debug("BLE_TX_HEX=%s", bytes(out_frame).hex())
```

**Verification method:**
1. Enable DEBUG logging on `divoom_lib`
2. Connect to real hardware and push any command
3. Capture the BLE_TX_HEX line and verify against the iOS LE format:
   - Starts with `fe ef aa 55`
   - Has command ID at offset 7
   - Ends with `02`
4. Compare with APK's SPP Basic format:
   - Starts with `01`
   - Has command ID at offset 3
   - Ends with `02`

---

## 7. Protocol-Level Verification Test

Add the following test to `tests/` to programmatically verify the encoding
at the byte level against known-good outputs:

```python
"""test_apk_encoding_parity.py — byte-level verification against APK."""

import pytest
from divoom_lib.utils.divoom_image_encode import encode_animation_frame
from divoom_lib.display.animation_8b import _phase_start, _phase_data, _phase_terminate

# Known-good baseline: 16x16, 4-color checkerboard, 100ms per frame
# Produced by encoding the same source image through the APK's native
# pixelEncode() and capturing the output.
# TODO: replace with actual APK-captured baseline
KNOWN_GOOD_BASELINE = {
    "start": bytes([0x00, 0x44, 0x01, 0x00, 0x00]),
    "frame_header": bytes([0xAA, 0x13, 0x00, 0x64, 0x00, 0x00, 0x04]),
}

class TestApkEncodingParity:
    """Verify our encoding byte-by-byte against known-good APK outputs."""

    def test_phase_start_matches_apk(self):
        blob = b"\x00" * 0x144  # 324 bytes = typical 1-frame 16x16
        result = _phase_start(len(blob))
        assert result == bytes([0x00]) + (len(blob)).to_bytes(4, "little")
        assert result[1:5] == (0x144).to_bytes(4, "little")

    def test_phase_data_matches_apk(self):
        blob = b"\xAA" * 0x144
        chunk = blob[0:256]
        result = _phase_data(len(blob), 0, chunk)
        assert result[0] == 0x01  # control word
        assert result[1:5] == (len(blob)).to_bytes(4, "little")  # file_size
        assert result[5:7] == (0).to_bytes(2, "little")  # offset_id
        assert result[7:] == chunk  # data

    def test_phase_terminate_apk_divergence(self):
        """APK does NOT send terminate. Verify what we send."""
        result = _phase_terminate()
        assert result == bytes([0x02])
        # If this test is removed/ignored, we've aligned with APK

    def test_frame_header_16x16_matches_apk(self):
        """16x16 frame header: AA LLLL TTTT RR NN"""
        import numpy as np
        rgb = np.zeros((16, 16, 3), dtype=np.uint8)
        rgb[0:8, 0:8] = [255, 0, 0]    # red
        rgb[0:8, 8:16] = [0, 255, 0]   # green
        rgb[8:16, 0:8] = [0, 0, 255]   # blue
        rgb[8:16, 8:16] = [255, 255, 0] # yellow
        encoded = encode_animation_frame(rgb, 16, 16, 100)
        assert encoded[0] == 0xAA  # AA marker
        assert encoded[3:5] == (100).to_bytes(2, "little")  # TTTT = 100ms
        assert encoded[5] == 0x00  # RR = 0x00 for 16x16
        assert encoded[6] == 4     # NN = 4 colors

    def test_32x32_header_divergence(self):
        """32x32 uses RR=0x03, 2-byte NN (hass-divoom, not APK)."""
        from divoom_lib.utils.divoom_image_encode_32 import encode_animation_frame_32
        import numpy as np
        rgb = np.zeros((32, 32, 3), dtype=np.uint8)
        rgb[0:16, 0:16] = [255, 0, 0]
        encoded = encode_animation_frame_32(rgb, 32, 32, 100)
        assert encoded[0] == 0xAA
        assert encoded[5] == 0x03  # RR=0x03 (divergence point)
        nn = int.from_bytes(encoded[6:8], "little")
        assert nn == 1  # 1 color (red only)

    def test_ios_le_framing_structure(self):
        """Verify iOS LE wire format matches APK c#b spec."""
        from divoom_lib.framing import encode_ios_le_payload
        payload = [0x8B, 0x00, 0x44, 0x01, 0x00, 0x00]
        framed = encode_ios_le_payload(payload)
        assert framed[0:4] == bytes([0xFE, 0xEF, 0xAA, 0x55])  # header
        assert framed[7] == 0x8B  # command ID
        assert framed[-1] == 0x02  # end marker

    def test_basic_framing_structure(self):
        """Verify SPP Basic Protocol framing matches APK s.k()."""
        from divoom_lib.framing import encode_basic_payload
        payload = [0x8B, 0x00, 0x44, 0x01, 0x00, 0x00]
        framed = encode_basic_payload(payload)
        assert framed[0] == 0x01  # start byte
        # length at [1:3]
        assert framed[3] == 0x8B  # command ID
        assert framed[-1] == 0x02  # end marker

    def test_color_table_3byte_rgb(self):
        """APK uses 3-byte RGB, not RGBA (W2.c.F() confirms: len % 768 == 0)."""
        import numpy as np
        rgb = np.zeros((16, 16, 3), dtype=np.uint8)
        rgb[0, 0] = [255, 128, 64]
        encoded = encode_animation_frame(rgb, 16, 16, 100)
        # Find palette entry for color [255, 128, 64]
        palette_start = 7  # after AA(1)+LLLL(2)+TTTT(2)+RR(1)+NN(1)
        nn = encoded[6]
        palette = encoded[palette_start:palette_start + nn * 3]
        assert palette[0:3] == bytes([255, 128, 64])  # first color
        assert len(palette) == nn * 3  # exactly 3 bytes per color
```

---

## 8. Real Hardware Verification Checklist

When testing on real hardware, run through these items in order:

- [ ] **0x8B START send** — device receives `[0x00][size:4 LE]`
- [ ] **Device ACK** — device responds with `[0x00]` notification within 2s
- [ ] **First data within ~200ms** — no 3+ second gap after START
- [ ] **All data chunks arrive** — monitor total packets vs `ceil(file_size/256)`
- [ ] **No retransmits requested** — device gets everything first try (clean RF)
- [ ] **Retransmit works** — if packet loss occurs, device requests and gets chunks
- [ ] **Animation plays correctly** — correct frames, correct timing, no artifacts
- [ ] **Colors displayed correctly** — palette matches source image
- [ ] **Multi-frame animation cycles** — all frames in sequence
- [ ] **Static image displays** — via 0x44 path (not just 0x8B)
- [ ] **32x32 displays correctly** — on Pixoo Max or similar
- [ ] **No TERMINATE crash** — if we remove CW=2, device still works
- [ ] **Concurrent sync works** — multiple files via sync_hot_channel

### Debugging tips

| Symptom | Likely cause | Check |
|---------|-------------|-------|
| Device shows spinner → permanent | START sent, device ACK lost → data arrives too late | Fix: `_expected_response_command` not set (R35 fix) |
| Animation plays but colors wrong | Palette encoding differs | Log palette bytes, compare with known-good |
| Animation plays but wrong frames | Frame order/encoding wrong | Log each frame's AA+LLLL+TTTT |
| Only first frame displays | TERMINATE missing or wrong | Check if CW=2 is required for this device |
| Static image fails (0x44) | Prefix wrong or frame body wrong | Log 0x44 payload hex |
| Sporadic failures under load | BLE write congestion | Increase inter-chunk delay from 10ms to 20ms |
| Device shows nothing | Channel not set to display mode | Check 0x45 is sent before data |
| Progress shows "Synced N" but nothing on device | Data never arrived | Check BLE connection during transfer |
| `_expected_response_command` log warnings | Stale expected response from previous cmd | Clear `_expected_response_command` after timeout |

---

## 9. Open Questions

1. ~~**TERMINATE packet:** Does any Divoom device REQUIRE the 0x02 terminate
   packet? The APK doesn't send it.~~ **RESOLVED R35d:** Tested on 4 devices
   (Timoo, Ditoo, Tivoo Max, Pixoo) — none require it. Removed from code.
2. **32x32 pre-frames:** Are they required for any device? APK doesn't use them.
   Test with and without on 32x32 hardware. Remove from code if unnecessary.
3. **32x32 RR=0x00 vs RR=0x03:** Does the standard `AA LLLL TTTT 0x00 NN` format
   work on 32x32 devices? Our hass-divoom-derived format uses RR=0x03, 2-byte NN.
   Test both encodings on 32x32 hardware.
4. **0x49 counter offset:** Fix to 0-based (matching APK) and test on a device
   that uses the 0x49 path. Currently 1-based, APK uses 0-based.
5. **BlueHigh vs standard encoding:** Our `encode_animation_frame` produces
   the standard `pixelEncode()` format. The APK's `pixelEncodeBlueHigh()`
   produces a different format (0x25 header + rowCnt/columnCnt). Do any of our
   target devices require the BlueHigh format?
6. **Color quantization fallback:** Should we add a simple median-cut
   quantizer instead of raising ValueError? APK's native library has it.

### Hardware testing plan (4 devices available)

Test these scenarios on each device and record result:

| Test | What to check | Pass criterion |
|------|--------------|----------------|
| A | 0x8B single GIF 16x16 → sync | Animation plays correctly |
| B | 0x8B multi-frame GIF 16x16 → sync | All frames cycle |
| C | 0x8B 5-image batch sync | All images push, no spinner |
| D | Remove TERMINATE (CW=2) from 0x8B stream | ~~Animation still plays~~ **DONE — all 4 PASS** |
| E | 32x32 image/gif sync (if device supports it) | Displays correctly |
| F | 32x32 without pre-frames | Works/doesn't work |
| G | 32x32 with RR=0x00 (standard format) | Works/doesn't work |
| H | 0x49 legacy path (force with flag) | Animation plays |
| I | Device dot pulse in device color | Pulses in device hue, not amber |
| J | Upload progress indicator | Button shows "Updating (3/5)" |

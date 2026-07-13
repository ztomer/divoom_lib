# Custom Channel Push: Current Implementation vs. APK

## The Problem

`sync_artwork` (gallery "Update Device") downloads a cloud file, decodes it,
resizes to device resolution, then calls `divoom.display.show_image()`.

`show_image()` calls `show_design()` then pushes the AA-encoded frames over
`0x8B` 3-phase protocol. The data transfers correctly and the device renders
it — **but on the HOT channel, not the CUSTOM/DESIGN channel**.

Root cause: our channel-routing mechanism (`0x45 [0x05]`) is different from the
APK's (`0xBD [0x31]`), and the APK uses a different data command family
(`0x014C`/`0x8C`) instead of `0x8B` for user-define content.

---

## Current Code — Wire Sequence

File references in `divoom_lib/display/__init__.py`.

```
show_design()                   → 0x45 [0x05, 0x00, 0x00, 0x00, 0x00,
                                           0x00, 0x00, 0x00, 0x00, 0x00]
                                     ("set light mode", payload = channel 0x05)

show_image() → _build_animation_blob(frames)
               → AA-format per frame:
                   0xAA, LLLL, TTTT, RR=0x00, NN, palette, pixel_indices

stream_animation_8b(blob)       → 0x8B [0x00, file_size:4 LE]         START
                                 0x8B [0x01, file_size:4 LE,
                                        chunk_idx:2 LE, chunk:≤256B]  DATA ×N
                                 _serve_8b_retransmits(…)              RETRANSMIT
```

**Wire bytes (before SPP framing)** for a single 16×16 frame:

```
45  05 00 00 00 00 00 00 00 00 00           ← channel switch to 0x05
8B  00 1A 00 00 00                          ← 0x8B START, size=26
8B  01 1A 00 00 00 00 AA 12 00 64 00 00    ← 0x8B DATA chunk 0
             01 00 02 00 FF 00 00 00
             00 00 00 00 00 00 00 00 00
```

Note: `0x45 [0x05]` is `SPP_SET_BOX_MODE` with payload `[USER_DEFINE_MODE=5]`.
The APK **never uses this command** for gallery push-to-device.

---

## APK — Wire Sequence

APK source: `DesignSendModel.playByBlue()` → `CmdManager.y3()` + `CmdManager.n()`.

APK source files (decompiled):
- `com/divoom/Divoom/view/fragment/designNew/model/DesignSendModel.java:145`
- `com/divoom/Divoom/bluetooth/CmdManager.java:1927` (y3), `1509` (n)

```
clear pixel cache queue            → internal (q.s().o())
stop hot update                    → 0x9F  (HotUpdateHandle.p().C())
"start gif" routing signal         → 0xBD [0x31]   (CmdManager.y3())
                                   ← SPP_DIVOOM_EXTERN_CMD
                                   ← SPP_SECOND_APP_SEND_GIF_START

[if device supports NewAniSendMode2020]:
  encode pixel data (e3.h encoder)
  send header                      → 0x014C [0x00, total_len:4 LE]
                                   ← SPP_APP_NEW_GIF_CMD2020
  send data packets ×N             → 0x014C [prefix, total_len, idx, suffix, chunk]
                                   ← SPP_APP_NEW_GIF_CMD2020

[else (old mode)]:
  send data packets ×N             → 0x49  [frames…]
                                   ← SPP_SET_MUL_BOX_COLOR
```

**Key APK sources and command IDs:**

| Enum | Value | Java source |
|------|-------|-------------|
| `SPP_DIVOOM_EXTERN_CMD` | `0xBD` (189) | `SppProc$CMD_TYPE.java:159` |
| `SPP_SECOND_APP_SEND_GIF_START` | `0x31` (49) | `SppProc$EXT_CMD_TYPE.java:36` |
| `SPP_APP_NEW_GIF_CMD2020` | `0x014C` (332) | `SppProc$CMD_TYPE.java:161` |
| `SPP_APP_NEW_USER_DEFINE2020` | `0x8C` (140) | `SppProc$CMD_TYPE.java:162` |
| `SPP_SET_USER_GIF` | `0xB1` (177) | `SppProc$CMD_TYPE.java:132` |
| `SPP_SET_MUL_BOX_COLOR` | `0x49` (73) | `SppProc$CMD_TYPE.java:55` |
| `SPP_SET_BOX_MODE` | `0x45` (69) | `SppProc$CMD_TYPE.java:51` |
| `SPP_HOT_PAUSE_FILE_SEND` | `0x9F` (159) | `SppProc$CMD_TYPE.java:110` |

---

## Key Differences

### 1. Channel Routing Signal

| Aspect | Current Code | APK |
|--------|-------------|-----|
| **Command** | `0x45 [0x05]` | `0xBD [0x31]` |
| **Name** | `SPP_SET_BOX_MODE` + user-define mode | `SPP_DIVOOM_EXTERN_CMD` + `SPP_SECOND_APP_SEND_GIF_START` |
| **Mechanism** | Channel switch (set active display mode) | Extended command (signal "next data is for custom channel") |
| **Effect** | Attempts to switch device to channel 0x05 | Tells device to route subsequent data to custom storage |

The APK sends NO `0x45 [0x05]` in the gallery push path at all. The
`SPP_SET_BOX_MODE` (0x45) is used only for the hot mode switch
(`[HOT_MODE=2]`) and for clock/visualizer channels — not for custom art.

`0xBD [0x31]` is the exclusive channel-routing primitive for user content.

### 2. Data Protocol

| Aspect | Current Code | APK (New Mode) | APK (Old Mode) |
|--------|-------------|----------------|----------------|
| **Command** | `0x8B` | `0x014C` | `0xB1` or `0x49` |
| **Name** | `SPP_APP_NEW_SEND_GIF_CMD` | `SPP_APP_NEW_GIF_CMD2020` | `SPP_SET_USER_GIF` / `SPP_SET_MUL_BOX_COLOR` |
| **Chunking** | 256-byte chunks, 2-byte idx | 200/256/182-byte chunks, 1-2 byte idx (per device pixel mode) | Full frame in one or few packets |
| **Header** | `[0x00, file_size:4 LE]` | `[0x00, total_len:4 LE]` | (none) |
| **Frame format** | AA format (`0xAA` + RR + NN + palette + pixels) | `e3.h` encoder (PixelBean → NDK pixelEncode) | Same encoder |
| **Terminate** | REMOVED (R35d) | Not sent (APK never sends CW=2) | Not sent |
| **Retransmit** | `_serve_8b_retransmits` | Not implemented (no retransmit in 0x014C) | N/A |

### 3. Encoder

| Aspect | Current Code | APK |
|--------|-------------|-----|
| **Format marker** | `0xAA` | `0xAA` (same — AA format is shared) |
| **RR** | `0x00` | `0x00` (confirmed parity in R35) |
| **NN** | 1 byte | 1 byte (confirmed parity in R35) |
| **Color palette** | 3 bytes per entry | 3 bytes per entry |
| **Pixel packing** | 1-bit per pixel (2 colors), 2-bit (4), 4-bit (16), 8-bit (256) | Same |
| **Implementation** | Pure Python `divoom_image_encode.py` | Java `e3.h`, then `NDKMain.pixelEncode()` (native C) |

The AA frame body is identical between our encoder and the APK's (verified in
R35c). The differences are all in the **wrapping protocol** — how the frames
are packaged, what command byte prefixes them, and what channel-routing
signal is sent first.

### 4. Hot Update Interaction

| Aspect | Current Code | APK |
|--------|-------------|-----|
| **Stop hot update before push?** | No | Yes — `HotUpdateHandle.p().C()` sends `0x9F` |
| **Why it matters** | If a hot file transfer is in progress, custom data may corrupt the hot storage | Ensures clean state for custom channel |

### 5. Send Model

| Aspect | Current Code | APK |
|--------|-------------|-----|
| **Send timing** | Immediate — each chunk sent as encoded | Header sent immediately (`q.s().F()`), data packets stored in `pixelCacheList`, sent by caller |
| **Ack handling** | `_await_8b_device_ready` waits for ACK after START | No explicit ack handling for 0x014C (fire-and-forget via `q.s().F()`) |
| **Flow control** | 50ms min inter-write gap, 10ms inter-chunk delay | 20ms inter-packet delay (same as hot update) |

---

## Why Data Ends Up on the Hot Channel

The `show_image` call path does:

1. `show_design()` → `0x45 [0x05, …]` — This command **should** switch the
   device to the user-define channel. If the device ignores it (or it's
   overridden by a subsequent action), the display remains on the current
   active channel.

2. `stream_animation_8b()` → `0x8B` — `SPP_APP_NEW_SEND_GIF_CMD` is a
   **generic** send-gif command. It pushes pixel data to the *currently
   active* channel on the device, not specifically to the custom channel.

So: if the device was on the HOT channel (from a previous `hot_update` or
user interaction), `0x45 [0x05]` fails to switch it, and `0x8B` pushes the
data to the HOT channel.

The APK avoids this by:
- Using `0xBD [0x31]` as an explicit "route to custom channel" signal
- Using `0x014C` (`SPP_APP_NEW_GIF_CMD2020`) which is specifically the
  "new user-define" GIF command, not the generic one
- Stopping any in-progress hot update first

---

## Command ID Cross-Reference

| Hex | APK Enum | Current Usage |
|-----|----------|---------------|
| `0x45` | `SPP_SET_BOX_MODE` | Channels: clock(0x00), lightning(0x01), cloud(0x02), vj(0x03), visualizer(0x04), **design(0x05)**, scoreboard(0x06), hot(0x02) |
| `0x8B` | `SPP_APP_NEW_SEND_GIF_CMD` | Our animation stream (3-phase with START/DATA/retransmit) |
| `0x49` | `SPP_SET_MUL_BOX_COLOR` | Our fallback path for single-frame images |
| `0xBD` | `SPP_DIVOOM_EXTERN_CMD` | **Not used** — APK's custom channel routing signal |
| `0x014C` | `SPP_APP_NEW_GIF_CMD2020` | **Not used** — APK's new-mode animation protocol (332 > 255, 2-byte command) |
| `0x8C` | `SPP_APP_NEW_USER_DEFINE2020` | **Not used** — APK's new-mode data packets |
| `0xB1` | `SPP_SET_USER_GIF` | **Not used** — APK's old-mode animation protocol |
| `0x9F` | `SPP_HOT_PAUSE_FILE_SEND` | `hot_update.py` sends it to cancel; **not sent before custom push** |

---

## Verification Results & Corrections

The plan below was double-verified against decompiled APK source. **Three critical
corrections** from the first draft:

1. **No `0x014C` in APK.** `SPP_APP_NEW_GIF_CMD2020` = 0x8B (139), used by
   `DesignSendModel` (drawing channel). New-mode custom art uses
   `SPP_APP_NEW_USER_DEFINE2020` = **0x8C** (140). All references to `0x014C`
   / `0x4C` removed.

2. **`0xBD [0x31]` is NOT the custom art routing signal.** It belongs to
   `DesignSendModel` (the transient drawing/GIF-send channel). The custom art
   persistent channel (`LightMakeNewModel`) uses `0xBD [0x17]` for page
   selection — no `0x31` needed in the push flow.

3. **N2 header first byte is `0x00`, not `0x01`.** Old mode:
   `[0x00, 0x00, page]`. New mode: `[0x00, totalLen:4, page]`. The `0x01`
   prefix is set on the internal `hVar` encoder for data chunk headers only.

### Two Channels — Don't Conflate

| Property | DesignSendModel (drawing) | LightMakeNewModel (custom art) |
|----------|--------------------------|-------------------------------|
| **Purpose** | Transient display, one-shot | Persistent storage, 3×12 slots |
| **Start signal** | `y3()` → `0xBD [0x31]` | `p1()` → `0xBD [0x17, page]` |
| **Header** | `CmdManager.n()/o()` | `CmdManager.N2(page, 12-items)` |
| **Data cmd** | `0x8B` (new) or `0x49` (old) | `0x8C` (new) or `0xB1` (old) |
| **End** | No explicit terminator | `CmdManager.K0()` → `[0x02]` |
| **Page select** | N/A | `0xBD [0x17, page]` |
| **APK source** | `DesignSendModel.java` | `LightMakeNewModel.java` |
| **Our current code** | `show_image` → `show_design` → `0x8B` | DONE — `design.py` (page select/clear) + `custom_art_push.py` (push/query) + `divoomd/src/art.rs` (`custom_art_push`/`custom_art_query_page`) + `custom_art.js` gallery UI |

---

## Corrected Implementation Plan

### Architecture Overview

Two independent workstreams:

| Workstream | What it does | Protocol | Target |
|------------|-------------|----------|--------|
| **Custom Art (page push)** | User selects a page (0-2), picks art, pushes to device's user-define flash storage | `p1(page)` + `N2()` + `y()` + `K0()` via `0xB1`/`0x8C` | Custom channel, persists across reboots |
| **Monthly Best → Hot** | Selected gallery items pushed to device's hot rotation | `0x9B`/`0xF7`/`0x9D`/`0x9E` (reuse `hot_update.py`) | Hot channel, firmware-decoded, persists across reboots |

---

### A. Custom Art — Page-Based Push

#### APK Reference Architecture

The device has **3 pages × 12 slots** (36 items total) for user-define art.
The APK (`LightMakeNewModel.java`) stores page data per-device per-page in a
local room database — it does NOT query the device before push. Instead it
maintains local cache and merges new single items with cached 12-slot page data.

```
┌─────────────────────────────────────┐
│  [Page 0]  [Page 1]  [Page 2]      │  ← page tabs → p1(index) → 0xBD [0x17, page]
├─────────────────────────────────────┤
│  ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐   │
│  │S0│ │S1│ │S2│ │S3│ │S4│ │S5│   │  ← 12 slots, always sent as full page
│  └──┘ └──┘ └──┘ └──┘ └──┘ └──┘   │
│  ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐   │
│  │S6│ │S7│ │S8│ │S9│ │S10││S11│   │
│  └──┘ └──┘ └──┘ └──┘ └──┘ └──┘   │
├─────────────────────────────────────┤
│  [Browse...]  [Push to Page]        │
└─────────────────────────────────────┘
```

**Full push flow** (from `LightMakeNewModel`):

```
r(pixelBeanList, true, pageIndex)
  │
  ├─ branch on pixelBean type:
  │    pic/ani/multi → o() merge + N2() header + z(header/body)
  │
  ├─ N2(page, 12-items) → single SPP frame:
  │    old mode: s.c(0xB1, [0x00, 0x00, page])
  │    new mode: s.c(0x8C, [0x00, totalLen_LE32, page])
  │
  └─ [event bus triggers] → v() → y() + K0()

       y():
         for each non-null pixelBean:
           encoded = hVar.g(pixelBean)    // AA encoder
         allEncoded = concatenate
         header = hVar.l([0x01])
         packets = hVar.d(allEncoded, sppCmd)  // sppCmd = 0xB1 or 0x8C
         for each packet:
           if new mode: q.s().H(packet)        // direct write
           else:        q.s().I(packet, true)  // interleave + sleep

       K0():
         if new mode: s.c(0x8C, [0x02])
         else:        s.c(0xB1, [0x02])
         → q.s().I(packet) or q.s().z(packet)
```

**When pushing 1 item** (the `o()` merge at LightMakeNewModel line 148-167):
- Loads existing 12-slot page data from local room DB
- Finds first empty slot (`i(array)`, returns 0..11)
- Puts new item into that slot
- Returns all 12 items → sends full page

#### Corrected: What We Need To Build

**Library layer** — `divoom_lib/tools/custom_art_push.py` (new):

1. **Page management** (0xBD sub-commands, in `design.py`):
   - `use_user_define_index(page)` → `0xBD [0x17, page]` — switch device to page 0/1/2
   - `clear_user_define_index(page)` → `0xBD [0x16, page]` — clear page on device
   - No `send_gif_start()` needed — that's the DesignSendModel path

2. **Page data push** (core logic):
   - `push_page(divoom, page, pixelbeans_12)` — encodes and pushes a full page
   - Sequence: encode AA frames → `N2(page, pixelbeans)` header → send all packets via `hVar.d()` → `K0()` end
   - Handles old (0xB1) vs new (0x8C) mode selection based on device caps

3. **Single-item push** (merge + push):
   - `push_item(divoom, page, slot, pixelbean, cached_page_data)` — merges into 12 then `push_page()`
   - If no cache, fills remaining 11 slots as empty PixelBeans

4. **Page query** (0x8E):
   - `query_page(divoom, page)` → sends `SPP_APP_GET_USER_DEFINE_INFO` → parses device response
   - Response payload format (from `LightMake64Model.x()`):
     ```
     Byte[0]: type (1=data chunk, 2=end of page)
     Byte[1]: page_id (type=1) or next_page (type=2)
     Byte[2..3]: total_count (LE16) — items on page
     Byte[4..5]: cur_seq (LE16) — chunk offset
     Byte[6..7]: item_count (LE16) — IDs in this chunk
     Byte[8..]:  item_count × 4-byte LE32 IDs
     ```
   - Response wraps in `0x8B` (SPP_COMMAND_CHECK) with sub-command `0x8E`

**Daemon layer** (`device_owner.py`):
- New RPC: `custom_art_push(file_ids[], page)`
- Downloads cloud files → encodes via AA encoder → merges with cache → pushes full page
- `custom_art_query_page(page)` → reads device page info via 0x8E

**GUI layer** (`web_ui/`):

1. **Page selector** — 3 pill buttons (Page 1/2/3)
   - Clicking sends `0xBD [0x17, page]` → device switches page display
   - Highlights selected page

2. **Slot grid** — 12 slots as flex grid
   - Each shows thumbnail from local cache or empty placeholder
   - Clicking selects target slot (where new item goes)
   - Support multi-select from gallery

3. **Gallery cache picker** — reuse `#custom-art-cache-grid`
   - Checkbox selection of cached items

4. **Push button** — "Push to Page"
   - Merges selected items into page data → calls daemon RPC `custom_art_push`

**gallery_sync.py:**
- `custom_art_push(file_ids[], page)` — sends RPC to daemon
- `query_custom_art_slots(page)` — sends 0x8E query RPC

#### Key Wire Formats (Verified from APK CmdManager.java)

Old mode (`SPP_SET_USER_GIF` = 0xB1 = 177):
```
N2() header:  [0x00, 0x00, page_index]                      → s.c(0xB1, ...)
K0() end:     [0x02]                                         → s.c(0xB1, ...)
Data chunks:  hVar.d(encodedData, 0xB1)
              hVar config: l({1}), p(true)  (f30417j=true)
              each chunk: [0x01][chunk_size:2 LE][chunk_data]  → s.c(0xB1, ...)
```

New mode (`SPP_APP_NEW_USER_DEFINE2020` = 0x8C = 140):
```
N2() header:  [0x00, totalLen_LE32, page_index]              → s.c(0x8C, ...)
K0() end:     [0x02]                                         → s.c(0x8C, ...)
Data chunks:  hVar.d(encodedData, 0x8C)
              hVar config: l({1}), p(false), i(true), q(256)
              (f30417j=false, f30416i=true → i9=4, i11=2)
              each chunk: [0x01][total_len:4 LE][idx:2 LE][data] → s.c(0x8C, ...)
```

All data chunks use the **same cmd** as the N2 header and K0 end for the chosen mode.
`s.c()` wraps everything: `[0x01][len:2 LE][cmd:1][payload...][crc16:2 LE][0x02]`.

Where `totalLen` = sum of `hVar.g(pixelBean).length` for all 12 items.

The **AA frame encoder** (`hVar.g(pixelBean)` → `NDKMain.pixelEncode()`) is
identical to our R35-verified Python encoder. Only the wrapping protocol
changes (new command IDs, new header format).

**Effort**: Medium (library: ~250 LOC, daemon: ~60 LOC, GUI: ~300 LOC)

---

### B. Monthly Best → Hot Channel Push

*No corrections needed — this section is verified against APK.*

#### What the APK Does

`HotUpdateHandle.y()`:

1. HTTP `POST Hot/GetHotFiles32` with `{"DeviceType": N, "IsTest": false}`
   where N maps from device pixel size (verified at lines 556-568):
   | Pixel size | DeviceType |
   |------------|------------|
   | 16 (Ditoo) | **1** |
   | 32 (Tivoo Max) | **0** |
   | 64 | **2** |
   | 128 | **3** |
   | 256 | **4** |

2. Response: `VendorList[] = {VendorId, FileList[]: {FileId, Version, Sha1}}`.
   Version offset by `f11004a` (instance counter).

3. For each file: download `https://fin.divoom-gz.com/{FileId}`, verify SHA1.

4. Send via device-driven hot protocol:
   - `0x9B` manifest → device requests via `0xF7`
   - `0x9D` file info (vendor, size, checksum, version)
   - `0x9E` 256-byte chunks with 20ms inter-packet delay
   - Device ACKs each file done (`[1]` or `[2]`)

5. Switch device to HOT_MODE: `0x45 [HOT_MODE=2]`

**For ≤64px devices, raw cloud `.bin` sent as-is** (confirmed by `C1301b.d()`).

#### What We Need To Build

**Approach**: Reuse `hot_update.py` but feed user-selected files.

**Library** (`hot_update.py`):
- Add `push_file_to_hot(divoom, file_bytes, vendor_id, version)` for
  arbitrary-file hot push (no HTTP manifest)

**Daemon** (`device_owner.py`):
- `sync_artwork` with `target="hot"` → raw `.bin` bytes to hot protocol

**GUI**:
- "Update Device" → replaces monthly best current button, pushes to hot channel
- After push: `0x45 [0x02]` to switch device to HOT_MODE

**Open question**: synthetic vendor/version IDs for user files (APK always uses
Divoom server values).

**Effort**: Small (~80 LOC library, ~30 LOC daemon, minimal GUI)

---

### C. Dependencies and Prerequisites

| Item | Needed for | Status |
|------|-----------|--------|
| AA frame encoder (hVar.g parity) | Custom art encode | DONE: R35 verified |
| 0xBD [0x17] p1(page) sub-cmd | Custom art page select | DONE: `display/design.py` |
| 0xBD [0x16] clear sub-cmd | Custom art page clear | DONE: `display/design.py` |
| N2() header + y() data send + K0() end (0xB1/0x8C) | Custom art push | DONE: `custom_art_push.py` + `divoomd/src/art.rs` |
| 0x8E response parser | Custom art page query | DONE: `custom_art_push.py::query_page` + `art.rs::cmd_custom_art_query_page` |
| Page/slot UI + push | Custom art gallery | DONE: `custom_art.js`/`custom_art.css` |
| `hot_update.py` (0x9B/F7/9D/9E) | Monthly best → hot | DONE: R36b HW-verified |
| `push_file_to_hot()` | Hot push of arbitrary files | TODO: Not started |
| Synthetic vendor/version scheme | Hot push for user files | TODO: Needs decision |

---

## Step-by-Step Implementation Sequence

### Phase 1 — Library: command infrastructure + custom art push

**Step 1.1: Add 0xBD sub-commands to `design.py`**

File: `divoom_lib/display/design.py`

Add two new sub-command IDs and their send methods to the existing `Design` class:

```python
# New sub-command IDs (from SppProc$EXT_CMD_TYPE.java)
SUB_USE_USER_DEFINE_INDEX = 0x17   # CmdManager.p1()
SUB_CLEAR_USER_DEFINE_INDEX = 0x16  # CmdManager.g()

async def use_user_define_index(self, page: int) -> bool:
    """Switch device to custom art page 0/1/2 (0xBD [0x17, page]).
    
    APK: CmdManager.p1(page) → q.s().z(s.c(0xBD, [0x17, page]))
    """
    return await self._send_subcmd(SUB_USE_USER_DEFINE_INDEX, [page & 0xFF])

async def clear_user_define_index(self, page: int) -> bool:
    """Clear custom art page on device (0xBD [0x16, page]).
    
    APK: CmdManager.g(page) → q.s().z(s.c(0xBD, [0x16, page]))
    """
    return await self._send_subcmd(SUB_CLEAR_USER_DEFINE_INDEX, [page & 0xFF])
```

Wire format: `s.c(0xBD, [subcmd, arg])` → `[0x01][len=5h][0xBD][subcmd][arg][crc16][0x02]`

**Step 1.2: Create `custom_art_push.py` — the core push module**

New file: `divoom_lib/tools/custom_art_push.py`

```python
"""APK-aligned custom art (user-define) channel push.
    
Protocol matches LightMakeNewModel.java:
  p1(page) → N2(page, 12-items) → y() data → K0()
  
Commands: 0xB1 (old) or 0x8C (new), determined by device caps.
"""
```

Key components:

1. **`push_page(divoom, page: int, pixelbeans_12: list[PixelBean]) -> bool`**
   - Encodes each pixelbean via existing AA encoder
   - Builds N2() header packet and sends it first (via send_command)
   - Builds data packets via hVar.d()-equivalent chunking
   - Sends each data packet
   - Sends K0() end packet
   - Uses existing `framing.py` s.c() equivalent for SPP framing

2. **`_build_n2_packet(page, total_len, use_new_mode) -> bytes`**
   - Old: `s.c(0xB1, [0x00, 0x00, page])`
   - New: `s.c(0x8C, [0x00, total_len:4 LE, page])`

3. **`_build_k0_packet(use_new_mode) -> bytes`**
   - `s.c(0xB1 or 0x8C, [0x02])`

4. **`_chunk_data(encoded_blob, use_new_mode, chunk_size=256) -> list[bytes]`**
   - Old (p=true): `[0x01][chunk_size:2 LE][data_slice]` per chunk → s.c(0xB1, ...)
   - New (p=false, i=true): `[0x01][total_len:4 LE][chunk_idx:2 LE][data_slice]` per chunk → s.c(0x8C, ...)

5. **`_device_supports_new_mode(divoom) -> bool`**
   - Check device capabilities for NewAniSendMode2020 support
   - Or default to old mode (0xB1) for maximum compatibility

6. **`query_page(divoom, page: int) -> list[int]`**
   - Sends `COMMANDS["app get user define info"]` with page byte
   - Parses response: wrapped in 0x8B with sub-command 0x8E
   - Response format (from LightMake64Model.x()):
     ```
     [type:1][page_id:1][total_count:2 LE][cur_seq:2 LE][item_count:2 LE][ids:4×N LE]
     ```
   - Returns list of 4-byte LE IDs of filled slots

**Step 1.3: Ensure command enums are complete**

File: `divoom_lib/models/commands.py`

Already has all needed commands (verified):
```python
"app new user define": 0x8c,        # SPP_APP_NEW_USER_DEFINE2020
"set user gif": 0xb1,               # SPP_SET_USER_GIF
"app get user define info": 0x8e,   # SPP_APP_GET_USER_DEFINE_INFO
"set design": 0xbd,                 # SPP_DIVOOM_EXTERN_CMD
```

No changes needed.

---

### Phase 2 — Daemon: new RPC handlers

**Step 2.1: Add `custom_art_push` handler to `device_owner.py`**

File: `divoom_daemon/device_owner.py`

Add method:
```python
def custom_art_push(self, args: dict) -> dict:
    """Push selected files to a specific page on the custom art channel.
    
    Args:
        file_ids: list of cloud file IDs to push
        page: target page (0, 1, or 2)
        slot: optional target slot (0-11); auto-assign if None
        mac: optional target device MAC
    """
```

Logic:
1. Download each `file_id` from `fin.divoom-gz.com/{file_id}`
2. Decode via `media_decoder` (same as existing sync_artwork)
3. Encode via AA encoder to get PixelBean-like byte arrays
4. Merge with existing page data (from cache or 0x8E query)
5. Call `push_page()` from the library module
6. Return success/failure

**Step 2.2: Add `custom_art_query_page` handler**

```python
def custom_art_query_page(self, args: dict) -> dict:
    """Query device for filled slot IDs on a page.
    
    Args:
        page: page to query (0, 1, or 2)
    """
```
Logic:
1. Call `query_page()` from library
2. Return list of slot IDs

**Step 2.3: Wire new RPCs into the daemon protocol**

File: `divoom_daemon/daemon_protocol.py`

Add entries to the command dispatch table mapping `"custom_art_push"` and
`"custom_art_query_page"` to the DeviceOwner handlers.

---

### Phase 3 — GUI: custom art gallery page/slot UI

**Step 3.1: Update `gallery_sync.py`**

File: `divoom_gui/gallery_sync.py`

Add methods:
```python
def custom_art_push(self, file_ids: list[str], page: int) -> bool:
    """Push files to custom art page on device."""

def query_custom_art_slots(self, page: int) -> list[int]:
    """Query device for filled slots on a page."""
```

Both call the corresponding daemon RPC via the existing command channel.

**Step 3.2: Update `index.html` — custom art panel**

Replace the current custom art panel (or modify it) to include:
- 3 page pill buttons (Page 1/2/3)
- 12-slot grid (flex layout, 4×3 or 6×2)
- Each slot shows thumbnail or empty placeholder
- "Push Selected" button

**Step 3.3: Create/update `templates_tools.js` or new `custom_art.js`**

Add the custom art gallery controller:
- Page switching: calls `divoom.design.use_user_define_index(page)` via RPC
- Slot grid rendering: shows thumbnails per slot
- Gallery file selection: reuse existing cache grid with checkboxes
- Push button: collects selected file IDs, calls `gallery_sync.custom_art_push()`
- Slot query: `query_custom_art_slots(page)` on page load

**Step 3.4: Wire to existing `channels_core.js`**

Ensure the custom art panel triggers page select when shown, and refreshes
slot grid when a page tab is clicked.

---

### Phase 4 — Monthly Best → Hot Channel

**Step 4.1: Add `push_file_to_hot()` to `hot_update.py`**

File: `divoom_lib/tools/hot_update.py`

```python
async def push_file_to_hot(divoom, file_bytes: bytes, vendor_id: int, 
                           version: int, file_size: int = None) -> bool:
    """Push arbitrary file bytes through the device-driven hot protocol.
    
    Skips the HTTP manifest fetch. Sends directly:
      0x9B manifest (1 vendor, 1 file)
      → wait for 0xF7 requests
      → send 0x9D file info
      → stream 0x9E chunks
    """
```

Reuse the existing `HotUpdate._serve_device_requests()` or extract its
request-serving loop to a reusable method that accepts a list of `HotFile`
objects rather than fetching from HTTP.

**Step 4.2: Add daemon RPC for hot push of user files**

File: `divoom_daemon/device_owner.py`

```python
def push_to_hot_channel(self, args: dict) -> dict:
    """Push user-selected files to device hot channel.
    
    Args:
        file_id: single file_id to push
        vendor_id: synthetic or user-configured vendor ID
        version: synthetic version number
    """
```

**Step 4.3: Update monthly best gallery button**

File: `divoom_gui/web_ui/templates_monthly_best.js`

Replace "Update Device" button handler → calls `push_to_hot_channel` instead
of `sync_artwork(target="device")`.

After successful push, send `0x45 [0x02]` (HOT_MODE) to switch device display.

---

### Step Dependencies

```
Phase 1 ──→ Phase 2 ──→ Phase 3
(no deps)    (needs P1)   (needs P2)
                             
Phase 4 is independent of P1-3 (separate code path, reuses existing hot_update.py)
```

Order to implement: Phase 1 first (library foundation), then Phase 2+3 
in parallel (daemon + GUI), then Phase 4 (monthly best wire-up).

### Gaps / Decision Needed Before Starting

| Question | Options | Recommendation |
|----------|---------|---------------|
| Detecting new vs old mode | Check device caps or default old | Default to old mode (0xB1) — works on all devices |
| Synthetic vendor ID for hot push | Fixed value like 999 | 999 works — device just stores the file |
| Page cache strategy | 0x8E query on each push vs local cache | 0x8E query on page load + cache in localStorage |
| 3 pages or start with 1 | Build all 3 now or 1 | Start with 1 page (12 slots), add pages later |
| 32px only vs 64px | Ditoo is 16×16 | Start 32px-only, generalize when 64px hw available |

### D. Open Questions

1. **Hot channel vendor/version**: what synthetic values for user-selected files?
   The APK always uses Divoom server IDs. Pick fixed values (e.g. vendor=999,
   version=1) or let user configure?

2. **Page-level cache strategy**: the APK caches full page data locally (room DB).
   For our web-based GUI, should we cache per-page in local storage, or query
   device via 0x8E every time?

3. **32px only?** Ditoo is 16×16. Support 64px now or defer?

4. **All 3 pages or start with 1?** APK uses 3 for 32px. Build all 3 or start
   with 1 and add later?

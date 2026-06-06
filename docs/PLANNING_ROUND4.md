# Planning Round 4 — 2026-06-05

## 0. Status

| Item | State | Notes |
|---|---|---|
| Round 3 close | ✅ 448 passed / 73 skipped / 0 failed | C encoder parity + perf shipped |
| 3 reference repos cloned | ✅ | `references/divoom-refs/{futpib,hass-divoom,andreas-mausch}` |
| Reference repos mined | ✅ | see §1 below |
| Round 4 plan | 🆕 this document | |

## 1. Reference Repos (cloned at `references/divoom-refs/`)

| Repo | Lang | Purpose | Link |
|---|---|---|---|
| **futpib/divoom-ditoo-pro-controller** | Rust | Modernized fork of andreas-mausch with the 3-phase `0x8B` animation protocol, framed as `Animation::serialize` in `src/protocol/animation.rs`. | https://github.com/futpib/divoom-ditoo-pro-controller |
| **d03n3rfr1tz3/hass-divoom** | Python | Home Assistant integration. SPP/Basic protocol. Authoritative `process_image`/`process_frame`/`process_pixels` for static + multi-frame on real devices (Tivoo/Ditoo/Pixoo). | https://github.com/d03n3rfr1tz3/hass-divoom |
| **andreas-mausch/divoom-ditoo-pro-controller** | Rust | Original CLI for Ditoo Pro. Cleaner Divoom file format reference. | https://github.com/andreas-mausch/divoom-ditoo-pro-controller |

### 1.1 Repo Layout (quick navigation)

```
references/divoom-refs/
├── futpib/
│   ├── Cargo.toml
│   ├── README.md
│   ├── TODO.md
│   └── src/
│       ├── protocol/
│       │   ├── animation.rs       ← 3-phase 0x8B protocol (StartSeeding / SendingData / TerminateSending)
│       │   ├── packet.rs          ← SPP Basic framing [01][u16 len][cmd][args][u16 csum][02]
│       │   ├── command.rs         ← full command enum
│       │   ├── extended_command.rs← 0xbd sub-cmds (0x14 user-define-time get, 0x15 set, 0x26 lang)
│       │   ├── alarm.rs           ← alarm payload
│       │   └── datetime.rs        ← datetime [yr%100, yr/100, mo, day, h, m, s]
│       ├── divoom_file_format/
│       │   ├── frame_header.rs    ← 0xAA magic, header layout
│       │   └── frame.rs           ← palette + LSB-first bit-packed pixel codec
│       └── …
├── hass-divoom/
│   ├── README.md
│   ├── hacs.json
│   └── custom_components/divoom/
│       ├── devices/
│       │   ├── divoom.py          ← full image/text/clock/light/etc, master
│       │   ├── pixoo.py           ← screensize=16, chunksize=200
│       │   ├── pixoomax.py        ← screensize=32, chunksize=200
│       │   ├── aurabox.py         ← 10×10, 8-color fixed
│       │   ├── timeboxmini.py     ← 11×11, RGB444, 182-byte chunks
│       │   ├── ditoo.py           ← keyboard + lyrics + scoreboard
│       │   ├── ditoomic.py        ← EQ (0xbd 0x1E)
│       │   ├── tivoo.py
│       │   └── timoo.py
│       └── notify.py             ← 32 modes, weather mode mapping
└── andreas-mausch/
    ├── Cargo.toml
    ├── README.md
    └── src/
        ├── lib.rs                 ← RFCOMM socket
        ├── protocol/command.rs    ← minimal commands (0x18, 0x43, 0x8b)
        └── divoom_file_format/animation.rs
```

## 2. Findings — Protocol

### 2.1 Transport: SPP/Basic vs iOS-LE/BLE

All three reference repos communicate with the user's 4 Divoom devices
(Timoo, Tivoo Max, Ditoo, Pixoo 16×16) over **Bluetooth Classic SPP /
RFCOMM**, not BLE. The Basic protocol framing is identical between
all three and matches ours:

```
[0x01]                          start
[length LE u16]                 length of (cmd + args + csum)
[cmd u8]
[args ...]
[checksum LE u16]               sum of [len][cmd][args] bytes
[0x02]                          end
```

Our `divoom_lib/framing.py:encode_basic_payload` and
`parse_basic_protocol_frames:210-256` are byte-identical to
`hass-divoom/divoom.py:188-275` and `futpib/protocol/packet.rs:15-46`.

**Implication:** the user's belief that "EvoBox is the only SPP device"
contradicts the reference repos. Our own `connection.py:69-73` already
auto-switches Timoo/Tivoo/Ditoo/Pixoo/Timebox to SPP. **This is the
correct, well-supported path.** Live cover art, image push, and
multi-frame animation are all going over SPP, not BLE.

### 2.2 The 0x8B 3-Phase Animation Protocol (newer, more robust)

`futpib/src/protocol/animation.rs:6-43` defines a 3-phase protocol
under command `0x8B` (source: `https://docin.divoom-gz.com/web/#/5/293`
= "App new send gif cmd 2020"):

```
StartSeeding   (control_word=0): [0x00] [file_size LE u32]                          5 bytes
SendingData    (control_word=1): [0x01] [file_size LE u32] [offset_id LE u16] [≤256 bytes data]
TerminateSending (control_word=2): [0x02]                                          1 byte
```

Wire framing (SPP) wraps each phase in Basic-protocol `[01][len][cmd][args][csum][02]`
with `cmd = 0x8B`. The 0x8B payload is the phase's serialized bytes
above. **Chunks are ≤256 bytes per `SendingData`, not 200.**

This is the protocol that successfully pushes multi-frame GIFs to all
modern Divoom devices (Timoo, Tivoo Max, Ditoo, Pixoo Max, Pixoo 16).
**Our current `encode_animation` uses 0x49 with 200-byte chunks** — this
works for single-frame and the device does ACK, but it does not cycle
the animation on Timoo firmware (Round 3 finding, repeated 5+ times).
Hypothesis: Timoo needs the 0x8B 3-phase protocol to actually play the
animation, not just store it.

### 2.3 The 0x49 Protocol (current, partial)

`encode_animation` builds:
```
packet := [TOTAL_LEN LE u16][PACKET_NUM u8][≤200 bytes frame data]
```
sent N times for one 0x49 command each. The 0x49 command is
documented at `divoom_lib/models/commands.py:36` (per RomRider
`_animAsDivoomMessages`). **Confirmed working for single-frame on
Timoo.** Confirmed ACK'd but not playing for multi-frame on Timoo.

### 2.4 The 0x44 Protocol (single static frame)

`encode_static_image` builds:
```
[0xAA][LLLL LE u16][0x00 0x00 0x00][NN u8][palette 3N][bit-packed pixels]
```
sent once as 0x44. Per `hass-divoom/divoom.py:289` and `divoom.py:673`
this should work for static single-frame. **Our live device test in
Round 3 found 0x44 is a silent no-op on Timoo firmware**, so we route
single-frame through 0x49 instead. This is a Timoo-firmware quirk; the
byte format is correct and works on other Divoom devices (Pixoo, Tivoo
Max, Ditoo, Timebox Evo).

### 2.5 `.divoom16` File Format (single-frame, used by both Rust repos)

```
[0xAA]                                magic byte
[u16 LE] length                       byte count of everything that follows
[u16 LE] time_ms                      per-frame duration (0x0000 for static)
[u8]    reuse_palette                 0x00 = new palette, 0x01 = append to prev
[u8|2]  color_count                   1 byte for 16×16, 2 bytes for 32×32 (hass-divoom:450)
[3*color_count bytes] palette         RGB tuples
[ceil(pixel_count * bits_per_pixel / 8)] pixels, bit-packed LSB-first
```

This is the **same** format as our `encode_animation_frame` output,
except the Rust repos' "static" path uses a 4-byte fixed header
`[0x00, 0x0A, 0x0A, 0x04]` (hass-divoom:289) instead of our
`[0x00, 0x00, 0x00]`. **Live test (Round 3) confirmed our
`[0x00, 0x00, 0x00]` works on Timoo for single-frame via 0x49** — so
the "0x0A, 0x0A, 0x04" variant is for 0x44 path on other devices.

### 2.6 32×32 PixooMax Quirk (the BIG one)

`hass-divoom/divoom.py:300-350, 444-450, 348-350, 430-432` documents:

1. **Two pre-frames** required at the start of any 0x49/0x44 push to
   a 32×32 device (Pixoo Max, Tivoo Max w/ extended LED):
   ```
   [0xAA][LLLL][0x00, 0x00, 0x05, 0x00, 0x00]         (5-byte pre-frame 1)
   [0xAA][LLLL][0x00, 0x00, 0x06, 0x00, 0x00, 0x00]   (6-byte pre-frame 2)
   ```
2. **Palette flag `0x03`** instead of `0x00` for 32×32 frames.
3. **2-byte `color_count`** (LE u16) instead of 1-byte u8.
4. **`make_framepart` index widths** are wider: u32 total_size + u16
   index, not u16 + u8.

**Our `encode_animation` / `encode_animation_frame` do NOT implement
any of this** — they hardcode 1-byte color count and 0x00 palette
flag. **This means cover art on Tivoo Max is silently broken** (single
frame works because the device falls back to 16×16 mode, but the
output is not PixooMax native). Need a `screensize` parameter.

### 2.7 `make_framepart` Chunk Header (current vs. needed)

**Our current (hass-divoom compatible) chunked-frame header:**
```
[TOTAL_LEN LE u16][PACKET_NUM u8][≤200 bytes chunk]
```

**PixooMax 32×32 chunked-frame header (per `hass-divoom:286-287`):**
```
[TOTAL_LEN LE u32][PACKET_NUM LE u16][≤200 bytes chunk]
```

This is **separately swappable** from the 0x44/0x49/0x8B command
choice — it's about how you wrap a frame in a chunked transfer.

## 3. Features Mined from the 3 Reference Repos

### 3.1 Feature Matrix (master table)

| # | Feature | Command | Source repo:file:line | Status in our code | Priority |
|---|---|---|---|---|---|
| 1 | **Multi-frame animation cycling** | `0x8B` 3-phase | `futpib:src/protocol/animation.rs:6-43` | ❌ partial: 0x49 ACK'd but not playing | P0 |
| 2 | **32×32 PixooMax cover art** | `0x44/0x49` w/ 2 pre-frames | `hass-divoom:devices/divoom.py:300-350,444-450,348-350` | ❌ hardcoded 16×16 | P0 |
| 3 | **Per-device `screensize`/`chunksize` config** | n/a (config) | `hass-divoom:devices/pixoo.py:7-13`, `pixoomax.py:7-13`, `timeboxmini.py:7-45`, `aurabox.py:7-22` | ❌ hardcoded 16×16 | P0 |
| 4 | **Static image push (16×16)** | `0x44` | `hass-divoom:devices/divoom.py:669-673,277-281` | ✅ working via 0x49 fallback (Round 3) | P0 |
| 5 | **Single-frame image push (Timoo firmware quirk)** | `0x49` | our finding 2026-06-05 | ✅ working | P0 |
| 6 | **EQ / Equalizer (Ditoo-Mic)** | `0xBD 0x1E [3 bytes]` | `hass-divoom:devices/ditooMic.py:15-27` | ❌ id defined, no helper | P1 |
| 7 | **Scoreboard tool** | `0x72` sub `0x05` | `hass-divoom:devices/divoom.py:755-756` (TODO) | ❌ placeholder only | P1 |
| 8 | **Lyrics view** | `0x45` channel 2 | `hass-divoom:devices/divoom.py:697-698` (TODO) | ❌ not implemented | P1 |
| 9 | **Keyboard control (Ditoo)** | `0x23` | `hass-divoom:devices/ditoo.py:18-32` | ❌ id defined, no helper | P1 |
| 10 | **Memorial tool** | `0x54` | `hass-divoom:devices/divoom.py:700-724` | ❌ id defined, no helper | P1 |
| 11 | **Sleep scene w/ audio** | `0xa2 0xa3 0xa4` | `futpib:src/protocol/command.rs:34-36` | ❌ id defined, no helper | P1 |
| 12 | **Alarm listening / vol** | `0x82 0xa5 0xa6` | `futpib:src/protocol/command.rs:31-33` | ❌ id defined, no helper | P1 |
| 13 | **Auto power off** | `0xAB 0xAC` | `futpib:src/protocol/command.rs:30, 38` | ❌ id defined, no helper | P1 |
| 14 | **Sleep color / light** | `0xAD 0xAE` | `futpib:src/protocol/command.rs:35-36` | ❌ id defined, no helper | P1 |
| 15 | **Low power switch** | `0xB2 0xB3` | `futpib:src/protocol/command.rs:30-32` | ❌ id defined, no helper | P1 |
| 16 | **User GIF / Rhythm** | `0xB1 0xB6 0xB7` | `hass-divoom:devices/divoom.py:65-138` (animation.py) | ❌ constants imported, senders missing | P1 |
| 17 | **Power-on channel** | `0x8A` | our `commands.py:77` | ❌ id defined, no helper | P1 |
| 18 | **Boot GIF** | `0x52` | our `commands.py:44` | ❌ id defined, no helper | P1 |
| 19 | **Sand paint ctrl** | `0x34` sub `0/1` | `divoom.py: drawing.py:331-380` | ✅ helper exists | P1 |
| 20 | **Picture scan ctrl (multi-screen scroll)** | `0x35` sub `0/1` | `divoom.py: drawing.py:382-437` | ✅ helper exists | P1 |
| 21 | **Drawing mul pad ctrl (3-screen grid)** | `0x3A` | `divoom.py: drawing.py:61-90` | ✅ helper exists | P1 |
| 22 | **Drawing big pad ctrl (32+ screens)** | `0x3B` | `divoom.py: drawing.py:92-123` | ✅ helper exists | P1 |
| 23 | **Drawing pad ctrl** | `0x58` | `divoom.py: drawing.py:125-152` | ✅ helper exists | P1 |
| 24 | **Drawing pad exit** | `0x5A` | `divoom.py: drawing.py:154-166` | ✅ helper exists | P1 |
| 25 | **Drawing mul encode single pic** | `0x5B` | `divoom.py: drawing.py:168-191` | ✅ helper exists | P1 |
| 26 | **Drawing mul encode pic (multi-screen store)** | `0x5C` | `divoom.py: drawing.py:193-218` | ✅ helper exists | P1 |
| 27 | **Send net temp / disp** | `0x5D 0x5E 0x73` | `hass-divoom:577-592, 845-860` | ❌ id defined, no helper | P2 |
| 28 | **Set temp** | `0x5F` | `hass-divoom:devices/divoom.py:579-592` | ❌ id defined, no helper | P2 |
| 29 | **Set radio frequency** | `0x61` | our `commands.py:59` | ❌ id defined, no helper | P2 |
| 30 | **Drawing mul encode gif play** | `0x6B` | `divoom.py: drawing.py:220-232` | ✅ helper exists | P2 |
| 31 | **Drawing encode movie play** | `0x6C` | `divoom.py: drawing.py:234-257` | ✅ helper exists | P2 |
| 32 | **Drawing mul encode movie play** | `0x6D` | `divoom.py: drawing.py:259-284` | ✅ helper exists | P2 |
| 33 | **Drawing ctrl movie play** | `0x6E` | `divoom.py: drawing.py:286-304` | ✅ helper exists | P2 |
| 34 | **Drawing mul pad enter (clear)** | `0x6F` | `divoom.py: drawing.py:306-329` | ✅ helper exists | P2 |
| 35 | **Get/set tool info** | `0x71 0x72` | `hass-divoom:564-575, 818-825` | ❌ id defined, no helper | P2 |
| 36 | **Get/set device name** | `0x75 0x76` | our `commands.py:69-70` | ❌ id defined, no helper | P2 |
| 37 | **Get SD music list (count + items)** | `0x07 0x7D` | our `commands.py:71, 106` | ❌ id defined, no helper | P2 |
| 38 | **Get/set alarm time** | `0x42 0x43` | `hass-divoom:485-522, 577-592` | ❌ id defined, no helper | P2 |
| 39 | **Get/set memorial time** | `0x53 0x54` | our `commands.py:45-46` | ❌ id defined, no helper | P2 |
| 40 | **Get device temp** | `0x59` | our `commands.py:51` | ❌ id defined, no helper | P2 |
| 41 | **Set temp unit** | `0x4C` | our `commands.py:43` | ❌ id defined, no helper | P2 |
| 42 | **Set temp type** | `0x2B` | our `commands.py:18` | ❌ id defined, no helper | P2 |
| 43 | **Set time type** | `0x2C` | our `commands.py:19` | ❌ id defined, no helper | P2 |
| 44 | **Set sleeptime (sleep duration)** | `0x40` | `hass-divoom:758-783` | ❌ id defined, no helper | P2 |
| 45 | **Set time manage** | `0x56 0x57` | our `commands.py:48-49` | ❌ id defined, no helper | P2 |
| 46 | **Set hot** | `0x26` | `hass-divoom:558-560` | ❌ id defined, no helper | P2 |
| 47 | **Set playstate (play/pause)** | `0x0A` | `hass-divoom:735-739` | ❌ id defined, no helper | P2 |
| 48 | **Get play status** | `0x0B` | our `commands.py:108` | ❌ id defined, no helper | P2 |
| 49 | **Get/set volume** | `0x08 0x09` | `hass-divoom:836-843` | ❌ id defined, no helper | P2 |
| 50 | **Set SD play music id** | `0x11` | our `commands.py:109` | ❌ id defined, no helper | P2 |
| 51 | **Set SD last/next** | `0x12` | our `commands.py:110` | ❌ id defined, no helper | P2 |
| 52 | **Send SD list over / status** | `0x14 0x15` | our `commands.py:111-112` | ❌ id defined, no helper | P2 |
| 53 | **Get SD play name** | `0x06` | our `commands.py:113` | ❌ id defined, no helper | P2 |
| 54 | **Get/set work mode** | `0x05 0x13` | our `commands.py:105, 114` | ✅ partial (get_work_mode helper exists) | P2 |
| 55 | **Set blue password (BT pairing)** | `0x27` | our `commands.py:13` | ❌ id defined, no helper | P2 |
| 56 | **Set gif speed** | `0x16` | our `animation.py:46-52` | ✅ helper exists | P2 |
| 57 | **Set game / game keypress** | `0xA0 0x17 0x21 0x88` | `hass-divoom:619-647, 627-647` | ❌ id defined, no helper | P2 |
| 58 | **Get/set sound ctrl** | `0xA7 0xA8` | our `commands.py:88-89` | ❌ id defined, no helper | P2 |
| 59 | **Set poweron voice vol** | `0xBB` | our `commands.py:103` | ❌ id defined, no helper | P2 |
| 60 | **Set text content / phone word attr** | `0x86 0x87` | our `commands.py:74-75` | ❌ id defined, no helper | P2 |
| 61 | **Set song dis ctrl** | `0x83` | our `commands.py:73` | ❌ id defined, no helper | P2 |
| 62 | **Set daylight switch** | `0x32` | our `commands.py:20` | ❌ id defined, no helper | P2 |
| 63 | **Get/set low power switch** | `0xB2 0xB3` | our `commands.py:95-96` | ❌ id defined, no helper | P2 |
| 64 | **Get/set SD music info** | `0xB4 0xB5` | our `commands.py:97-98` | ❌ id defined, no helper | P2 |
| 65 | **Modify user gif items** | `0xB6` | our `commands.py:99` | ❌ id defined, no helper | P2 |
| 66 | **Set SD music position** | `0xB8` | our `commands.py:101` | ❌ id defined, no helper | P2 |
| 67 | **Set SD music play mode** | `0xB9` | our `commands.py:102` | ❌ id defined, no helper | P2 |
| 68 | **App need get music list** | `0x47` | our `commands.py:40` | ❌ id defined, no helper | P2 |
| 69 | **App send EQ gif** | `0x1B` | our `animation.py:127-138` | ✅ helper exists | P2 |
| 70 | **App new user define** | `0x8C` | our `commands.py:79` | ❌ id defined, no helper | P2 |
| 71 | **App big 64 user define** | `0x8D` | our `commands.py:80` | ❌ id defined, no helper | P2 |
| 72 | **App get user define info** | `0x8E` | our `commands.py:81` | ❌ id defined, no helper | P2 |
| 73 | **Set design (sub-cmd dispatch)** | `0xBD` | `futpib:src/protocol/extended_command.rs:11-15` | ❌ id defined, no helpers | P2 |
| 74 | **Set alarm gif / memorial gif** | `0x51 0x55` | our `commands.py:42, 47` | ❌ id defined, no helper | P2 |
| 75 | **Set brightness** | `0x74` | `hass-divoom:524-531` | ❌ id defined, no helper (cmd exists, no wrapper) | P2 |
| 76 | **Get/set auto power off** | `0xAB 0xAC` | our `commands.py:90-91` | ❌ id defined, no helper | P2 |
| 77 | **Set date time** | `0x18` | `hass-divoom:577-592, futpib:src/protocol/datetime.rs:13-30` | ❌ id defined, no helper | P2 |
| 78 | **LAN/TCP transport (port 7777)** | n/a (transport) | `hass-divoom:devices/divoom.py:86-88, 100-103, 111-113` | ✅ `divoom_lib/lan_transport.py` exists | n/a |
| 79 | **Divoom file format codec** | n/a (file) | `futpib:src/divoom_file_format/frame.rs`, `frame_header.rs` | ✅ `gui/media_decoder.py` exists | n/a |
| 80 | **AES-CBC cache .bin decode** | n/a (storage) | reverse-engineered from `~/.config/divoom-control/cache_gallery/*.bin` | ✅ `gui/media_decoder.py` (key=`78hrey23y28ogs89`, IV=`1234567890123456`) | n/a |

**Summary:** ~40 features already wired up, ~50 features need helpers (mostly the P2 tier).
Critical path is P0 (multi-frame + 32×32) + P1 (EQ, scoreboard, lyrics, keyboard, memorial, sleep, alarm, user GIF).

### 3.2 Critical (P0)

| # | Feature | Status in our code | Source of truth | Fix |
|---|---|---|---|---|
| 1 | **Multi-frame animation cycling on Timoo** | ❌ ACK'd but not playing | `futpib/animation.rs` | Implement 0x8B 3-phase protocol; auto-detect 32×32 |
| 2 | **32×32 PixooMax cover art** | ❌ Silently falls back to 16×16 | `hass-divoom:300-350` | Add `screensize` + 2 pre-frames + palette flag 0x03 + 2-byte color count |
| 3 | **Cover art push (single image, Tivoo Max)** | ❌ Renders but might use 0x44 not 0x49 | our `display/__init__.py:show_image` | Audit `media_sync._push_frame` log; force 0x49 path |
| 4 | **Per-device `screensize`/`chunksize` config** | ❌ Hardcoded 16×16 | `hass-divoom/devices/pixoo.py`, `pixoomax.py`, `timeboxmini.py` | Add to `DivoomConfig` |

### 3.3 High-value missing features (P1)

| # | Feature | Command | Source of truth | Status |
|---|---|---|---|---|
| 5 | EQ / Equalizer (Ditoo-Mic) | `0xbd 0x1E` | `hass-divoom/ditooMic.py:15-27` | ❌ command id defined, no helper |
| 6 | Scoreboard tool | `0x72` sub `0x05` | `hass-divoom:755-756` (marked TODO) | ❌ placeholder only |
| 7 | Lyrics view | `0x45` channel 2 | `hass-divoom:697-698` (marked TODO) | ❌ not implemented |
| 8 | Keyboard control | `0x23` | `hass-divoom/ditoo.py:18-32` | ❌ id defined, no helper |
| 9 | Memorial tool | `0x54` | `hass-divoom:700-724` | ❌ id defined, no helper |
| 10 | Sleep scene w/ audio | `0xa2 0xa3 0xa4` | `futpib/command.rs:34-36` | ❌ id defined, no helper |
| 11 | Alarm listening / vol | `0x82 0xa5 0xa6` | `futpib/command.rs:31-33` | ❌ id defined, no helper |
| 12 | Auto power off | `0xab 0xac` | `futpib/command.rs:30, 38` | ❌ id defined, no helper |
| 13 | Sleep color / light | `0xad 0xae` | `futpib/command.rs:35-36` | ❌ id defined, no helper |
| 14 | Low power switch | `0xb2 0xb3` | `futpib/command.rs:30-32` | ❌ id defined, no helper |
| 15 | User GIF / Rhythm | `0xb1 0xb6 0xb7` | `divoom.py:65-138` | ❌ constants imported, senders missing |
| 16 | Power-on channel | `0x8a` | our `commands.py:77` | ❌ id defined, no helper |
| 17 | Boot GIF | `0x52` | our `commands.py:44` | ❌ id defined, no helper |

### 3.4 Lower-priority but cheap to add (P2)

All P2 features listed in §3.1 above (rows 18-77). These follow the
same pattern: command id is defined in `divoom_lib/models/commands.py`
but no high-level helper exists. They can be added in a batch by
following the existing patterns in `divoom_lib/display/*.py` and
`divoom_lib/display/animation.py`.

## 4. Findings — Bugs in Our Code

| # | File:line | Bug | Severity | Fix |
|---|---|---|---|---|
| 1 | `divoom_lib/display/display_animation.py` | **Old, unused**, but still imports `number2HexString` which doesn't exist (would throw `AttributeError` at runtime). | low (dead code) | Delete or migrate to use `framing.int2hexlittle` |
| 2 | `divoom_lib/display/display_animation.py:74-79` | **Old, unused** — uses MSB-first bit packing. The device needs LSB-first. | low (dead code) | Same — dead code, see #1 |
| 3 | `divoom_lib/display/display_animation.py:108` | **Old, unused** — static prefix `"000000"` instead of `"000a0a04"`. | low (dead code) | Same — dead code |
| 4 | `divoom_lib/utils/divoom_image_encode.py` | Hardcoded 1-byte `NN`, no `screensize` parameter, no `paletteFlag=0x03` for 32×32. | high | Add `screensize` parameter; branch on 16 vs 32 |
| 5 | `divoom_lib/display/animation.py:_handle_ansgc_sending_data` | `file_size` is unused (only `file_offset_id` + `file_data` are appended). The futpib reference requires `[file_size LE u32]` in the SendingData phase. | medium | Remove unused `file_size` from the SendingData phase, OR include it as a re-confirmation of the total. Confirm with live test. |
| 6 | `divoom_lib/display/animation.py:app_new_send_gif_cmd` | Implemented but never called. | high (dead feature) | Wire it up to `show_image` and live-test |
| 7 | `divoom_lib/connection.py:69-73` | Auto-switches to SPP correctly, but the SPP path's `BTSppTransport` 2-second `asyncio.sleep` (line 147-150) is fragile. | medium | Document the cause (macOS Tahoe 26.5.1 SPP reconnection) |
| 8 | `divoom_lib/framing.py:166` | Checksum range `mv[4:n+7]` is correct for iOS-LE, but the Basic protocol parser at `parse_basic_protocol_frames:226-227` uses `4 + length` which is right. ✓ no bug | n/a | n/a |
| 9 | `divoom_lib/native/image_encoder.py:103-110, 156-157` | `out_size` calculation `7 + 256*3 + (w*h + 7) // 8` may under-allocate for 32×32 (palette can be wider, pixel data is 32×32=1024 pixels = 1024 bytes at 8bpp). | high (silent truncation risk) | Add a `screensize`-aware size; bump worst case to `7 + 65536*3 + 65535` |
| 10 | `gui/media_sync.py:_push_frame` (line 182-209) | Calls `dev.display.show_image` for cover art — which is correct. The "0x31 in log" is just decimal-for-hex confusion: `0x31` is the same as `0x49` decimal-in-hex-in-response-marker. The device IS ACK'ing our 0x49 push. | low (cosmetic confusion) | Document this in the code comment; add a unit test that asserts the 0x49 response parser handles 0x31. |

## 5. Implementation Plan (ordered)

### Phase A — Window drag jerkiness (item 0 from user, top priority)

1. **Add instrumentation** to `app.js:224-259` to log `pendingDx`/`pendingDy` deltas and rAF flush intervals.
2. **Check `gui_api.py:152-` for `drag_window`** — is it `setWindowPosition` or delta-based? If delta-based, switch to absolute position. If position-based, ensure the deltas are not lost.
3. **Candidate fixes:**
   - Remove the rAF throttle entirely and call `drag_window` synchronously on mousemove. The host IPC overhead is the actual bottleneck, not the JS event rate.
   - OR use absolute `e.clientX`/`e.clientY` to compute target position and only call `drag_window` with the *current* absolute delta from a known starting position.
   - OR coalesce `mousemove` events with `requestIdleCallback` (lower priority than rAF) and apply on idle.
4. **Test:** Add a Playwright test that fires a sequence of mousemoves with `requestAnimationFrame` timing and asserts the deltas sum to the expected total.
5. **Verification:** Manual drag on macOS with the build, drag in 3 different speeds, verify no visible "jump back and forth".

### Phase B — Multi-frame animation cycling on Timoo (item 1)

The current 0x49 chunked approach is ACK'd but doesn't cycle on Timoo.
Hypothesis: Timoo expects the 0x8B 3-phase protocol (per
`futpib/animation.rs` and `https://docin.divoom-gz.com/web/#/5/293`).

1. **Add `send_animation_8b` helper to `divoom_lib/display/animation.py`:**
   - Phase 1 (StartSeeding): `[0x8B][0x00][file_size LE u32]` (5 bytes payload)
   - Phase 2 (SendingData): `[0x8B][0x01][file_size LE u32][offset_id LE u16][≤256 bytes data]`
   - Phase 3 (TerminateSending): `[0x8B][0x02]` (1 byte payload)
   - All wrapped in SPP Basic `[01][len][8B][args][csum][02]`.

2. **Add 0x8B codec to `divoom_lib/utils/divoom_image_encode.py`:**
   - `encode_animation_8b(frames: List[Frame]) -> List[bytes]` returns the 3 phases as raw payloads.

3. **Update `divoom_lib/display/__init__.py:show_image`:**
   - If `frames_count == 1`: keep current 0x49 path (works on Timoo).
   - If `frames_count > 1`: try 0x8B first; fall back to 0x49 if device doesn't respond correctly.

4. **Test:** Add a live-device integration test that pushes a 3-frame animation via 0x8B and asserts the device cycles.

### Phase C — 32×32 PixooMax support (item 1 cont'd)

1. **Add `screensize: int` to `DivoomConfig`** (default 16, set to 32 for Pixoo Max, Tivoo Max w/ extended LED).
2. **Update `divoom_lib/utils/divoom_image_encode.py`:**
   - `encode_animation_frame` takes a `screensize` param.
   - For screensize=32: use `paletteFlag=0x03`, 2-byte `color_count` (LE u16).
   - Optionally emit the two pre-frames `[0x05 0x00 0x00]` and `[0x06 0x00 0x00 0x00]` (hass-divoom:348-350).
3. **Update `divoom_lib/display/__init__.py:show_image` to read `screensize` from config** and pass it through.
4. **Update `divoom_lib/native/image_encoder.py:_c_encode_animation_frame`** to take `screensize` and dispatch to a new C function `divoom_encode_animation_frame_32` for the 32×32 case.
5. **Update `divoom_lib/native_src/image_encode.c`:** add `divoom_encode_animation_frame_32` with the wider header.
6. **Test:** Add parity tests for 32×32 against the Python reference.

### Phase D — Cover art push bug (item 3)

Audit the user's log `01 06 00 04 31 55 50 e0 00 02`:
- `01` = start
- `06 00` = len 6
- `04` = response marker
- `31` = original command 0x31 hex = **49 decimal** = our 0x49 (animation frame)
- `55` = ACK
- `50` = ? (status byte — unknown meaning, not an error)
- `e0` = ?
- `00 02` = checksum + end

**The device IS responding to 0x49 successfully.** The "0x31" in the
log is decimal-for-hex confusion — the device echoes 0x49 (decimal
0x31 when mistakenly read as hex). **No actual bug here**, just a
documentation issue.

**Action:** add a unit test that asserts the parser handles 0x31
correctly. Add a doc comment in `media_sync.py:_push_frame` clarifying
this.

### Phase E — Feature Helpers (P1 + P2 batch, from §3.1)

Following the existing pattern in `divoom_lib/display/{light,drawing,animation,text,animation_user}.py`,
add high-level helpers for every command id that doesn't already have one.
Organize by channel (system, alarm, music, etc.) not by command-id-number.

#### Phase E.1 — System (`divoom_lib/system.py`)

1. **`set_brightness(value: int)`** — `0x74 [1 byte 0-100]`
2. **`set_device_name(name: str)`** — `0x75 [utf-8 bytes]`
3. **`get_device_name()`** — `0x76 []`
4. **`get_device_temp()`** — `0x59 []`
5. **`set_date_time(dt: datetime)`** — `0x18 [yr%100, yr/100, mo, day, h, m, s]` (futpib `datetime.rs:13-30`)
6. **`set_time_type(value: int)`** — `0x2C [1 byte]` (12/24 hour)
7. **`set_temp_type(c_or_f: int)`** — `0x2B [0/1]`
8. **`set_temp_unit(c_or_f: int)`** — `0x4C [0/1]`
9. **`set_hot(value: bool)`** — `0x26 [0/1]`
10. **`set_sleeptime(minutes: int, ...)`** — `0x40` (hass-divoom:758-783)
11. **`set_sleep_scene(...)`**, **`get_sleep_scene()`** — `0xA2 0xA3 0xA4` (futpib:34-36)
12. **`set_sleep_color(r, g, b)`** — `0xAD [3 bytes]`
13. **`set_sleep_light(r, g, b, brightness)`** — `0xAE [4 bytes]`
14. **`set_auto_power_off(minutes: int)`** / **`get_auto_power_off()`** — `0xAB 0xAC`
15. **`set_low_power_switch(enabled: bool)`** / **`get_low_power_switch()`** — `0xB2 0xB3`
16. **`set_poweron_channel(channel: int)`** — `0x8A [1 byte]`
17. **`set_poweron_voice_vol(volume: int)`** — `0xBB [1 byte]`
18. **`set_sound_ctrl(enabled: bool)`** / **`get_sound_ctrl()`** — `0xA7 0xA8`
19. **`set_volume(value: int)`** / **`get_volume()`** — `0x08 0x09`
20. **`set_playstate(playing: bool)`** / **`get_play_status()`** — `0x0A 0x0B`

#### Phase E.2 — Tools (`divoom_lib/tools/*.py`)

21. **`set_eq(dynamic, mode, stream)`** — `0xBD 0x1E` (Ditoo-Mic)
22. **`set_scoreboard(blue: int, red: int)`** — `0x72 0x05 [2 bytes]`
23. **`set_countdown(value: bool, h, m)`** — `0x72 0x03 [...]` (hass-divoom:563-575)
24. **`set_timer(value: int)`** — `0x72 0x00 [...]` (hass-divoom:818-825)
25. **`set_noise(enabled: bool)`** — `0x72 0x02 [...]`
26. **`set_memorial(day, h, m, text)`** — `0x54 [...]` (hass-divoom:700-724)
27. **`get_memorial_time()`** — `0x53 []`
28. **`set_alarm_gif(slot, ...)`** — `0x51 [...]`
29. **`set_memorial_gif(...)`** — `0x55 [...]`
30. **`set_boot_gif(...)`** — `0x52 [...]`
31. **`set_user_gif(slot, ...)`** / **`modify_user_gif_items(...)`** — `0xB1 0xB6`
32. **`set_rhythm_gif(...)`** — `0xB7`
33. **`set_send_net_temp(value, weather)`** / **`set_send_net_temp_disp(...)`** / **`get_net_temp_disp()`** — `0x5D 0x5E 0x73`
34. **`set_temp(value, c_or_f)`** — `0x5F`
35. **`set_keyboard(mode: int)`** — `0x23` (Ditoo)
36. **`show_lyrics(...)`** — `0x45 channel 2`

#### Phase E.3 — Music / SD card (`divoom_lib/music.py`)

37. **`get_sd_music_list_total()`** — `0x7D []`
38. **`get_sd_music_list(...)`** — `0x07 [...]`
39. **`get_sd_music_info(...)`** / **`set_sd_music_info(...)`** — `0xB4 0xB5`
40. **`set_sd_play_music_id(id: int)`** — `0x11`
41. **`set_sd_last_next(direction: int)`** — `0x12`
42. **`send_sd_list_over()`** — `0x14`
43. **`send_sd_status(...)`** — `0x15`
44. **`get_sd_play_name()`** — `0x06`
45. **`set_sd_music_position(seconds: int)`** — `0xB8`
46. **`set_sd_music_play_mode(mode: int)`** — `0xB9`
47. **`app_need_get_music_list(...)`** — `0x47`

#### Phase E.4 — Alarms (`divoom_lib/alarms.py`)

48. **`get_alarm_time(slot: int)`** — `0x42 [1 byte]`
49. **`set_alarm(slot, h, m, weekdays, mode, trigger, freq, vol)`** — `0x43 [...]` (hass-divoom:485-522)
50. **`set_alarm_vol_ctrl(slot, vol)`** — `0x82 [...]`
51. **`set_alarm_listen(slot, enabled)`** — `0xA5 [...]`
52. **`set_alarm_vol(vol)`** — `0xA6 [1 byte]`
53. **`set_scene_vol(vol)`** — `0xA4 [1 byte]`
54. **`set_sleep_scene_listen(enabled)`** — `0xA3 [1 byte]`

#### Phase E.5 — Drawing (already mostly done, fill gaps)

55. ✅ Sand paint (0x34), Pic scan (0x35), Mul pad (0x3A), Big pad (0x3B), Pad ctrl (0x58), Pad exit (0x5A), Mul encode single pic (0x5B), Mul encode pic (0x5C), Mul encode gif play (0x6B), Encode movie play (0x6C), Mul encode movie play (0x6D), Ctrl movie play (0x6E), Mul pad enter (0x6F) — all in `divoom_lib/display/drawing.py`.

#### Phase E.6 — Design sub-cmd dispatch (`divoom_lib/display/design.py`)

56. **`set_eq(dynamic=False, mode=0, stream=0)`** — `0xBD 0x1E [3 bytes]`
57. **`set_scoreboard(blue: int, red: int)`** — `0xBD 0x05 [2 bytes]`
58. **`set_language(lang: int)`** — `0xBD 0x26 [1 byte]` (futpib `extended_command.rs:13`)
59. **`set_user_define_time(...)`** — `0xBD 0x14 [...]` (futpib:11)
60. **`get_user_define_time()`** — `0xBD 0x15 []` (futpib:12)
61. **`set_rhythm_gif(...)`** — `0xBD 0xB7` (already partial in `animation.py`)

#### Phase E.7 — Game (`divoom_lib/display/game.py`)

62. **`set_game(value: int)`** — `0xA0 [2 bytes]` (hass-divoom:619-625)
63. **`set_game_keypress(value: int)`** — `0x88 [0/1 byte]` (hass-divoom:627-647)
64. **`set_game_key_down(key: int)`** — `0x17 [1 byte]`
65. **`set_game_key_up(key: int)`** — `0x21 [1 byte]`

#### Phase E.8 — Text (partial, mostly done)

66. ✅ `set_text_content` (0x86), `set_light_phone_word_attr` (0x87) — command ids exist, but helpers are in `divoom_lib/display/text.py` already. Verify completeness.

#### Phase E.9 — Design sub-cmd dispatch (already covered E.6)

**Test strategy:** Each helper gets 1-2 unit tests (encode side, no live device). Encodes match the byte format documented in the reference repos. The single-source-of-truth is `references/divoom-refs/{futpib,hass-divoom,andreas-mausch}`. Add `tests/test_display_helpers.py` as the umbrella.

### Phase F — C perf improvements (item 2)

Findings from Round 3: C/Python ratio is 0.99-1.09 (essentially tied)
on M4 Max. ctypes overhead cancels C speedup for small inputs. Real
gains require either:

1. **Batched encoder API**: `divoom_encode_animation_batch(frames, out_buf)` that encodes N frames in one C call. Eliminates per-frame ctypes overhead.
2. **NEON SIMD for the bit-packing loop** in `divoom_lib/native_src/image_encode.c`. Currently scalar; the 8-bit pixel pack can vectorize for 1, 2, 4, and 8 bpp cases.
3. **Pre-allocated out_buf caching**: avoid allocating a new `ctypes.c_ubyte * out_size` on every call.

**Action:** Implement batched encoder, benchmark with `tests/perf_image_encode.py`. Target: 3-5× speedup for typical 16×16 / 32-frame animations.

### Phase G — Documentation

1. **Update `docs/PLANNED_WORK.md`** status table.
2. **Add `docs/DIVOOM_PROTOCOL_SUMMARY.md`** with the 0x44/0x49/0x8B comparison, sourced from the three reference repos.
3. **Update `CHANGELOG`** with Round 4 closing notes.

## 6. Ordered Next Actions (single-week plan)

### Day 1 — Quick wins + user items
1. (item 0) Window drag jerkiness — instrument, fix, test
2. (item 3) Add doc comment + test for cover art 0x49/0x31 confusion
3. Add `set_brightness` helper (P2 #75) — common GUI use, currently raw command

### Day 2 — Multi-frame + 32×32 (P0)
4. (item 1) Add 0x8B 3-phase encoder in Python
5. (item 1) Add 32×32 screensize support (palette flag 0x03, 2-byte color count, 2 pre-frames)
6. (item 1) Add C encoder variants for 0x8B and 32×32 with parity tests
7. (item 1) Live device test: 3-frame 0x8B on Timoo
8. (item 1) Live device test: 32×32 cover art on Tivoo Max

### Day 3 — P1 system + tools
9. Phase E.1 system helpers (20 helpers from §E.1)
10. Phase E.2 tools helpers (16 helpers from §E.2, including scoreboard, EQ, memorial, sleep)
11. Phase E.6 design sub-cmd dispatch (6 helpers from §E.6)

### Day 4 — P1 music + alarms + game
12. Phase E.3 music/SD card helpers (11 helpers)
13. Phase E.4 alarm helpers (7 helpers)
14. Phase E.7 game helpers (4 helpers)

### Day 5 — C perf + docs
15. (item 2) Batched C encoder + NEON bit-pack, target ≥3× speedup
16. Update `docs/PLANNED_WORK.md` status table
17. Add `docs/DIVOOM_PROTOCOL_SUMMARY.md` (0x44/0x49/0x8B comparison, sourced from refs)
18. Update `CHANGELOG` with Round 4 closing notes

### Day 6+ — Optional P2 cleanup
19. Fill any remaining P2 gaps (rows 18-77 in §3.1)

## 7. Success Criteria

### P0 (must ship)
- [ ] Window drag: no "jump back and forth" at 60 fps on macOS
- [ ] Multi-frame: 3-frame GIF cycles on Timoo via 0x8B
- [ ] 32×32: PixooMax cover art renders at native resolution
- [ ] Cover art: doc clarifies 0x31/0x49 confusion, parser test passes
- [ ] C perf: batched encoder ≥ 3× speedup for 32-frame input
- [ ] All existing tests still pass (no regressions)

### P1 (should ship)
- [ ] `divoom_lib/system.py` with all 20 system helpers
- [ ] `divoom_lib/tools/{scoreboard,eq,memorial,sleep,keyboard}.py` with at least the high-impact ones (scoreboard, EQ, memorial, sleep)
- [ ] `divoom_lib/display/design.py` with 5+ sub-cmd helpers
- [ ] `divoom_lib/music.py` and `divoom_lib/alarms.py` with at least set_alarm / get_alarm_time / set_volume / set_sd_play_music_id
- [ ] `divoom_lib/display/game.py` with set_game + set_game_keypress

### P2 (nice to have, batched if time)
- [ ] All command ids in `commands.py` have at least a stub helper
- [ ] At least 460+ unit tests pass

### Documentation
- [ ] `docs/PLANNING_ROUND4.md` and `docs/PLANNED_WORK.md` updated
- [ ] `docs/DIVOOM_PROTOCOL_SUMMARY.md` created (0x44/0x49/0x8B comparison)
- [ ] `CHANGELOG.md` updated
- [ ] `references/divoom-refs/{futpib,hass-divoom,andreas-mausch}` retained as source of truth

## 8. File-by-File Change Plan

| File | Change | Reason |
|---|---|---|
| `divoom_lib/utils/divoom_image_encode.py` | Add `screensize` param to `encode_animation_frame` / `encode_static_image` / `encode_animation`; add `encode_animation_8b(frames)` | P0 #1, #2 |
| `divoom_lib/display/__init__.py` | Read `screensize` from config, pass to encoder; route multi-frame via 0x8B first | P0 #1, #2, #4 |
| `divoom_lib/display/animation.py` | Add `send_animation_8b(frames)` helper, call it from `show_image` when frames_count > 1 | P0 #1 |
| `divoom_lib/native_src/image_encode.c` | Add `divoom_encode_animation_frame_32` + `divoom_encode_animation_8b` | P0 #1, #2, item 2 |
| `divoom_lib/native/image_encoder.py` | Add Python wrappers for the 2 new C functions; bump `out_size` calc for 32×32 | P0 #1, #2 |
| `divoom_lib/system.py` | NEW. 20 system helpers from §E.1 | P1 #1-20 |
| `divoom_lib/tools/__init__.py` | NEW package | P1 |
| `divoom_lib/tools/scoreboard.py` | NEW. set_scoreboard helper | P1 #6 |
| `divoom_lib/tools/eq.py` | NEW. set_eq helper | P1 #5 |
| `divoom_lib/tools/memorial.py` | NEW. set_memorial helper | P1 #10 |
| `divoom_lib/tools/sleep.py` | NEW. set_sleep_* helpers | P1 #11, #13 |
| `divoom_lib/tools/countdown.py` | NEW. set_countdown helper | P2 |
| `divoom_lib/tools/timer.py` | NEW. set_timer helper | P2 |
| `divoom_lib/tools/noise.py` | NEW. set_noise helper | P2 |
| `divoom_lib/music.py` | NEW. SD card music helpers | P1 #37-47 |
| `divoom_lib/alarms.py` | NEW. Alarm helpers | P1 #48-54 |
| `divoom_lib/display/design.py` | NEW. Sub-cmd dispatch (0xBD 0x14, 0x15, 0x1E, 0x26, etc.) | P1 #56-60 |
| `divoom_lib/display/game.py` | NEW. set_game + set_game_keypress | P1 #62-65 |
| `divoom_lib/models/commands.py` | Verify all command ids are present (they are) | n/a |
| `divoom_lib/framing.py` | Add `screensize`-aware `encode_basic_payload` (u32 total_size + u16 index for 32×32) | P0 #2 |
| `tests/test_native_image_encoder.py` | Add parity tests for 0x8B + 32×32 | P0 |
| `tests/test_display_helpers.py` | NEW. Unit tests for all new helpers (encode-side, no live device) | P1 |
| `tests/perf_image_encode.py` | Add batched encoder benchmark | P2 item 2 |
| `tests/test_e2e_mock_device.py` | Add screensize-aware mock | P0 |
| `tests/test_ble_write_race.py` | (no change) | n/a |
| `docs/PLANNED_WORK.md` | Update status table | n/a |
| `docs/PLANNING_ROUND4.md` | This document | n/a |
| `docs/DIVOOM_PROTOCOL_SUMMARY.md` | NEW. Protocol comparison sourced from refs | n/a |
| `gui/media_sync.py` | Add doc comment about 0x31/0x49 confusion | P0 #3 |
| `gui/web_ui/app.js` | Fix window drag jerkiness (Phase A) | item 0 |
| `gui/gui_api.py` | Update `drag_window` if needed (Phase A) | item 0 |
| `references/divoom-refs/` | Retained as source of truth | n/a |
| `CHANGELOG.md` | Add Round 4 entry | n/a |

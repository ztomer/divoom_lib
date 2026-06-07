# divoom-control

Control Divoom pixel-display devices (Pixoo / Tivoo / Timebox / Ditoo …) from
your Mac — both as a **Python library** and a **desktop Control Center app**.

The project has three parts:

1. **`divoom_lib/`** — a high-level async Python library that speaks the Divoom
   BLE protocol (and LAN where supported): channels, image/animation push, text,
   clock, brightness, alarms, FM radio, notifications, and more.
2. **`gui/`** — a [pywebview](https://pywebview.flowrl.com/) desktop **Control
   Center** (macOS) with a glassmorphic UI: live previews, the channel grid,
   live widgets (album art / stocks / system monitor), a gallery, a multi-panel
   "virtual wall", and a tools/settings area. Plus an optional native menubar app.
3. **Native C accelerators** (`gui/libdivoom_compact.dylib`, built from
   `divoom_lib/native_src/` + `gui/compact.c`) — palette encoder, LANCZOS
   downsampler, and frame escaping. Every accelerated path has a pure-Python
   fallback, and both are held to the same correctness tests (see *Testing*).

> Unofficial project, not affiliated with Divoom. Use at your own risk.

---

## Features

- **Discovery** — scan for Divoom devices over BLE; manage known LAN devices.
- **Channels** — Clock, Cloud, VJ Effects, EQ/visualizer, Ambient light,
  Scoreboard, Text.
- **Image & animation push** — static images and GIFs, encoded to the device's
  palette format and streamed via the 0x8B 3-phase protocol (16px today; 32px
  encoder included).
- **Live widgets** — auto-push **album cover art** on track change (Spotify /
  Apple Music), **stock tickers**, and a **system monitor**.
- **Gallery** — browse + sync the Divoom "monthly best" gallery to the device.
- **Virtual wall** — drive a multi-panel grid as one composite display.
- **Tools** — alarms, sleep aid, timer / countdown / noise meter, FM radio,
  anniversary/memorial countdown.
- **Device settings** — brightness, 12/24h, °C/°F, screen orientation & mirror,
  device name, auto-power-off, time sync, weather push, factory reset.
- **Notification mirroring** — trigger the device's notification display.

---

## Requirements

- **macOS** for the GUI, the menubar app, and macOS media/now-playing sync.
  The `divoom_lib` library itself is cross-platform (anything `bleak` supports).
- **Python 3.10+** (the code uses `X | None` type syntax).
- Python deps in `requirements.txt` (`bleak`, `aiohttp`, `pillow`, `pywebview`, …).
- A C compiler (clang) is optional — only needed to build the native
  accelerators; without it everything falls back to pure Python.

## Install

```bash
pip install -r requirements.txt
# optional: build the native accelerators (Python fallback works without this)
bash scripts/build_libdivoom.sh
```

## Run the Control Center (GUI)

```bash
python3 gui/gui_main.py
```

> On macOS, BLE access is gated by per-app permission (TCC). The first scan
> prompts for Bluetooth permission; grant it to the launching terminal/app.

## Use the library

```python
import asyncio
from divoom_lib.divoom import Divoom
from divoom_lib.utils.discovery import discover_device

async def main():
    device, _ = await discover_device()            # scan over BLE
    divoom = Divoom(mac=device.address)
    await divoom.connect()
    try:
        await divoom.display.show_image("art.gif")     # push a static image / GIF
        await divoom.device.set_brightness(80)
        await divoom.notification.show_notification(6) # WhatsApp icon
    finally:
        await divoom.disconnect()

asyncio.run(main())
```

More runnable scripts are in `examples/`.

---

## Testing

```bash
make test            # builds the native dylib, then runs the unit suite
# or directly:
python3 -m pytest -q
python3 -m pytest -q --run-hardware   # also run BLE integration tests (needs a device)
```

~690 tests. The unit suite needs no hardware (BLE integration tests are skipped
by default). `conftest.py` automatically rebuilds the native dylib if it's
missing or older than its C sources, so the **encoder correctness suite runs
against both the C and the Python implementations** (`test_encoder_both_impls.py`)
— this is the guard that keeps the two implementations from drifting.

---

## Project layout

```
divoom_lib/            Async BLE/LAN library
  divoom.py              Divoom facade (.display, .device, .system, .alarm,
                         .radio, .notification, .design, …)
  framing.py             SPP framing/escaping (C-accelerated + Python fallback)
  connection.py          transport + command send/response
  display/               channels, images, animation (0x8B/0x49), text, drawing
  system/                device settings, time, weather, sound
  scheduling/            alarms, sleep, timeplan
  media/                 music/volume, FM radio
  tools/                 timer, countdown, noise, notification
  utils/                 image encode/decode, downsample, discovery, media source
  native/ + native_src/  ctypes wrappers + C sources for the encoders/downsampler
gui/                   Desktop Control Center (pywebview) + menubar app
  gui_main.py            launcher + Python↔JS bridge
  web_ui/                frontend (app.js, channels.js, widgets.js, …)
  libdivoom_compact.dylib  built native library
scripts/build_libdivoom.sh   builds the dylib
references/             protocol references (decompiled APK, other implementations)
docs/                   SESSION_HANDOFF, planning rounds, validation notes
tests/                  pytest suite
```

## Contributing / working notes

This repo is worked by multiple agents and sessions sharing one git tree. See
**`AGENTS.md`** for the conventions and **`docs/SESSION_HANDOFF.md`** for current
state and open threads. Keep tests green and update the handoff each round.

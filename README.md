# divoom-control

Control Divoom pixel-display devices (Pixoo / Tivoo / Timebox / Ditoo …) as a
**Python library**, a **headless daemon** (local or over the network), and a
**desktop Control Center app**.

The project has three packages plus a native accelerator:

1. **`divoom_lib/`** — high-level async library speaking the Divoom BLE protocol
   (plus Bluetooth-Classic SPP and LAN where supported): channels, image/animation
   push, text, clock, brightness, alarms, FM radio, notifications, and more. Runs
   on **macOS and Linux**. Includes the CLI (`divoom-control`) and an MCP server.
2. **`divoom_daemon/`** — a headless, always-on agent that is the **single owner**
   of the device connection and serves a command/event protocol over a Unix
   socket and (optionally) TCP. On macOS it also does notification monitoring and
   provides a menu-bar app. Runs on **macOS and Linux**.
3. **`divoom_gui/`** — a [pywebview](https://pywebview.flowrl.com/) desktop
   **Control Center** (macOS): live previews, channel grid, live widgets (album
   art / stocks / system monitor), a gallery, a multi-panel "virtual wall", and a
   tools/settings area. It is a **thin client of the daemon** — it owns no BLE
   connection and auto-spawns the daemon if one isn't running.

The **native accelerator** `divoom_lib/libdivoom_compact.{dylib|so}` (palette
encoder, LANCZOS downsampler, frame escaping) is built from
`divoom_lib/native_src/`. Every accelerated path has a pure-Python fallback, and
both are held to the same correctness tests (see *Testing*).

> Unofficial project, not affiliated with Divoom. Use at your own risk.

---

## Features

- **Discovery** — scan for Divoom devices over BLE; manage known LAN devices.
- **Channels** — Clock, Cloud, VJ Effects, EQ/visualizer, Ambient light,
  Scoreboard, Text.
- **Image & animation push** — static images and GIFs, palette-encoded and
  streamed via the 0x8B 3-phase protocol (16px today; 32px encoder included).
- **Live widgets** — auto-push **album cover art** on track change (Spotify /
  Apple Music, macOS), **stock tickers**, and a **system monitor**.
- **Gallery** — browse + sync the Divoom "monthly best" gallery to the device.
- **Virtual wall** — drive a multi-panel grid as one composite display.
- **Tools** — alarms, sleep aid, timer / countdown / noise meter, FM radio,
  anniversary/memorial countdown.
- **Device settings** — brightness, 12/24h, °C/°F, orientation & mirror, name,
  auto-power-off, time sync, weather push, factory reset.
- **Notification mirroring** — trigger the device's notification display (macOS).
- **Headless / networked** — run the daemon on one machine (e.g. a Linux box near
  the device) and control it from another over TCP with a shared token.

---

## Requirements

- **macOS or Linux** for `divoom_lib` + `divoom_daemon` (BLE via `bleak` —
  CoreBluetooth on macOS, BlueZ on Linux). The **GUI + menu-bar + now-playing
  sync are macOS-only** today.
- **Python 3.10+** (uses `X | None` type syntax).
- Python deps in `requirements.txt` (`bleak`, `aiohttp`, `pillow`, `pywebview`, …).
- A C compiler (clang/gcc) is optional — only to build the native accelerator;
  without it everything falls back to pure Python.

## Install

```bash
pip install -r requirements.txt        # or: pip install -e .
# optional: build the native accelerator (Python fallback works without it)
bash scripts/build_libdivoom.sh        # -> .dylib on macOS, .so on Linux
```

## Run the daemon (headless)

```bash
# local only (Unix socket; the GUI auto-spawns this for you)
divoom-control daemon

# headless network server on a LAN, token-authenticated (R19)
divoom-control daemon --host 0.0.0.0 --port 9009 --token "$DIVOOM_DAEMON_TOKEN"
```

Remote clients (including the GUI) target it by setting `DIVOOM_DAEMON_HOST`,
`DIVOOM_DAEMON_PORT`, and `DIVOOM_DAEMON_TOKEN`.

## Run the Control Center (GUI, macOS)

```bash
python3 divoom_gui/gui_main.py
```

> On macOS, BLE access is gated by per-app permission (TCC). The first scan
> prompts for Bluetooth permission; grant it to the launching terminal/app.
> The GUI auto-spawns the daemon, which owns the device connection.

## Use the library

```python
import asyncio
from divoom_lib.divoom import Divoom
from divoom_lib.utils.discovery import discover_device

async def main():
    device, _ = await discover_device()                # scan over BLE
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

> Note: the library lets you own the device directly. If the daemon is running it
> already holds the connection (single-owner) — stop it first, or talk to it via
> the daemon protocol instead. More runnable scripts are in `examples/`.

---

## Testing

```bash
make test                              # builds the native lib, then the unit suite
python3 -m pytest -q                   # ~991 tests, no hardware needed
python3 -m pytest -q --run-hardware    # also BLE integration tests (needs a device)
```

The unit suite needs no hardware. `conftest.py` auto-rebuilds the native lib if
it's missing or older than its C sources, so the **encoder correctness suite runs
against both the C and Python implementations** (`test_encoder_both_impls.py`) —
the guard that keeps the two from drifting.

---

## Project layout

```
divoom_lib/            Async BLE/LAN library (macOS + Linux)
  divoom.py              Divoom facade (.display, .device, .system, .alarm, …)
  framing.py             SPP framing/escaping (native-accelerated + Python)
  connection.py          transport + command send/response
  native_lib.py          resolves libdivoom_compact.{dylib|so|dll}
  display/ system/ scheduling/ media/ tools/ utils/   domain submodules
  native/ + native_src/  ctypes wrappers + C sources for encoders/downsampler
  libdivoom_compact.*    built native library (.dylib / .so)
  cli.py                 the `divoom-control` CLI (incl. `daemon` subcommand)
divoom_daemon/         Headless device owner + Unix/TCP server (+ macOS menubar)
  daemon.py              DivoomDaemon: device ownership, command dispatch, server
  daemon_protocol.py     NDJSON wire protocol + DaemonClient
  macos_notifications.py menubar.py menubar_status.py   (macOS only)
divoom_gui/            Desktop Control Center (pywebview, macOS) — daemon client
  gui_main.py            launcher + Python↔JS bridge
  daemon_bridge.py       ensure_daemon() + DaemonDeviceProxy
  web_ui/                frontend (app.js, channels.js, widgets.js, …)
scripts/build_libdivoom.sh   cross-platform native build
docs/                  ARCHITECTURE, REVIEW, planning rounds, SESSION_HANDOFF
tests/                 pytest suite
```

## Contributing / working notes

This repo is worked by multiple agents and sessions sharing one git tree. See
**`AGENTS.md`** for conventions, **`docs/SESSION_HANDOFF.md`** for current state +
open threads, **`ARCHITECTURE.md`** for the system map, and
**`docs/REVIEW_2026-06.md`** for the latest code/UX/architecture review. Keep
tests green and update the handoff each round.

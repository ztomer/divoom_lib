# Planning: Round 13 — capability detection + examples/CLI + macOS auto-source notifications _(2026-06-06)_

> **Input:** "go" (after R12 §D audit). Three independent deliverables picked:
> §1 capabilities (foundation), §2 examples/+CLI (public API surface),
> §3 macOS auto-source notifications (real feature, closes R10 deferral).
> Order: §1 → §2 → §3 (capabilities are foundation for §2; §3 is the highest-
> risk + highest-reward piece, last).

## §1 — Device capability detection (FOUNDATION)

**Why first:** §2 (CLI) and §3 (notifications) both want to know "what can
this device do?". Without a single source of truth, each callsite has its
own switch.

### Lib
- **New `divoom_lib/models/capabilities.py`** — `Capabilities` dataclass
  with bool/int fields + `DEVICE_CAPABILITIES` table mapping device-type
  name → `Capabilities`. Source = `DeviceTypeEnum` from
  `references/apk/decompiled_src/.../DeviceFunction.java:540-580` +
  decompiled `SppProc$CMD_TYPE.java` (which commands exist) + common
  knowledge about which models have which chips (FM, SD, scoreboard).
- **`Divoom.capabilities` property** — returns the `Capabilities` for the
  connected device. Default = "Pixoo (4)" conservative (16×16, no FM, no
  SD, no scoreboard). Once we have a `device_type` field (R5 left this
  unimplemented; we'll add it via the `get_device_info` set), look up by
  type.
- **Capability flags:**
  - `screensize: int` (16 or 32)
  - `has_fm: bool` (FM radio chip — Tivoo/TivooMax/Ditoo/Timoo/TimeboxEvo yes; Pixoo no)
  - `has_sd: bool` (SD card slot — TivooMax/Ditoo/Timoo yes; Pixoo no)
  - `has_lightning: bool` (channel 0x45 index 0x01 — most modern devices)
  - `has_scoreboard: bool` (channel 0x45 index 0x06 — newer devices with scoreboard widget)
  - `has_anim_8b: bool` (0x8B 3-phase animation — 32px devices + recent 16px firmwares)
  - `has_orientation: bool` (0xBD 0x23 — recent firmwares)
  - `has_screen_mirror: bool` (0xBD 0x24 — recent firmwares)
  - `has_factory_reset: bool` (0xBD 0x25 — recent firmwares)
  - `has_alarm: bool` (0x42/0x43 — most)
  - `has_sleep: bool` (0x40/0x41 — most)
  - `has_weather: bool` (0x5D/0x5E — most)
  - `has_low_power: bool` (0xB2/0xB3 — most)
  - `has_24h_clock: bool` (0x2C — most)
  - `has_temp_unit: bool` (0x2B — most)

### GUI
- **`gui_api.get_capabilities()`** returns the current device's capability
  dict for the JS side. JS uses it to show/hide cards (FM card hidden on
  Pixoo-1; SD-related cards hidden on non-SD devices; Orientation card
  hidden on devices without `has_orientation`).
- No new tests for GUI gating — it falls out of the existing UI presence
  tests + the new `Capabilities` tests.

### Tests
- `tests/test_capabilities.py` — table lookups for all 4 user's devices
  (Pixoo/TivooMax/Ditoo/Timoo); default fallback for unknown types;
  immutable dataclass.

## §2 — `examples/` + `divoom-control` CLI

**Why second:** builds on §1. Restores a real README promise (it claims
`examples/` exists; it doesn't). Adds a scripting path for power users.

### Status

- [x] **`examples/`** shipped — 6 working scripts (weather deferred, see below).
- [x] **`divoom_lib/cli.py`** shipped — 10 subcommands, 22 tests, all green.
- [x] **Shell wrapper** shipped — `./divoom-control` calls `python -m divoom_lib.cli`.

### `examples/`
- `examples/discover_and_connect.py` — scan, pick first device, connect, print model + capabilities.
- `examples/push_static_image.py` — load a local image, push via `divoom_lib`.
- `examples/push_animated_gif.py` — load a GIF, encode, push 3-phase.
- `examples/set_radio.py` — tune to a freq, save preset.
- `examples/set_alarm.py` — set an alarm at a time on weekdays.
- `examples/auto_connect.py` — connect to last-known device, replay last push.

> **Weather example deferred.** `divoom_lib/system/temp_weather.py` defines
> `TempWeatherCommand` (0x5F) but it is **not wired to the Divoom facade**
> — `divoom.weather` is not an attribute. `Capabilities.has_weather` flags
> support, but the public method to call is missing. The 3-line wiring
> (mirror `Music`/`Radio` in `divoom.py:106-107`) is a small follow-up
> flagged for R14.

### CLI (`divoom-control` command)
- `divoom-control scan` — list devices.
- `divoom-control set-volume N` — single-device set (0-15).
- `divoom-control set-brightness N` — single-device set (0-100).
- `divoom-control set-radio FREQ` — single-device set (e.g. `875` for 87.5 MHz).
- `divoom-control set-alarm HH:MM WEEKDAYS` — single-device set.
- `divoom-control push-image PATH` — push a local image to first device.
- `divoom-control push-gif PATH` — push a local GIF.
- `divoom-control capabilities` — print the connected device's capabilities.
- All commands: `--mac AA:BB:CC:DD:EE:FF` to target a specific device;
  default = first discovered.
- Entry point: **shell wrapper** at repo root `./divoom-control` (calls
  `python -m divoom_lib.cli`). Symlink into `$PATH` or call directly. A
  full `pyproject.toml` `[project.scripts]` entry point is deferred to
  R14 — adding it unilaterally would change the packaging layout
  (this repo currently has neither `pyproject.toml` nor `setup.py`),
  and that's a different kind of change from the lib work.

### Tests
- `tests/test_cli.py` — subprocess runs each command with `--help` and
  verifies the help text is sensible; mock the device layer for any
  command that hits a device.

### Status

- [x] **`examples/`** shipped — 6 working scripts (weather deferred, see below).
- [x] **`divoom_lib/cli.py`** shipped — 10 subcommands, 22 tests, all green.
- [x] **Shell wrapper** shipped — `./divoom-control` calls `python -m divoom_lib.cli`.

## §3 — macOS auto-source notifications (FEATURE)

**Why last:** highest risk (TCC permission model), highest reward (real
user-visible feature; closes R10/R12 §D deferral).

### Approach
- **`gui/macos_notifications.py`** — uses `pyobjc-framework-UserNotifications`
  (the modern API, NSUserNotificationCenter) to subscribe to macOS
  notifications. On receipt, calls `divoom_lib.notification.show_notification(app_type)`
  or `show_notification_text(text)`.
- **Background thread** — runs in a daemon thread alongside the GUI.
- **App identity** — TCC requires a bundled .app to grant notification
  permission. The current `gui/gui_main.py` is a `python3` script. Options:
  1. **Stub .app bundle** — provide a `gui/DivoomControl.app/` shell that
     wraps `python3 gui/gui_main.py` so TCC sees a proper bundle ID.
     Documents the "launch via the .app" workflow.
  2. **AppleScript bridge** — `osascript` can subscribe to System Events
     notifications without TCC. Lower setup cost, but AppleScript is
     fragile across macOS versions.
  3. **`pync`** — third-party lib that wraps the older NSUserNotification
     API. Works without bundling, but deprecated since macOS 11.
- **Decision:** start with option 3 (`pync` or `pync-only`) for the
  proof-of-concept; if it works, ship. If TCC blocks it, fall back to
  option 1 (provide a `.app` shell). Document the launch instructions
  in `docs/NOTIFICATIONS_SETUP.md`.
- **Per-app routing table** — the lib's `NOTIFICATION_APPS` has 14
  indexed app types. macOS notifications carry `NSApplicationName`. Map
  common macOS apps to the device's app index (WhatsApp, Slack, Messages,
  Mail, Telegram, Signal, Discord, Twitter, Instagram, FaceTime, Calendar,
  Reminders, Spotify, Photos).

### GUI
- **Settings → Devices card** — adds a "Mirror macOS notifications"
  toggle + an "Open .app bundle" button + per-app enable checkboxes.
  Wired in `gui/web_ui/templates.js` + `gui/web_ui/settings.js` (already
  has the event-delegation pattern from R9).
- `gui_api.start_notification_listener()` / `stop_notification_listener()`.

### Tests
- `tests/test_macos_notifications.py` — module-level import + class
  instantiation; **not** the full macOS permission flow (that's a
  manual end-to-end check). The class should expose
  `_map_app_name(name) -> int` as a testable static.
- Mock the `pyobjc`/`pync` boundary so tests don't need macOS notifications.

### Status

- [x] **`gui/macos_notifications.py`** shipped — `MacNotificationMonitor`
  (1Hz polling), `MacAppRouter` (substring routing, 14 default rules),
  `parse_notification_record`, `find_notification_db_path`. Tradeoffs
  documented in `docs/NOTIFICATIONS_SETUP.md`.
- [x] **`gui_api` integration** shipped — `_notification_sink`,
  `_send_notification_async`, `start_notification_listener`,
  `stop_notification_listener`, `is_notification_listener_running`.
  Uses fire-and-forget `_schedule_async` so the polling thread never
  blocks on BLE.
- [x] **Tests** shipped — `tests/test_macos_notifications.py` (18 tests
  with mocked SQLite + injectable time source) + 5 R13 tests in
  `tests/test_gui_api.py` (mocked `MacNotificationMonitor`).
- [x] **Docs** shipped — `docs/NOTIFICATIONS_SETUP.md` (setup,
  permissions, custom routing JSON, manual test checklist).
- [ ] **GUI Settings card** — "Mirror macOS notifications" toggle +
  per-app checkboxes in Settings → Devices. **DEFERRED to R14** —
  the lib + tests are the high-value part of §3; the GUI toggle is a
  30-line `templates.js` + `settings.js` follow-up that depends on
  visual layout decisions (where in the Devices card, what colour the
  on/off pill uses, etc.). Until then, the listener can be started
  via `api.start_notification_listener()` from a devtools console or
  scheduled via `launchd`.

## Order of execution

1. §1 capabilities — single commit.
2. §2 examples/ + CLI — single commit (or two: examples first, CLI second).
3. §3 notifications — single commit (or two: lib + GUI).
4. Update SESSION_HANDOFF + CHANGELOG; push.

## Kill criterion

If §3 hits a TCC wall that requires app bundling on day 1 (no shortcut),
ship §1 + §2 and defer §3 to R14 with a clear "needs .app bundle" note.

## Open follow-ups (carry to R14+)

- **Task #20** — gates SD player UI and read-backs everywhere. Hardware
  investigation. Not in R13 scope.
- **Timeplan hardware verification** — needs Timebox Evo or similar.
- **Cloud round** — separate transport; auth broken.
- **§A visual pass** — user runs the GUI for the eyeball check.

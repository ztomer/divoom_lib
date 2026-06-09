# Changelog

All notable changes to divoom-control are documented here. The
format is loosely Keep-A-Changelog; entries are grouped by
shipped milestone (per the project planning docs).

---

## 2026-06-09 — Review verification + `/zreview` command

- Verified the DeepSeek multi-lens review (`docs/REVIEW_2026-06.md`) against the
  actual code. Added **§0 Verification Pass** tagging each finding
  confirmed/partial/false-positive.
- **False positives caught**: §1.1 `cmd_push_gif`→`show_image` is correct, not a
  bug (`show_image` is the animation path); §1.11 `iscoroutinefunction` is not in
  `mcp_server.py`; the §3 "0% on CLI/MCP/LAN" coverage claims are false
  (38/66/52%) and `framing.py` is 92% not 13%. Real TOTAL coverage **62%**.
- **Corrected priority order** in §0.5; genuinely thin coverage areas are
  `scheduling/`, `display/drawing.py`, `tool.py`.
- Added `.claude/commands/zreview.md` — repeatable four-lens (Bob/Linus/Rams/Kare)
  + coverage review with mandatory per-finding verification; documents that the
  suite runs on `/opt/homebrew/bin/python3.14`.
- Suite re-run on py3.14: **1094 passed, 75 skipped**.

---

## Round 32 — 2026-06-08 (Monthly Best reorg + Routines + device selector + Text fix)

### A — Monthly Best → full-width multi-select gallery

- **§A1**: the devices (sync-targets) panel moved out of Monthly Best into
  Settings → Routines. Monthly Best is now a single full-width gallery card
  (`.monthly-best-layout` is `grid-template-columns: 1fr`).
- **§A2**: removed the ghost "Fetch Gallery" button (fetch already auto-fires on
  style change + tab activation). Gallery style is now remembered **per device**
  in `config.ini` `[gallery]` via new `get_gallery_style`/`set_gallery_style`
  API; the active device's preferred style is restored on startup before the
  cached gallery renders. The style dropdown sits in the old button location.
- **§A3**: each gallery tile carries a selection checkbox (all checked by
  default); added "Select All" / "Clear" controls (virtual-wall styling) and
  dropped the "Gallery" / "Divoom Cloud" header chrome. "Update Device" now
  pushes **every checked** image.

### B — Settings → Routines card

- New layout: device selector | gallery-style selector, a **macOS-style toggle**
  (`.switch`/`.slider-round`, not a checkbox) for auto-sync, interval, the moved
  devices list, "Save Schedule" + "Sync devices now". Auto-sync stays
  daemon-driven (reads `hotchannel_config.json`).

### C — Device selector

- **§C1**: stripped the `BLE:`/`LAN:` transport prefix from the sidebar device
  selector — names are clean (the connectivity dots convey transport).
- **§C2**: the sidebar preview mirrors the **last image this app pushed** to each
  device (devices can't report their framebuffer). `setDevicePreview()` is called
  from the gallery push and the custom-art push; the map persists in
  `localStorage` and `restoreDevicePreview()` runs on connect/switch, falling back
  to the product icon.
- **§C3**: replaced the device dropdown with **per-device dots** overlaid on the
  preview — color-coded via `deviceColor()`, tooltips show names, click switches.
  The `<select>` is kept hidden as canonical state; `renderDeviceDots()` mirrors
  it and highlights the active device.

### D — Channels → Text fix ("nothing appeared")

- The Text card pushed via the 0x87 "set light phone word attr" (LPWA) sequence,
  which the Pixoo-class LED matrices don't render — so nothing showed. The
  known-working references (hass-divoom, futpib) render text into image frames and
  push them via the normal image path. `push_text` (GUI `LightingApi`) now renders
  the text with our no-AA bitmap font onto a device-sized canvas (scaling to fit)
  and pushes via `display.show_image()`. `speed`/`effect_style` are accepted for
  call-compat but unused (static image); scrolling frames are a follow-up.
  **Not hardware-verified** — the render + push-path are unit-tested.

### E — Settings → Connectivity cleanup

- Removed the "Connectivity & Privacy" explainer legend (markup + `.connectivity-legend*`
  styles); the four corner transport dots already convey state.

Suite **1094 passed / 75 skipped / 0 failed**. Browser-preview verified the dots,
gallery multi-select, and Routines card. Full write-up: `docs/PLANNING_ROUND32.md`.

---

## Round 31 — 2026-06-08 (Font improvement + CJK infrastructure + warning fixes)

### Better half-font downsampling

- Changed half-font extraction from OR rule (any of 4) to majority rule (≥2 of 4).
  The OR rule collapsed `B`/`8` and other glyph pairs at ~5px; majority preserves
  glyph distinction while retaining enough stroke fidelity for the small display.
- Regenerated `divoom_fond16_default_half.bin` with the improved algorithm.

### CJK font infrastructure

- Added `APK_RANGES` table (the 18 Unicode ranges from the APK's `CmdManager.C2()` /
  `F2/d.java` including CJK 0x4E00-0x9FA5) to `divoom_lib/fonts/bitmap_font.py`.
- `BitmapFont.__init__` now accepts an optional `range_table` parameter; when
  provided, glyph lookup walks the range table (supports non-contiguous ranges)
  instead of the flat ASCII offset.
- `BitmapFont.from_apk_asset(path)` classmethod loads a raw APK font blob and
  returns a range-table-enabled `BitmapFont` that can map CJK, Hangul, Greek,
  Arabic, etc. glyphs.
- `_find_glyph_offset(cp)` walks the range table — returns `None` for codepoints
  outside all ranges (falls back to `?`).

### Warning fixes

- `CommandQueue.submit()` / `_add()` / `_dequeue()` / `_cancel_worker()`: close
  coroutine objects before raising exceptions so Python 3.14's `RuntimeWarning:
  coroutine was never awaited` is not emitted during garbage collection.
- `test_r13_start_notification_listener_wires_sink`: mock `_schedule_async` with
  a side-effect that closes the captured coroutine instead of discarding it.
- Full suite clean with `-Werror::RuntimeWarning`: 1093 passed, 0 warnings.

### Tests

- 3 new CJK font tests: range-table CJK mapping, unknown codepoint fallback,
  ASCII glyphs still work with full APK font.
- Suite: 1093 passed / 75 skipped (was 1090).

---


### `DaemonDeviceProxy.push_animation()`

- New convenience method on the daemon proxy: `push_animation(file_or_data, *, token)`
  accepts a local file path *or* raw bytes (written to a temp file). Runs
  `display.show_image()` inside an exclusive-mode session so the 0x8B 3-phase
  streaming sequence is never interleaved with other commands.

### MCP `push_animation` tool

- 13th MCP tool: `push_animation(file|data)` — pushes a GIF/animation via 0x8B.
  Accepts a local `file` path OR base64-encoded `data` (for remote clients without
  a shared filesystem). When `divoom` is a `DaemonDeviceProxy`, uses
  `push_animation()` for exclusive-mode protection; otherwise falls back to
  `display.show_image()`.
- Schema uses `oneOf` to require exactly one of `file` or `data`.

### Tests

- 3 MCP tests: file path, base64 data, both/neither validation.
- 2 bridge tests: push_animation with file path, push_animation with raw bytes.
- Suite **1090 / 75 / 0** (+5).

### Files touched

- `divoom_daemon/daemon_client.py` — `DaemonDeviceProxy.push_animation()`.
- `divoom_lib/mcp_tools.py` — `push_animation` tool handler, schema, description.
- `tests/test_mcp_server.py` — 3 new tests, tool count 12→13.
- `tests/test_daemon_bridge.py` — 2 new tests; `_Facade.show_image()` added.
- `docs/PLANNING_ROUND30.md` — new.

---

## Round 29 — 2026-06-08 (Exclusive mode through daemon RPC)

### Wire exclusive mode through device_call

- **`DaemonClient.device_call()`** gets a `token` param — ships in the RPC
  payload. The daemon's `DeviceOwner.device_call()` extracts it and passes
  it through to `_run_device(coro, token=token)`, so the command queue's
  exclusive-mode dispatch gates the call.
- **`DaemonClient.exclusive_start(token)` / `exclusive_end(token)`** — new
  RPC methods that call `CommandQueue.acquire(token)` / `.release(token)`
  on the daemon's event loop. Both handlers submit with `token=token` so
  the queue dispatches them inside the exclusive session.
- **Daemon command registry** registers `exclusive_start` / `exclusive_end`
  → `DeviceOwner.exclusive_start` / `.exclusive_end`.
- **`DaemonDeviceProxy.exclusive(token)`** — async context manager that
  issues `exclusive_start` / `exclusive_end` RPCs and returns a token-tagged
  proxy for nested calls. Usage:
  ```python
  async with proxy.exclusive("anim-1") as p:
      await p.display.show_light(255, 0, 0)
      await p.lan.set_brightness(80)
  ```
- **Tests**: 6 new daemon-bridge tests (exclusive start/end, token
  validation, token-through-device_call, proxy exclusive context,
  RPC plumbing). Suite 1085 / 75 / 0 (+6).

### Files touched

- `divoom_daemon/daemon_protocol.py` — `device_call` accepts `token`;
  `exclusive_start`/`exclusive_end` methods on `DaemonClient`.
- `divoom_daemon/device_owner.py` — `exclusive_start`/`exclusive_end`
  handlers; `device_call` forwards `token` to `_run_device`.
- `divoom_daemon/daemon.py` — `exclusive_start`/`exclusive_end` in
  command registry.
- `divoom_daemon/daemon_client.py` — `DaemonDeviceProxy.exclusive()` ctx
  manager; `__call__`/`__getattr__` propagate `_token`.
- `tests/test_daemon_bridge.py` — 6 new exclusive-mode tests.
- `tests/test_gui_api.py` — updated `device_call` mock expectation for
  new `token` kwarg.
- `docs/PLANNING_ROUND29.md` — new.

---

## Round 28 — 2026-06-08 (MCP daemon-route + scan filter + tab spacing + bitmap font)

### Tab layout fixes (r2 — follow-up to the spacing centralisation)

- **Channels giant glass pane.** `#control-panel .grid-layout` left its rows on
  the grid default `align-content`, which stretched BOTH auto rows — ballooning
  the tab pane into a ~217px empty glass box. Fixed with
  `grid-template-rows: auto 1fr` (pane = content height, card takes the rest).
- **Tools/Settings 21px gap below the tab pane.** `.tab-content` is a flex
  column with `gap: 20px`, so the pane inherited a 20px flex gap (+1px margin).
  Tokenised the panel gap (`--panel-gap: 20px`) and added
  `.tab-content > .tabs-section { margin-bottom: calc(var(--tab-pane-gap) - var(--panel-gap)) }`
  so the flex (Tools/Settings) and grid (Channels) contexts both yield exactly
  `--tab-pane-gap` (1px) below the pane.
- **Tab row shifted left/right between sub-tabs.** `.tabs-row` was centered with
  `margin: 0 auto`; the centre moved as the panel scrollbar appeared/disappeared,
  and it never lined up with the left-aligned cards. Now left-anchored (stable +
  aligned).
- **Settings glass pane wrapped the whole panel.** `templates_settings.js` never
  closed `.tabs-section` after the tab row, so all 5 content panels were nested
  *inside* the tab glass pane (browser auto-closed it at the fragment end). Added
  the missing `</div>` so the panels are siblings.
- Tests: `tests/test_tabs_chrome.py` retargeted + extended (flex gap cancel,
  grid `auto 1fr`, left-aligned row, Settings pane-not-wrapping regression).

### Device text font halved (r3)

- The full-size bitmap glyphs (~9–10px) dominated a 16px matrix. Added a
  **half-size variant** (`divoom_fond16_default_half.bin`, ~5px tall): each glyph
  is the cropped APK glyph 2×-downsampled with an OR rule (a 2×2 block lights if
  ANY source pixel is lit, so 1px strokes survive), re-placed in the same 16-cell
  format so `BitmapFont` reads it unchanged. `scripts/extract_apk_font.py` now
  emits both assets. New `get_small_font()`; `media_source.py` rasterises device
  text with it. +2 tests (asset present, small ≈ half the full height).

### Device text uses a real bitmap font (no anti-aliasing)

- Text rasterised for the device (stock ticker, etc.) was drawn with PIL
  `ImageFont.load_default(size=…)` — an anti-aliased TrueType font that turns to
  grey mush at 16/32/64px. Replaced with a **1-bit bitmap font extracted from the
  official Divoom APK** (`assets/divoom_fond16_default.bin`), so glyphs match
  exactly what the device shows in the Divoom app.
- **Reverse-engineered the APK font format** (from `F2/d.smali`): 32 bytes/glyph
  (16×16 @ 1bpp), glyph for codepoint `cp` at offset `(cp-0x21)*32` for printable
  ASCII, stored rotated 270°. `scripts/extract_apk_font.py` bakes out the
  rotation and writes the printable-ASCII subset (95 glyphs, 3040 bytes) to
  `divoom_lib/fonts/divoom_fond16_default_ascii.bin`.
- **New `divoom_lib/fonts/`** (`BitmapFont`, `get_default_font()`): proportional,
  pixel-exact rendering (`draw_text`/`render`/metrics); `max_width` drops whole
  glyphs on narrow matrices instead of clipping mid-stroke; unsupported
  codepoints fall back to `?`. Verified crisp: rendered pixels are only bg or fg,
  never an AA grey.
- `media_source.py` rewired to the bitmap font; `ImageFont` import + `_tiny_font`
  removed. `pyproject.toml` ships `divoom_lib/fonts/*.bin`.
- Tests: `tests/test_bitmap_font.py` +10 (asset size, upright 'A', proportional
  widths, crispness, max_width, fallback, and a guard that media_source uses no
  anti-aliased font).

### Tab chrome spacing centralised (one source of truth)

- Every tab area (Channels, Tools, Settings) now sits on an identical glass pane
  with `[2px] tab-row [2px]` vertical padding and a `1px` gap to the content
  cards below. Previously Channels (grid) double-spaced (grid `gap:20px` +
  `margin-bottom:16px` ≈ 36px) while Tools/Settings (block) had 16px.
- **New tokens in `style.css :root`** — the *only* place tab spacing is defined:
  `--tab-pane-pad-y: 2px`, `--tab-pane-pad-x: 12px`, `--tab-pane-gap: 1px`.
  `.tabs-section` (tabs.css) consumes them; `margin-bottom` is the universal gap
  mechanism. `#control-panel .grid-layout` gets `gap: 0` so the grid context
  doesn't double-space (verified: actual pane→card gap = 1px in all three).
- Tests: `tests/test_tabs_chrome.py` +3 (tokens defined once, .tabs-section uses
  them, channels grid gap zeroed).

### MCP server no longer owns its own BLE connection

- **`cmd_mcp_server`** (`divoom_lib/cli_commands.py`) rewritten to route through
  the daemon instead of calling `_resolve_device()` (which opened a *second* BLE
  connection to the device the daemon already owns — R17 single-owner — and
  failed with `DeviceConnectionError: ... was not found`, surfaced as a Python
  traceback in the GUI's MCP card). It now builds the tool catalog against a
  `DaemonDeviceProxy` via `ensure_daemon()`. `--mac` is optional; new
  `--socket/--host/--port/--token` flags target a local or remote daemon
  (mirrors the `daemon` command + the R19 network model).
- **Daemon client plumbing moved** `divoom_gui/daemon_bridge.py` →
  `divoom_daemon/daemon_client.py` (so `divoom_lib` can use it with no backwards
  `lib`→`gui` dependency). `daemon_bridge.py` is now a thin re-export shim;
  all existing `from divoom_gui.daemon_bridge import ...` call-sites/tests
  unchanged.
- **`mcp_control.start(mac=None)`** + `gui_api.start_mcp_server` no longer
  require a MAC (the confusing CoreBluetooth UUID shown in the card is no longer
  needed — the daemon already owns the device).
- **`get_capabilities`** (`divoom_lib/mcp_tools.py`) now awaits an awaitable
  `to_dict()` so the read-only tool works through the proxy (was returning an
  unawaited coroutine).

### Scan returns Divoom devices only

- **`discover_all_divoom_devices`** (`divoom_lib/utils/discovery.py`): removed the
  "if nothing matches, return ALL named devices" fallback that dumped every
  random BLE peripheral (headphones, watches, …) into the device list. New
  `is_divoom_name()` helper + `DIVOOM_NAME_KEYWORDS` single source of truth
  (added `divoom`, `aurabox`, `planet`).

### Tests

- `tests/test_discovery.py`: +4 (is_divoom_name match/reject, filter, no-fallback).
- `tests/test_mcp_server.py`: +2 (no-MAC subcommand, daemon-routing — asserts
  `_resolve_device` is never called).
- Suite **1061 passed / 75 skipped / 0 failed** (+6).

---

## Round 26 — 2026-06-08 (Daemon channel-switch API + weather fix)

### Library — `divoom_lib/`

- **New `Display.set_temperature_channel()`** (`divoom_lib/display/__init__.py`):
  APK-canonical 6-byte 0x45 format `[0x01, temp_type, R, G, B, 0x00]`. Switches
  device to TEMPRETURE display mode — the essential first step that was missing
  (weather data alone via 0x5F does nothing without the channel switch).

- **New `Display.set_clock_rich()`** (`divoom_lib/display/__init__.py`):
  APK C2() 10-byte 0x45 format with correct humidity/weather/date overlay
  positions. Kept alongside existing `show_clock()` (hass-divoom layout) for
  backward compat — no overlay reorder.

- **`TEMPRETURE_CHANNEL = 0x01`** constant added (`divoom_lib/models/constants.py`):
  canonical APK alias for the TEMPRETURE display mode channel.

### GUI — `divoom_gui/`

- **`WidgetsApi.push_weather()` fixed** (`divoom_gui/api/widgets.py`): now a
  two-step sequence — (1) switch to TEMPRETURE channel via 0x45 APK-canonical
  bytes, (2) push weather data via 0x5F. Previously sent 0x5F only (no channel
  switch), so weather data would not display.

- **New `WidgetsApi.set_temperature_channel()`** — standalone bridge for channel
  switch without a weather data push.

- **New `LightingApi.set_clock_rich()` / `set_temperature_channel()`** —
  GUI bridge methods exposing the new display primitives.

- **New `DivoomGuiAPI.set_temperature_channel()` / `set_clock_rich()`** —
  pywebview JS-accessible bridge methods.

- **Weather card "Push to Device" button** (`divoom_gui/web_ui/templates_widgets.js`):
  manual push alongside existing auto-push on card selection. Wired via
  `pushWeatherToDevice()` in `widgets.js`.

### Tests

- **+3 tests** (`tests/test_e2e_mock_device.py`):
  `test_temperature_channel_switch_apk_format` — APK 6-byte 0x45 format,
  `test_temperature_channel_fahrenheit_red` — Fahrenheit + red channel,
  `test_clock_rich_apk_format` — APK C2() 10-byte 0x45 format.

- **Contract test updated** (`tests/test_widgets_weather.py`):
  `test_weather_card_has_no_panel_hint` relaxed to allow "Push to Device"
  button (was asserting no buttons at all).

- **Suite: 1025 passed / 75 skipped / 0 failed** (+3 from 1022).

### Docs

- **`docs/LLD_R26.md`** — comprehensive three-layer low-level design covering
  library (`Display.*`), GUI (`WidgetsApi`/`LightingApi`/bridge), and daemon
  (zero new commands — `device_call` dispatch handles routing automatically).

## Round 25 — 2026-06-08 (Channel architecture cross-verification)

### Research — `docs/CHANNEL_ARCHITECTURE.md` written and cross-verified

- **Authoritative channel architecture doc** (`docs/CHANNEL_ARCHITECTURE.md`, 370+ lines)
  covering all 7 light channels, 5 work modes, APK byte formats, device-specific
  variations, overlay toggle positions, weather codes, BLE pacing, and interleaving
  risks. Cross-verified against 3 sources: APK decompile (authoritative), hass-divoom
  (secondary), futpib (tertiary).

- **4 errors found and corrected during cross-verification**:
  1. **futpib channel table was wrong** — incorrectly mapped futpib modes to APK
     channel IDs 0x00-0x06. futpib uses a different numbering scheme (0x01=Light
     with sub_modes 0-6, 0x02=Hot, 0x03=Special, 0x04=Music; no 0x00/0x05/0x06).
  2. **"Both 10-byte CLOCK formats work" was speculative** — changed to documented
     divergence with unknown device compatibility.
  3. **Weather code table incomplete** — added APK's full 18-code OpenWeatherMap
     mapping (had only the 6-code hass-divoom subset).
  4. **hass-divoom transport mischaracterized** — it uses persistent TCP SPP, not
     BLE reconnection per command (only futpib reconnects).

- **TEMPRETURE 6-byte format CONFIRMED** from APK `CmdManager.t2()`:
  `[1, temp_type, R, G, B, 0]` — our committed code used a rotated byte order.
  Firmware-tested order may differ (documented as device-specific divergence).

- **CLOCK dual 10-byte format conflict documented**: APK C2() uses byte 4=humidity,
  5=weather, 6=date. hass-divoom/our lib uses 4=weather, 5=temp, 6=calendar.
  APK format takes precedence for new code.

- **5 divergences from APK catalogued**: CLOCK 10-byte layout, missing TEMPRETURE
  channel switch, weather code subset, constant naming, command naming.

- **APK-first authority established** — explicit priority hierarchy in doc preamble.
- **Emoji-free policy maintained** — cross/checkmark symbols replaced with `[conflict]`/`[same]`.

### Fixed — TEMPRETURE channel switch byte order (committed)

- Corrected byte order: `[1, R, G, B, ?, 0]` (rotated) was a decompile
  misinterpretation. APK's `t2()` field order is `(mode, temp_type, r, g, b)`.
  Working tree reverted to no channel switch pending R26 APK-correct implementation.

- **Removed test** `test_weather_push_switches_channel_before_data` (tested the
  wrong byte order). Re-add in R26 with correct APK payload assertion.

### Planning

- `docs/PLANNING_ROUND26.md` created — R26 focuses on daemon channel-switch API
  with APK-canonical byte formats.

## Round 24 — 2026-06-08 (BLE detection from GUI, no user intervention)

### Fixed — macOS BLE scan returned empty in the GUI

- **TCC responsible-process attribution (the root cause).** pywebview re-hosts
  the GUI process as `Python.app` (`org.python.python`), which is NOT in the
  user's Bluetooth grant list, so a daemon spawned the normal way inherited that
  ungranted identity and `CBCentralManager.authorization()` came back 0/2 →
  every scan was silently empty (or aborted with a TCC privacy violation).
  `spawn_daemon` (`divoom_gui/daemon_bridge.py`) now spawns the daemon with
  **`responsibility_spawnattrs_setdisclaim`** via a libc `posix_spawn` (new
  `_spawn_disclaimed_macos()`; POSIX_SPAWN_SETSID + file_actions redirecting
  stdout/stderr to `/tmp/divoom_daemon.log`). The daemon becomes its OWN
  responsible process, attributed to the granted `python3.14` binary regardless
  of which process launched it. Verified `CBauth == 3` and all 4 devices found
  from the GUI, a terminal, and the agent harness. Falls back to
  `subprocess.Popen` on non-macOS or if the disclaim spawn is unavailable.
- **Client read timeout shorter than the scan.** The daemon only replies after
  scanning for `timeout` seconds, but `DaemonClient.send_command` read with its
  2s default socket timeout, so a successful reply arrived too late and showed up
  as `"timed out"`. `send_command` gained a `read_timeout` override and `scan`
  now waits `timeout + 10s`.
- Daemon `scan()` logs `pid / sys.executable / CBCentralManager.authorization()`
  before scanning so the attribution state is visible in the daemon log.

### Fixed — MCP server subprocess failed with `DaemonDeviceProxy` not a string

- The MAC fallback in `start_mcp_server()` used `self.current_divoom.mac` but
  `DaemonDeviceProxy.__getattr__` returns another proxy for any name NOT in
  `_STATUS_ATTRS` (= `is_connected`, `lan`, `_conn`). `self.current_divoom.mac`
  returned a `DaemonDeviceProxy(path="mac")` instead of a string, which
  `subprocess.Popen` rejected as `TypeError: expected str, not DaemonDeviceProxy`.
- **Fix**: `gui_api.py:426` uses `self.current_divoom._conn.mac` — `_conn`
  resolves via status to `_ConnView(st.get("mac"))` which IS the real MAC string.
- Test: `tests/test_daemon_bridge.py::test_proxy_conn_mac_resolves_from_device_status`

### Fixed — weather push created an unawaited proxy coroutine (RuntimeWarning)

- `Weather.__init__` stored `divoom.logger` on `self`. When the device is a
  `DaemonDeviceProxy`, `divoom.logger` returns a child proxy (not a real logger),
  and `self.logger.info(...)` in `Weather.set()` created a coroutine object that
  was never `await`ed — producing a `RuntimeWarning` and silently leaking the
  coroutine. The `send_command(0x5F, ...)` call after it still worked, but the
  warning filled logs.
- **Fix**: `Weather` now uses a module-level `logger` instead of `divoom.logger`.
- Tests: `test_weather_set_proxy_daemon_roundtrip` (e2e proxy → daemon → wire),
  `test_weather_set_emits_0x5f_frame`, `test_weather_set_negative_temp`.

### Changed — system monitor device preview (bars, no letters, fixed colors)

### Changed — custom art gallery cache: cross-scope `window.*` prefix

### Added — daemon configuration file (`daemon.ini`)

- **`divoom_daemon/daemon_config.py`** — `DaemonConfig` loaded from
  `~/.config/divoom-control/daemon.ini`, alongside the GUI's `config.ini`. A
  commented default file is written on first load so the knobs are discoverable.
  Knobs: `scan_timeout`, `scan_limit` (0 = no cap), `scan_read_slack`,
  `client_timeout`, `reconnect_scan_timeout`.
- **Removed scan magic numbers.** The hardcoded `+10s` client read padding, the
  `DaemonClient` `2.0s` timeout, the `15`/`4` scan defaults (in three places),
  and the `3.0s` reconnect scans now all resolve from this config — one source of
  truth. The GUI's per-scan `timeout` still wins; the config is the fallback
  (Divoom discovery is slow, so the defaults are deliberately large).
- Tests: `tests/test_daemon_config.py` (defaults, file-write, override parse,
  0-limit edge, bad-value + missing-section fallback, slack helper).

### Fixed — switching devices failed with "Daemon connect failed: timed out"

- The `connect`/`disconnect` RPCs used `DaemonClient`'s 2s default read timeout,
  but BLE connection setup is far slower — the client abandoned the connect
  exactly 2.000s in while the daemon was still mid-handshake. Added a
  `connect_timeout` knob (default 20s) to `daemon.ini`, applied to
  `connect_device` + `disconnect_device`. Quick commands keep the short
  `client_timeout`.

### Changed — unified tab rows on a glass strip (all three panels)

- Previously only Channels had a glass panel behind its tabs; Tools + Settings
  had bare tabs on a transparent strip. Now `.tabs-section` is a glass panel
  (matching `.glass-card`) holding the centered tab row in Channels, Tools, and
  Settings, with a consistent gap to the content below. Channels' tab row moved
  out of the content card-header into its own `.tabs-section` strip; Tools went
  full-width. (No menubar "launched successfully" toast either — removed as a
  routine, non-actionable notification.)

---

## Round 23 — 2026-06-07 (REVIEW §1.2 + §1.3 + §1.4 + §1.5)

### §1.2 — gui_api collaborator integration

- **`gui_api.py` refactored from 891 → 444 LOC** — every bridge method
  that existed in an `ApiBase` collaborator now delegates to one of 5
  collaborators (`ConnectionApi`, `LightingApi`, `ToolsApi`, `WidgetsApi`,
  `WindowApi`). The collaborators share state via `state_getter` lambda
  wrapping `self.__dict__` and share the daemon client via a common getter.
- **`AsyncLoopThread` moved** from inline definition to `divoom_gui.api`
  (shared with all collaborators).
- **Removed dead code** from `gui_api.py`: `_device_status()`, `_target()`,
  `_dispatch()`, `_tool_call()`, `_as_bool()` — all now live in collaborators.
- **`send_notification` added to `ToolsApi`** with app_type range guard.
- **`set_brightness`, `set_volume`, `display_wall_image`, `display_custom_art`
  added to `LightingApi`** (follow the `_dispatch` pattern for wall/single
  routing).
- **File-size guardrail updated**: `gui_api.py` removed from ALLOWLIST
  (now 444 LOC ≤ 500).
- **Deduplication**: all `logging` + `try/except` boilerplate removed from
  `gui_api.py` delegation methods; logging + error handling lives in the
  collaborators.
- Suite: 989 passed / 75 skipped (same as R22 — zero regressions).

### §1.3 — daemon.py responsibility extraction (4 waves)

- **Wave 1 — command registry** (5d3f7d1): 14-arm if-ladder in
  `handle_command()` → dict-based `_init_registry()`. Shared handlers
  via alias (`get_status` = `notification_status`). No behavior change.
- **Wave 2 — SocketServer** (7c0cc31): extracted
  `divoom_daemon/socket_server.SocketServer` — Unix + TCP listeners,
  accept loop, subscriber fan-out, token auth. Composed via
  `command_handler` + `status_event_factory` callbacks.
- **Wave 3 — NotificationService** (73b39bd): extracted
  `divoom_daemon/notification_service.NotificationService` — notification
  monitor lifecycle, status derivation, sink + broadcast. Composed via
  `broadcast` + `send_notification` callbacks.
- **Wave 4 — DeviceOwner** (e3612b0): extracted
  `divoom_daemon/device_owner.DeviceOwner` — device lifecycle
  (connect, disconnect, device_call, scan, wall, sync, probe_lan)
  and notification BLE sender. All command handlers registered via
  `_init_registry()`.
- **daemon.py reduced from 730 → 132 LOC** — removed from file-size
  ALLOWLIST (now 10 entries, down from 11).
- Suite: 989 passed / 75 skipped (zero regressions, same as R22).

### §1.4 — DeviceSlot dataclass (c29c715)

- **`divoom_lib/models/device_slot.py`** — `@dataclass DeviceSlot(device, x, y, size, width, height)`.
- **Exported** from `divoom_lib/models/__init__.py`.
- **Replaced all ad-hoc 6-tuple construction/destructuring** in `wall.py` and `device_owner.py`.
- Suite: 989 passed / 75 skipped (zero regressions).

### §1.5 — web_ui file splits (>500 LOC → <500 LOC)

- **6 oversized files split into 14 files**, all under 500 LOC:
  - `templates.js` (718) → 4 domain files: `templates_tools.js` (124), `templates_monthly_best.js` (64), `templates_widgets.js` (200), `templates_settings.js` (330).
  - `app.js` (619) → `app_globals.js` (196) + `app_init.js` (425).
  - `channels.js` (578) → `channels_core.js` (149) + `channels_grids.js` (436).
  - `settings.js` (745) → `settings_hardware.js` (344) + `settings_features.js` (404).
  - `widgets.css` (524) → `widgets_base.css` (301) + `widgets_extra.css` (224).
  - `style.css` (510) → `style.css` (279) + `style_extra.css` (236).
- **ALLOWLIST shrunk from 10 → 4 entries** (`media_sync.py`, `downsample.c`, `constants.py`, `cli.py` remain).
- **`index.html`** script loading updated for all JS splits.
- **`style.css`** @import chain updated for CSS splits.
- **8 test files** updated to use concatenated `_cat()` path helper for split files.
- Suite: 980 passed / 75 skipped (zero regressions on relevant tests).

## Round 22 — 2026-06-07 (menubar refactor: top-level package + daemon client)

The menubar agent is moved from `divoom_daemon/` to its own
top-level `divoom_menubar/` package, and rewritten as a pure daemon
client (no BLE, no socket server). This respects R17's single-owner
rule: the daemon owns the device + notification monitor; the menubar
and GUI are thin clients.

- **New `divoom_menubar/` package** with `menubar_client.py` (testable
  logic, no AppKit) and `menubar.py` (Cocoa status item + menu).
  Removed `divoom_daemon/menubar.py` + `menubar_status.py` (they had
  their own BLE + socket server, violating single-owner).
- **Event-driven via daemon subscription.** The menubar calls
  `DaemonClient.subscribe()` and receives `EVENT_STATUS` events
  (`state` + `counters`) pushed by the daemon on every notification
  listener start/stop/error and routed notification. Title updates
  instantly — **zero polling** (matching user feedback for MCP toggle
  and menubar).
- **Menu actions.** "Start/Stop Notifications" → daemon commands.
  "Open Notifications..." launches the GUI with `--tab data-sources
  --card notifications` (deep link to Live Widgets → Notifications).
- **CLI entry point.** `divoom-control menubar` (synchronous handler,
  runs Cocoa event loop).
- **Tests.** `tests/test_menubar.py` (6 tests) — pure logic, CI-friendly.
- Suite: 938 → 944 passed (+6 tests).

---

## Round 23 — 2026-06-07 (500-LOC debt fully retired + GUI cloud-auth crash fix)

- **GUI no longer crash-loops when Divoom cloud auth fails**: the polled
  transport-status panel triggered a failing network guest login each tick and
  let the exception escape into pywebview. Added cache-only
  `divoom_auth.get_cached_credentials()` + a 120s failure cooldown; status (and
  GUI startup) read the cache only. Verified clean launch. Retired the obsolete
  `gui_api._push_menubar_status` (imported a deleted module). Root cause
  (guest login RC=10) is upstream Divoom; cloud features need a configured
  account — local BLE/LAN control is unaffected.
- **Every `divoom_*` source file is now under 500 LOC** and `tests/test_file_size.py`
  enforces it (allow-list empty). The 2026-06 regression was retired across R23:
  gui_api → `divoom_gui/api/*`, daemon → DeviceOwner/NotificationService/
  SocketServer + command registry, `DeviceSlot`, web_ui splits, menubar → daemon
  client (opencode), then `cli.py`→`cli_commands.py`, `constants.py`→
  `constants_scheduling.py`, `media_sync.py`→`audio_visualizer.py`, and
  `downsample.c`→`downsample_kernel.{c,h}` (byte-identical output verified).
- Suite 994 / 0 / 75.

## Round 21 — 2026-06-07 (review + documentation overhaul)

- **`docs/REVIEW_2026-06.md`**: code/architecture review (Linus + Uncle Bob),
  UI/UX review (Rams + Kare), and a "rewrite the lib + daemon in Rust?" analysis
  (verdict: don't rewrite the library; the daemon is the only defensible Rust
  candidate, and only with an embedded/footprint driver).
- **500-LOC rule enforced**: `tests/test_file_size.py` fails on any unlisted
  source file over 500 LOC, with a shrink-only allow-list of the 11 current
  offenders (so the rule can't silently re-drift).
- **Docs rewritten to current reality**: `README.md` + `ARCHITECTURE.md`
  (3-package + daemon-owns-device + Unix/TCP network + macOS/Linux); new
  `docs/README.md` index separating canonical from historical docs.
- **Removed 10 stale docs** (CODE_REVIEW, APP_IMPROVEMENT_PLAN, PLANNED_WORK,
  next_phase_requirements, DESKTOP_GUI, ENGINEERING_NOTES, brightness_investigation,
  DRAG_FIX_HISTORY, DEVICE_VALIDATION_PLAN, PLANNING_ROUND2_CONTINUATION) —
  recoverable from git history.
- Suite → 993 / 0 / 75. The recommended >500-LOC refactors + a live UI pass +
  an optional Rust daemon spike are staged (see REVIEW §1.7), not yet done.

## Round 20 — 2026-06-07 (Linux compatibility: daemon + libraries)

`divoom_lib` + `divoom_daemon` now run on Linux, not just macOS (BLE via
bleak/BlueZ; the R19 network server is platform-neutral). See
`docs/PLANNING_ROUND20.md`.

- **Per-platform native lib**: `divoom_lib/native_lib.py` resolves
  `libdivoom_compact.{dylib|so|dll}`; all four ctypes loaders (framing,
  media_decoder, native.image_encoder, native.downscaler) go through it.
- **Cross-platform build**: `scripts/build_libdivoom.sh` produces a `.dylib` on
  macOS (clang) and a `.so` on Linux (`cc -shared -fPIC -lm`); ARM→NEON,
  x86_64→SSE2.
- **Portable C**: `compact.c` guarded `<arm_neon.h>` + its NEON tile-row copy
  behind `DIVOOM_HAVE_NEON`; x86_64 uses a byte-identical `memcpy`. Both paths
  verified to compile (arm64 NEON build + an x86_64 cross-compile).
- **Platform-aware tooling**: conftest auto-rebuild + pyproject package-data ship
  `*.dylib`/`*.so`/`*.dll`.
- **Daemon on Linux**: notification monitoring is macOS-only; off macOS
  `_cmd_start` reports a clean `unsupported`/idle state (never builds the Mac
  monitor). `media_source` now-playing returns None off macOS.
- +12 tests; suite → 991 / 0 / 75. **Not yet run on real Linux hardware**
  (cross-compile + platform-guard unit tests). Gaps by design: no Linux
  notification monitor / now-playing / menu-bar.

## Round 19 — 2026-06-07 (daemon as a headless network server: TCP + token + binary blobs)

The daemon can now run as a headless LAN server, not just a local Unix socket.
See `docs/PLANNING_ROUND19.md`.

- **Why JSON**: NDJSON is the control plane (small, debuggable, transport-
  agnostic); device pixels/GIFs are the data plane, deliberately kept out of JSON.
- **TCP listener alongside Unix** (`DivoomDaemon(host, port, token)`): one accept
  thread per listener; `divoom-control daemon --host 0.0.0.0 --port 9009 --token`.
- **LAN + token auth**: TCP requests must carry the shared token
  (`hmac.compare_digest`); Unix connections stay trusted (local fs perms). The
  TCP listener is **fail-closed** — it refuses to start without a token. Token
  falls back to `DIVOOM_DAEMON_TOKEN`.
- **Binary over the wire**: `device_call` gained `blobs={argIdx: base64}`; the
  daemon materializes each to a temp file and substitutes the path. The GUI's
  `DaemonDeviceProxy` auto-ships local-file args as blobs when talking to a remote
  (TCP) daemon, so media/gallery/cover-art push works remotely with no call-site
  changes. `DaemonClient.from_env()`/`ensure_daemon()` target a remote daemon when
  `DIVOOM_DAEMON_HOST` is set.
- +7 tests (`tests/test_daemon_network.py`); suite → 986 / 0 / 75. **Not yet
  hardware-verified; token travels plaintext over TCP — add TLS for untrusted
  networks (follow-up).**

## Round 16-17 — 2026-06-07 (headless daemon + 3-way package split + single-owner cutover mechanism)

The project became three top-level packages — `divoom_lib` (pure protocol +
native dylib), `divoom_daemon` (headless device owner + macOS notification
routing + event socket), `divoom_gui` (pywebview presentation, thin client) —
and gained a headless daemon with a Unix-socket NDJSON protocol. See
`docs/PLANNING_ROUND16.md` + `docs/PLANNING_ROUND17.md`.

- **R16 — daemon core**: `daemon_protocol.py` (NDJSON framing, request/response
  + `subscribe`/stream, `DaemonClient`) + `daemon.py` (server owning the device
  + macOS notification monitor) + a `divoom-control daemon` CLI subcommand.
- **R17 P1-P4,P6 — physical 3-way split**: moved the daemon core, macOS
  notification + menubar modules into `divoom_daemon/`; moved the native dylib +
  `compact.c` into `divoom_lib/` (its true home; fixed all 9 path refs); renamed
  `gui/` → `divoom_gui/` (+ 19 test path-hacks); rewrote `pyproject.toml` to find
  all three packages with per-package data. Browser-verified via the Playwright
  DOM tests. Suite held 959 → 963 / 0.
- **R17 P5 — full single-owner cutover**: BLE is single-owner, so the daemon is
  now the sole device owner and the GUI is a thin client — **no BLE connection is
  held in the GUI anywhere**. **Daemon**: `device_call` (dotted dispatch, target
  device|wall), enriched `connect` (BLE+LAN+auto), `device_status`, `scan`,
  `wall_configure` (idempotent), `probe_lan`, `sync_artwork` (download+decode+
  resize+stream daemon-side, binary off the socket); a dedicated device asyncio
  loop surviving across calls. **GUI**: `ensure_daemon()` auto-spawns a detached
  daemon; `DaemonDeviceProxy` routes `proxy.x.y(...)` through `device_call` and
  answers is_connected/lan/_conn from `device_status`, so `current_divoom`/
  `wall_instance` become proxies and media_sync (live widgets) routes through the
  daemon with no rewrite; scanner_mixin + gallery sync delegate to the daemon.
  **Library**: `DivoomWall` gained switch_channel/push_text/set_brightness/
  set_volume; `media_decoder` moved divoom_gui→divoom_lib. **After P5 the daemon
  must run for the GUI to control the device** (auto-spawned). +14 tests; the 5
  gui_api tests that mocked direct BLE were rewritten to the daemon-client model.
  Suite → 980 / 0 / 75. **Not yet hardware-verified** — runtime drive + the
  menubar→daemon-subscription cleanup are scoped in `PLANNING_ROUND17.md`.
- **R18 — product fixes** (landed alongside): weather auto-fetch + device re-push
  + IP geolocation (no more hard-coded "Berlin"); system-monitor frame grey-box
  removal; smaller stock arrow + tiny stock-name font; Tools/Settings tab icons;
  fit-to-content tab bar + theme selector; **credentials-erase fix**
  (`presets_manager.save_credentials` preserves a blank password instead of
  wiping it + only invalidates the token cache on real change).

## Round 15 — 2026-06-07 (UI unification, monthly best, weather widget, settings refactor, MCP server, menubar)

Six user-driven changes plus a new MCP server feature. The unifying
theme is **making the GUI more honest**: removing buttons that should
be automatic, moving things to where users expect them, and giving
the menubar + an MCP server a real role in the workflow. **+117 tests**,
suite 829 → 946 passed. See `docs/PLANNING_ROUND15.md` for the
full plan + outcome.

- **§1+§7 — Tab style unification** (`2c819325`): single source of
  truth `gui/web_ui/tabs.css` for `.tabs-row` / `.tab-btn` / `.tab-icon`.
  Segmented-pill (Kare: clear silhouettes; Rams: less but better, one
  form for "sub-tab" across the app). Active state = `--primary` bg +
  white text. Channel/Tools/Settings/Theme rows migrated; panel CSS
  files (`channels.css`, `settings.css`) alias legacy class names.
  Optional 16×16 SVG icon prefix. **Lesson**: backticks inside template
  literal comments break JS parsing. Use plain text in inline comments
  inside template strings. `tests/test_tabs_chrome.py` (16 tests).
  Suite 829 → 846.
- **§2 — Monthly Best auto-fetch + box cap** (`0e23253f`): Gallery
  card now auto-fetches on tab activation; changing the classify
  dropdown auto-reloads via `window.loadGallery()`. "Fetch Gallery"
  button hidden. Renamed "Push Selected to Device" → "Update Device"
  and "Sync All → Devices" → "Update Devices". Dropped "Refresh"
  button. Box cap `minmax(110px, 1fr)` → `minmax(110px, 168px)`.
  `tests/test_gallery_auto_fetch.py` (10 tests). Suite 846 → 856.
- **§4 — Settings refactor** (`24f95690`): `.danger-zone` extracted to
  its own `card.glass-card.danger-card` (red border via a single
  `settings.css` rule). Added 7d (`604800`) and 30d (`2592000`) to
  `#routines-auto-sync-interval`; `MAX_INTERVAL = 2592000` clamp in
  `divoom_lib/hotchannel_config._normalize()` is the belt-and-braces
  for bad JSON files. `tests/test_routines_intervals.py` (10 tests).
  Suite 856 → 866.
- **§3 — Live Widgets weather card + Notifications move** (`b7c1e4d7`):
  new `divoom_lib/weather_provider.py` (WTTrIn + Stub + auto-fallback,
  env: `DIVOOM_CONTROL_WEATHER_{PROVIDER,LAT,LON,LOCATION}`, default
  Berlin). `gui/gui_api.get_weather()` sync wrapper, `push_weather()`
  uses live weather + `divoom.weather.set()`. Weather card moved to
  top-level Live Widgets grid with 128×128 preview + 16×16 SVG icon +
  7-segment temp. 10-min poller + auto-push on selection. Notification
  manual + notification mirror cards moved from Settings → Devices to
  Live Widgets. `tests/test_weather_provider.py` (30 tests) +
  `tests/test_widgets_weather.py` (11 tests). Suite 866 → 907.
- **§5 — MCP server + GUI toggle** (`121d0b5`): new
  `divoom_lib/mcp_server.py` (`MCPServer`, `Tool` dataclass, JSON-RPC
  dispatcher per spec 2024-11-05; methods: `initialize`, `tools/list`,
  `tools/call`, `ping`; std codes: `-32700` parse, `-32600` invalid
  request, `-32601` method not found, `-32602` invalid params,
  `-32603` internal error; notifications get no reply). 12 tools in
  `divoom_lib/mcp_tools.py`: `set_volume`, `set_brightness`,
  `set_light_mode`, `set_weather`, `set_alarm`, `set_radio`,
  `set_low_power`, `set_screen_orientation`, `show_image`, `play_sound`
  (best-effort), `get_capabilities`, `get_device_state`. CLI
  `divoom-control mcp-server --mac <MAC>` runs the stdio loop.
  `gui/mcp_control.py` (`MCPController` subprocess, new process group
  for clean SIGTERM, log to `~/.config/divoom-control/mcp-server.log`).
  Settings → Connectivity card with Start/Stop buttons + status pill
  + log tail. **No background polling** — the status card refreshes
  on initial mount, on tab activation, and after Start/Stop click.
  `docs/MCP_SERVER.md` ships with config snippets for Claude Desktop,
  Cursor, Cline, Continue. `tests/test_mcp_server.py` (25 tests).
  Suite 907 → 932.
- **§6 — Menubar notification status** (event-driven): the menubar
  status item now shows the macOS notification-listener state —
  `Divoom (active|idle|error)` with a green/grey/amber tint — plus an
  "Open Notifications..." menu item that launches the GUI to Live
  Widgets → Notifications. **No polling** (user rejected it twice): the
  GUI *pushes* status to the menubar's Unix socket only on
  start/stop/error via `gui_api._push_menubar_status`. AppKit-free logic
  in new `gui/menubar_status.py`; `menubar.py` handles the
  `notification_status` IPC without a BLE auto-connect; `gui_main`
  gained `--tab`/`--card` (URL params honored by `settings.js`).
  `tests/test_menubar_ipc.py` (14 tests incl. a Unix-socket round-trip).
  Suite 932 → 946.

**Test count:** 829 → 946 (+117). **Suite:** 946 passed, 75 skipped,
0 failed. Zero regressions across R8→R15.

---

## Round 14 — 2026-06-07 (R13 follow-ups: weather, routing JSON, GUI card, packaging)

Four deliverables closing out the R13 follow-up list. **+74 tests**,
suite 755 → 829 passed. See `docs/PLANNING_ROUND14.md` for the
full plan + outcome.

- **§1 — `Weather` facade**: new `divoom_lib/system/weather.py` with a
  clean `Weather` class (`set`, `set_temperature`, `set_weather`).
  Wired to the Divoom facade as `divoom.weather`. The old
  `TempWeatherCommand` is now a thin shim — fixes the latent
  `number2HexString()` bug (function lives in
  `divoom_lib/utils/converters.py`, not on the Divoom instance) that
  would have crashed at first `update_temp_weather()` call. CLI
  `set-temperature` subcommand added. `examples/set_weather.py`
  re-added (R13 §2 had deferred it). +27 tests.
- **§2 — Custom routing JSON loader** (`gui/macos_notifications.py`):
  `load_routing_table(path)` / `save_routing_table(rules, path)`;
  honors `DIVOOM_CONTROL_ROUTING` env var, defaults to
  `~/.config/divoom-control/notification_routing.json` (same
  XDG-convention dir as `devices.json`). Corrupt-file tolerant —
  warn + fall back to `DEFAULT_ROUTING`. Validates `app_type` ∈
  `NOTIFICATION_APPS` (1-14); bad entries are dropped with a
  warning, not crashed. Atomic save via `.tmp` + `replace()`. New
  `MacAppRouter.from_file(path)` classmethod. `MacNotificationMonitor`
  loads from the custom file by default. +19 tests.
- **§3 — GUI Settings → Devices card**: new "macOS Notifications"
  card under Settings → Devices with toggle, live status pill
  (running / stopped / error / unsupported), counters (seen /
  routed / dropped), and a routing JSON editor (textarea + Save /
  Reset to defaults). `gui_api` adds `get_notification_listener_status()`
  and `save_notification_routing(json_text)` with hot-reload (the
  running monitor's router is replaced, no listener restart
  required). JSON editor was chosen over per-app checkboxes
  because the rules ARE JSON and a checkbox matrix would be a
  parallel state to keep in sync. +5 gui_api tests.
- **§4 — `pyproject.toml`**: first packaging file in the repo.
  setuptools backend, PEP 621 metadata, version `0.14.0`,
  `requires-python = ">=3.10"`. Core deps from `requirements.txt`.
  `[gui]` extra: `pywebview` + `pyobjc-framework-Cocoa`
  (darwin-gated). `[test]` / `[dev]` extras.
  `[project.scripts]` registers `divoom-control = divoom_lib.cli:main`
  as a real console script. `tool.setuptools.package-data` ships
  the `libdivoom_compact.dylib` + `web_ui/*` with the `gui`
  package. Verified `pip install -e .` + the resulting
  `divoom-control --help` works. The legacy shell wrapper
  `./divoom-control` is kept for in-tree dev without an editable
  install. +12 packaging tests.

**Test count:** 755 → 829 (+74). **Suite:** 829 passed, 75 skipped,
0 failed. Zero regressions across R8→R14.

---

## Round 13 — 2026-06-06 (capability detection + examples/CLI + macOS notifications)

Three deliverables, all on the kill-criterion-aware path. See
`docs/PLANNING_ROUND13.md` for the full plan.

- **§1 — Capability detection** (`167a1019`): hardware-derived identifier
  hierarchy. `Divoom.capabilities` property consults explicit
  `device_type` → MAC `DeviceRegistry` (`~/.config/divoom-control/devices.json`)
  → `manufacturer_data` fingerprint → baseline. **`screensize` renamed to
  `panel_resolution`** (per-panel pixels, not wall composite — the new
  `wall_resolution()` helper in `divoom_lib/wall.py` makes the distinction
  explicit). `ADVERTISED_FINGERPRINTS` table starts empty; populate as the
  user identifies new devices. **CI fix**: `tests/test_live_widgets_diagnostic.py`
  now `pytest.importorskip`s playwright instead of `sys.exit(2)` at import
  time (which was crashing the entire pytest run). +33 tests.
- **§2 — `examples/` + `divoom-control` CLI** (`16cb8b8`): 6 example
  scripts (`discover_and_connect`, `push_static_image`, `push_animated_gif`,
  `set_radio`, `set_alarm`, `auto_connect`) + 10-subcommand CLI with shared
  parent-parser options (`--mac`, `--type`, `--timeout`, `--json`, `-v`).
  Shell wrapper at `./divoom-control` (symlink into `$PATH`). **Weather
  example deferred** — `TempWeatherCommand` (0x5F) isn't wired to the
  Divoom facade. **`pyproject.toml` deferred** — repo has no packaging
  file today; adding one is a separate kind of change. +22 tests.
- **§3 — macOS notification mirroring** (pending commit): polls the
  macOS Notification Center SQLite DB (the same approach used by
  `mac-notification-forwarder`, Hammerspoon, etc. — Apple's public
  notification API only fires for *our own* app's notifications; DB-poll
  bypasses TCC). `MacAppRouter` with 14 default rules. `gui_api` integration
  uses fire-and-forget `_schedule_async` so the polling thread never blocks
  on BLE. **GUI Settings card deferred to R14**. Setup guide in
  `docs/NOTIFICATIONS_SETUP.md`. +23 tests.

**Suite:** 755 passed / 0 failed / 74 skipped (up from R12's 677).
Zero regressions across R8→R13.

## Round 12 §D — 2026-06-06 (deferred features audit)

Full audit in **`docs/PLANNING_ROUND12_D_AUDIT.md`**. Verdict: 0 features
exposed, 0 dropped. All 5 stay in the lib with rationale per feature:

- **Timeplan** (0x56/0x57) — DEFER. Field semantics for `mode`/`trigger_mode`/
  `type` are obfuscated ints in the decompiled APK with no third-party
  documentation. `gui_api.set_timeplan` exists but is a guess; no UI card.
  Lib stays wire-correct.
- **SD card player** (0x06/0x07/0x0B/0x11/etc.) — DEFER. Requires `get_sd_music_list`
  (0x07) response, which is a `get_*` read-back blocked by task #20.
  Plus device-specific (only Tivoo Max / Ditoo / Timoo have SD slots).
- **Game** (0xA0/0x88/0x17/0x21) — DEFER. No useful host UX on a single
  device; the device has its own buttons. Control sets are device-specific.
- **Drawing / sand / picture scan** (0x3A/0x3B/0x58/0x5A-0x5C/0x6B-0x6F/0x34/0x35)
  — DEFER. Non-trivial UI per mode (freehand canvas, sand generator, scroll
  preview). **`pic_scan_ctrl` (0x35) flagged UNVERIFIED** — no entry in
  `SppProc$CMD_TYPE.java` (decompiled APK); single-line comment added in
  `divoom_lib/display/drawing.py`.
- **Cloud HTTP (200+ endpoints)** — DEFER (own round). Out of BLE scope;
  auth broken (`UserNewGuest RC=10`); large surface (clock-face store,
  weather city search, pomodoro, white-noise, TTS, …).

No code changes this round beyond the audit doc + 1 comment.

---

## Round 12 — 2026-06-06 (§A Phase 7 closeout: tools regroup + segmented-pill)

Inner Tools sub-tab renamed to **Sessions** (resolves the Tools/Tools
parent-sub-tab naming collision; "Sessions" is the device-manual term for the
multi-timer/noise/sleep bundle). Tools regroup: Device Settings + Display +
Notification moved to Settings → Devices; Weather moved to Live Widgets;
Anniversary moved to Time (with Alarms). `settings.css` unified segmented-pill
(`.settings-tab-btn` + `.tools-subtab-btn` grouped; `.settings-tabs-nav` +
`.tools-tabs-nav` pill-wrapper alias). 5 regression tests
(`test_r12_tools_subtab_uses_sessions_not_tools_inner_collision`,
`test_r12_unified_segmented_pill_css`,
`test_r12_anniversary_moved_into_time_subtab`,
`test_r12_weather_moved_into_live_widgets`,
`test_r12_device_settings_moved_to_settings_devices`).

Suite: **677 passed / 73 skipped / 0 failed** (up from 672).

Earlier R12: **§C** framing dual-impl correctness test caught + fixed two
Python-fallback crashes (list→memoryview in `encode_basic_payload` escape +
`encode_ios_le_payload`). **§A Phases 2–6** shipped (sticky custom-art push
footer, ambient color gating, scoreboard Reset, appbar corner transports +
right-aligned sliders + brightness-mapped thumb, scoreboard restyle BLUE-over-
RED, Virtual Wall toolbar icons+labels, font sweep). Lessons consolidated in
`docs/ENGINEERING_NOTES.md`; stale state pruned; new cross-agent state in
`docs/SESSION_HANDOFF.md`.

 **§A Phases 2–7 are UI changes — visual pass needed**: run
`python3 gui/gui_main.py` to verify appbar, scoreboard, wall toolbar, font
sweep, segmented-pill, and tools regroup. Then **§D** (deferred features) →
**§E** (push the ~34-commit arc to origin).

---

## Round 10 — 2026-06-06 (APK-only frontier: notification mirroring / ANCS)

The headline APK feature (report §3): `SPP_SET_ANDROID_ANCS`. Shipped as a
**manual trigger** (auto-sourcing macOS notifications deferred). Protocol
re-verified against the decompiled source — see `docs/PLANNING_ROUND10.md`.

### Added

- **lib**: command `"set android ancs": 0x50`; `NOTIFICATION_APPS` (14 apps);
  `divoom_lib/tools/notification.py` (`Notification.show_notification`,
  `show_notification_text`) on facade `d.notification`.
- **GUI**: `gui_api.send_notification(app_type, text="")` (guards 1-14) +
  Tools→Device **Notification** card (app select, optional text, Send).
- 11 tests (6 lib byte-exact incl. ≥8 wire-skip + 128-byte truncation, 2 bridge,
  3 static UI/exposure).

### Notes

- **Report corrections:** command is **0x50** (report said 0x60); there is **no
  RGB payload** — real forms are a single-byte index (slot 8 skipped on the wire)
  and `[type, len, *utf8]`.
- Deferred: auto-source real macOS notifications; cloud HTTP surface.

Full suite: 538 passed / 0 failed / 73 skipped.

---

## Round 9 — 2026-06-06 (APK-only frontier: screen orientation + factory reset)

R8 closed the lib→GUI gap; R9 targets capabilities the APK has but `divoom_lib`
lacked — needing *new lib code*. Full inventory + confirmed payloads in
`docs/PLANNING_ROUND9.md` (verified against decompiled `CmdManager.java`).

### Added

- **lib** `divoom_lib/display/design.py` (0xBD EXT dispatcher): `set_screen_dir`
  (0xBD 0x23), `set_screen_mirror` (0xBD 0x24), `factory_reset` (0xBD 0x25,1).
- **GUI** Tools→Device **Display** card: orientation select (0/90/180/270°),
  mirror toggle, and a `.danger-zone` factory-reset button gated by a
  `confirm()` + typed-"RESET" prompt. Bridge `factory_reset(confirm)` also
  refuses unless the literal `"RESET"` token is passed (belt & suspenders).
- 10 tests (5 lib byte-exact, 2 bridge incl. token guard, 3 static UI/exposure).

### Notes

- **Brightness was NOT re-added** — it already exists (`device.set_brightness`,
  0x74) with a LAN/multi-target bridge + appbar slider. The excavation's main
  correction: `SPP_SET_SYSTEM_BRIGHT` (116) == 0x74.
- Deferred: ANCS notification mirroring (own round); cloud HTTP surface.

Full suite: 527 passed / 0 failed / 73 skipped.

---

## Round 8 — 2026-06-06 (Feature excavation: device settings, FM, weather, memorial)

Excavated the lib↔GUI gap (`docs/PLANNING_ROUND8.md`): the library implements
~140 device methods, the GUI exposed ~58. Surfaced more, in a restructured
Tools tab.

### Added

- **Tools tab → sub-tabs** (Utilities / Device / Radio). Alarms/Sleep/Tools
  moved under **Utilities**.
- **Device Settings** (Device sub-tab): 24-hour toggle (0x2c), °F toggle (0x2b),
  low-power toggle, device name (0x75), auto-power-off (0xab), **Sync time from
  this Mac** (0x18). Bridges in `gui_api.py`; un-faceted helpers (`DateTimeCommand`,
  `DeviceSettings`) instantiated on the active device.
- **Weather** push (`update_temp_weather`).
- **Anniversary/Memorial** editor (`scheduling/alarm.set_memorial_time`, 0x54).
- **FM Radio** tuner + presets (`media/radio.set_radio_frequency`).

### Deferred

- **Timeplan UI**: `set_timeplan` bridge shipped + unit-tested, but
  `set_time_manage_info` mode/type semantics are unverified — no UI card (avoid a
  hallucinated control). Revisit with hardware. SD player / Game / Drawing /
  0xBD EXT remain Phase 2/3.

Full suite: 517 passed / 0 failed.

---

## Round 7 — 2026-06-06 (Feature harvest: surface un-exposed divoom_lib modules)

Surfaces previously un-exposed `divoom_lib` modules in the GUI (see
`docs/PLANNING_ROUND7.md`). Each feature: backend bridge in
`gui/gui_api.py` + UI + unit tests.

### Added

- **Text Channel** — new "Text" channel card/panel (input, color, effect,
  speed). `push_text()` runs the full LPWA (0x87) sequence
  (display-box→font→color→speed→effect→content) over `display/text.py`.
- **Alarms editor** — Settings → Divoom: 10-slot list (enable, hour:minute,
  weekday mask, Save; "Read from device"). `get_alarms()`/`set_alarm()` wrap
  `scheduling/alarm.py` (0x42/0x43).
- **Sleep Aid** — Settings → Divoom: minutes + color + volume, Start/Stop.
  `start_sleep()`/`stop_sleep()` wrap `scheduling/sleep.py`.
- **Tools** — Settings → Divoom: stopwatch (start/stop/reset), countdown
  (mm:ss), noise meter. `set_timer()`/`set_countdown()`/`set_noise()` wrap
  `tools/{timer,countdown,noise}.py`.

### Changed (Round 7.1)

- **New "Tools" sidebar tab.** Alarms, Sleep Aid, and Tools
  (timer/countdown/noise) moved out of Settings → Divoom into a dedicated
  top-level **Tools** category (`gui/web_ui/templates.js:tools`, nav-btn +
  `<section id="tools">` in index.html, injected in `app.js`). Alarm rows now
  render on the `tab-changed` → `tools` event.
- **Added `AGENTS.md` core rule:** after every round, update the cross-session
  handoff (CHANGELOG + planning doc + commit) so the shared opencode/Claude
  sessions can keep up. The git history + docs are the cross-session memory.

### Notes

- Alarm read-back (0x42) needs the device to answer a query; on hardware
  those time out (see `docs/DEVICE_VALIDATION_PLAN.md`), so the editor is
  set-oriented. Full suite: 513 passed / 0 failed.

---

## Round 6 — 2026-06-06 (Monthly Best layout simplification + new functionality exposure)

### Changed — Monthly Best layout (Option B from `docs/PLANNING_ROUND5.md` §3)

- **Right card renamed "Sync Targets & Schedule" → "Devices".**
  The header now matches its sole remaining content. Found in
  `gui/web_ui/templates.js:monthly-best-layout`.
- **Schedule UI block removed from Monthly Best.** The
  `hc-schedule` block, the "Enable scheduled sync (runs headless)"
  checkbox, and the Save Schedule button are all gone from the
  Monthly Best template. The block was moved wholesale to
  Settings → Routines (see "Added" below).
- **Per-row MAC address removed from sync-target rows.** The
  `renderSyncTargets` function in `gui/web_ui/gallery.js` no
  longer creates a `.target-addr` element, and the
  `.target-addr` CSS class is removed from `gallery.css`. The
  MAC is already visible in Settings → Bluetooth Scanner.
- **Grid proportions changed to a true halve.**
  `gallery.css:.monthly-best-layout` now uses
  `grid-template-columns: 1.6fr 0.6fr` (gallery 73% / devices
  27%). Previous `1.4fr 1fr` was 58/42; the right card is now
  genuinely the minor column.
- **"Sync All → Targets" button label renamed to
  "Sync All → Devices".** Found in `templates.js:monthly-best`.
- **Orphaned schedule handlers removed from `gallery.js`.**
  The `loadHotChannelSchedule` function and the
  `hc-save-schedule-btn` click handler are gone. Settings.js
  loads the form on tab change / sub-tab click instead.

### Added — Settings → Routines sub-tab (auto-sync gallery)

- **"Routines" sub-tab in Settings nav.** New button between
  "Divoom" and "Connectivity" in `templates.js:settings-nav`.
- **`#settings-routines` content block.** New "Auto-Sync
  Gallery" card with an enabled checkbox
  (`#routines-auto-sync-enabled`), an interval select
  (`#routines-auto-sync-interval` with options 1h / 6h / 12h /
  24h), a Save button (`#routines-auto-sync-save`), and a
  status line. The form sends `{ enabled, interval }` (the
  old `classify` field is dropped — it was a developer-term
  leak).
- **JS handler in `settings.js`.** New
  `window.loadRoutinesAutoSync` loads the config on the
  `tab-changed` event (to settings) or on click of the
  Routines sub-tab. The form save pushes to the existing
  `get_hot_channel_config` / `save_hot_channel_config` API
  methods (`gui/gallery_sync.py:415-426` — API unchanged
  for backward-compat; the persisted JSON key is also
  unchanged).
- **Dropped developer term "headless".** The old "Enable
  scheduled sync (runs headless)" label is replaced with
  the user-friendly "Enable auto-sync to gallery".

### Added — Volume slider in appbar

- **`#appbar-volume-slider` + `#appbar-volume-value`.** New
  slider in `gui/web_ui/index.html:appbar` (positioned
  after the brightness slider). Range 0–15 (the protocol's
  actual range, per `divoom.music.set_volume`, 0x08). Kare:
  show the raw value, no magic normalization. The volume
  is intentionally a separate slider from brightness
  (0–100) — different ranges, different semantics.
- **Handler in `gui/web_ui/app.js`.** `input` event updates
  the `N/15` display; `change` event calls
  `window.pywebview.api.set_volume(val)`. On startup,
  `get_volume()` initializes the slider to the device's
  current value. `change` (not `input`) is used to push to
  avoid spamming 0x08 writes during slider drag.
- **Speaker SVG icon** (Apple SF Symbols–style) replaces
  the previous brightness-adjacent UI element.

### Added — Scoreboard channel-card in Control Panel

- **New channel-card with `data-channel="scoreboard"`.**
  Positioned after the Ambient card in
  `gui/web_ui/index.html:channel-grid`. SVG scoreboard
  icon.
- **`#panel-scoreboard` markup.** 2 number inputs
  (`#scoreboard-red` 0–999, `#scoreboard-blue` 0–999).
  No Show / Hide / Enabled buttons — see "Round 6.1
  behavior fix" below for why.
- **Click the card → switches the device to the
  scoreboard channel (0x06).** This is the same pattern
  as Clock, VJ, EQ, and Design: clicking the card fires
  `switch_channel("scoreboard")`, which dispatches to
  the new `divoom_lib.display.show_scoreboard()` method.
  The scoreboard channel sits in the same `set light
  mode` (0x45) family as the other channels; the wire
  payload is `[0x06, 0, 0, 0, 0, 0, 0, 0, 0, 0]`
  (10 bytes, same padding as show_clock /
  show_visualization / show_effects / show_design).
- **Edit a number → auto-pushes the score** via the
  0x72 set-tool command (`set_scoreboard(1, red, blue)`).
  Same pattern as the clock color input and the
  ambient color input: change event fires the API
  call, no separate "Apply" button.

### Round 6.1 — 2026-06-06 (scoreboard behavior fix)

User feedback: "scoreboard should switch to the channel
and push changes automatically without the user pressing
the show scoreboard button — this is how all the other
channels behave." The Round 6 initial implementation had
a Show button + an Enabled checkbox + a Hide button
(unlike every other channel). The fix:

- **Removed `scoreboard-show-btn`, `scoreboard-hide-btn`,
  and `scoreboard-enabled` from the HTML panel.** The
  panel now contains only the 2 number inputs.
- **Removed scoreboard from the no-`switch_channel`
  skip list** in `channels.js`. The card click now
  fires `switch_channel("scoreboard")`, which lands in
  the new `show_scoreboard()` method.
- **Show/Hide button handlers removed** from
  `channels.js`. Replaced with a single
  `pushScoreboard()` function wired to the `change`
  event of both number inputs.
- **New `divoom_lib/display/show_scoreboard()` method**
  + `switch_channel("scoreboard")` dispatch.
- **Why no "Hide" button**: per user, "hide is
  essentially 'clear' since it clears the score" —
  clearing the score is what setting both inputs to 0
  already does. No separate Clear button is needed.

### Added — `gui_api.py` methods

- **`set_volume(self, volume: int) -> bool`** — clamps to
  0–15. Wall-mode fan-out (one write per device). Music
  fallback (writes to `divoom.music.set_volume`).
- **`get_volume(self) -> int | None`** — returns the
  device's current volume or None if unreachable.
- **`set_scoreboard(self, on_off: int, red: int = 0, blue: int = 0) -> bool`** —
  calls `target.scoreboard.set_scoreboard(on_off, red, blue)`
  with 0x72 set-tool framing. Clamps red/blue to 0–999.

### Documented gaps (intentional)

- **No battery badge in appbar.** User requested a
  device-battery indicator (planning doc §6.1 Phase 1),
  but `divoom_lib` has NO protocol command for device
  battery level. The only related commands are
  0xB2 / 0xB3 (low-power auto-dim switch), which control
  the device's dim behavior — they do NOT report battery
  level. The Divoom Cloud mobile app shows device battery
  over the cloud, not BLE / SPP. Adding a fake battery
  badge (e.g. showing the laptop's battery) would be
  misleading. **The test
  `test_no_battery_badge_intentionally_not_implemented`
  guards against this.** To unblock: (1) find a protocol
  command (possibly in Divoom Cloud over HTTPS), (2)
  implement in `divoom_lib`, (3) add a GUI badge, (4)
  add `get_battery()` in `gui_api.py`, (5) update the
  guard test to assert the new badge exists.

### Files

- `gui/web_ui/templates.js` — Monthly Best card renamed,
  schedule block removed, Routines sub-tab added.
- `gui/web_ui/gallery.js` — orphaned schedule handlers
  removed; the dead `window.loadHotChannelSchedule()`
  call in the 1500ms mount timer is replaced with a
  comment pointing to settings.js.
- `gui/web_ui/gallery.css` — grid `1.4fr 1fr` → `1.6fr 0.6fr`,
  `.target-addr` rule removed.
- `gui/web_ui/settings.js` — `loadRoutinesAutoSync` and
  save handler added; 2 event listeners (tab-changed +
  click on routines sub-tab) at end of DOMContentLoaded.
- `gui/web_ui/index.html` — volume slider in appbar,
  Scoreboard channel-card + panel.
- `gui/web_ui/app.js` — volume slider `input`/`change`
  handlers + `get_volume` startup init.
- `gui/web_ui/channels.js` — scoreboard removed from
  no-`switch_channel` list (Round 6.1); show/hide button
  handlers replaced with `pushScoreboard()` wired to the
  number inputs' `change` events.
- `gui/gui_api.py` — `set_volume`, `get_volume`,
  `set_scoreboard` added.
- `divoom_lib/display/__init__.py` — new
  `show_scoreboard()` method + `switch_channel("scoreboard")`
  dispatch (Round 6.1).
- `tests/test_round6_layout_and_exposure.py` — **19 new
  regression tests** (static-analysis + Playwright smoke).
- `tests/test_e2e_mock_device.py` — **2 new e2e tests** for
  show_scoreboard + switch_channel("scoreboard") wire
  bytes (Round 6.1).

### Test count

- Round 6 initial: 505 passed / 73 skipped / 0 failed
  (+19 Round 6 regression tests).
- Round 6.1: **507 passed / 73 skipped / 0 failed** (+2
  e2e tests for show_scoreboard / switch_channel).
- No regressions. Wall-clock full suite: ~70s.

### Live device

- Volume slider and scoreboard show/hide: NOT yet
  live-tested. The transport-level correctness of the
  underlying protocol calls is covered by the existing
  `divoom_lib` unit tests (mock transport) and
  `test_e2e_mock_device.py`. Manual device verification
  is recommended before the next GUI deployment.

### Design notes

- The Monthly Best dialectic (4 options A/B/C/D) is
  documented in `docs/PLANNING_ROUND5.md` §3. Option B
  (this implementation) was the user pick via 4-option
  confirmation: schedule moves to Settings, all 5
  asks in Phase 1, "Auto-Sync Gallery" naming, no
  relocation hint. Kare: pixel-perfect clarity
  (N/15 raw, no normalization). Rams: simpler
  right card (73/27, not 58/42), `1.6fr 0.6fr` is
  the "good" (true halve) pattern.

---

### Fixed

- **Window drag fix (final).** The frameless window drag now works
  on macOS single-monitor and multi-monitor setups. The fix is the
  combination of:
  - pywebview's bundled `pywebview-drag-region` CSS-class mechanism
    (re-enabled on the appbar in `gui/web_ui/index.html:24`).
  - A gated monkey-patch to `webview.platforms.cocoa.BrowserView.move`
    in `gui/gui_main.py:111-128` that drops the `self.screen.origin.x`
    term, fixing upstream
    [pywebview#1820](https://github.com/r0x0r/pywebview/issues/1820)
    (May 2026). The patch is gated by a source-based detection
    helper `_pywebview_1820_bug_present()` (lines 27-66) that
    inspects `BrowserView.move` and only applies the patch when
    the bug token `self.screen.origin.x + x` is present. When
    pywebview ships the upstream fix, the token disappears from
    the source, the helper returns False, and the patch is
    skipped (logged: "pywebview #1820 already fixed upstream;
    skipping patch"). When that happens, the entire block in
    `gui_main.py:96-128` can be deleted.
- **Self-deactivation contract verified.** Two new tests in
  `tests/test_gui_drag_instrumented.py`:
  - `test_pywebview_1820_detection_matches_source` — canary that
    fails if the detection token no longer matches the bug
    signature in the installed pywebview. This is the trigger
    for deleting the workaround.
  - `test_pywebview_1820_detection_simulates_upstream_fix` —
    monkey-patches `webview.platforms.cocoa.BrowserView.move`
    into the upstream-recommended fix shape and asserts the
    detection returns False. Verifies the self-deactivation
    contract.

### Changed

- **`gui/gui_main.py`** — added the detection helper and gated
  the patch application. ~40 LOC added.
- **`tests/test_gui_drag_instrumented.py`** — added 2 new
  detection-contract tests (4 → 6 total). Updated
  `test_gui_main_patches_cocoa_drag` to assert the new
  structure (detection helper present, patch body does not
  contain the bug token).
- **`docs/PLANNED_WORK.md`** §5 #0 — updated status table
  entry to point to the new history file and document the
  self-deactivation contract.
- **`docs/PLANNING_ROUND2_CONTINUATION.md`** §1 — corrected
  the original §1 dialectic recommendation (Approach A was
  rejected by implementation). Added §14 documenting the
  final 4-attempt journey.

### Added

- **`docs/DRAG_FIX_HISTORY.md`** — full history of all 4
  drag fix attempts, why each failed, what the final correct
  fix is, and how to undo the workaround when pywebview ships
  #1820. Future maintainers: read this before "simplifying" the
  drag mechanism.

### Removed

- **Custom JS drag handler** from `gui/web_ui/app.js` (had
  caused 2 of the 4 failed attempts to jump around).
- **Custom Python `drag_window`** from `gui/gui_api.py` (was
  the source of 3 failed attempts, including a 16ms Timer
  debounce that was theoretically correct but missed the
  real bug).

### Test count

- Before: 484 passed / 73 skipped / 0 failed.
- After: 486 passed / 73 skipped / 0 failed (+2 detection-
  contract tests).
- No regressions. Wall-clock full suite: 66.85s.

### Upstream status

- **pywebview#1820 still OPEN** as of 2026-06-06. No PR, no
  branches. The monkey-patch is still required.
- Issue link: https://github.com/r0x0r/pywebview/issues/1820

---

## Round 4 — 2026-06-05 (cover upload, 0x44→0x49 remap)

### Fixed

- **`set animation frame` command was 0x44, now 0x49.** Per the
  protocol summary (`docs/DIVOOM_PROTOCOL_SUMMARY.md`) and APK
  reference, 0x44 is a *single-frame static image* command, and
  0x49 is the *multi-frame animation* command. The library was
  remapping `show_image` through 0x44 with the multi-frame body,
  which the device parsed as a static image and silently dropped
  subsequent frames. `divoom_lib/models/commands.py:36` now
  reads `"set animation frame": 0x49`. Single-frame "animations"
  worked by coincidence — 0x44 + first-frame bytes happens to
  parse as a valid static image.
- **Multi-frame 0x8B 3-phase protocol** implemented in
  `divoom_lib/display/animation_8b.py` (142 LOC) and routed from
  `divoom_lib/display/__init__.py:show_image`. Falls back to
  0x49 if the device rejects the 0x8B handshake.
- **32×32 PixooMax support** — new encoder in
  `divoom_lib/utils/divoom_image_encode_32.py` (119 LOC) +
  C encoder in `divoom_lib/native_src/image_encode_32.c` (286 LOC).

### Test count

- 448 passed / 73 skipped / 0 failed (up from 369).
- +79: 27 encoder + 1 time kwarg + 2 deleted make_framepart/chunks
  + 28 wall canvas + 11 native 32×32 parity + 10 0x8B chunker.

### Files

- `divoom_lib/models/commands.py:36` — remap to 0x49.
- `divoom_lib/display/animation_8b.py` — new, 0x8B 3-phase.
- `divoom_lib/utils/divoom_image_encode_32.py` — new, 32×32 encoder.
- `divoom_lib/native_src/image_encode_32.c` — new, 32×32 C encoder.
- `divoom_lib/native/image_encoder.py` — 432 LOC, wraps C fast path.
- `tests/test_native_image_encoder_32.py` — 11 parity tests.
- `tests/test_e2e_mock_device.py::test_show_image_emits_0x49_frames`
  — renamed from `test_show_image_emits_0x44_frames`.

### Live device

- 2 live-device verifications (4-quadrant, half-green/red) .
- C encoder byte-identical to Python encoder (40/40 parity tests).
- 0x49 push correctly framed and ACKed by device.
- Multi-frame cycling on Timoo: deferred (device firmware behavior
  requires additional commands not yet identified).

---

## Round 3.5 — 2026-06-05 (P1 helpers, sound, game)

### Added

- **`divoom_lib/system/control.py`** (75 LOC) — `Control` class with
  `set_keyboard` (0x23), `set_hot` (0x26), `set_light_mode` (0x45).
- **`divoom_lib/display/design.py`** — 0xBD sub-cmd dispatch:
  `set_eq`, `set_language`, `set_user_define_time`,
  `get_user_define_time`.
- **`divoom_lib/system/sound.py`** — `SoundControl` class with
  song display, power-on voice vol, ambient sound, auto
  power-off. Registered on `Divoom`.
- **`divoom_lib/game.py`** (167 LOC) — `hide_game`, `set_key_down`
  (0x17), `set_key_up` (0x21), `set_magic_ball_answer` (0x88),
  `exit_game`, 9 game ID constants.
- **26 P1 helper tests** in `tests/test_round4_p1_helpers.py`.

### Test count

- 408 → 448 passed (+40), 73 skipped, 0 failed.

### Live device

- All 4 devices (Pixoo 16×16, Tivoo Max, Ditoo, Timoo) live-tested.

---

## Round 3 — 2026-06-05 (cover upload, 0x44→0x49)

- (Merged into Round 4 above.)

---

## Round 2 — 2026-06-05 (drag, channel-switch, perf)

- **Drag fix attempts 1-3** — all reverted. See
  `docs/DRAG_FIX_HISTORY.md` for the journey.
- **`display_image` wrapper** — implemented in
  `divoom_lib/display/__init__.py:display_image` as a thin
  alias for `show_image` + optional `wait_for_display` poll.
  8 unit tests in `tests/test_display_image_wrapper.py`.
- **BLE start_notify guard** — added `_notifications_started`
  flag in `divoom_lib/ble_transport.py`. Bug was real;
  macOS CoreBluetooth raises "Characteristic notifications
  already started" if `start_notify` is called twice without
  a `stop_notify` in between.
- **Push to Device button** — layout was already correct
  from Round 0/1; added 2 Playwright regression tests in
  `tests/test_monthly_best_button_visible.py`.
- **C downscaler perf profile** — confirmed hypothesis (a)
  from `PLANNED_WORK.md §6`: 99% of samples in
  `downsample_lanczos3` inner loop. Fix deferred (4-pixel
  NEON deinterleave is a follow-up). Byte-exact path is
  shipped and not user-blocking.
- **Test count:** 354 → 369 → 380 → 408 → 448 → 484 → 486.

---

## Round 1 — 2026-06-04 (hands-on followup, 6 issues)

- 1a: Love (pulse) is rainbow, not pulse — solid-color pulse 12s
  linear `love-color-cycle`.
- 1b: Color picker not visually distinct — dashed border + "+"
  SVG icon; click opens picker.
- 2: Window drag jumps between two positions — rAF-throttle in
  `widgets.js`; final-mousemove-only semantics. **Later reverted
  in favor of the Round 5 final fix** (see `DRAG_FIX_HISTORY.md`).
- 3: Gallery only "NeonSkull" — `load_cached_gallery` rebuilds
  from `cache_gallery/` when stale; 233 items recovered.
- 4a/4b: Live cover art — visualiser removed; manual 144×144
  push button in Live Widgets music card.
- 5: Stocks preview outside container bounds — `min-width: 0` on
  flex children.
- 6a/6b: System monitor — removed white panel; 3 labeled bars
  (CPU/MEM/BAT) with device-matched colors; removed duplicate
  `const sysmonDisplayBtn`.

---

## Round 0 — 2026-06-04 (visual regression, 8 issues)

- 1: Window drag regression (first occurrence) — move handler
  to `app.js`, `clientX/Y`, `preventDefault`, document delegation.
- 2.1: Custom Art button always visible — `flex:1; min-height:0`
  on scroll container, button pinned.
- 2.2: Color-picker wrapper click delegation — `<div>` →
  `<label>`; remove `channels.js` delegation block.
- 2.3: Ambient layout per Kare/Rams.
- 3: Ambient preview fixes (5 modes) — Love=solid-color pulse;
  Plants=16×16 pixel grid; Sleeping=green; No-mosquito=orange 40%.
- 4: Monthly best empty space — `flex:1; min-height:0` chain on
  gallery card.
- 5: Live widgets — multiple regressions (visualizer removed,
  sysmon = colored bars, `bindCardSelection` re-attached).
- 6: Device selector sidebar — speaker/res moved to Settings
  "Connectivity" sub-tab; preview image enlarged to 120×120.
- 7: Cleanup — dead `.appbar-device` CSS removed;
  `appbarSelect` → `sidebarDeviceSelect`.
- 8: Phasing (A–E) — all phases A–E executed.

## Round 25 — 2026-06-08 (Channel architecture research)

### Added

- `docs/CHANNEL_ARCHITECTURE.md` — comprehensive research doc from the
  decompiled APK covering all 7 light modes, the 6-byte vs 10-byte CLOCK
  formats, overlay toggle byte positions, TEMPRETURE channel payload, and
  the two-model split (`m`/LightInfo vs `k`/LightCache). Includes a
  byte-by-byte comparison of our `show_clock()` vs the APK's `CmdManager.C2()`
  (our bytes 4-6 are shifted — we set "weather" where the APK expects
  "humidity"). See doc for full implementation recommendations.

### Fixed

- **Weather push reverted** (`push_weather()` in `widgets.py`): the APK
  decouples data push (0x5F) from channel switch (0x45). The 0x45 TEMPRETURE
  channel switch with arbitrary model-field values was sending garbage bytes
  that could crash the device. Removed the channel switch — weather data is
  now pushed as 0x5F only (consistent with the APK). The channel must be
  switched separately.
- Removed test `test_weather_push_switches_channel_before_data` which tested
  the reverted behaviour.

---

## Round 27 — 2026-06-08 (Command queue with ring buffer, maxsize, item timeout)

### Added — `divoom_daemon/command_queue.py`

- **`CommandQueue` class** (`divoom_daemon/command_queue.py`): FIFO command
  queue wrapping the daemon's asyncio loop. Replaces direct
  ``asyncio.run_coroutine_threadsafe(coro, loop).result()`` in
  ``DeviceOwner._run_device()`` so all device-call dispatch is serialised
  through a single queue.

- **`maxsize` parameter** (constructor): bounded queue with pre-allocated
  ring buffer (``_Ring``). ``submit()`` raises ``QueueFull`` when at
  capacity. Zero = unbounded (dynamic list-backed).

- **`item_timeout` parameter** (constructor): per-item timeout checked at
  dequeue time. Expired items are transparently rejected with
  ``TimeoutError`` before the worker picks the next item.

- **`timeout` parameter** (``submit()`` / ``submit_async()``): per-submit
  override of the queue-wide ``item_timeout``. ``None`` disables timeout for
  that item; omit to inherit the queue default.

- **Exclusive mode** (``queue.exclusive(token)`` context manager, lines
  240-250): atomic multi-phase scopes. Items with a matching token are
  dispatched; non-matching items queue behind the exclusive session.

- **``QueueFull`` / ``QueueStopped``** exception classes: raised
  synchronously from ``submit()`` when the queue is at capacity or stopped.

### Changed — `divoom_daemon/device_owner.py`

- **``_run_device()``** now routes through ``self._cmd_queue.submit()``
  instead of ``asyncio.run_coroutine_threadsafe``. Lazily creates the queue
  via ``_device_loop()`` if not yet initialised (fixed regression where
  queue was ``None`` for early callers).

- **``DeviceOwner.stop()``** now stops the command queue before stopping
  the loop, preventing "Task was destroyed" warnings.

### Tests — `tests/test_command_queue.py`

- 30 tests total (was 14). Added:
  - Exclusive mode: multiple tokens, token=None with exclusive active
  - Stress: 50 concurrent submissions, 30-thread sync submit, 100-item burst
  - Lifecycle: submit after stop raises QueueStopped, start/stop cycle
  - Maxsize: full rejection, at-capacity acceptance, active-item exclusion
  - Item timeout: stale expiry, per-submit override, explicit None survival
  - Exception propagation: all built-in exception types
  - Null result: coroutine returning ``None``

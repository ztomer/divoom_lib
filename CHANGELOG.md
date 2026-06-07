# Changelog

All notable changes to divoom-control are documented here. The
format is loosely Keep-A-Changelog; entries are grouped by
shipped milestone (per the project planning docs).

---

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

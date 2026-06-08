# Session Handoff — read this first

This is the **cross-agent session state**. opencode and Claude Code keep their
own conversation stores (they can't share a live session), so THIS FILE + the
git history + CHANGELOG are the shared memory. Any agent (opencode or Claude)
should read this on entry and **update it at the end of every round** (see the
core rule in `AGENTS.md`).

## How to resume

- **opencode**: `opencode -s ses_184471307ffeCUHgzv9w51O0oA` (or
  `opencode export <id>` to read it as JSON).
- **Claude Code**: reads `CLAUDE.md` → `AGENTS.md` → this file, plus `git log`.
- Both: `git log --oneline`, `CHANGELOG.md`, `docs/PLANNING_ROUND*.md`.

## Current state — _update this section each round_

- **R23 — REVIEW §1.2 + §1.3 + §1.4 + §1.5 SHIPPED. Suite 980 / 0 / 75.**
  - **§1.2** — `gui_api.py` refactored from 891 → 444 LOC by composing 5 `ApiBase`
    collaborators (`ConnectionApi`, `LightingApi`, `ToolsApi`, `WidgetsApi`,
    `WindowApi`). Every bridge method that existed in a collaborator now
    delegates to it; all logging + error handling lives in collaborators.
    `AsyncLoopThread` moved from inline definition to `divoom_gui.api`.
    Removed dead code: `_device_status()`, `_target()`, `_dispatch()`,
    `_tool_call()`, `_as_bool()` — all now in collaborators.
    `send_notification` added to `ToolsApi`. `set_brightness`, `set_volume`,
    `display_wall_image`, `display_custom_art` added to `LightingApi`.
    File-size guardrail: `gui_api.py` removed from ALLOWLIST (444 ≤ 500).
  - **§1.3** — daemon.py 4-wave extraction:
    - Wave 1 (5d3f7d1): command registry (if-ladder → dict).
    - Wave 2 (7c0cc31): `SocketServer` → `divoom_daemon/socket_server.py`.
    - Wave 3 (73b39bd): `NotificationService` → `divoom_daemon/notification_service.py`.
    - Wave 4 (e3612b0): `DeviceOwner` → `divoom_daemon/device_owner.py`.
    - daemon.py: 730 → 132 LOC; removed from ALLOWLIST (10 entries).
    - New modules: 3 (socket_server, notification_service, device_owner).
  - **§1.4** — `DeviceSlot` dataclass shipped (c29c715):
    - `divoom_lib/models/device_slot.py` with `@dataclass DeviceSlot(device, x, y, size, width, height)`.
    - Exported from `divoom_lib/models/__init__.py`.
    - Replaced all ad-hoc 6-tuple construction/destructuring in `wall.py` and `device_owner.py`.
  - **§1.5** — 6 web_ui files > 500 LOC split into 14 files:
    - `templates.js` (718) → 4 files: `templates_tools.js` (124), `templates_monthly_best.js` (64), `templates_widgets.js` (200), `templates_settings.js` (330).
    - `app.js` (619) → `app_globals.js` (196) + `app_init.js` (425).
    - `channels.js` (578) → `channels_core.js` (149) + `channels_grids.js` (436).
    - `settings.js` (745) → `settings_hardware.js` (344) + `settings_features.js` (404).
    - `widgets.css` (524) → `widgets_base.css` (301) + `widgets_extra.css` (224).
    - `style.css` (510) → `style.css` (279) + `style_extra.css` (236).
    - ALLOWLIST shrunk from 10 → 4 entries (`media_sync.py`, `downsample.c`, `constants.py`, `cli.py`).
    - `index.html` + `style.css` @import chain updated; 8 test files updated.
  - Suite 980 passed / 75 skipped (zero regressions across §1.2–§1.5).

- **R22 — menubar refactor: top-level package + daemon client. Suite 944 / 0 / 75.**
  - New `divoom_menubar/` package (menubar_client.py, menubar.py) at repo root.
  - Menubar rewritten as pure daemon client: connects to daemon's Unix socket,
    subscribes to EVENT_STATUS events for real-time status updates. **No BLE,
    no socket server** — respects R17 single-owner rule (daemon owns device +
    notification monitor).
  - Event-driven: daemon pushes EVENT_STATUS on listener start/stop/error +
    every routed notification. Menubar title updates instantly — zero polling
    (user explicitly rejected polling for both MCP toggle and menubar).
  - Menu: Start/Stop Notifications → daemon commands; "Open Notifications..."
    deep-links GUI to `--tab data-sources --card notifications`.
  - CLI: `divoom-control menubar` (sync handler, blocks on Cocoa loop).
  - `tests/test_menubar.py` (6 tests, pure logic, no AppKit).
  - Deleted `divoom_daemon/menubar.py` + `menubar_status.py` (had own BLE +
    server, violating single-owner).

- **R21 — review + doc overhaul. Suite 993 / 0 / 75.**
  - `docs/REVIEW_2026-06.md`: full code/architecture review (Linus + Uncle Bob),
    UI/UX review (Rams + Kare), and the "rewrite lib+daemon in Rust?" analysis.
    Key findings: 11 files >500 LOC (rule regressed); `gui_api.py` (921) is a God
    Object with ~150 LOC of duplicated wall/single branching; `daemon.py` (730) is
    an if-ladder dispatch + 4 responsibilities; wall 6-tuple should be a dataclass.
    Rust verdict: don't rewrite the lib; the *daemon* is the only defensible Rust
    candidate, and only with an embedded/footprint driver.
  - **Executed in R21:** `tests/test_file_size.py` (500-LOC guardrail with a
    shrink-only allow-list of the 11 current offenders); README + ARCHITECTURE
    rewritten; docs index; removed 10 stale docs.
  - **Executed in R22:** menubar refactor into `divoom_menubar/` (daemon client).
  - **Executed in R23:** gui_api collaborator integration (API split into 5
    collaborators, gui_api.py 891→444 LOC, removed from ALLOWLIST).
  - **Executed in R23 (§1.3):** daemon.py 4-wave extraction (command registry
    + SocketServer + NotificationService + DeviceOwner; daemon.py 730→132 LOC;
    removed from ALLOWLIST).
  - **Staged (still need doing):** REVIEW §1.4 (DeviceSlot dataclass), §1.5
    (web_ui splits).

- **R20 — Linux compatibility (daemon + libraries) SHIPPED. Suite 991 / 0 / 75.**
  `divoom_lib` + `divoom_daemon` run on Linux; BLE via bleak/BlueZ; the R19
  network server is platform-neutral. See `docs/PLANNING_ROUND20.md`.
  - `divoom_lib/native_lib.py` resolves `libdivoom_compact.{dylib|so|dll}`; all 4
    ctypes loaders use it. `build_libdivoom.sh` is cross-platform (clang/.dylib on
    macOS, cc/.so on Linux). `compact.c` NEON now guarded (`DIVOOM_HAVE_NEON`),
    x86_64 uses byte-identical memcpy — both paths verified to compile.
  - Daemon notification monitoring is macOS-only; off macOS `_cmd_start` returns
    a clean `unsupported`/idle state (no Mac monitor built). `media_source`
    now-playing returns None off macOS.
  - **Not run on real Linux hardware yet** (cross-compile + platform-guard unit
    tests only). Gaps by design: no Linux notification monitor / now-playing /
    menu-bar (macOS-only); a D-Bus/MPRIS backend would be future work.

- **R19 — daemon as a headless NETWORK server SHIPPED. Suite 986 / 0 / 75.**
  (User: "why JSON for on-device RPC? + I want the daemon to run headless over
  the network." Decisions: TCP alongside Unix · LAN + token · ship image bytes.)
  - JSON answer: NDJSON is the *control plane* (small, debuggable, transport-
    agnostic); device pixels/GIFs are the *data plane*, kept out of JSON (binary
    needs base64). See `docs/PLANNING_ROUND19.md`.
  - `DivoomDaemon(host, port, token)`: binds Unix (always) + an AF_INET listener
    when host/port set. TCP requests need a token (`hmac.compare_digest`); Unix
    stays trusted (no token). **Fail-closed**: TCP without a token won't start.
    Token falls back to `DIVOOM_DAEMON_TOKEN`. CLI: `divoom-control daemon
    --host 0.0.0.0 --port 9009 --token <secret>`.
  - Binary over the wire: `device_call` gained `blobs={argIdx: b64bytes}`; the
    daemon writes each to a temp file and substitutes the path. `DaemonClient`
    encodes blobs; `DaemonDeviceProxy` auto-ships local-file args as blobs when
    `is_remote` (TCP) — so media/gallery/cover-art work remotely with no call-site
    changes. `DaemonClient.from_env()` + `ensure_daemon()` target a remote daemon
    when `DIVOOM_DAEMON_HOST` is set (and never spawn).
  - +7 tests (`tests/test_daemon_network.py`). **Not hardware-verified; token is
    plaintext over TCP (add TLS for untrusted nets — follow-up).**

- **R17 P5 — FULL CUTOVER SHIPPED. The daemon is the sole BLE owner; the GUI is
  a thin client. Suite 980 / 0 / 75.** (User chose "do the full flip now.")
  - Daemon (`9cd76a73`, `abc83a20`, `8cb8e10e`): `device_call` (dotted dispatch,
    target device|wall), enriched `connect` (BLE+LAN+auto), `device_status`
    {connected,mac,lan_ip,wall}, `scan`, `wall_configure` (idempotent),
    `probe_lan`, `sync_artwork` (download+decode+resize+stream daemon-side); a
    dedicated device asyncio loop that survives across calls.
  - GUI (`divoom_gui/daemon_bridge.py` + scanner_mixin + gui_api + gallery_sync):
    `ensure_daemon()` auto-spawns a detached daemon; `DaemonDeviceProxy` routes
    `proxy.x.y(...)` through `device_call` and answers is_connected/lan/_conn from
    `device_status`. `current_divoom`/`wall_instance` are proxies — so media_sync
    (live widgets) routes through the daemon with NO rewrite. No `Divoom(`/
    `DivoomWall(` construction left in the GUI.
  - Library: `DivoomWall` gained switch_channel/push_text/set_brightness/
    set_volume; `media_decoder` moved divoom_gui→divoom_lib.
  - **AFTER P5 the daemon MUST be running for the GUI to control the device**
    (the GUI auto-spawns it via `divoom-control daemon`).
  - **Remaining (needs the live app + hardware — NOT verified, unit-green only):**
    (1) runtime-drive every GUI path against a real device; (2) menubar still
    uses `gui_api._push_menubar_status` → should subscribe to the daemon's status
    stream instead (the daemon already owns the monitor + broadcasts); (3)
    save_lan_config no longer hot-attaches LAN to a live device (applies on next
    connect). See `PLANNING_ROUND17.md §outcome P5`.

- **R18 — live-widgets + tabs fixes SHIPPED** (user feedback). Weather card
  auto-populates on load; weather location now IP-geolocated via wttr.in (no more
  hardcoded "Berlin"); weather 10-min poll re-pushes to the device; sysmon lost
  its grey gauge-track box; stock ticker got a smaller arrow + small font so the
  acronym fits; Tools/Settings sub-tabs got `.tab-icon` SVGs; the pill row +
  theme selector size to content. Suite **963 / 0 / 75**. *(item: weather
  device-sync still needs hardware verification.)*
- **Credentials-erased bug FIXED:** the settings form never re-populated the
  password field, so a plain re-save wrote `password=""`; the 23h token-cache
  expiry then degraded the account to a guest token. `save_credentials` now keeps
  a stored password on blank re-saves. +3 regression tests.
- **R17 (3-way split) — PHYSICAL split DONE (P1-P4, P6).** `divoom_lib` /
  `divoom_daemon` / `divoom_gui` are three top-level packages; the daemon core +
  notifications + menubar live in divoom_daemon; the dylib in divoom_lib; gui/ is
  renamed divoom_gui/. pyproject finds all three; entry points verified. Suite
  **963 / 0 / 75** (Playwright DOM tests browser-verify the rename). **P5 (the
  behavioural daemonisation) is the one remaining large piece** — see below.
  - **P5 blocker/decision:** the BLE connection is single-owner, so the daemon
    and GUI can't both hold the device. Correct model = **daemon owns the device;
    GUI is a thin RPC client** (generic `device_call` RPC + `gui_api` proxies, no
    direct BLE in the GUI; scanning/wall/LAN move to the daemon). It's a large,
    high-risk rewrite of the 935-line `gui_api` — needs its own tested program.
    See `docs/PLANNING_ROUND17.md` §outcome P5.

- **In flight — R16 daemon (P1+P2 shipped) → folding into R17 (3-way split).**
  Architecture correction from the user: the macOS notification monitor + ALL
  background device-driving must live in a **headless daemon**, not the GUI
  (presentation only). R16 P1 (`gui/daemon_protocol.py` — NDJSON command +
  subscribe/stream + `DaemonClient`) and P2 (`gui/daemon.py` — `DivoomDaemon`
  owns device + monitor + routing + event socket; `divoom-control daemon` CLI;
  monitor/device-sender injectable) are SHIPPED + tested (13 daemon tests).
  Suite **959 passed / 0 failed**.
  - **R17 — 3-way package split IN PROGRESS** (`divoom_lib`/`divoom_daemon`/
    `divoom_gui`). **P1–P3 SHIPPED**: `divoom_daemon/` package created; daemon
    core + `macos_notifications` + `menubar*` moved there; the native dylib +
    `compact.c` moved into `divoom_lib/` (all 9+ refs fixed, rebuilt, green).
    Suite **959 / 0 / 75**. **Next = P4**: rename `gui/` → `divoom_gui/` (move
    gui_main/gui_api/presets_manager/web_ui; the background modules ride along
    until P5), fix the **10 test `sys.path` hacks** + menubar's `../gui/gui_main`
    path + pyproject `gui`→`divoom_gui`. Then **P5** behavior migration (media_sync
    /gallery/scanner → daemon; gui_api+menubar become DaemonClients; removes R15
    §6 GUI-push), **P6** pyproject finalize, **P7** close. See
    `docs/PLANNING_ROUND17.md` §outcome. R16 P3/P4 are folded into P5.

- **Last round shipped:** Round 15 (§1+§7, §2, §3, §4, §5, §6 SHIPPED —
  round complete). 829 → 946 passed, +117 tests, zero regressions.
  **§6 menubar (event-driven, no polling):** the menubar status item shows
  `Divoom (active|idle|error)` with a green/grey/amber tint + an "Open
  Notifications..." item; the GUI pushes status to the menubar's Unix socket on
  start/stop/error (`gui_api._push_menubar_status`); AppKit-free logic in new
  `gui/menubar_status.py`; `gui_main --tab/--card` URL params honored by
  `settings.js`. `tests/test_menubar_ipc.py` (14). The plan's "poll every 5s"
  was dropped — user rejected polling twice. **MCP server live** — `divoom-control mcp-server
  --mac <MAC>` exposes 12 tools over stdio JSON-RPC. GUI toggle in
  Settings → Connectivity with **no background polling** (initial
  fetch + tab-activation + click-driven refresh only — user
  explicitly rejected 5s polling as "notifications every 5s").

  - **§1+§7 — Tab style unification** (`2c819325`): single source
    of truth `gui/web_ui/tabs.css` (`.tabs-row` / `.tab-btn` /
    `.tab-icon`); segmented-pill across Channel/Tools/Settings/Theme
    rows; Kare 16×16 SVG icon prefix optional. +16 tests. **Lesson
    learned:** backticks in template-literal comments break JS
    parsing — use plain text in inline comments inside template
    strings.
  - **§2 — Monthly Best auto-fetch** (`0e23253f`): `window.loadGallery()`
    auto-fires on tab activation + classify change. Renamed "Push
    Selected to Device" → "Update Device"; dropped "Refresh" button.
    Box cap `minmax(110px, 168px)`. +10 tests.
  - **§4 — Settings refactor** (`24f95690`): `.danger-zone` extracted
    to own `card.glass-card.danger-card` (red border via `settings.css`).
    Added 7d (`604800`) and 30d (`2592000`) to routines; `MAX_INTERVAL
    = 2592000` clamp in `hotchannel_config._normalize()`. +10 tests.
  - **§3 — Live Widgets weather card + Notifications move**
    (`b7c1e4d7`): new `divoom_lib/weather_provider.py` (WTTrIn +
    Stub + auto-fallback; env `DIVOOM_CONTROL_WEATHER_{PROVIDER,
    LAT, LON, LOCATION}`; default Berlin). Weather card has 128×128
    preview + 16×16 SVG icon + 7-segment temp; auto-push on select +
    10-min poller. Notification manual + mirror cards moved from
    Settings → Devices to Live Widgets. +41 tests (30 + 11).
  - **§5 — MCP server + GUI toggle** (`121d0b5`): new
    `divoom_lib/mcp_server.py` (MCPServer, Tool dataclass, JSON-RPC
    per spec 2024-11-05; methods: `initialize`, `tools/list`,
    `tools/call`, `ping`; std codes: `-32700`/`-32600`/`-32601`/
    `-32602`/`-32603`; notifications get no reply). 12 tools in
    `divoom_lib/mcp_tools.py`: `set_volume` (0-15),
    `set_brightness` (0-100), `set_light_mode` (named→channel),
    `set_weather` (-127..128, named→WeatherType), `set_alarm`
    (10 slots, weekday_mask 0-127), `set_radio` (875-1080),
    `set_low_power` (bool), `set_screen_orientation` (0/90/180/270 +
    mirror), `show_image` (local path), `play_sound` (100-3000ms
    best-effort via set_hot), `get_capabilities` (read-only),
    `get_device_state` (read-only with safe fallback). CLI
    `divoom-control mcp-server --mac <MAC>` runs the stdio loop.
    `gui/mcp_control.py` spawns `python -m divoom_lib.cli mcp-server`
    as a subprocess (new process group for clean SIGTERM); logs to
    `~/.config/divoom-control/mcp-server.log`. Settings → Connectivity
    card with Start/Stop buttons + status pill + log tail (20 lines /
    16 KB). **No 5s polling** — initial fetch + tab-activation + click
    refresh only. `docs/MCP_SERVER.md` ships with config snippets
    for Claude Desktop, Cursor, Cline, Continue. +25 tests. **The
    AsyncMock lesson:** auto-spy on `MagicMock` does NOT return
    AsyncMocks for sub-attributes; you must explicitly set
    `d.music.set_volume = AsyncMock(return_value=...)` to get
    `assert_awaited_*_with` assertions working.

  Suite: **946 passed / 0 failed / 75 skipped** (up from R15 start
  at 829). **+117 tests across R15 §1-§6**. Zero regressions
  across R8→R15.

- **Earlier rounds:** R14 (weather facade, routing JSON, GUI card,
  pyproject.toml); R13 (capability detection + examples/CLI +
  macOS notifications); R12 §A P7 (Tools→Sessions sub-tab rename),
  §D audit, §E pushed; R11 push-path bug fixes; R10 ANCS; R9 screen
  orientation + factory reset (0xBD EXT); R8 device settings/FM/weather
  /memorial + Tools sub-tabs; R7 surfaced text/alarms/sleep/tools.
  See `CHANGELOG.md` + `docs/PLANNING_ROUND*.md`.
- **Git:** R8→R15 arc is in the working tree, ready to push.

## Open threads / next up

1. **Push to origin.** Local is ~10 commits ahead (R15 §1-§6, R22 menubar,
   R23 §1.2–§1.5).
2. **R12 §A visual pass pending** (user-run `python3 gui/gui_main.py`):
   verify appbar corner transports, scoreboard restyle, wall toolbar,
   font sweep, segmented-pill, tools regroup, sub-tab rename to
   "Sessions", **and the new macOS Notifications card under
   Settings → Devices** (R14 §3) and the **new MCP Server card under
   Settings → Connectivity** (R15 §5).
3. **R12 §B hardware verification pending** (user-run): album cover
   renders un-distorted; custom-art/live push end-to-end; weather
   push via `divoom-control set-temperature 18 --weather clear`.
4. **get_* read-back times out on real devices** (task #20): get
   queries 0x42/0x46/0x13 get no parseable response (likely
   query-framing mismatch). Gates every "read from device". See
   `docs/DEVICE_VALIDATION_PLAN.md`.
5. **Channel-switch hardware bug (Divoom Max):** first switch works,
   rest don't; not root-caused. All switches are `set light mode`
   (0x45) fire-and-forget.
6. **Deferred features** (R12 §D): see
   `docs/PLANNING_ROUND12_D_AUDIT.md`.
7. **MCP enhancements:** HTTP+SSE transport, `subscribe_*` tools.

## Hardware note

macOS Bluetooth TCC is per responsible-process; drive real BLE by launching via
Terminal (`open *.command`). Device UUIDs + method in `docs/DEVICE_VALIDATION_PLAN.md`.

  - **§1 — `Weather` facade** (`<commit>`): new
    `divoom_lib/system/weather.py` with `Weather.set()`,
    `set_temperature()`, `set_weather()`. Wired to the Divoom
    facade as `divoom.weather`. The old `TempWeatherCommand` in
    `divoom_lib/system/temp_weather.py` is now a thin shim that
    delegates — fixes the latent `number2HexString()` bug (the
    function lives in `divoom_lib/utils/converters.py`, not on
    the Divoom instance) and unblocks the `examples/set_weather.py`
    deferred from R13 §2. CLI `set-temperature` subcommand added
    with `--weather` choice. +27 tests (21 weather + 4 CLI + 2
    legacy regression checks). Encodes temperatures using
    `(256 + c) & 0xFF` for negatives; range -127..128 (R14
    `[+-]0x7F|0x80` — the 0x5F command uses a signed byte).
  - **§2 — Custom routing JSON loader** (`<commit>`): new
    `load_routing_table(path)` / `save_routing_table(rules, path)`
    in `gui/macos_notifications.py`. Path resolves via
    `DIVOOM_CONTROL_ROUTING` env var, falling back to
    `~/.config/divoom-control/notification_routing.json`
    (XDG-convention, same dir as `devices.json`). Corrupt-file
    tolerant: warns + falls back to `DEFAULT_ROUTING`. Validates
    app_type ∈ NOTIFICATION_APPS (1-14) — bad entries are dropped
    with a warning, not crashed. Atomic save via `.tmp` + rename.
    `MacAppRouter.from_file(path)` classmethod. `MacNotificationMonitor`
    now loads from the custom file by default. +19 tests.
  - **§3 — GUI Settings → Devices card** (`<commit>`): new
    "macOS Notifications" card under Settings → Devices with
    toggle (start/stop listener), live status (running / stopped /
    error / unsupported), counters (seen / routed / dropped), and
    a routing-rules JSON editor (textarea + Save / Reset to
    defaults). `gui_api` adds `get_notification_listener_status()`
    and `save_notification_routing(json_text)` with hot-reload
    (the running monitor's router is replaced, no listener
    restart required). Status pill uses `--font-mono`. +5
    `test_gui_api` tests. **Note:** per-app checkboxes were
    considered but the JSON editor is more honest (the rules
    ARE JSON, the user is a developer) and avoids a parallel
    state to keep in sync. Card is keyboard-accessible.
  - **§4 — `pyproject.toml`** (`<commit>`): first packaging
    file in the repo. setuptools backend, PEP 621 metadata,
    version `0.14.0`, Python `>=3.10`. Core deps (`bleak`,
    `aiohttp`, `pillow`, `tomli`/`tomli-w`) match
    `requirements.txt`. `[gui]` extra: `pywebview` + `pyobjc`
    (darwin-only). `[test]` / `[dev]` extras. `[project.scripts]`
    registers the `divoom-control` entry point → `divoom_lib.cli:main`.
    `tool.setuptools.package-data` ships the dylib + `web_ui/`
    with the `gui` package. Verified `pip install -e .` succeeds
    + `divoom-control --help` works. **The legacy
    `./divoom-control` shell wrapper is KEPT** for in-tree dev
    without an editable install. +12 packaging tests.

  Suite: **829 passed / 0 failed / 75 skipped** (up from R13's
  755; the +1 skip is the live playwright diagnostic that
  depends on optional deps). **+74 tests across R14 §1-§4**
  (27 weather, 19 routing, 5 gui_api, 12 pyproject, 11 misc
  incidental). Zero regressions across R8→R14.

  Pre-existing in R13: **§5 — Fonts SHIPPED** (`10a29f64`): one
  CSS variable per font family; `style.css` is single source of
  truth; `tests/test_fonts.py` guards the rule.
  **§6 — No emojis SHIPPED** (`10a29f64`):
  `scripts/remove_emojis.py` swept 365 emojis; `tests/test_no_emojis.py`
  guards it.

- **Earlier rounds:** R13 (capability detection + examples/CLI +
  macOS notifications); R12 §A P7 (Tools→Sessions sub-tab rename),
  §D audit, §E pushed; R11 push-path bug fixes; R10 ANCS; R9 screen
  orientation + factory reset (0xBD EXT); R8 device settings/FM/weather
  /memorial + Tools sub-tabs; R7 surfaced text/alarms/sleep/tools.
  See `CHANGELOG.md` + `docs/PLANNING_ROUND*.md`.
- **Git:** R8→R14 arc is in the working tree, ready to commit + push.

## Open threads / next up (see docs/PLANNING_ROUND14.md for the full plan)

1. **R14 §1-§4 — commit + push** (current working tree): all four
   R13 follow-up sections complete and green.
2. **R12 §A visual pass pending** (user-run `python3 gui/gui_main.py`):
   verify appbar corner transports, scoreboard restyle, wall toolbar,
   font sweep, segmented-pill, tools regroup, sub-tab rename to
   "Sessions", **and the new macOS Notifications card under
   Settings → Devices** (R14 §3).
3. **R12 §B hardware verification pending** (user-run): album cover
   renders un-distorted; custom-art/live push end-to-end; weather
   push via `divoom-control set-temperature 18 --weather clear`.
4. **get_* read-back times out on real devices** (task #20): get
   queries 0x42/0x46/0x13 get no parseable response (likely
   query-framing mismatch). Gates every "read from device". See
   `docs/DEVICE_VALIDATION_PLAN.md`.
5. **Channel-switch hardware bug (Divoom Max):** first switch works,
   rest don't; not root-caused. All switches are `set light mode`
   (0x45) fire-and-forget.
6. **Deferred features** (R12 §D): see
   `docs/PLANNING_ROUND12_D_AUDIT.md` — Timeplan UI blocked on
   unverified `mode`/`type` semantics; SD player blocked on task
   #20; Game has no host UX; Drawing needs a non-trivial UI per mode;
   Cloud HTTP is its own round (auth broken).
7. **R14 §3 — verify the new card on a real Mac** with notifications
   actually firing; routing JSON editor parses + saves +
   hot-reloads the live monitor without restart.

## Hardware note

macOS Bluetooth TCC is per responsible-process; drive real BLE by launching via
Terminal (`open *.command`). Device UUIDs + method in `docs/DEVICE_VALIDATION_PLAN.md`.

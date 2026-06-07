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

- **Last round shipped:** Round 15 (§1+§7, §2, §3, §4, §5 SHIPPED;
  §6 not started). Five commits, 829 → 932 passed, +103 tests,
  zero regressions. **MCP server live** — `divoom-control mcp-server
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

  Suite: **932 passed / 0 failed / 75 skipped** (up from R15 start
  at 829). **+103 tests across R15 §1+§2+§3+§4+§5**. Zero regressions
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

1. **R15 §6 — Menubar (not started).** Plan: poll
   `get_notification_status` less aggressively (or event-driven);
   status-item title suffix `(active)/(idle)/(error)` with color
   tints. "Open Notifications..." menu item. ~4 tests. **Carry the
   "no background polling" lesson from §5** — the user has explicitly
   flagged this twice.
2. **Push R15 to origin.** Local is 5 commits ahead (`git log --oneline`
   for the last 5 shows R15 §1+§7, §2, §4, §3, §5 in that order).
3. **R12 §A visual pass pending** (user-run `python3 gui/gui_main.py`):
   verify appbar corner transports, scoreboard restyle, wall toolbar,
   font sweep, segmented-pill, tools regroup, sub-tab rename to
   "Sessions", **and the new macOS Notifications card under
   Settings → Devices** (R14 §3) and the **new MCP Server card under
   Settings → Connectivity** (R15 §5).
4. **R12 §B hardware verification pending** (user-run): album cover
   renders un-distorted; custom-art/live push end-to-end; weather
   push via `divoom-control set-temperature 18 --weather clear`.
5. **get_* read-back times out on real devices** (task #20): get
   queries 0x42/0x46/0x13 get no parseable response (likely
   query-framing mismatch). Gates every "read from device". See
   `docs/DEVICE_VALIDATION_PLAN.md`.
6. **Channel-switch hardware bug (Divoom Max):** first switch works,
   rest don't; not root-caused. All switches are `set light mode`
   (0x45) fire-and-forget.
7. **Deferred features** (R12 §D): see
   `docs/PLANNING_ROUND12_D_AUDIT.md` — Timeplan UI blocked on
   unverified `mode`/`type` semantics; SD player blocked on task
   #20; Game has no host UX; Drawing needs a non-trivial UI per mode;
   Cloud HTTP is its own round (auth broken).
8. **MCP enhancements (post-R15):** HTTP+SSE transport, `subscribe_*`
   tools, auth (none now; macOS-only + per-user-uid is the default
   trust boundary).

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

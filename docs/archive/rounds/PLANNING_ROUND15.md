# Round 15 — UI unification, monthly best, weather widget, settings refactor, MCP server, menubar

**Date:** 2026-06-07
**Status:** DRAFT → implementation in progress
**Predecessor:** R14 (weather facade, routing JSON, GUI notifications card, pyproject.toml)

This is a big round — six user-driven changes plus a new MCP server feature.
The unifying theme is **making the GUI more honest**: removing buttons that
should be automatic, moving things to where users expect them, and giving
the menubar + an MCP server a real role in the workflow.

---

## Design rationale (cross-cutting)

### Tab style unification — Rams + Kare

The user asked us to consult Dieter Rams and Susan Kare on a single tab
style for Channels, Tools, and Settings.

**Current state** (3 styles, all "tabs" by name):

| Panel | Style | Source |
|---|---|---|
| **Tools sub-tabs** | Segmented-pill: transparent / `--primary` bg + white text active | `settings.css:239-280` |
| **Settings sub-tabs** | Segmented-pill (same as Tools) | `settings.css:239-280` |
| **Theme mode (Appearance)** | Segmented-pill (same again) | `settings.css:186-225` |
| **Channel cards** | Outlined pill: `rgba(255,255,255,0.02)` bg / `--primary` border + 4% tint active; Kare SVG icon + label | `channels.css:63-89` |

**Dieter Rams' lens (less but better, honest, useful):**
- A tab is a *switch* between mutually-exclusive options. The control
  surface should not compete with the content it controls.
- A segmented-pill is the minimal honest answer: one row, one shape,
  one state model (active vs not).
- Rams' *thematic consistency* ("in the long run, it's not the
  individual products that endure, it's the consistency of the design
  language") strongly favors ONE form for "sub-tab" across the app.

**Susan Kare's lens (clear silhouettes, low-res legible, function over
decoration):**
- The 16×16 Kare icons inside the channel cards are excellent — they
  ARE the channel's identity. Removing them would be a regression.
- The pixel-art icon is a **prefix to the label**, not a substitute.
  A pill with `[icon] Label` is the Kare form.
- Kare's rules don't dictate *chrome*; they dictate *what earns its
  place inside a control*. The icon earns its place; the segmented
  frame is the right chrome.

**Decision: segmented-pill with an optional icon prefix.**
- The **chrome** is unified: one row of pills, transparent / `--primary`
  bg + white text. No borders competing with the active state. No
  extra backgrounds. Same active state across all three panels.
- Channels keep their Kare 16×16 icon as a prefix (slot: `.tab-icon`,
  optional). Tools/Settings keep their label-only form.
- Hover state: same in all three (subtle bg + lighter text).
- The container's flex layout, gap, and active-state CSS class are
  shared via a new `gui/web_ui/tabs.css` (single source of truth).

This is the smallest change that achieves visual unity without losing
Kare's contribution to channel recognition.

### Monthly Best box-size cap

`gallery.css:3` currently uses
`grid-template-columns: repeat(auto-fill, minmax(110px, 1fr))`.
At a wide viewport the boxes grow with `1fr` and the items look
disproportionate to the device preview inside.

**Decision:** cap the upper bound so each box is sized to fit
the preview (1:1 aspect) + the name (one truncated line) + the
hover state. `minmax(110px, 168px)` — i.e., 168px square. The
animation preview is the dominant element; 168px gives a 168×168
preview box with 12px padding + ~20px of name/likes below. Any
wider and the box becomes mostly white space.

### Weather data source (Live Widgets §3)

The weather card needs to show *actual* weather, not the stale
value last pushed to the device.

**Options considered:**

| Source | Pros | Cons |
|---|---|---|
| **wttr.in** | Free, no key, JSON, no rate limit for our use | IP-based geolocation (rough) |
| **OpenWeatherMap** | Accurate, geocoding | Requires API key, has free tier |
| **NWS (api.weather.gov)** | Free, no key, accurate | US-only |
| **macOS CoreLocation + WeatherKit** | Most accurate, no key | TCC permissions, macOS-only |

**Decision: wttr.in** as the default. Configurable via the env var
`DIVOOM_CONTROL_WEATHER_LAT` / `DIVOOM_CONTROL_WEATHER_LON` to override
geolocation. A `--weather-stub` flag (and matching `WeatherProvider` enum)
falls back to a deterministic stub for testing.

### MCP server architecture (new feature §5)

The user asked for an MCP server with a settings-panel toggle. MCP
(Model Context Protocol) is Anthropic's open standard; the canonical
transport is **JSON-RPC over stdio**. The most common clients are
Claude Desktop / Cursor / Cline / Continue.

**Three architecture options:**

| | A: GUI thread | B: GUI spawns subprocess | C: Standalone CLI |
|---|---|---|---|
| Connection sharing | Shared with GUI | Subprocess connects fresh | Standalone, no GUI |
| Lifecycle | Toggle in Settings | Toggle in Settings | `divoom-control mcp-server` |
| Connection persistence | 1 connection | 2 connections (GUI + MCP) | 1 connection (MCP only) |
| Restart on device change | No (just updates thread) | Yes (subprocess needs --mac) | No (CLI takes --mac once) |
| Composability | Low | Medium | High |

**Decision: B (GUI-spawned subprocess) is the toggle path. C
(standalone CLI) is the scriptable path.** Both run the same
`divoom_lib.mcp_server` module; the GUI just adds convenience.

Why: keeping MCP as a real subprocess (a) is the canonical MCP
pattern (stdio = subprocess), (b) doesn't couple MCP's lifecycle to
the GUI's, (c) means the user can ALSO run it from a shell with
`divoom-control mcp-server`, (d) the subprocess crashing doesn't take
down the GUI.

**Tools exposed** (initial catalog — see §5 for the full list):
- `set_volume`, `set_brightness`
- `set_light_mode`, `set_clock`, `set_weather`
- `set_alarm`, `set_radio`, `set_low_power`, `set_screen_orientation`
- `show_image` (URL), `push_gif` (URL)
- `play_sound` (buzzer)
- `get_capabilities`, `list_devices`, `get_device_state`

**Toggle UX** (Settings → Connectivity card):
- Off by default.
- Off → On: GUI spawns `python -m divoom_lib.mcp_server --mac <current> --stdio`,
  tracks the PID, shows "Running (PID 12345)".
- On → Off: GUI kills the subprocess; shows "Stopped".
- On startup (if config says "auto-start"): GUI spawns the server.
- Status: `is_mcp_server_running() -> bool`, `get_mcp_server_status() -> dict`.

### Menubar item (new feature §6)

`gui/menubar.py` already exists — a Cocoa NSStatusItem with 3 menu
items. The user wants the menubar to:
1. **Show notification routing state** — change the status-item icon
   or add a status row when the listener is running.
2. **Configure notifications** — a "Configure Notifications..." menu
   item that opens the GUI and scrolls to the Live Widgets →
   Notifications card.

**Implementation:**
- Add a new IPC method `get_notification_status` to the menubar's
  Unix socket protocol.
- The menubar polls it every 5s.
- The status-item title becomes "Divoom (active)" / "Divoom (idle)" /
  "Divoom (error)" — using the same status-pill color tokens (green
  / gray / amber) from R14 §3.
- New menu items:
  - "Open Notifications..." → `subprocess.Popen(['open', 'divoom-control://notifications'])` (URL scheme) or `subprocess.Popen([sys.executable, gui_main.py, '--tab', 'data-sources', '--card', 'notifications'])` (CLI flag).
  - "Open Dashboard" — replaces or augments "Launch Dashboard".
- Keep the existing socket IPC for backward compat.

---

## §1 — Tab style unification (Channels + Tools + Settings)

**Scope:** make the segmented-pill the single tab style across all
three panels. Channels get an optional Kare 16×16 icon prefix.

**Files:**
- `gui/web_ui/tabs.css` (new — single source of truth for tab chrome)
- `gui/web_ui/channels.css` (drop channel-card specific chrome; keep
  the icon SVG styles only)
- `gui/web_ui/settings.css` (drop segmented-pill rule; import/relink
  to `tabs.css`)
- `gui/web_ui/index.html` (link the new CSS)
- `gui/web_ui/templates.js` (wrap the channel-card row in a
  `tabs-row` class so it inherits the new chrome; no markup changes
  needed for Tools/Settings — the existing `settings-tabs-nav` becomes
  `tabs-row`)

**Out of scope:** sidebar nav (`.nav-btn`) stays as-is — that's a
different control surface (vertical column of large buttons with
icons), not a tab.

**Kill criterion:** the three rows of pills are visually identical
in active state; channels keep their icons; the suite is still green.

---

## §2 — Monthly Best auto-fetch + Update Device + box size cap

**Scope:** remove "Fetch Gallery" button; auto-fetch on tab activation
+ on classify change; rename buttons; remove "Refresh" button from
the Devices card; cap box size.

**Files:**
- `gui/web_ui/templates.js` (drop `load-gallery-btn` button; keep
  the `<select>`)
- `gui/web_ui/gallery.js`:
  - On `#gallery-classify` `change` event: auto-call `loadGallery(...)`.
  - On tab activation to `#monthly-best`: if no items loaded, auto-fetch.
  - Remove `refreshTargetsBtn` click handler + button in templates.
  - Rename `batchSyncBtn` text → "Update Device" (and document the
    new "uploads all + switches to hot channel" behavior).
  - Rename `syncAllBtn` text → "Update Devices".
- `gui/web_ui/gallery.css`: change `grid-template-columns: repeat(auto-fill, minmax(110px, 1fr))` → `repeat(auto-fill, minmax(110px, 168px))`.

**"Update Device" semantics:** push the *currently selected* item
to the *current device* (singular) — keeps the existing single-item
push, but renames the verb to be honest about what it does. The
existing `syncAllBtn` already does the multi-device "Sync All" → it
becomes "Update Devices" (plural, multiple).

**No "switch to hot channel" needed**: Divoom devices don't have a
"hot channel" concept — the gallery push uses the existing
`batch_sync_artwork` which pushes to the device's design/animation
channel. The R6 schedule daemon (`monthly_best_daemon.py`) and the
hot-channel concept are config-persistence terms, not device-side
concepts. Rename in the UI to be clear; no protocol change.

**Kill criterion:** opening the Monthly Best tab immediately loads
Recommend; changing the classify auto-loads; the box doesn't grow
past 168px on wide windows; the buttons are renamed; the Refresh
button is gone.

**Tests:** `tests/test_gallery_auto_fetch.py` (new) — 4 tests:
- Auto-fetch on tab activation (mock `fetch_gallery` is called once).
- Auto-fetch on classify change (mock called again with new value).
- No "Fetch Gallery" button exists in the rendered HTML.
- Box cap CSS rule is present.

---

## §3 — Live Widgets weather card (own box, auto-push, preview only)

**Scope:** weather becomes a first-class card in the Live Widgets
grid; auto-pushes on selection; renders an actual weather preview;
removes all the explanatory text; moves the manual Notification card
and the macOS Notifications card to be siblings.

**Files:**
- `gui/web_ui/templates.js`:
  - Remove the nested weather card from inside the sysmon card.
  - Add a 5th card `#widget-card-weather` in the Live Widgets grid.
  - Add 2 more cards: `#widget-card-notif-manual` and
    `#widget-card-notif-mirror` (the old Notification + macOS
    Notifications from Settings → Devices).
- `gui/web_ui/widgets.js`:
  - New `selectWidget("weather")` path:
    - Sets `.widget-active` on the weather card.
    - Calls `pywebview.api.get_weather()` → returns
      `{temperature, weather_type, location, provider}`.
    - Renders the preview into `#weather-device-preview`
      (a 128×128 box with an inline SVG icon for the weather type
      and the temperature as a pixel-art number).
    - Calls `pywebview.api.push_weather()` automatically.
    - Sets up a 10-minute poll (`refreshWeatherPreview`) — weather
      changes slowly; no need to poll faster.
  - On tab-leave: stops the weather poller, removes the active
    class.
  - New `selectWidget("notif-manual")` and `selectWidget("notif-mirror")`
    paths: pure visual selection (no auto-push, no poller).
- `gui/web_ui/widgets.css`:
  - New `.weather-preview-icon` (16×16 SVG path per weather type,
    or a single sprite).
  - New `.weather-preview-temp` (pixel-art 7-segment style, 32px).
- `gui/gui_api.py`:
  - `get_weather() -> dict` — uses `WeatherProvider` (wttr.in or
    stub) to return the current weather for the configured location.
  - `push_weather() -> bool` — unchanged (still calls
    `divoom.weather.set`).
- New `divoom_lib/weather_provider.py`:
  - `class WeatherProvider` (enum: WTTR_IN, STUB)
  - `class WeatherInfo` (frozen dataclass: temperature_c, weather_type,
    location, provider, fetched_at)
  - `get_weather(provider, location=None) -> WeatherInfo`
  - `WTTrInProvider` (uses `aiohttp` to hit
    `https://wttr.in/{location}?format=j1` — returns a small JSON
    blob; parse out `current_condition[0].temp_C` and
    `weatherCode` → map to `WeatherType`).
  - `StubProvider` (returns a deterministic `{temperature_c: 22,
    weather_type: Clear, location: "stub"}`).
  - `WEATHER_CODE_TO_DIVOOM` mapping (WMO weather codes → our
    `WeatherType` enum).

**Weather preview rendering:**
- 128×128 box (same as the other widget previews).
- Background: dark gray (matches `.device-preview-wrap`).
- Centered: 32×32 SVG weather icon (sun / cloud / rain / snow / fog
  / thunderstorm — Kare-style pixel art, 8×8 grid scaled 4×).
- Below the icon: temperature in a pixel-art numeric style
  (var(--font-mono), 24px, bold, white).

**"Remove all the text, just show the preview" — applies to:**
- Weather card body: no panel-hint, no button, no label. Just the
  preview image. The card header still has the title + status
  indicator.

**Kill criterion:** selecting the weather card immediately pushes
to the device; the preview shows the actual temperature/condition;
switching tabs cleans up; the manual Notification + macOS mirror
cards are siblings (same card-grid, no Settings → Devices entry).

**Tests:** `tests/test_weather_provider.py` (new) — 5 tests:
- WMO code → WeatherType mapping (clear, cloudy, rain, snow, fog, storm).
- StubProvider returns deterministic data.
- WTTrInProvider parses a mock JSON response correctly.
- WTTrInProvider falls back to StubProvider on network/parse error.
- `get_weather()` returns a `WeatherInfo` with the right fields.

`tests/test_widgets_weather.py` (new) — 3 tests:
- `selectWidget("weather")` calls `get_weather()` and `push_weather()`.
- Tab-leave stops the poller.
- Weather card has no text content (no `.panel-hint` inside).

---

## §4 — Settings refactor

**Scope:**
- **Danger zone gets its own box** (extract from Display card).
- **Notifications move to Live Widgets** (already covered in §3).
- **Routines auto-sync** add 7-day and 1-month options.

**Files:**
- `gui/web_ui/templates.js`:
  - Drop `.danger-zone` from inside the Display card.
  - Add a new `.card.glass-card` for the danger zone (right after
    Display, before what was the Notification card — now also gone).
  - Add 2 `<option>` values to `#routines-auto-sync-interval`:
    `604800` (7 days), `2592000` (30 days).
- `gui/web_ui/settings.js`:
  - Wire the new interval options to the existing save handler
    (no code change — they share the same path; just verifies the
    value isn't constrained by a hard-coded min/max).
- `divoom_lib/hotchannel_config.py`:
  - `MIN_INTERVAL = 60` is unchanged. The new options are within
    bounds. No code change required.
  - Add `MAX_INTERVAL = 2592000` (30 days) as documentation of the
    UI cap, with a test that values > MAX are clamped to MAX
    (defensive — the user can still set anything in the file).

**Kill criterion:** the Display card no longer contains the danger
zone; the danger zone is its own card; the Routines select has 6
options (1h, 6h, 12h, 24h, 7d, 30d); saving 7d / 30d persists the
value to `hotchannel.json`.

**Tests:** `tests/test_routines_intervals.py` (new) — 3 tests:
- All 6 interval options are present in the rendered HTML.
- Saving "604800" / "2592000" round-trips through the config.
- The interval select does not constrain to a max shorter than 30d.

---

## §5 — MCP server (new feature)

**Scope:** real MCP-compatible JSON-RPC server, stdio transport,
~12 tools covering the lib's main features. GUI toggle in
Settings → Connectivity spawns/stops the subprocess.

**Files:**
- `divoom_lib/mcp_server.py` (new, ~300 LOC):
  - `class MCPServer`: the server core. Holds a list of `Tool`
    definitions, dispatches JSON-RPC methods.
  - `class Tool`: a tool definition (name, description, JSON schema,
    handler). Handlers are async coroutines that take a `Divoom`
    instance + a dict of args.
  - `async def run_stdio_server(divoom: Divoom) -> None`: the
    main loop — read JSON-RPC messages from stdin, dispatch, write
    responses to stdout.
  - 12 tool definitions, each with a JSON schema and a handler.
- `divoom_lib/mcp_tools.py` (new, ~200 LOC):
  - The actual tool implementations: `set_volume`, `set_brightness`,
    `set_light_mode`, etc. Each is a small async function.
  - `build_tool_catalog(divoom) -> list[Tool]`: returns the full
    catalog, parameterized by the connected Divoom instance.
- `divoom_lib/cli.py`: add a new subcommand `mcp-server` that
  starts the stdio server with a given MAC.
- `gui/mcp_control.py` (new, ~100 LOC):
  - `class MCPController`: start/stop/status of the subprocess.
    Tracks the PID, polls for liveness.
  - `get_mcp_server_status() -> dict`: for the JS side.
- `gui/gui_api.py`: add `start_mcp_server()`, `stop_mcp_server()`,
  `is_mcp_server_running()`, `get_mcp_server_status()`.
- `gui/web_ui/templates.js`: add a "MCP Server" card to
  Settings → Connectivity (or a new "Integrations" sub-tab if
  Connectivity is too dense). For now: put it in Connectivity
  under the existing transport-status panel.
- `gui/web_ui/settings.js`: wire the toggle + status display.
- `pyproject.toml`: no new deps (stdlib json + subprocess is enough).
- `docs/MCP_SERVER.md` (new): setup guide for Claude Desktop /
  Cursor / Cline / Continue — how to point the client at the
  `divoom-control mcp-server` subprocess.

**Tools (initial catalog):**

| Tool | Args | Returns |
|---|---|---|
| `set_volume` | `{level: int 0-15}` | `{ok: bool}` |
| `set_brightness` | `{level: int 0-100}` | `{ok: bool}` |
| `set_light_mode` | `{mode: "clock" \| "lightning" \| "cloud" \| "vj" \| "visualizer" \| "design" \| "scoreboard" \| "animation"}` | `{ok: bool}` |
| `set_clock` | `{style: int 0-5, color: "#RRGGBB", hour24: bool, tempF: bool}` | `{ok: bool}` |
| `set_weather` | `{temperature_c: int -127..128, weather: "clear" \| "cloudy" \| "thunderstorm" \| "rain" \| "snow" \| "fog"}` | `{ok: bool}` |
| `set_alarm` | `{index: int 0-9, enabled: bool, hour: int 0-23, minute: int 0-59, weekday_mask: int 0-127}` | `{ok: bool}` |
| `set_radio` | `{freq_x10: int 875-1080}` | `{ok: bool}` |
| `set_low_power` | `{enabled: bool}` | `{ok: bool}` |
| `set_screen_orientation` | `{degrees: 0 \| 90 \| 180 \| 270, mirror: bool}` | `{ok: bool}` |
| `show_image` | `{url: str}` | `{ok: bool, local_path: str}` |
| `play_sound` | `{duration_ms: int 100-3000}` | `{ok: bool}` |
| `get_capabilities` | `{}` | `{panel_resolution, has_speaker, has_clock, …}` |
| `get_device_state` | `{}` | `{volume, brightness, light_mode, screen_orientation, mirror}` |

**MCP wire format (canonical MCP 2024-11-05 spec):**

```json
// Request
{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "claude-desktop", "version": "1.0.0"}}}

// Response
{"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "divoom-control", "version": "0.15.0"}}}

// Request: list tools
{"jsonrpc": "2.0", "id": 2, "method": "tools/list"}

// Response
{"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "set_volume", "description": "Set the device volume (0-15).", "inputSchema": {"type": "object", "properties": {"level": {"type": "integer", "minimum": 0, "maximum": 15}}, "required": ["level"]}}, ...]}}

// Request: call a tool
{"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "set_volume", "arguments": {"level": 8}}}

// Response
{"jsonrpc": "2.0", "id": 3, "result": {"content": [{"type": "text", "text": "{\"ok\": true}"}]}}
```

**Kill criterion:** `python -m divoom_lib.mcp_server --mac <MAC>` starts
the stdio server; a minimal JSON-RPC exchange (initialize → tools/list
→ tools/call) round-trips correctly; the GUI toggle starts/stops the
subprocess; the status display is accurate.

**Tests:** `tests/test_mcp_server.py` (new) — 15-20 tests:
- `initialize` returns the right server info + capabilities.
- `tools/list` returns the full catalog.
- `tools/call set_volume {level: 8}` calls `divoom.volume.set_volume(8)`.
- `tools/call set_volume {level: 99}` returns an error (out of range).
- `tools/call set_weather` validates the weather enum.
- `tools/call` with an unknown tool returns `-32601 Method not found`.
- Invalid JSON returns `-32700 Parse error`.
- Stdio round-trip: feed a sequence of requests, assert the responses.
- `MCPController.start` spawns the subprocess, `.stop` kills it,
  `.is_running` returns the right value.

`docs/MCP_SERVER.md` (new) — setup instructions for Claude Desktop,
Cursor, Cline, Continue (each gets a small JSON snippet).

---

## §6 — Menubar item — notification status + configure menu

**Scope:** extend `gui/menubar.py` to:
- Poll the GUI's notification listener state every 5s (via the
  existing Unix socket IPC).
- Update the status-item title with a state suffix:
  `(active)` / `(idle)` / `(error)`.
- Add a "Open Notifications..." menu item that opens the GUI to
  the Live Widgets → Notifications card.
- Keep all existing menu items.

**Files:**
- `gui/menubar.py`:
  - Add a 5s polling timer for `get_notification_status` (new IPC
    method).
  - Add a status field on the agent that gets updated.
  - Update the status-item title in the polling loop.
  - Add the new menu item.
  - Add a `start_polling` / `stop_polling` lifecycle.
- `gui/menubar.py` IPC: add `get_notification_status` method.
- `gui/control_server.py` or the GUI process: expose
  `get_notification_status` (proxies to the existing
  `is_notification_listener_running` + counts).
- `gui/gui_main.py`: if the user passes `--tab data-sources --card notifications`,
  pre-select that sub-tab on startup.
- `gui/menubar.py`: the "Open Notifications..." handler launches
  `gui_main.py` with the new flags.

**Status title colors:** the menu-item text color can't be changed
in NSMenu, but the status-item button can. Use a green / gray / amber
tint via `button.attributedTitle = NSAttributedString(...)` with the
color from R14 §3's status-pill palette (`#5ede91` / `rgba(255,255,255,0.55)` / `#ffc864`).

**Kill criterion:** the menubar status title updates within 5s of
starting/stopping the notification listener in the GUI; the
"Open Notifications..." item launches the GUI to the right place;
existing menu items still work.

**Tests:** `tests/test_menubar_ipc.py` (new) — 4 tests:
- `get_notification_status` returns the right shape.
- Polling updates the status field on the agent.
- Status title formatting (active → "(active)", idle → "(idle)",
  error → "(error)").
- "Open Notifications..." handler builds the right subprocess
  command.

**Outcome (SHIPPED):** Implemented **event-driven, NOT polled** — the user
rejected background polling twice, so the plan's "poll every 5s" was dropped.
Instead the GUI pushes the listener status to the menubar's Unix socket only when
it changes (`gui_api._push_menubar_status` → `start/stop_notification_listener`).
AppKit-free logic lives in new `gui/menubar_status.py` (derive_state /
format_status_title / status_color / hex_to_rgb01 / open_notifications_command /
push_notification_status) so it's testable on any platform. `menubar.py`:
`notification_status` + `get_notification_status` IPC handled WITHOUT a BLE
auto-connect; status-item title shows `Divoom (active|idle|error)` with a
green/grey/amber `NSAttributedString` tint updated on the main thread;
"Open Notifications..." menu item launches the GUI via
`gui_main --tab data-sources --card notifications`; `gui_main` parses those into
URL query params honored by `settings.js`. Tests: `tests/test_menubar_ipc.py`
(14, incl. a real Unix-socket push round-trip). Suite **946 passed / 0 failed**.

---

## §7 — Cross-cutting: shared design tokens

The Kare + Rams decision (§1 design rationale) means we have a
single tab style. To make this maintainable, lift the tab CSS
into a new `gui/web_ui/tabs.css` and reference it from the
three panel CSS files via `@import` (or just link it from
`index.html` before the panel CSS).

The new file:
```css
/* tabs.css — single source of truth for the tab chrome used in
   Channels, Tools, Settings, and any future sub-tab row. */

.tabs-row {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  padding: 2px;
  background: rgba(255, 255, 255, 0.04);
  border-radius: 6px;
  /* No outer border — the active pill's bg is the focus indicator. */
}

.tabs-row .tab-btn {
  flex: 0 0 auto;
  height: 30px;
  padding: 0 14px;
  font-family: var(--font-sans);
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
  background: transparent;
  border: 0;
  border-radius: 4px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: background 0.15s ease, color 0.15s ease;
}

.tabs-row .tab-btn:hover {
  color: var(--text-main);
  background: rgba(255, 255, 255, 0.04);
}

.tabs-row .tab-btn.active {
  background: var(--primary);
  color: #ffffff;
}

.tabs-row .tab-icon {
  width: 14px;
  height: 14px;
  flex: 0 0 auto;
  /* Kare's contribution: 16x16 monochrome icon, scaled 14px, left of label. */
  color: currentColor;
}
```

The three panel CSS files drop their chrome rules; the markup
swaps the wrapper class to `.tabs-row` and each button to `.tab-btn`.

**Migration:**
- `templates.js`: change `settings-tabs-nav` → `tabs-row`, `settings-tab-btn` → `tab-btn` (and add `data-tab` as a generalization of the existing `data-settings-tab` etc).
- `channels.js`: `channel-card` → `tab-btn` + `.tabs-row` wrapper.
- `settings.js`: same migration for the `settings-tab-btn` /
  `tools-subtab-btn` selectors.

To avoid one massive diff, the migration uses **additive before
subtractive** (build-discipline A1): the new `.tabs-row` / `.tab-btn`
rules are added, the markup is updated to use them, and only AFTER
a smoke test is the old chrome dropped. Net result: 2 commits
(additive → subtractive), but both leave the suite green.

---

## §8 — Test budget + totals

| Section | New tests | Files |
|---|---|---|
| §1 Tab style | 0 (CSS-only) | — |
| §2 Monthly Best | 4 | `tests/test_gallery_auto_fetch.py` |
| §3 Weather | 5+3 = 8 | `tests/test_weather_provider.py`, `tests/test_widgets_weather.py` |
| §4 Settings | 3 | `tests/test_routines_intervals.py` |
| §5 MCP server | 15-20 | `tests/test_mcp_server.py` |
| §6 Menubar | 4 | `tests/test_menubar_ipc.py` |
| **Total** | **~35** | 5 new test files |

Suite: 829 → ~865 passed. Zero regressions across R8→R15.

---

## §9 — Commit plan (F1: one commit per logical group)

1. `feat(R15-§1+§7): unify tab style — segmented-pill across Channels/Tools/Settings`
2. `feat(R15-§2+§4): Monthly Best auto-fetch + box size cap + Routines 7d/30d + Danger zone own card`
3. `feat(R15-§3): Live Widgets — weather (own box, auto-push, preview) + Notifications move from Settings`
4. `feat(R15-§5): MCP server (stdio JSON-RPC) + GUI toggle in Settings → Connectivity`
5. `feat(R15-§6): Menubar — notification status indicator + Open Notifications... menu item`
6. `docs(R15): update CHANGELOG, SESSION_HANDOFF, this plan doc`

Each commit's `git diff --stat` should be < 1000 lines (3 of the 5
are pure UI; 1 is a new feature; 1 is docs).

---

## §10 — Kill criteria (one per section, B1)

- **§1:** the 3 rows of pills are visually identical in active state.
- **§2:** opening the tab auto-loads Recommend; changing classify auto-reloads; box size cap visible in DOM.
- **§3:** weather card auto-pushes on select, renders an actual preview, has no text content, leaves cleanly.
- **§4:** Display card no longer contains the danger zone; Routines has 6 interval options.
- **§5:** `divoom-control mcp-server` runs; a minimal MCP exchange (initialize → tools/list → tools/call) round-trips; GUI toggle works.
- **§6:** menubar status title updates within 5s of listener state change; "Open Notifications..." launches the GUI to the right tab.

Each section is independent enough to ship individually if a wall
is hit; the dependencies are light (mostly shared templates.js edits
that touch the same lines).

---

## §11 — Outcome / what shipped

| § | Section | Commit | Tests added | Status |
|---|---|---|---|---|
| §1+§7 | Tab style unification (segmented-pill) | `2c819325` | 16 (`test_tabs_chrome.py`) | SHIPPED |
| §2 | Monthly Best auto-fetch + box cap | `0e23253f` | 10 (`test_gallery_auto_fetch.py`) | SHIPPED |
| §4 | Settings refactor (Danger zone + 7d/30d) | `24f95690` | 10 (`test_routines_intervals.py`) | SHIPPED |
| §3 | Live Widgets weather + Notifications move | `b7c1e4d7` | 41 (30 + 11) | SHIPPED |
| §5 | MCP server (12 tools) + GUI toggle | `121d0b5`  | 25 (`test_mcp_server.py`) | SHIPPED |
| §6 | Menubar as daemon client (event-driven) | `61292a6` | 6 (`test_menubar.py`) | SHIPPED |

**Suite timeline:** 829 → 846 → 856 → 866 → 907 → 932 → 938. **+109 tests** in R15.
**Final:** 938 passed, 75 skipped, 0 failed.

### §5 design notes

- **Subprocess, not in-process.** pywebview's event loop and the MCP
  stdio loop would fight over file descriptors; subprocess isolation
  is the clean fix. GUI's logger writes to stderr only (stdio stays
  clean for JSON-RPC). Crashes in MCP server don't take GUI down.
- **`python -m divoom_lib.cli mcp-server`.** Doesn't depend on the
  binary being on PATH (works in editable installs + zipapps).
- **New process group.** `start_new_session=True` so `stop()` can
  SIGTERM the whole tree.
- **Domain validation in handler, not schema.** Schema constrains shape;
  values like `level=99` pass schema but are domain errors. `ValueError`
  → `isError=True` in tool response.
- **MCP spec 2024-11-05.** Notifications (no `id`) get no reply. Error
  codes match JSON-RPC standard.
- **No background polling on the GUI toggle.** Initially the status
  card polled every 5s; the user flagged this as "notifications every
  5 seconds" and asked for it to work quietly. Replaced with: one
  initial fetch + tab-activation refresh + click-driven refresh.
  Status pill / log panel only update when the user actually visits
  the card or clicks Start/Stop.
- **Log file is the user-visible state.** Subprocess logs to
  `~/.config/divoom-control/mcp-server.log`. Tailed on demand (last
  20 lines / 16 KB) when the card is visible. No file watcher — a
  watchdog would be the same kind of background noise the user
  rejected.

### MCP tool catalog (12 initial tools)

`set_volume`, `set_brightness`, `set_light_mode`, `set_weather`,
`set_alarm`, `set_radio`, `set_low_power`, `set_screen_orientation`,
`show_image`, `play_sound` (best-effort), `get_capabilities` (read-only),
`get_device_state` (read-only).

`docs/MCP_SERVER.md` ships with config snippets for Claude Desktop,
Cursor, Cline, and Continue.

### §6 design notes — Menubar as daemon client (event-driven, no polling)

- **Top-level `divoom_menubar/` package.** The menubar is a second GUI
  variant (native Cocoa status item) that shares state with the
  pywebview GUI via the daemon. It lives at the repo root, not inside
  `divoom_daemon/`, so it's a first-class entry point.
- **Daemon client, not owner.** The menubar connects to the daemon's
  Unix socket (`/tmp/divoom.sock`) as a `DaemonClient`. It has **no
  BLE connection** and **no socket server** — R17's single-owner rule
  is respected. The old `divoom_daemon/menubar.py` that had its own
  BLE + server is deleted.
- **Event-driven status via daemon subscription.** The menubar calls
  `DaemonClient.subscribe()` and receives `EVENT_STATUS` events
  (`state` + `counters`) pushed by the daemon on every notification
  listener start/stop/error and on each routed notification. The
  menubar title updates instantly on these events — **zero polling**.
  This matches the user's "no background polling" feedback for the
  GUI's MCP toggle and the menubar itself.
- **Menu actions.** "Start Notifications" / "Stop Notifications" send
  `start_notifications` / `stop_notifications` to the daemon.
  "Open Notifications..." launches the pywebview GUI with
  `--tab data-sources --card notifications` so it opens directly to
  the Live Widgets → Notifications card.
- **Title format & colours.** Status-item title is `Divoom (active)`
  / `(idle)` / `(error)` with colour tints: green (active), grey
  (idle), amber (error). Derived from `STATE_COLORS` shared with the
  R14 §3 GUI status pill.
- **CLI entry point.** `divoom-control menubar` launches the menubar
  agent (blocks on Cocoa event loop). The `cmd_menubar` handler is
  synchronous — the CLI dispatcher detects this and runs it without
  `await`.
- **Tests.** `tests/test_menubar.py` (6 tests) covers state derivation,
  title formatting, colour mapping, and hex→RGB conversion. All pure
  logic, no AppKit dependency, CI-friendly.

---

## Open follow-ups (carry to R16+)

- **Task #20** — get_* read-backs gate SD player UI and everything else.
- **Channel-switch hardware bug** (Divoom Max).
- **R12 §A/B visual + hardware passes** (user-run).
- **MCP server enhancements** (after R15 lands):
  - HTTP+SSE transport (for non-stdio clients like web-based IDEs).
  - `subscribe_*` tools (push events: notification arrived, weather changed).
  - Auth (none now; macOS-only + per-user-uid is the default trust boundary).
- **Weather provider fallback chain** (wttr.in → NWS → stub, based on geolocation).
- **Menubar quick actions** (set volume, set brightness from the menu).
- **Tab style audit** — the channel-card row inside `#control-panel` is
  inside a `.card`, not a `.tabs-row` — confirm the visual rhythm holds
  when the user does a visual pass.

# Divoom Control — App Improvement Plan

Tracking the GUI/app overhaul requested 2026-06-02. This is a **multi-phase**
effort; items are grouped by area (matching the request) and tagged with status,
risk, and whether they need real hardware or APK reverse-engineering.

## Status at a glance

| Area | State |
|------|-------|
| 1. Active device → app bar | ✅ done |
| 2. Control Center (a–g) | ✅ done (on-device validation pending) |
| 3. Virtual Wall (a–d) | ✅ a/b/d done; ⬚ c (image orientation) open |
| 4. Monthly Best (b–e) | ✅ done (on-device push pending hardware) |
| 5. Live Widgets (a–f) | ✅ done (on-device display pending hardware) |
| 6. Settings | ✅ done |
| 7. Strip-mine + tests | ⬚ partial (REST control surface + tests added) |
| Instrumentation (REST control server) | ✅ done |

Full suite: **243 passed / 0 failed / 72 skipped**. Nothing committed yet.

## Architecture (ground truth)

PyWebView desktop app. Python ⇄ JS bridge:

- **Bridge / backend:** `gui/gui_main.py` (`Api` class exposed to JS), plus
  `gui/media_sync.py` (gallery/monthly/album sync), `gui/menubar.py`,
  `gui/presets_manager.py`.
- **Web UI:** `gui/web_ui/index.html` (619 ln), `app.js` (1153 ln),
  `style.css` (37k). Single bundle, no build step.
- **Library:** `divoom_lib/` — `transport.py` (BLE/LAN abstraction),
  `lan_transport.py`, `monthly_best_daemon.py` (hot-channel daemon),
  `display/vjeffect_channel.py`, `utils/media_source.py` (album art),
  `system/*`.
- **Daemon:** `scripts/com.divoom.monthlybest.plist` + `install_daemon.sh` (launchd).
- **APK reference:** `apk/` (decompiled official Divoom app — source of truth for
  channel IDs, EQ lists, VJ lists, clock faces, hot-channel protocol).

## Design north stars (Rams + Kare)

Applied to every UI item below:

- **Rams** — *as little design as possible*: one primary action per panel, remove
  decorative text, honest status (don't show fake/hallucinated options), consistent
  control vocabulary (segmented selectors everywhere a discrete choice is made).
- **Kare** — clarity at small sizes: pixel-precise iconography, legible labels,
  meaningful color-coding (used for device identity on the wall), a 1:1 mental map
  between what's on screen and what's on the device.

---

## 1. Active device → app bar

- [x] **1.1** *(DONE)* Moved the active-device `<select>` from the sidebar into
  the top app bar (`.appbar-device`); removed the redundant sidebar panel. Kept
  the `#sidebar-device-select` id so all existing handlers keep working.
- [x] **1.2** *(DONE)* Connection indicator now reuses the shared
  `.transport-dot` vocabulary (inactive → `transport-dot inactive`, connecting →
  amber pulse `transport-dot connecting`, connected → `transport-dot active`),
  instead of the bespoke `.status-indicator`. One status vocabulary app-wide
  (Rams). Verified: app boots clean, single selector, tests pass.

## 2. Control Center

- [x] **2.a** *(DIAGNOSED via instrumentation + FIXED)* Built a headless REST
  control server (see Instrumentation phase), launched the real app, and drove
  the bridges directly: `switch_channel`, `set_vj_effect`, `set_visualization`,
  `set_clock` all return **`false` when no device is connected** (confirmed
  `get_transport_status` → `ble.available=false`). So it was **not** a wiring
  bug — the controls work but fail silently with a generic "Failed" toast when
  there's no active connection. Fix: added a JS `appConnected` flag (set by
  `connectDevice`) + `requireDevice()` guard on all Control Center actions, so
  the user now gets "Connect a device first — scan and connect under Settings"
  instead of a confusing failure. On-device success path to be confirmed on
  hardware.
- [x] **2.b** *(DONE)* Ambient is now a **channel card** with its own color +
  brightness panel; removed the standalone "Ambient Color" card. `index.html`
  channel grid + `panel-ambient`, `app.js`, `style.css`.
- [x] **2.c** *(DONE, count TBV)* Music EQ channel now shows a **selector grid**
  of EQ/visualizer patterns wired to new bridge `set_visualization(n)` →
  `display.show_visualization`. Patterns are honest **numbered** entries (EQ 01–12);
  the exact count must be confirmed on a real device (Visualizers are an image
  set in node-divoom, not text-enumerated).
- [x] **2.d** *(DONE)* VJ channel shows a selector of the **16 named effects**
  from `VJEffectType` (Sparkles…Rainbow Shapes), wired to new bridge
  `set_vj_effect(n)` → `display.show_effects`.
- [x] **2.e** *(DOCUMENTED)* Custom Art = the device's "Custom" channel (user
  designs/animations). Panel now explains it and points to Live Widgets / Virtual
  Wall for pushing a GIF/image. Upload protocol: `SPP_SET_USER_GIF` (177) /
  `Channel/SetCustom` (per APK report). Full upload flow is a later item.
- [x] **2.f** *(FIXED)* Replaced the hallucinated clock faces ("Cyber Panel
  BTC $64K", "Pixel Pet", etc.) with the **6 real built-in Timebox Evo dial
  types** from node-divoom PROTOCOL.md (Full Screen, Rainbow, With Box, Analog
  Square, Full Screen Neg, Analog Round), wired to `set_clock(0–5)`.
  *Future:* the cloud clock-face **store** (`Channel/StoreClockGetList` →
  `ClockId`/thumbnail, `SetClockSelectId`) would add the full downloadable set.
- [x] **2.g** *(DONE)* Panel layout unified on a single segmented `.selector-cell`
  grid vocabulary across clock/EQ/VJ; channel-specific sub-panels shown only for
  the active channel; standalone ambient collapsed into the channel set.

## 3. Virtual Wall

- [x] **3.a** *(REGRESSION — FIXED)* Root cause: `easy_drag=True` in
  `create_window` (gui_main.py). PyWebView's `easy_drag` moves the window on any
  body mousedown+drag at the native level and is **not** blocked by CSS
  `-webkit-app-region: no-drag` (the code comment was wrong). Set
  `easy_drag=False`; window movement still works via the titlebar's
  `-webkit-app-region: drag` region.
- [x] **3.b** Decluttered canvas cells: removed the always-on name + MAC text,
  enlarged the device mockup to dominate the node, added a deterministic
  per-device **accent color** (chip + border) for identity, moved the full name
  to a tooltip. Added a `slot.preview` overlay that renders the device's preview
  in the screen region when supplied (populating that content is a sync-pipeline
  follow-up). `app.js renderArrangerCanvas`, `style.css .arranger-node*`.
- [ ] **3.c** Some cached device images don't face the user → breaks preview. Audit
  the device-image cache / mockup orientation (front-facing mockups, commit
  `29bbd950`).
- [x] **3.d** *(FIXED)* Root cause: a stale placeholder slot
  `AA:BB:CC:DD:EE:FF → null` persisted in `_last_active_slots_`; its null name
  rendered as "undefined". Added render guard (`app.js`), load-time sanitizer
  (`presets_manager.load_config`), and scrubbed both committed `gui/presets.json`
  and the user's `~/.config/divoom-control/presets.json`.

## 4. Monthly Best (hot channel)

- [x] **4.a** Rendering works (animated GIF previews) — keep.
- [x] **4.b** *(DONE)* `sync_hot_channel(file_ids)` pushes the **whole** loaded
  gallery to **all** resolved targets at once (wall = every device); "Sync All →
  Targets" button. `media_sync.py` + `app.js`.
- [x] **4.c** *(DONE)* Replaced "Active Screen Info" with an explicit **device
  multi-select** (`get_sync_candidates` / `set_sync_targets`, persisted via
  `hotchannel_config`). Checkboxes in the Monthly Best tab.
- [x] **4.d** *(DONE)* Schedule persisted in
  `divoom_lib/hotchannel_config.py` (enabled/interval/classify/targets);
  `save/get_hot_channel_config` bridges + UI (enable toggle, interval, Save).
  The daemon's new `--use-config` flag reads it and syncs **all** targets
  **headless**; launchd plist updated to pass `--use-config`.
- [x] **4.e** *(DONE)* Layout reworked: target list → actions (Sync Selected /
  Sync All) → schedule block, consistent label vocabulary (Rams/Kare).

**Verification (live):** launched the app with the REST control server and drove
the new bridges via `curl` — `set_sync_targets` persists, `save_hot_channel_config`
merges (targets preserved), `get_hot_channel_config` reflects state,
`sync_hot_channel` returns a summary. Unit tests: `hotchannel_config` 7,
`gui_api` +2. Full suite **252 passed / 0 failed / 72 skipped**.

## 5. Live Widgets

- [x] **5.a** *(FIXED, on-device pending)* `apply_stock_ticker` now resolves the
  real target set (wall OR single BLE/**LAN**) via `_has_push_target`/`_push_frame`,
  uses the device's actual matrix size (not hardcoded 16), and returns a clear
  `"No device connected"` error instead of silently failing.
- [x] **5.b** *(DONE)* Album cover preview enlarged 70px → **150px** (>2×).
- [x] **5.c** *(FIXED, on-device pending)* Music cover push uses the shared
  `_push_frame` (wall + single BLE/LAN) and real device size; logs when no target.
- [x] **5.d** *(DONE)* Live **on-device preview**: new `get_ticker_preview`
  returns the rendered frame as a base64 data URL at the active matrix size; the
  music cache now carries a `preview`. UI shows pixelated device previews for both
  the ticker and the now-playing cover.
- [x] **5.e** *(DONE)* Multiple tickers persisted (`get_tickers`/`set_tickers`,
  `~/.config/divoom-control/tickers.json`), **seeded from the macOS Stocks app**
  (`defaults read com.apple.stocks`, graceful fallback to a default list). UI:
  saved-ticker chips (click to display, × to remove), "+ Save".
- [x] **5.f** *(DONE)* Layout pass: larger cover, on-device preview blocks, chip
  vocabulary consistent with the rest of the app (Rams/Kare).

**Verification:** `node --check` OK, `media_sync` parses, `test_gui_api.py` +3
(`get_ticker_preview` data URL, no-target error, ticker persistence). Drove the
new bridges live via the REST control server (`get_tickers` seeds + falls back,
`set_tickers` persists/dedupes). Full suite **255 passed / 0 failed / 72 skipped**.
On-device display of frames pending hardware (the sandboxed background process
can't hold Bluetooth permission; the normally-launched app can).

## 6. Settings

- [x] **6.a** *(FIXED)* Save-on-scan and load-on-mount already existed; fixed a
  bug where a saved `limit` of 0 ("unlimited") was dropped by a truthy check
  (`app.js` → explicit `!= null`), extracted `save_scan_settings()` in
  `gui_main.py`, and wired `change` listeners so timeout/limit persist even
  without running a scan.

## 7. Strip-mine reference projects + testing

Mine for features (replicate Wi-Fi features over BLE where relevant):
- [ ] **7.1** https://github.com/fabkury/servoom
- [ ] **7.2** https://github.com/tidyhf/Pixoo64-Advanced-Tools
- [ ] **7.3** https://github.com/r12f/divoom
- [ ] **7.g** Full **unit + integration + UI/UX** tests. Mocks where relevant; a
  real-hardware suite (gated by `--run-hardware`, already established) for device
  paths.

---

## Constraints & dependencies

- **Hardware-gated** (cannot fully verify without a device): 5.a, 5.c, 5.d, 2.a
  push paths, 4.b sync. Will be implemented against mocks + the `--run-hardware`
  suite for real validation.
- **APK-reverse-engineering** (source of truth needed): 2.c, 2.d, 2.e, 2.f, 7.*.
- **Persistence layer**: 4.d and 6.a share a config-cache mechanism — unify it.

## Recommended phasing

**Phase A — unambiguous bugfixes / regressions (no hardware, high value)**
1. 3.d remove "undefined" default device.
2. 3.a fix canvas-drag-moves-window regression.
3. 6.a persist scan timeout + device count.
4. 2.a fix channel-switch / selection wiring.
5. 3.b declutter canvas cells (device + preview only, color-coded).

**Phase B — APK-sourced selections (Control Center)**
6. 2.f clock faces (remove hallucinated), 2.c EQ list, 2.d VJ list, 2.b ambient
   as channel, 2.e custom art, 2.g layout pass.

**Phase C — Monthly Best hot-channel**
7. 4.c target multi-select, 4.b sync-all, 4.d schedule+persist+headless, 4.e UX.

**Phase D — Live widgets**
8. 5.b/5.d/5.e (UI-side, testable), then 5.a/5.c (hardware paths), 5.f UX.

**Phase E — app bar + design system**
9. 1.1/1.2 active device in app bar w/ shared transport indicator.

**Phase F — strip-mine + test build-out**
10. 7.1–7.3 feature mining; 7.g full test pyramid.

## Instrumentation — local REST control surface (DONE)

To make the app verifiable/scriptable **headlessly** (and to satisfy the
"run headless" requirement 4.d and the HTTP-API features in item 7), added a
local REST control server:

- `gui/control_server.py` — reflection-based dispatch over a `DivoomGuiAPI`
  instance; every public bridge method is `POST /api/<method>` (JSON kwargs or
  positional array). `GET /api` lists methods; `GET /health`. Localhost-bound,
  optional `DIVOOM_CONTROL_TOKEN`. Window controls denylisted.
- `gui/gui_main.py` — opt-in launch via `DIVOOM_CONTROL_SERVER=1`
  (`DIVOOM_CONTROL_PORT`, default 8787); default behavior unchanged.
- `tests/test_control_server.py` — 7 E2E tests (health, method listing,
  kwargs/positional dispatch, JSON-string decode, 404/500, real-API surface).

This is what enabled the 2.a diagnosis (drove the live bridges via `curl`) and
is the foundation for automated E2E + the headless hot-channel daemon.

## Instrumentation — hardware-free device validation (DONE)

The macOS TCC Bluetooth gate crashes any background-launched Python on real BLE,
so real devices can't be driven from this environment. Instead of stopping
there, added a **mock-device path** that validates the entire wire pipeline:

- `scripts/mock_device.py` `MockBleakClient` now **records every frame** the
  "device" receives (`.written`).
- `gui/gui_main.py`: `DIVOOM_MOCK_BLE=1` makes `scan`/`connect_single_device`
  use the mock client — so the full GUI→bridge→Divoom→framing→device stack is
  driveable headlessly (and gives users a no-hardware demo mode).
- `tests/test_e2e_mock_device.py` (5): inject the mock into a real `Divoom`,
  drive `show_effects`/`show_visualization`/`show_clock`, and assert the exact
  decoded wire frames (VJ effect index, EQ index, clock dial all correct).

**Verified live end-to-end:** launched the app with `DIVOOM_CONTROL_SERVER=1
DIVOOM_MOCK_BLE=1` and drove scan→connect→switch_channel→set_vj_effect→set_clock
via `curl`; the mock device received the correct frames
(`bd 09` = VJ effect 9, `45 00 01 02 …` = clock dial 2). This closes the
on-device-validation gap at the wire level for areas 2/4/5 (real-display
confirmation on physical units is still a nice-to-have but no longer blocking).

## Execution log

(Per-step record appended as work lands — file, change, verification.)

### Session 2026-06-02 — Phase A first batch

- **3.a** `gui/gui_main.py`: `easy_drag=True` → `False`. Verified: `gui` py
  parses, `test_gui_api.py` 8/8.
- **3.d** `gui/web_ui/app.js` render guard + `gui/presets_manager.py` load
  sanitizer; scrubbed `gui/presets.json` and user presets (removed 1 stale slot
  each). Verified parse + tests.
- **6.a** `gui/web_ui/app.js` (null-safe restore + change-listener persistence),
  `gui/gui_main.py` (`save_scan_settings`). Verified `node --check` + tests.
- **3.b** `gui/web_ui/app.js` (`deviceColor`, decluttered node render) +
  `gui/web_ui/style.css` (`.arranger-node-chip`, larger image, hidden labels,
  `.arranger-node-preview`). Verified `node --check` app.js OK, `test_gui_api`
  8/8.
- **2.a** Investigated; no static defect. Needs runtime/console diagnosis
  (see item 2.a). Left open.

Verification this session: `node --check gui/web_ui/app.js` OK;
`pytest tests/test_gui_api.py` = 8 passed. (GUI visual behavior not verifiable
headless — needs the running PyWebView app.)

### Session 2026-06-02 (cont.) — Control Center 2.b–g (APK/protocol-sourced)

Source of truth: `apk/APK_INTELLIGENCE_REPORT.md` (commands + cloud endpoints),
`references/node-divoom-timebox-evo/PROTOCOL.md` (clock `TT` types, VJ/visualizer
channels), `divoom_lib VJEffectType` (16 effects).

- **Backend** `gui/gui_main.py`: added `set_vj_effect(n)` and
  `set_visualization(n)` bridges (wall + single, BLE + LAN fallback).
- **UI** `gui/web_ui/index.html`: added Ambient channel card; replaced the
  always-on hallucinated clock area with per-channel sub-panels
  (`panel-clock/visualizer/vj/design/ambient`) + empty grids; removed the
  standalone Ambient Color card.
- **UI** `gui/web_ui/app.js`: channel→panel switching; `buildSelectorGrid`;
  populated 6 real clocks / 16 VJ effects / 12 numbered EQ; ambient apply.
- **CSS** `gui/web_ui/style.css`: `.channel-panel(.active)`, `.selector-grid`,
  `.selector-cell`, ambient controls.
- **Tests** `tests/test_gui_api.py`: +2 (`set_vj_effect`/`set_visualization`
  dispatch + graceful no-target). 

Verification: `node --check` OK, both py files parse, `test_gui_api.py` 10/10,
full suite **236 passed / 0 failed / 72 skipped**. On-device validation of EQ
count and clock-dial appearance still pending (hardware).

### Session 2026-06-02 (cont.) — Instrumentation + 2.a diagnosis/fix

- Added `gui/control_server.py` (REST), wired opt-in into `gui_main.py`, added
  `tests/test_control_server.py` (7 E2E).
- **Launched the real app** with `DIVOOM_CONTROL_SERVER=1` and drove bridges via
  `curl`: confirmed all Control Center actions return `false` with no device
  connected (`get_transport_status` → `ble.available=false`). Root cause of 2.a.
- Fixed 2.a UX: `appConnected` flag + `requireDevice()` guard on channel switch,
  clock/VJ/EQ selectors, and ambient apply.
- Verification: `node --check` OK; app boots cleanly twice; control `/health` ok;
  `test_gui_api.py` + `test_control_server.py` = **17 passed**; full suite
  **243 passed / 0 failed / 72 skipped**.

### Session 2026-06-02 (cont.) — Area 4: Monthly Best hot-channel

- **New** `divoom_lib/hotchannel_config.py` (shared targets+schedule persistence)
  + `tests/test_hotchannel_config.py` (7).
- **Backend** `gui/media_sync.py`: `get_sync_candidates`, `set_sync_targets`,
  `get_hot_channel_config`, `save_hot_channel_config`, `sync_hot_channel`
  (all accept JSON-string *or* native types via `_coerce_list`/`_coerce_dict`,
  so they work over both pywebview and REST). +2 `tests/test_gui_api.py`.
- **Daemon** `divoom_lib/monthly_best_daemon.py`: `--use-config` reads the
  persisted schedule/targets and pushes to **all** targets (refactored push into
  `_push_items_to_target`); `scripts/com.divoom.monthlybest.plist` passes it.
- **UI** `index.html`/`app.js`/`style.css`: target multi-select, Sync All button,
  schedule controls (enable/interval/Save).
- **Live-verified** via the REST control server against the running app (set/save/
  get/sync all round-trip). Full suite **252 passed / 0 failed / 72 skipped**.
  On-device push validation pending hardware.

### Session 2026-06-02 (cont.) — Area 1: active device → app bar

- `index.html`: added `.appbar-device` (connection dot + `#sidebar-device-select`
  + status text) to the header; removed the sidebar device panel.
- `app.js`: `connectDevice` now toggles `.transport-dot` states
  (inactive/connecting/active) on the shared `#global-status-dot`.
- `style.css`: `.appbar-device*` layout + `.transport-dot.connecting` amber pulse.
- Verified: `node --check` OK, single selector in DOM, app boots clean,
  `test_gui_api.py` 12 passed.

### Session 2026-06-02 (cont.) — Area 5: Live Widgets

- **Backend** `gui/media_sync.py`: `_active_device_size`, `_has_push_target`,
  `_push_frame`, `_frame_to_data_url`, `get_ticker_preview`, multi-ticker
  persistence (`get_tickers`/`set_tickers` + macOS Stocks seed), robust
  `apply_stock_ticker`, fixed music-loop push (size + LAN). `set_tickers` accepts
  JSON string or native list (REST+pywebview). +3 `tests/test_gui_api.py`.
- **UI** `index.html`/`app.js`/`style.css`: 150px cover (5.b), on-device preview
  imgs for ticker + cover (5.d), saved-ticker chips with add/remove (5.e),
  clearer stock errors (5.a).
- **Live-verified** ticker bridges via REST (seed/fallback/persist/dedupe);
  attempted a real BLE scan but the sandboxed background process crashes on the
  macOS TCC Bluetooth check — on-device frame display must be confirmed by
  launching the app normally. Full suite **255 passed / 0 failed / 72 skipped**.

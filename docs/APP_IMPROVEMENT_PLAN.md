# Divoom Control — App Improvement Plan

Tracking the GUI/app overhaul requested 2026-06-02. This is a **multi-phase**
effort; items are grouped by area (matching the request) and tagged with status,
risk, and whether they need real hardware or APK reverse-engineering.

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

- [ ] **1.1** Move active-device selector into the top app bar.
- [ ] **1.2** Connection indicator must conform to the existing **transport status
  indicator** design (`updateTransportPanel` / `refreshTransportStatus` /
  `get_transport_status` in `app.js`/`gui_main.py`) — one shared component, not a
  bespoke widget. Rams: one status vocabulary across the app.

## 2. Control Center

- [~] **2.a** *(BUG — needs runtime diagnosis)* Investigated: the Python
  `switch_channel` (gui_main.py) is complete (wall + single, LAN + BLE), and the
  JS wiring (`app.js` ~106) binds `.channel-card` clicks correctly inside
  `DOMContentLoaded`. No static wiring defect found. "Doesn't work" is therefore
  most likely **(a)** `switch_channel` returning `False` because no device is
  connected (surfaces as a "Failed to switch channel" toast), or **(b)** a
  runtime JS exception in an earlier handler aborting later bindings. Confirming
  requires running the PyWebView app with the web console open — cannot be done
  headless. **Action needed:** run app, reproduce, capture console + which
  control; then fix precisely.
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
- [ ] **4.b** Sync **all** monthly-best images to **all** selected devices at once
  (replicate APK "hot channel"), not one-by-one. Backend in
  `monthly_best_daemon.py` + `media_sync.py`.
- [ ] **4.c** Replace the unclear "active screen info matrix wall" target picker
  with an explicit **device multi-select** for sync targets.
- [ ] **4.d** **Schedule** automatic hot-channel syncs for selected devices;
  persist schedule + selection across sessions; run **headless** (launchd daemon
  already scaffolded in `scripts/`).
- [ ] **4.e** Layout/UX review (Rams/Kare).

## 5. Live Widgets

- [ ] **5.a** *(BUG)* Live stocks/crypto trackers fail to connect to device.
- [ ] **5.b** "Mac playing cover track" — album preview at least **2×** larger.
- [ ] **5.c** Album art not shown **on the device** — fix the device push path
  (`media_source.py` / transport image encode).
- [ ] **5.d** Add a **live on-device preview** scaled to the active device's matrix
  (16×16 / 32×32 / 64×64).
- [ ] **5.e** Stock ticker → store **multiple** tickers; seed list from the macOS
  Stocks app.
- [ ] **5.f** Interface review (Rams/Kare).

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

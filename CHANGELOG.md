# Changelog

All notable changes to divoom-control are documented here. The
format is loosely Keep-A-Changelog; entries are grouped by
shipped milestone (per the project planning docs).

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

- 2 live-device verifications (4-quadrant, half-green/red) ✓.
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

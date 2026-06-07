# Planned work — bugs, fixes, deferred investigations _(2026-06-05)_

> **Single source of truth** for known bugs, fix plans, and deferred
> investigations. Replaces the three superseded plan files
> (`VISUAL_REGRESSION_FIX_PLAN.md`, `GUI_CLEANUP_FOLLOWUP_PLAN.md`,
> `GUI_CLEANUP_ROUND2_PLAN.md`).
>
> **Author's note** (D2: document the decision, not just the code):
> consolidation happened after three rounds of plan documents had
> accumulated overlapping context, completed items, and lingering
> open questions. Anything you find missing here is missing on
> purpose — add it.

---

## 0. Status overview

| Round | Scope                                  | Status      | Tests before → after |
|------:|----------------------------------------|-------------|----------------------|
|   –   | Prior sessions (iOS-LE framing, system device bug, brightness parser, image-push KeyError) | Done | – |
| 0     | Visual regressions (8 issues)          | **Done**    | 290 → 306            |
| 1     | Hands-on followup (6 issues)           | **Done**    | 306 → 308            |
| 2     | Round 2 (4 + 1 + 1)                    | **Partial** | 308 → 313 → 354      |
|   –   | C downscaler (Phase 10, moved out of `gui/`) | **Done** | 313 → 354 (+38)   |
| 3.1   | Cover upload (palette encoder, 0x44→0x49 routing) | **Done** | 354 → 408 (+54: +27 encoder, +1 time kwarg, -2 deleted make_framepart/chunks, +28 wall canvas; net per-file encoder: +26) |

**Current baseline:** 408 passed / 73 skipped / 0 failed.
**Goal of this document:** every future hand-off starts from here.

---

## 1. Design lens — Kare + Rams combined

Per user (2026-06-04): **Kare = Susan Kare** (Mac bitmap icon designer,
Chicago font, "Solitaire" cursor) and **Deiter = Dieter Rams** (Braun
industrial designer of the 10 principles). The GUI follows their
**combined** principles — applied at every fix.

### Susan Kare principles
- **Pixel-perfect clarity** — render at the native grid, no
  anti-aliasing on device previews.
- **Honest representation** — an icon/preview looks like what the
  thing actually does, not what we wish it did.
- **Restraint** — the fewest pixels possible to convey meaning.
- **Friendly** — approachable, not corporate.
- **Platform-native** — use the OS's own controls where they exist
  (e.g. the macOS color picker is correct, don't reinvent it).

### Dieter Rams' 10 principles
1. **Innovative** — don't copy, find the right idea.
2. **Useful** — every element earns its place.
3. **Aesthetic** — minimal, not barren.
4. **Understandable** — self-explanatory.
5. **Unobtrusive** — chrome stays out of the user's way.
6. **Honest** — no fake animations, no fake states.
7. **Long-lasting** — survives the next refactor.
8. **Consistent** — the same idea looks the same in every place.
9. (Environmentally friendly — N/A for UI.)
10. **As little design as possible** — "less but better".

### How this lens changes the fixes

| Fix | Kare/Rams verdict |
|---|---|
| Custom Art button pinned to bottom | Rams #4 Understandable + #10 As little as possible. The flex layout is the right tool; no decoration needed. |
| Color-picker `<div>` → `<label>` | **Kare: use platform-native** — `<label>` is the HTML-native click-to-open-input pattern. Don't reinvent with JS. |
| Ambient previews | **Rams #6 Honest** — previews must show what the device actually does. **Kare: pixel-perfect, restraint, no animation that doesn't exist on the device.** |
| Monthly Best empty space | **Rams #10 As little as possible** — fill empty space with content, not decoration. |
| Live widgets broken | **Rams #4 Understandable** — if a widget fails, surface it honestly. |
| Device selector move | **Rams #5 Unobtrusive** — speaker/res aren't selector concerns. The image becomes the main visual. |

### Decision: 10 favorites (override of Rams #10)

Per user (2026-06-04): **10 last-selected as favorites**, not the
Kare/Rams-consensus 5. Kare/Rams are guides, not laws (D4: explicit
no-action as output). Layout is a single row of 6 fixed swatches + 1
color-picker circle + 10-favorites row. No decorative bloat.

---

## 2. Done — Round 0 (visual regression, 8 issues)

| #   | Issue                                  | Fix                                                                                      | Test added                       |
|----:|----------------------------------------|------------------------------------------------------------------------------------------|----------------------------------|
| 1   | Window drag regression                 | Move handler to `app.js`, `clientX/Y`, `preventDefault`, document delegation              | `test_gui_drag_instrumented.py`  |
| 2.1 | Custom Art button always visible       | `flex:1; min-height:0` on scroll container, button pinned                                | DOM assertion in drag test       |
| 2.2 | Color-picker wrapper click delegation  | `<div>` → `<label>`; remove `channels.js` delegation block                                | covered by drag test             |
| 2.3 | Ambient layout per Kare/Rams           | Resolved in §1 above                                                                      | –                                |
| 3   | Ambient preview fixes (5 modes)        | Love=solid-color pulse; Plants=16x16 pixel grid; Sleeping=green; No-mosquito=orange 40%  | (visual review only)             |
| 4   | Monthly best empty space               | `flex:1; min-height:0` chain on gallery card                                             | drag test asserts parent         |
| 5   | Live widgets — multiple regressions     | Visualizer removed; sysmon = colored bars; `bindCardSelection` re-attached                | `test_live_widgets_diagnostic.py`|
| 6   | Device selector sidebar                | Speaker/res moved to Settings "Connectivity" sub-tab; preview image enlarged to 120×120   | –                                |
| 7   | Cleanup                                | Dead `.appbar-device` CSS removed; `appbarSelect` → `sidebarDeviceSelect`                | –                                |
| 8   | Phasing (A–E)                          | All phases A–E executed                                                                   | –                                |

**Lesson (D3, document the dead-ends):** the original Round 0 plan had
6 open questions Q1–Q6. All resolved 2026-06-04 22:54 EDT. The
"ambient layout" question is the only one that survives as a long-
term design question; Kare/Rams have given a concrete proposal
(§1 above) and the user has overridden it with 10 favorites.

---

## 3. Done — Round 1 (6 hands-on issues)

| #   | Issue                                       | Fix                                                                                          | Test                              |
|----:|---------------------------------------------|----------------------------------------------------------------------------------------------|-----------------------------------|
| 1a  | Love (pulse) is rainbow, not pulse          | Solid-color pulse 12s linear `love-color-cycle`; Kare tiny heart accent                       | Drag test                          |
| 1b  | Color picker not visually distinct          | Dashed border + "+" SVG icon; click opens picker                                            | Drag test                          |
| 2   | Window drag jumps between two positions     | rAF-throttle in `widgets.js`; final-mousemove-only semantics                                 | Drag test                          |
| 3   | Gallery only "NeonSkull"                    | `load_cached_gallery` rebuilds from `cache_gallery/` when stale; 233 items recovered         | `test_gallery_cache_rebuild.py`    |
| 4a  | Live cover art — visualiser eating space    | Removed `toggleAudioVisualizer`, polling loop, `.audio-bars` element; enlarged cover area    | Live widgets diagnostic            |
| 4b  | Live cover art — not uploaded/displayed     | Manual 144×144 push button in Live Widgets music card                                         | Live widgets diagnostic            |
| 5   | Stocks preview outside container bounds     | `min-width: 0` on flex children of stocks card layout                                        | Drag test                          |
| 6a  | System monitor — white/gray preview         | Removed white panel; 3 labeled bars (CPU/MEM/BAT) with device-matched colors                 | Live widgets diagnostic            |
| 6b  | System monitor — not on device              | Removed duplicate `const sysmonDisplayBtn` (real bug; not the channel-switch problem)        | Live widgets diagnostic            |

---

## 4. Done — Round 2 (4 + 1 + 1)

| #   | Issue                                       | Status     | Fix / Where                                                                                       |
|----:|---------------------------------------------|------------|---------------------------------------------------------------------------------------------------|
| 1   | Custom art `chunksize` AttributeError        | **Done**   | `Divoom.__init__` sets `self.chunksize = kwargs.get('chunksize', models.DEFAULT_CHUNK_SIZE)`. 3 tests in `test_divoom_chunksize.py`. |
| 4   | C downscaler (LANCZOS3) for cover art       | **Done**   | `divoom_lib/native_src/downsample.c` + `divoom_lib/native/downscaler.py` + `scripts/build_libdivoom.sh`. 38 byte-exact tests + perf smoke. Moved out of `gui/` per user ("it's a library function, not a gui-only function"). |
| –   | C downscaler byte-exact to PIL              | **Done**   | 24/24 hand-picked cases, 500/500 random stress. INT32 fixed-point, sign-aware weight rounding, full pre-mult/resample/un-premult in C, NEON intrinsics with `vmlaq_s32`/`vsetq_lane_s32`. |

---

# Planned work — bugs, fixes, deferred investigations _(2026-06-06)_

## 5. Status of Round 2 (updated 2026-06-06, post-session)

| #   | Item                            | Status               | Where                                                                           |
|----:|---------------------------------|----------------------|---------------------------------------------------------------------------------|
| 0   | Window drag: native pywebview drag-region + #1820 patch (idempotent) | **Done** | Re-enabled `pywebview-drag-region` class on `<header class="integrated-appbar">` in `gui/web_ui/index.html:24` (the JS side of pywebview's bundled drag mechanism). Removed the broken custom drag handler from `gui/web_ui/app.js` and the broken `drag_window` from `gui/gui_api.py`. Applied the upstream-recommended monkey-patch from issue #1820 in `gui/gui_main.py:111-128` (gated by `_pywebview_1820_bug_present()` in `gui/gui_main.py:27-66`, which inspects the source of `webview.platforms.cocoa.BrowserView.move` and only applies the patch when the literal token `self.screen.origin.x + x` is present — the same token the upstream fix necessarily removes). 6 regression tests in `tests/test_gui_drag_instrumented.py`: 4 static guards (drag-region class present, patch applied without the bug term in its body, no custom JS handler, no custom Python `drag_window`) + 2 detection-contract canaries (the helper agrees with the actual pywebview source, and the helper correctly returns False when the source is monkey-patched into the upstream-recommended fix shape). Behavioral test deliberately omitted (pywebview's `customize.js` is only injected by `webview.start()`, not when serving HTML over plain HTTP, so headless Playwright cannot exercise the drag). Full history of 4 attempts (1 OS-native + 1 custom + 2 hybrid) and why each failed is in `docs/DRAG_FIX_HISTORY.md`. Self-deactivation contract: when pywebview ships #1820, the detection helper returns False, the patch is skipped (logged: "pywebview #1820 already fixed upstream; skipping patch"), and the entire block in `gui_main.py:96-128` can be deleted. Manual test required on real macOS window to confirm the drag still works end-to-end. |
| 1   | Custom art `chunksize`          | **Done** (prior)     | `Divoom.__init__` sets `self.chunksize`.                                        |
| 1b  | Push to Device button sticky    | **Done** (regression test) | Layout was already correct from Round 0/1; added 2 Playwright tests in `tests/test_monthly_best_button_visible.py`. |
| 2/3 | Cover art push silently fails   | **In progress**      | Root cause narrowed: BLE write race (macOS CoreBluetooth reports `is_connected=True` while writes fail with "disconnected"). |
| 3a  | `display_image` wrapper         | **Done**             | `divoom_lib/display/__init__.py:display_image` (alias for `show_image` + optional `wait_for_display` poll). 8 unit tests. |
| 4   | C downscaler (LANCZOS3)         | **Done** (prior)     | `divoom_lib/native_src/downsample.c` + Python wrapper.                          |
| –   | C perf 4-pixel NEON deinterleave | **In progress**      | Hypothesis (a) from §6 confirmed by `sample` profile (99% in inner loop). Implementation pending. |
| –   | Bonus: BLE start_notify guard   | **Done**             | `divoom_lib/ble_transport.py:_notifications_started` flag (surfaced by diagnostic). |
| –   | Bonus: drag regression test rewrite | **Done**         | `tests/test_gui_drag_instrumented.py` rewritten as 5 tests: 4 static guards (appbar has NO `pywebview-drag-region`, `gui_main.py` patches `BrowserView.move`, `app.js` has custom drag handler, `gui_api.py` has `drag_window`) + 1 Playwright **behavioral** test (`test_drag_handler_is_wired` — loads real `gui/web_ui/index.html` in headless Chromium, stubs `pywebview`, simulates drag, asserts `drag_window` was called with non-zero deltas and the cumulative sum matches the displacement). The behavioral test would fail if the JS drag handler were removed or replaced with the broken `pywebview-drag-region` mechanism. |
- **Fix (rejected approach):** custom Python `drag_window` micro-debounce
  in `gui_api.py` + JS rAF throttle in `app.js`. Round 4 Round 5 ship
  was correct in theory (16ms Timer, anchor chain) but the user reported
  "jumps around like crazy" in manual testing. The root cause was not
  Python-side coalescing — it was a complete miss of the built-in
  pywebview drag-region mechanism.
- **Fix (rejected, Round 6 first attempt):** delegate to pywebview's
  bundled `pywebview-drag-region` mechanism
  (`webview/js/customize.js:69-89` + `pywebviewMoveWindow`). User
  reported "window is now not draggable at all" — root cause was
  TWO bugs in pywebview 6.2.1:
  1. **Coordinate double-count in `cocoa.py:811-815`** (upstream
     issue #1820, May 2026): `BrowserView.move` adds
     `self.screen.origin.x` to the X coordinate the JS sends.
     On multi-monitor setups this jumps the window off-screen
     mid-drag. On single-monitor it's a no-op because
     `screen.origin = (0, 0)`, BUT...
  2. **Contract mismatch in `customize.js:44-48`**: JS sends
     deltas (`ev.screenX - initialX`) to a Python method that
     expects absolute coordinates (`window.move` calls
     `setFrameTopLeftPoint_`). Even on single-monitor, this
     teleports the window to near `(delta, flipped_y)` on every
     mousemove. We had additionally set
     `DRAG_REGION_DIRECT_TARGET_ONLY=True`, which made
     child-element clicks (the vast majority of user clicks on
     the appbar) fail the `.matches()` check entirely, hence
     "not draggable at all".
- **Final fix (Round 6 second attempt):**
  1. Removed `pywebview-drag-region` class and
     `DRAG_REGION_DIRECT_TARGET_ONLY=True`.
  2. Restored the simple custom drag handler in `app.js`
     (mousedown on `.integrated-appbar` → mousemove sends
     cumulative deltas → mouseup ends). Skips clicks on
     `button, select, input, .no-drag` so window controls
     still work.
  3. Restored `gui/gui_api.py:drag_window(dx, dy)` — simplest
     possible: `self.window.move(self.window.x + dx,
     self.window.y + dy)`. No debounce, no anchor chain.
  4. Applied the upstream-recommended monkey-patch from
     issue #1820 in `gui/gui_main.py:53-77`: drops the
     `self.screen.origin.x` term from `BrowserView.move` on
     macOS. This fixes the multi-monitor off-screen jump bug.
     The patch is a no-op on single-monitor (where
     `screen.origin = (0, 0)`).
  5. Added a **behavioral regression test**
     (`test_drag_handler_is_wired`) that loads the real
     `gui/web_ui/index.html` in headless Chromium, stubs the
     pywebview bridge, simulates a drag, and asserts the
     `drag_window` calls were made with non-zero deltas and
     the cumulative sum matches the requested displacement.
- **Rams #4 understandable:** user perceives one smooth follow.
- **Verification (still required):** manual drag in the real
  app. The custom handler matches the previous simple version
  (commit `4b515edc`) that worked in earlier rounds; the
  multi-monitor patch from #1820 fixes the upstream bug that
  would have caused off-screen jumps if the user is on
  multi-monitor.

### 5.2 #1b — "Push to Device" button always visible

- **Symptom:** button pushed out of view when gallery has many items.
- **Target layout:**
  ```
  +----- card body -----+
  | last-5-selected     |  ← always visible
  |---------------------|
  | gallery grid        |  ← flex:1, scrollable
  | (scrollable)        |
  |---------------------|
  | Push to Device      |  ← always visible, sticky bottom
  +---------------------+
  ```
- **Fix:** card body `display: flex; flex-direction: column`;
  `.gallery-grid` `flex: 1; overflow-y: auto; min-height: 0`;
  button `flex-shrink: 0`.
- **Risk:** layout change could cascade to gallery and monthly-best
  card; test all 3.

### 5.3 #2 — Cover art push silently succeeds, device doesn't display

- **Symptom:** `push_music_cover_now` returns `success: true`, log
  shows the bytes, but device screen does not update.
- **Suspected root cause:** `_music_sync_loop` (`gui/media_sync.py`)
  calls `_push_frame(out_path, size)` → `dev.display.show_image(...)`
  which sends image bytes only. It does NOT switch the device to the
  design/custom-art channel. Device stays on the previous channel
  (clock/visualizer); new image is buffered but not displayed.
- **Fix:** before pushing, send channel-switch command. Channel IDs
  (verify against protocol): design=0x05, clock=0x03, visualizer=0x04.
  Add an explicit `switch_to_channel(0x05)` before the image push.
- **Verification:** push cover art → device displays it.
- **Status:** requires live device test.
- **Updated 2026-06-05 (per `docs/PLANNING_ROUND2_CONTINUATION.md §9.2`):**
  the original "channel switch missing" premise is **wrong** — the
  library's `divoom_lib/display/__init__.py:75-101 show_image()`
  *already* calls `show_design()` (line 77) before pushing image
  bytes. The channel switch (0x45 0x05 = SOUND_USER mode) is on
  the wire. The actual root cause of the silent push failure is
  a BLE write race: macOS CoreBluetooth reports `is_connected=True`
  while writes return "disconnected". The current retry logic
  doesn't recover from this state. **Fix in progress** in
  `divoom_lib/ble_transport.py` — see `PLANNING_ROUND2_CONTINUATION.md §12.1`.

### 5.4 #3 — Live widgets not displayed on device (same root cause as #2)

- **Symptom:** cover art, stocks, and sysmon all push without errors
  but device doesn't update.
- **Same fix as #2:** wrap every `_push_frame` call in a
  `switch_to_design_channel` first. The existing
  `trigger_notification` (line 309: "Push pixel art frame (which
  switches BLE device to design channel automatically)") already
  shows the pattern — apply it to music/stocks/sysmon.
- **Research items:**
  - find the existing channel-switch helper
  - verify the design channel ID
  - add regression test asserting channel-switch sent before image push
- **Status:** requires live device test.
- **Risk:** wrong channel ID will leave the device in a broken state.

### 5.5 #3a — `display_custom_image` library wrapper (user-suggested)

- **Idea (user, 2026-06-05):** once #2/#3 work end-to-end, wrap the
  full sequence in `divoom.display_custom_image(file_path)`:
  1. switch to design channel (`0x45 0x05 ...`)
  2. open the image (any format PIL supports)
  3. encode for device's active matrix size
  4. push image bytes via `0x44`
  5. (optional) confirm by re-reading `get work mode`
- **Why:** future widget dev (notifications, weather, calendar,
  custom dashboards) all need the same 3-step dance. Current 3
  callers (`_push_frame` × cover art / stocks / sysmon) each do the
  dance slightly differently and miss steps.
- **API sketch (Kare: minimal, Rams #4 understandable):**
  ```python
  async def display_custom_image(
      self, file_path: str, size: int | None = None,
      wait_for_display: bool = False,
  ) -> bool
  ```
  - `size=None` auto-detects the device's matrix size
  - `wait_for_display=True` polls `get work mode` after push
- **Migration:** refactor `_push_frame` to call this wrapper, then
  music/stocks/sysmon all get the same hardening for free.
- **Status:** implement after #2 is fixed and verified manually.

---

## 5.5. Done — Round 3 §1 (cover upload, 2026-06-05)

### Learning 1: Timoo image push MUST use 0x49, NOT 0x44 (corrected 2026-06-05)

**Original (incorrect) claim (Round 3 initial session):**
> "Timoo requires 0x49 for image display, NOT 0x44. 0x44 is a silent
> no-op on the animation channel."

**What was actually wrong (corrected after deeper investigation):**
The comment in `divoom_lib/models/commands.py` correctly said the
distinction was 0x44=image/0x49=animation, but the actual mapping
was `"set animation frame": 0x44` (WRONG — should be 0x49). The
"silent no-op" was a misreading of the live behavior.

**Actual finding:**
- `0x44` is the **single-frame static image** command. Body is one
  palette+indices block prefixed by `00 0A 0A 04`. The device renders
  the bytes that fit that single-frame static layout.
- `0x49` is the **multi-frame animation** command. Body is a sequence
  of `[LE u16 total_len][u8 packet_num][≤200 bytes chunk]` packets
  containing concatenated `AA LLLL TTTT RR NN COLORS PIXELS` blocks.
  The device auto-loops the animation.

**Bug:** `show_image` was wrapping the 0x49-format animation packet
in a 0x44 command. The device parsed the first frame's
`AA LLLL 000000 NN …` as a static image and silently discarded
subsequent frames. Single-frame "animations" worked by coincidence —
0x44 + first-frame bytes happens to parse as a valid static image.

**Fix applied (corrected this session):**
- `divoom_lib/models/commands.py:30` remapped
  `"set animation frame": 0x49`. Comment updated to clarify 0x44 vs
  0x49 semantics.
- `tests/test_e2e_mock_device.py::test_show_image_emits_0x44_frames`
  renamed to `test_show_image_emits_0x49_frames` and updated to
  assert 0x49.

**Multi-frame animation cycling: deferred to Round 4.** The 0x49 push
is correctly framed and the device ACKs it (response
`01 06 00 04 49 55 00 b0 00 02`, where `0x55` = ACK and `0xb0` is
status), but the device continues to display a previously-stored
custom animation instead of the one we just pushed. Tested:
- 0x49 upload + 0x6B (`drawing mul encode gif play`) → no cycle
- 0x49 upload + 0x6E 0x01 (`drawing ctrl movie play` start) → no cycle
- 0x6E 0x01 + 0x5C + 0x6E 0x01 → no cycle
- 0x6E 0x01 + 0x5C (raw concatenated frames) + 0x6B → no cycle
- Push a 32-frame Magic 9 .bin file from
  `~/.config/divoom-control/cache_gallery/` via 0x49 → no cycle
  (device ignored it)

Likely root cause: Timoo firmware expects a slot-selection command
(`SPP_SECOND_USE_USER_DEFINE_INDEX` = 23) before 0x49 push, OR the
device is paired via BT Classic with the cloud app and BLE push is
being ignored. **Requires Timoo firmware reverse-engineering or a
captured cloud-push trace to resolve.**

### Learning 2: RomRider wire format is byte-correct (with caveats)

After fixing the header (Round 3 fix-1: `LLLL = 7 + 3N + p`, not
`3N + p`; 3 zero bytes between LLLL and NN, not 2; animation TTTT
is little-endian, not big-endian; **animation packet header is
`[LE u16 total_len][u8 counter]`, NOT `[BE u16 total_len][BE u16
counter]`**), the wire bytes match the RomRider
`asDivoomMessage` output exactly. The format itself was correct;
only the header field semantics were off.

### Learning 3: Channel state check uses 0x46, not 0x13

- `0x13` (get work mode) returns a 20-byte payload where byte 0 is
  `0x00` (some internal state, not the channel).
- `0x46` (get light mode) returns a 20-byte payload where **byte 0
  is the current channel** (0x05 = Animation, 0x01 = Lightning, …).

The existing `system/device.py::get_work_mode` (command 0x06 in our
codebase, not 0x13) is a different query that does NOT return the
channel. Use 0x46 for "is the device on the animation channel?"
checks.

### Status
- 27 unit tests in `tests/test_divoom_image_encode.py` 
- 4 unit tests in `tests/test_image_processing.py` 
- 40 new parity tests in `tests/test_native_image_encoder.py` 
- 10 new perf tests in `tests/perf_image_encode.py` 
- 9 mock-device tests in `tests/test_e2e_mock_device.py` 
  (renamed `test_show_image_emits_0x44_frames` → `_0x49_frames`)
- 2 live-device verifications (4-quadrant, half-green/red) 
- C encoder shipped in `divoom_lib/native_src/image_encode.c` 
- C encoder byte-identical to Python encoder (40/40 parity tests) 
- `show_image` now uses 0x49 
- Test count: 448 passed, 73 skipped, 0 failed 

---

## 6. Deferred investigation — C downscaler perf gap

- **Observation:** C downscaler is consistently **0.3–0.8× of PIL's
  throughput** (i.e. 1.3–3.3× *slower*) across all 8 benchmark
  workloads. Output is byte-exact, so the gap is purely a
  performance issue.
- **Decision (B4, honest deferral):** ship the byte-exact
  implementation; investigate the perf gap as a follow-up. The
  perf test (`tests/perf_downsample.py::test_perf_smoke`) is now
  a **regression alarm** — fails only if native *unexpectedly*
  beats PIL (which would mean PIL regressed).
- **Two leading hypotheses:**
  1. **PIL processes 4 input pixels per NEON op** via `vld4q_u8`
     deinterleave; we currently process 1 pixel per op.
  2. **The clang auto-vectorizer prefers the 4-channel (RGBA)
     access pattern**; the 3-channel RGB loop gets a worse
     schedule.
- **Next step:** implement 4-pixels-at-a-time SIMD and re-benchmark.
  Hypothesis (a) is the more likely culprit and has a higher expected
  payoff.

---

## 7. Out of scope / parked (deliberate no-action)

Per D4: these are *explicit* no-action decisions, not forgotten items.

| Item                                            | Reason                                                                              |
|-------------------------------------------------|-------------------------------------------------------------------------------------|
| BT Classic SPP transport                        | Phase 8 already documented as blocked at the OS level (macOS Tahoe 26.5.1 SPP reconnection bug). Held as future-option. iOS-LE over BLE is the production path. |
| Divoom Cloud auth (`UserNewGuest failed: RC=10`)| API change on the server side; not user-config-fixable. App falls back to guest mode + on-disk `cache_gallery/`. |
| Bumble + USB BT dongle                           | Not deployable without hardware.                                                    |
| Wholesale ambient layout redesign               | Kare/Rams consensus proposal in §1; user has overridden Rams #10 with 10 favorites. |
| GUI framework migration (React/Vue/Svelte)      | Out of scope. Pure-JS, no build step.                                               |
| Arranger popup on mobile                        | Not a target platform.                                                              |
| Drag-direction cursor feedback                  | Not user-reported.                                                                  |
| Settings 5th sub-tab (beyond Connectivity)      | Not user-requested.                                                                 |

---

## 8. Verification protocol

After any fix ships:

1. `pytest -q` — expect **354+ passed / 0 failed / 72 skipped**.
2. **Manual smoke** (if the fix is GUI-visible): open the app and
   walk through the affected tab. For Round 2 #2/#3, this is a
   **mandatory** live-device test (per-item verification in §5).
3. New regression tests must pass and must be added for any new
   bug class (per A2: parity proof before cutover).

---

## 9. Risk register (consolidated, current)

- **#0** drag throttle change could regress previous fixes; keep
  the regression test green.
- **#1b** layout change could cascade to gallery + monthly-best;
  test all 3 card layouts.
- **#2/#3** channel-switching is protocol-sensitive; the wrong
  channel ID will leave the device in a broken state. Verify
  channel ID against `docs/DIVOOM_PROTOCOL_SUMMARY.md` before
  any push.
- **#3a** wrapper API is a public-API change; review against
  `DivoomProtocol` and `models` before shipping.
- **Perf investigation** is low-priority; the byte-exact path
  already meets functional requirements. If the gap becomes a
  user-visible regression (e.g. album collection >500 frames
  blocks the GUI), re-prioritize.

---

## 10. Files that reference this document

- `docs/CODE_REVIEW.md` — Phases 9 (Round 0+1 visual cleanup) and
  10 (C downscaler). These are the historical CHANGELOG of what
  shipped; the planned-work items live here, not there.
- `docs/DEVICE_VALIDATION_PLAN.md` — live device test plan for
  Round 2 #2/#3 verification.
- `docs/TESTING_STRATEGY.md` — overall test architecture.
- `docs/DIVOOM_PROTOCOL_SUMMARY.md` — channel IDs and command
  bytes referenced by §5.3 and §5.4.

---

## 11. Superseded documents (removed 2026-06-05)

These three plan files were the input to the consolidation. They
are no longer present in the tree:

- `docs/VISUAL_REGRESSION_FIX_PLAN.md` — Round 0 (all done).
- `docs/GUI_CLEANUP_FOLLOWUP_PLAN.md` — Round 1 (all done).
- `docs/GUI_CLEANUP_ROUND2_PLAN.md` — Round 2 (partial — pending
  items captured in §5).

If you need the original 8-issue Round 0 detail, the design-lens
discussion, or the Q1–Q6 question records, the surviving content
is in §1, §2, and §5 of this file. Anything not in those sections
was *resolved* and the resolution is in `docs/CODE_REVIEW.md`
Phase 9.

---

**End of plan. Next hand-off: live-device verification of the
drag fix (manual test protocol in
`docs/DRAG_FIX_HISTORY.md`), then §5.3 (#2 channel-switch)
followup on a real device, then §5.4 (#3) and §5.5 (#3a wrapper).**

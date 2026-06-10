# Round 40 — UI batch: bug fix, toggles everywhere, Device Settings sidebar, daemon lifecycle

User batch (2026-06-10), items numbered as given (item 7 was already shipped by
the user's own R37-R39 work — verify only). Implement, add test coverage, and
make GitHub CI green (`.github/workflows/tests.yml`, macos runner).

## §2 Custom art push fails: "cannot identify image file …gif" — BUG

`owner_art.custom_art_push._encode_file` handles magic 43 (extract GIF) and
magic 9/18/26 (`decode_cloud_to_gif`), then `Image.open`s the result. **Hot
files are format 0xAA** (and live in the same gallery cache the Custom Art
library shows), so assigning a hot tile to a slot downloads an 0xAA body that
falls through as "gif" → `Image.open` → `cannot identify image file`.
Fix: route `raw[0] == 0xAA` through the existing
`media_decoder.decode_hot_file_to_gif` (R39's preview decoder); include the
file_id in the error. Test: synthetic 0xAA + magic-9 + plain-GIF bodies through
a refactored, testable resolver (`divoom_lib/media_decoder.resolve_to_gif` —
one function that turns ANY known cloud download into GIF bytes; reused by
`sync_artwork` too, killing the duplicated branching).

## §3 Gallery previews → same size as hot channel

Hot tiles are fixed 112px (`.hot-preview-thumb`); gallery tiles fill a
responsive grid column (padding-bottom:100% box). Fix: cap the gallery grid's
column width at ~124px (`grid-template-columns: repeat(auto-fill, minmax(112px,
124px))` on `.gallery-grid`) so tiles render at hot-channel scale.

## §4 Toggle-ification (Live Widgets + Routines)

Reference pattern: Auto-Sync Gallery card header — `.card-header.flex-header`
with a `.switch` at the right edge.
- **Routines → Anniversary**: `#memorial-enabled` hc-toggle → `.switch` in the
  card header (right edge).
- **Widgets → System Monitor**: `#sysmon-live` ("Live (5s)") hc-toggle →
  header-right `.switch`; REMOVE `#sysmon-display-btn` ("Push to Device").
- **Widgets → Weather**: REMOVE "Push to Device" button; add header-right
  `.switch` `#weather-live` ("Live (15m)") — when on, push weather now and
  every 15 minutes (`setInterval`, cleared on toggle-off). Persist both live
  toggles in localStorage (`divoom.sysmonLive`, `divoom.weatherLive`).
- **Widgets → macOS Notifications**: `#macnotif-toggle` hc-toggle → `.switch`
  in the card header (right, next to the status pill). Label stays in-card as
  hint text.

## §5 Settings tabs always visible when scrolling

`#settings .tabs-section` → `position: sticky; top: 0; z-index: 20` +
opaque-ish background (the glass strip already has `var(--card-bg)`; add a
backdrop blur fallback). Sticky works because `.main-content` is the scroll
container and `.tabs-section` is a direct flow child of the section.

## §6 Routines → Schedule: name↔toggles gap

`renderSyncTargets` gives the style-tab pill `flex:1` so it stretches and
strands the switch far right. Fix: tabs `flex: 0 0 auto`, switch pushed right
via `margin-left: auto` — name + tabs sit together, switch stays at the edge.

## §7 Pixel Art sidebar item — ALREADY SHIPPED (verify only)

User's R37-R39 work added `data-tab="pixel-art"` + `templates_pixel_art.js`
(Custom Art / Gallery / Hot Channel tabs) and stubbed the old locations.
Round adds: preview-verify tab switching still works after this round's edits.

## §8 New sidebar item "Device Settings"

Move from Settings → Devices: the **Device Settings** card, **Display** card,
**Danger zone** card → new sidebar entry + section, ONE glass pane, in this
exact order (user wireframe):

1. `[Device name input | Save]`
2. `[12 / 24-hour]` — segmented pill (replaces toggle)
3. `[°C / °F]` — segmented pill (replaces toggle)
4. `[Normal / Low power]` — segmented pill (replaces toggle)
5. `[Auto power-off (minutes input) | Save]`
6. `[Orientation 0/90/180/270 segmented]` (existing pill moves here)
7. `[Mirror toggle]` (stays a switch)
8. `[Update device time]` (renamed from "Sync time from this Mac")
9. (spacer)
10. **Danger zone** (factory reset) at the bottom, inside the same pane,
    `danger-card` styling on the inner block.

Existing element IDs are KEPT (`hour24-toggle` semantics → segmented buttons
write the same API calls) so `settings_hardware.js` wiring changes stay small.
Sidebar nav button added after Routines; section template
`templates_device_settings.js`; Settings → Devices keeps scan/connect tables
only.

## §9 Connectivity: "Keep daemon alive when quitting dashboard" toggle

Default **OFF** = the dashboard, menubar, and daemon live and die together;
ON = independent lifecycles. Event-driven (no polling):

- Setting `keep_daemon_alive` in `config.ini [gui]`; toggle in Settings →
  Connectivity; `gui_api.get/set_keep_daemon_alive`.
- Daemon `_cmd_shutdown` now **broadcasts a `shutdown` event** to subscribers
  before exiting (it already has the event bus + a 0.25s grace).
- **Menubar**: already runs a daemon event subscription (`menubar_client`).
  On `shutdown` event: if NOT keep-alive → `NSApp.terminate` (menubar follows
  the system down). Menubar "Quit Divoom": if keep-alive → just exit the
  menubar (no daemon shutdown); else → daemon `shutdown()` (which broadcasts →
  dashboard + menubar close) then exit.
- **Dashboard**: `gui_main` starts a tiny subscriber thread; on `shutdown`
  event and NOT keep-alive → `window.destroy()`. On window close (after
  `webview.start()` returns): if NOT keep-alive → `client.shutdown()`.
- Tests: daemon broadcasts shutdown event (in-process daemon fixture);
  pure-logic tests for the menubar/dashboard decision helpers.

## Delivery checklist

- [ ] §2 fix + `resolve_to_gif` refactor + tests
- [ ] §3 gallery CSS cap
- [ ] §4 toggles (4 cards) + 15m weather interval + persistence
- [ ] §5 sticky settings tabs
- [ ] §6 schedule row spacing
- [ ] §7 verify pixel-art tab still healthy in preview
- [ ] §8 Device Settings sidebar section + segmented pills + JS rewire + tests
- [ ] §9 lifecycle events + toggle + tests
- [ ] Browser-preview verification of every UI item
- [ ] Full suite green locally → push → **watch GitHub CI to green** (gh tools)

## §outcome
_(fill as items land)_

# Round 32 — Monthly Best + Settings reorg + device selector

**Do not start until R31 is confirmed shipped.**

## A. Monthly Best panel → Settings → Routines

### A1. Move devices panel
Relocate the devices panel from Monthly Best to Settings → Routines.

### A2. Gallery auto-fetch on style change
- Dropdown for gallery type: on change, fetch immediately (no button press).
- Remember preferred gallery type per device — store in existing `.ini` files.
- On restart, load last-fetched images for each device's preferred style.
- Remove the "Fetch Gallery" button.
- Put the drop-down in the old button's location.

### A3. Multi-select gallery images
- Add selection squares (checkboxes) to each gallery image.
- Default: all images selected.
- Remove "Gallery" and "Divoom Cloud" header text.
- Add "Clear" and "Select All" buttons (style = virtual wall).
- Extend gallery panel to the right.

## B. Settings → Routines layout

New card:

```
[device selection dropdown | gallery style dropdown]
[enable auto-sync toggle (macOS-style toggle, not checkbox)]
[save schedule]
[sync devices now]
```

Auto-sync is handled by the daemon, not the app.

## C. Device selector improvements

### C1. Remove BLE prefix
User-facing names should be clean — strip the BLE prefix.

### C2. Device preview
Show a preview of what the device is currently displaying.

### C3. Dot-based device switching
Replace the dropdown with the connectivity indicator (four round dots),
color-coded per the existing scheme, placed inside the preview area.
Tooltips show device names. Quick switching between devices via dots.

## D. Channels → Text fix
Investigate and fix (currently broken — no details yet).

## E. Settings → Connectivity cleanup
Remove the connectivity and privacy explainer text.

---

## Outcome — SHIPPED (2026-06-08)

Suite **1094 passed / 75 skipped / 0 failed**. All of A–E landed across 6 commits.

### A — Monthly Best (templates_monthly_best.js, gallery.js, gallery.css, gallery_sync.py)
- **A1** done: devices/sync-targets panel removed from Monthly Best; it now lives
  in Settings → Routines. `.monthly-best-layout` is single-column (`1fr`).
- **A2** done: ghost Fetch button removed entirely; style change auto-fetches (it
  already did) and now also persists the style **per device** in `config.ini`
  `[gallery]` (`get_gallery_style`/`set_gallery_style` on `GallerySyncMixin`). On
  startup `loadPreferredGalleryStyle()` restores the active device's style before
  the cached gallery renders. Dropdown sits in the old button location.
- **A3** done: per-tile checkboxes (default all checked), Select All / Clear
  (virtual-wall buttons), removed "Gallery"/"Divoom Cloud" header chrome, gallery
  spans full width. "Update Device" pushes every checked image.

### B — Routines card (templates_settings.js, settings_features.js)
- New card: `[device select | gallery-style select]`, macOS-style toggle
  (`.switch`), interval select, the moved devices list, "Save Schedule" + "Sync
  devices now". Auto-sync remains daemon-driven (hotchannel_config.json).

### C — Device selector (index.html, sidebar.css, app_globals.js, app_init.js, gallery.js)
- **C1** done: stripped `BLE:`/`LAN:` prefix from the sidebar selector.
- **C2** done: preview shows the **last image pushed** by this app per device
  (user-confirmed interpretation — no live framebuffer readback exists).
  `setDevicePreview`/`restoreDevicePreview`, persisted in localStorage; wired from
  the gallery + custom-art push sites.
- **C3** done: dropdown replaced by per-device dots in their own glass pill
  **below** the preview (`renderDeviceDots`) — recycles the corner
  connectivity-dot chrome (`.corner-transports` pill + `.transport-dot`), per-device
  colors, wraps for >4 devices (no cap), rebuilds on every device add/remove
  (wired via `updateDeviceSelectorDropdown` + `syncArrangerToPython`). Tooltipped,
  click-to-switch; `<select>` kept hidden as canonical state.

### D — Channels → Text fix (divoom_gui/api/lighting.py)
- Root cause: the 0x87 LPWA "set light phone word attr" sequence does not render
  on the Pixoo-class LED matrices (confirmed against hass-divoom + futpib, which
  both render text to image frames). `push_text` now renders the text with our
  bitmap font onto a device-sized canvas and pushes via `display.show_image()`.
  **Static image only** — `speed`/`effect_style` are accepted but unused;
  scrolling-frame animation is the follow-up. **Needs hardware verification.**

### E — Connectivity cleanup (templates_settings.js, settings.css)
- Removed the Connectivity & Privacy legend markup + `.connectivity-legend*` CSS.

### Post-R32 follow-ups (user feedback, same session)
- **Dots in a glass pill below the preview** (index.html, sidebar.css, app_globals.js):
  moved out of the preview overlay; recycles the corner connectivity-dot chrome
  (`.corner-transports` pill + `.transport-dot`), per-device colors, wraps for >4
  devices (no cap), rebuilds on add/remove (via `updateDeviceSelectorDropdown` +
  `syncArrangerToPython`).
- **Settings → appbar gear pill** (index.html, appbar.css, sidebar.css,
  settings_hardware.js): round glass `#appbar-settings-btn` to the right of the
  brightness/volume bars opens the Settings tab (highlights the gear; cleared when
  a sidebar nav is chosen). The sidebar Settings button was removed and the
  device-selector panel pinned to the sidebar bottom (`margin-top:auto`).
  `?tab=settings` deep-link now matches any `[data-tab]`. Test + visual-tester
  updated; verified in fresh Playwright (gear opens settings, 28px round pill).
- **Removed the bottom-right connectivity indicator pill** (index.html,
  appbar.css, settings_hardware.js): the fixed `.corner-transports` pill + four
  `#tr-*-dot` dots are gone (the per-device sidebar dots convey state now), along
  with the now-dead `updateTransportPanel`/`refreshTransportStatus` 5s poll that
  only fed it. Tests assert the indicator is removed.

### Follow-ups / not done
- **D scrolling text**: current fix is a static centered render; long text on a
  16px matrix scales down small. A futpib-style scrolling-frame animation that
  honours speed/effect is the proper follow-up. Hardware-verify the static fix.
- **Daemon auto-sync schedule**: the Routines toggle/interval/targets persist to
  `hotchannel_config.json` (daemon-read) as before; no new daemon scheduler was
  added this round — confirm the daemon acts on it.
- **C2** only mirrors the gallery + custom-art push sites; other push paths
  (text, wall split, weather) don't yet update the preview.

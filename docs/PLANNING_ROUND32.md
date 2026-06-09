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

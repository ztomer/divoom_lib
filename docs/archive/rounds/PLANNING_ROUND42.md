# Round 42 — bug batch: persistence, macOS 26 NC db, pixel-art loaders, wall push

User batch (2026-06-10, "go"). Triage findings + fixes per item:

## §1 Scan timeout/limit don't persist
`save_scan_settings` writes `[gui] timeout/limit` to config.ini on every scan,
but NOTHING reads them back — the template hardcodes `value="60"`/`value="4"`.
Fix: `gui_api.get_scan_settings()` (reads config.ini) + populate the two inputs
on Settings load.

## §2 "macOS Notification Center DB not found" on macOS 26
On this machine the DB exists at
`~/Library/Group Containers/group.com.apple.usernoted/db2/db` (381KB, readable)
— `find_notification_db_path()` only probes under `DARWIN_USER_DIR`
(Sonoma/Sequoia layouts). Fix: add the Group Containers candidate (absolute,
not relative to DARWIN_USER_DIR). Keep the old candidates.

## §3 Pixel Art → Custom Art: "no cached gallery files"
`loadCustomArtCacheGrid()` is only triggered by the OLD Channels "design" panel
switch (`channels_core.showChannelPanel`), which no longer exists in the UI —
custom art moved to Pixel Art, whose sub-tab handler (settings_features.js)
loads gallery + hot but NOT custom art. Fix: call it on `pixel-custom-art`
sub-tab click AND on pixel-art tab activation when custom-art is the active
sub-tab (it's the default sub-tab).

## §4 Hot channel stuck on "Loading hot channel manifest..."
The sub-tab handler calls `window.loadHotPreview`, but gallery_hot.js never
exposes the closure on `window` → undefined → no fetch. The only working
trigger is `tab-changed` when hot is ALREADY the active sub-tab. Fix: one line
(`window.loadHotPreview = loadHotPreview`).

## §5 Wall presets gone between sessions
presets.json now holds ONLY `_last_active_slots_` — the named preset never
survived. Two real hazards found:
1. `save_preset` silently no-ops when the name field is empty and `prompt()`
   fails — **pywebview's cocoa backend does not implement window.prompt** →
   name = "" → silent return. The user believed they saved.
2. `update_wall_slots` (fires on every arranger change) reads-modifies-writes
   presets.json; on any read failure it rewrites the file with ONLY
   `_last_active_slots_` — destroying all named presets.
Fix: (a) replace the prompt() fallback with an inline error toast pointing at
the name field; (b) make `update_wall_slots` non-destructive (skip the write if
the file exists but can't be parsed) + atomic write (tmp+rename) for both
writers.

## §6 Virtual wall: no preview, images not pushed
R41 added arranger previews; push path = `display_wall_image` →
`_dispatch(show_image)` → daemon wall target. Needs runtime debugging against
the real devices (wall = daemon-owned multi-device). Investigate: does
`wall_configure` get called before push (is_free_form change in R41)? Does
show_image reach each wall slot device (0x8B per device)? The user asks whether
we must convert to Divoom format + switch channel first — show_image already
encodes + the per-device push switches to drawing mode (show_design). Iterate
with daemon RPCs; success = both devices render their crop.

## §7 Routines → Schedule +15% width
560px → 644px max-width.

## §8 Device Settings: right-align controls
Rows already use `justify-content:space-between`; the name + auto-off rows have
inputs mid-row. Right-align the control cluster in every row (labels left,
controls right).

## §9 MCP server toggle → header-right
Move `#mcp-toggle` from the card body into the card-header (flex-header), like
Background agent; PID detail stays in the body.

## Delivery
Each fix + test coverage where testable (§1 get_scan_settings, §2 candidate
list, §5 non-destructive update_wall_slots); browser-preview verify UI items;
full suite; commit per logical group; push + CI watch.

## §outcome — ALL 9 SHIPPED (e2029fd7 → 33dba70f)

- **§1** scan settings restore (`get_scan_settings` + input populate).
- **§2** macOS 26 NC db found at `group.com.apple.usernoted/db2/db`; unreadable
  store now raises an ACTIONABLE PermissionError (Full Disk Access guidance)
  that reaches the menubar tooltip. NOTE FOR USER: grant Full Disk Access to
  python3 to actually enable notification mirroring.
- **§3** Custom Art library loads on Pixel Art entry + sub-tab click (the old
  handler called a function that never existed).
- **§4** Hot manifest loads on sub-tab click (`window.loadHotPreview` exposure).
- **§5** presets: prompt() silent no-op replaced with an explicit toast (cocoa
  pywebview has no window.prompt); update_wall_slots no longer wipes named
  presets on a corrupt file; atomic writes everywhere. The previously lost
  preset is unrecoverable.
- **§6** virtual wall HW-debugged on Ditoo+Pixoo: wall_configure + device_call
  client read-timeouts (the 2s quick timeout strikes again), and the arranger
  previews were an un-awaited proxy coroutine poisoning the JSON reply. Live:
  32x16 split image pushed to both devices in 1.3s, per-device preview
  data-URLs returned. No format conversion/channel switch needed — show_image
  encodes + switches per device.
- **§7** 336→386px. **§8** right-aligned clusters. **§9** MCP header toggle.
- Tests: +7 (`tests/test_r42_fixes.py`). Suite 1327/75/1 — the 1 fail is the
  pre-existing playwright viewport test (CI skips playwright; R40-documented).
- All UI verified in browser preview (fresh-fetch + stubbed pywebview).

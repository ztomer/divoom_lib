# Native UI Parity Tracker (Rust egui vs Python)

Living record for the "/loop until parity" run. The Python UI (`divoom_gui/` +
`divoom_menubar/`) is the spec; this tracks each `gui_api`/mixin feature's status
in the Rust UI (`native-port/divoom-ui/`). Updated every iteration.

Legend: ✓ done · ⚠ partial/buggy · ✗ missing · ↔ mis-mapped (wrong tab)

_Started 2026-06-29 after a full audit found the earlier "Phase 3 complete" claim
overstated (~1/3 of the surface actually wired). Python stays the reference,
never deleted._

## Structural fixes (do first — these are WRONG, not just missing)
- [x] ✓ **Live Widgets tab** re-mapped to live data feeds (music/sysmon/weather/
  stocks toggles → `live_job_start`/`live_job_stop`). `widgets.rs` rewritten.
- [x] ✓ **Gallery** moved under **Pixel Art** (Paint/Gallery sub-tabs). New
  `gallery.rs`; `pixel_art.rs` gained the sub-tab row.

## Read-backs (UI currently shows hardcoded defaults, not device state)
- [x] ✓ `get_brightness` → appbar slider (fetched on device-connect)
- [x] ✓ `get_volume` → appbar slider
- [x] ✓ `get_device_name` → Device Settings name field
- [ ] ✗ `get_scoreboard_state` → scoreboard inputs
- [ ] ✗ `get_alarms` → Schedule editor
- [ ] ✗ `get_keep_daemon_alive` → Settings toggle
- [ ] ✗ `get_work_mode` / `get_transport_status` → status display

## Channels
- [x] ✓ clock face, visualizer, VJ, ambient, scoreboard
- [x] ✓ clock color (`set_clock_rich`) — fixed: now sends kwargs {style,twentyfour,color}
- [ ] ✗ `switch_channel` not explicitly called (show_* covers most; verify text/score)
- [ ] ✗ Text push (`push_text`) — needs bitmap-font→image render
- [ ] ✗ Sessions panel: `start_sleep`/`stop_sleep`/`set_timer`/`set_countdown`/`set_noise`

## Device Settings
- [x] ✓ name, 12/24h, temp, power, auto-off, orientation, mirror, factory reset
- [ ] ✗ `sync_time` — daemon gap (DateTimeCommand not a device_call leaf; task chip)

## Schedule
- [x] ✓ alarms `set_alarm`
- [ ] ✗ `get_alarms` fetch into editor
- [ ] ✗ `set_memorial` (memorial countdown)
- [ ] ✗ `set_timeplan` (time plan)

## Settings
- [x] ✓ notifications start/stop/status, LAN probe
- [ ] ✗ keep-alive get/set (currently local-only)
- [ ] ✗ `save_lan_config` + LAN device add/delete list
- [ ] ✗ `save_notification_routing`
- [ ] ✗ `send_notification` (test)
- [ ] ✗ MCP server start/stop/status (subprocess)
- [ ] ✗ scan settings (`get_scan_settings`/`save_scan_settings`)
- [ ] ✗ cloud login (`save_credentials`) — gallery can't auth without it
- [ ] ✗ export/import settings (`PresetsManagerMixin`)

## Live Widgets (data feeds) — the MediaSyncMixin
- [x] ✓ music sync (`live_job_start mac "music"`)
- [x] ✓ stocks sync + symbol (`live_job_start mac "stocks" {symbol}`)
- [x] ✓ system stats (`live_job_start mac "sysmon"`)
- [x] ✓ weather sync (`live_job_start mac "weather"`)
- [ ] ✗ audio visualizer (`toggle_audio_visualizer`, `get_audio_levels`)
- [ ] ✗ `live_job_list` (show running jobs) + per-feed params (interval)

## Weather
- [ ] ✗ `push_weather` / `get_weather` / `set_temperature_channel` panel

## FM radio
- [ ] ✗ `set_fm_frequency`

## Pixel Art tab (web = Custom Art + Gallery + Hot Channel)
- [x] ✓ paint editor + push (`show_image`)
- [x] ✓ Gallery (cloud, `fetch_gallery`) — moved here (Gallery sub-tab)
- [ ] ✗ Custom Art browser (`display_custom_art`)
- [ ] ✗ Hot Channel scheduler

## Virtual Wall
- [x] ✓ basic slots → `wall_configure`
- [ ] ✗ `update_wall_slots` / `display_wall_image`

## Presets
- [ ] ✗ save/load/list presets, preset files (`PresetsManagerMixin`)

## Tray menubar
- [x] ✓ Show Dashboard / Notifications / Quit (basic)
- [ ] ✗ device section + color-coded status (parity with pyobjc menubar)

## Progress log
- 2026-06-29: audit done; tracker created; docs corrected. Starting gap closure.
- 2026-06-29 iter1: read-backs (brightness/volume/device-name) fetched on
  device-connect (status idle→active) + applied to UI; clock-color bug fixed
  (set_clock_rich now sends kwargs). Added app.call_kw helper. Build green.
- 2026-06-29 iter2: STRUCTURAL fix — Live Widgets re-mapped to live data feeds
  (music/stocks/sysmon/weather toggles → live_job_start/stop, gated on a connected
  device); gallery moved under Pixel Art (Paint/Gallery sub-tabs, new gallery.rs).
  Added app.active_mac + toggle_live_job. Verified by screenshot. Build green.

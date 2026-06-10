# Round 44 — wall colors, device name, lifecycle, connection truth, per-device live sync, device preview content

User batch (2026-06-10). Triage + approach per item. Two are large
(per-device live sync; device-preview content); the rest are bugs/polish.

## §1 Virtual wall paints solid red / blue instead of the loaded image
"Two devices → one screen red, the other blue, not the image we loaded."
Red-left/blue-right is exactly the split of the R42 test image I pushed during
debugging — strong signal the **wall split CACHE is serving stale crops**
(`divoom_lib/wall.py` show_image, `~/.config/divoom-control/cache_wall/`). The
R43 cache key = `stem_md5(path)[:8]_size_mtime` — if the user re-exports/reloads
to the SAME arranger temp path with a same-ish size, or two different sources
collide on the short key, the cached quadrant from a previous push is reused.
Also: a solid-color crop appears when the crop rectangle is degenerate
(free-form min/max math) → each device gets a 1px region stretched.
Plan: (a) make the cache key collision-proof (full sha256 of the FILE BYTES,
not the path) + include slot geometry; (b) verify crop math on hardware with a
known gradient image — confirm each device shows its real quadrant; (c) purge
stale cache on geometry change. HW-test on Ditoo+Pixoo.

## §2 Device Settings "Device name" = the editable Bluetooth name
Today the field is a bare input with placeholder "Read from device…" and never
populated. The user wants it pre-filled with the current device name (the BLE
advertised name for BT devices) and editable → Save renames. `set_device_name`
exists. Need `get_device_name` (return the connected device's name — from the
discovered list / BLE name) and populate the input on Device Settings entry +
on connect.

## §3 Clock-format pill misaligned
The clock-format `.tabs-row` is wider than the Celsius/Fahrenheit + Normal/Low
pills below it, so its right edge doesn't line up. Equalize: give the three
2-option pills the same fixed width (or the buttons equal flex-basis) so their
right edges align.

## §4 Menubar stays alive after quitting dashboard (bg agent OFF)
The signals exist (R40 §9: dashboard close → daemon.shutdown() → EVENT_SHUTDOWN
broadcast → menubar terminates) but it doesn't fire in practice. Runtime-debug
the real process chain: is daemon.shutdown() actually called on window close?
Does the daemon broadcast before the subscriber drops? Does the menubar's
`get_keep_daemon_alive()` read False? Likely the broadcast races the socket
close (0.25s) OR the GUI process is killed before the post-`webview.start()`
code runs. Fix: broadcast EVENT_SHUTDOWN BEFORE the reply/grace and flush; and
have the dashboard send shutdown from a window-closing/closed EVENT handler
(pywebview `events.closing`) rather than only after `start()` returns.

## §5 Devices show "active" when the connection actually failed
`connectDevice` (app_globals.js) sets `transport-dot active` on
`connect_single_device(address).then(res => res ? active : inactive)`. If the
daemon returns success-ish but the BLE connect actually failed (the R42 connect
timeout / a half-open connection), the dot lies. Make `connect_single_device`
return the REAL connection state (verify `device_status.connected` after
connect, not just "command sent"), and the dot follow that.

## §6 Live widgets keep updating their device after switching target
Today the live-widget loops are GUI-side `setInterval`s that push to the
CURRENT target only; switching target abandons the old device (shows last
image). The user wants: a widget activated on device A keeps being driven by
the DAEMON even after the GUI switches to device B. This is an architecture
move: the daemon owns per-device "live job" loops (sysmon/weather/stock/clock),
keyed by MAC, that keep pushing until explicitly stopped. GUI toggles
start/stop a daemon job for the active device instead of running its own timer.
Large — scope a `divoom_daemon/live_jobs.py` (per-MAC asyncio tasks through the
device loop) + RPCs `live_job_start(mac, kind, params)` / `live_job_stop` /
`live_job_list`. Phase it: sysmon first (already has apply_system_stats), then
weather, then stocks.

## §7 Device preview shows the active channel/widget content
The lower-left device preview shows the last pushed image or the product icon.
The user wants the device's CURRENT content (active channel / live widget /
its wall piece) composited INTO the preview's screen area — possibly rotated to
face the user. We already capture last-pushed frames (setDevicePreview, wall
last_previews). Plan: (a) a device-frame compositor that draws the current
frame into the product image's screen rectangle (per-model screen bbox); (b)
feed it from the existing push sites + the new daemon live jobs (§6) so it
tracks live content; (c) the "regenerate images to face the user" = render the
product PNGs at a slight 3D-forward angle with a flat screen rect we can paste
into (asset work — may defer to a follow-up).

## Order
§3 (tiny CSS) → §2 (device name) → §5 (connection truth) → §4 (menubar quit,
runtime) → §1 (wall cache, HW) → §6 (per-device live sync, big) → §7 (preview
content, big; asset regen may defer).

## §outcome
_(fill as items land)_

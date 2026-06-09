# Round 34 — Routines/Sidebar polish + hot-channel sync failure

User batch (2026-06-09): four items. Order chosen bug-first; the alarms redesign
is the largest.

## §1 Hot-channel sync "failure to upload all the images" — INVESTIGATE + FIX

**Prime suspect (found in triage): the same client-read-timeout bug class as the
R24 scan/connect fixes.** `DaemonClient.sync_artwork`
(`divoom_daemon/daemon_protocol.py:270`) sends `sync_artwork` with the default
2s `client_timeout`. The daemon downloads + decodes + **streams the image to the
device over BLE**, which takes far longer than 2s per image — so the GUI's
`batch_sync_artwork` sees "timed out" → `sync_hot_channel`
(`divoom_gui/gallery_sync.py:439`) marks the file failed, while the daemon may
still be uploading it fine. With N images synced sequentially, most/all get
falsely reported failed.

Plan:
1. Add a `sync_read_timeout` knob to `daemon.ini` (`daemon_config.py`), default
   generous (120s — BLE streaming of an animation is slow); wire into
   `DaemonClient.sync_artwork` via `read_timeout=` (mechanism already exists).
2. Re-test a multi-image hot-channel sync; check `/tmp/divoom_daemon.log` for
   the daemon-side truth (did uploads actually fail, or only the client read?).
3. **APK as source of truth** (`references/apk/`, per `CHANNEL_ARCHITECTURE.md`:
   APK is authoritative): verify our hot-channel upload sequence against the
   decompiled app — command IDs, chunking, per-frame acks, inter-image delays.
   If the daemon-side log shows REAL device errors after the timeout fix, diff
   our `sync_artwork`/encoder path against the APK's gallery-push flow
   (`references/apk/decompiled_src/`, `APK_INTELLIGENCE_REPORT.md`).
4. Improve the reply: `sync_hot_channel` returns only `{ok, synced, failed}` —
   add a per-file `error` string so the UI can say WHY a file failed.

## §2 Device-selector connect: pulse while connecting

The animation already exists — found it:
- `.status-indicator.connecting` + `@keyframes pulse` in `sidebar.css:128-137`
  (scale 0.9→1.1 + opacity alternate, amber glow). Also `dot-pulse` in
  `appbar.css:54` (used by `#global-status-dot.connecting`, set from
  `app_globals.js:126`).

Plan: the per-device switch dots (R33, rendered into `#device-dots` by
`app_globals.js:74`) get a `.connecting` state. In the dot's click handler
(`app_globals.js:129`, before `connect_single_device(address)`):
add `.connecting` class to the clicked dot → reuse the sidebar `pulse`
keyframes (`.device-dot.connecting { animation: pulse 1.5s infinite alternate; }`
in `sidebar.css`, matching the status-indicator treatment); on promise resolve,
clear the class (success → active/connected styling, failure → revert + existing
error toast). One CSS rule + ~4 lines of JS.

## §3 Auto-Sync Gallery card: more horizontal + vertical space (no wrapping)

Cause found: the Schedule sub-tab grid is capped at `max-width: 540px`
(`templates_routines.js:13`), but each sync-target row
(`gallery.js:245-296`) is `dot + name + 4 style tab-btns (Recommend/Cartoon/
Creative/Nature) + toggle` — too wide for 540px, so the `.tabs-row` (which has
`flex-wrap: wrap` from `tabs.css`) wraps onto a second line.

Plan:
1. Widen the Schedule grid `max-width` 540 → ~760px (window is 1080 now, fits).
2. `.sync-device-row`: `flex-wrap: nowrap`; give the name
   `overflow:hidden; text-overflow:ellipsis; white-space:nowrap; min-width:90px`
   so long names truncate instead of pushing the tabs.
3. The row's inner `.tabs-row`: `flex-wrap: nowrap` override + slightly tighter
   `.tab-btn` padding in this context if needed.
4. Vertical: bump row padding (6px → 10px) + `gap` between rows so toggles and
   tabs don't crowd; verify in preview at 1080px.

## §4 Alarms: weekday table, live updates, add/remove/clear

Current (`settings_features.js:60-123`, `templates_routines.js:49-55`): 10 fixed
rows, each repeating 7 weekday checkboxes + a per-row Save button calling
`set_alarm(idx, enabled, hour, minute, week)`; all 10 always shown.

New model — a proper table:
- **Header row**: `On | Time | Mon Tue Wed Thu Fri Sat Sun | (remove)`.
  CSS grid `.alarms-table` with `grid-template-columns: auto auto repeat(7, 1fr) auto`;
  weekday names appear ONCE in the header, each row gets 7 toggle cells
  (clickable day cells, `.active` state) instead of labeled checkboxes.
- **Show only non-empty alarms** by default. Empty = `status` falsy AND
  `week == 0` (slot never configured). Hidden empty slots are the pool for Add.
- **"+ Add alarm"** button (header, right): takes the first free slot of the 10,
  appends a row with defaults (07:00, no days, enabled), writes it immediately.
  Disabled when all 10 slots are in use.
- **"Clear all"** button: confirm, then zero every slot
  (`set_alarm(i, false, 0, 0, 0)` for i in 0..9) and empty the table.
- **Per-row remove (×)**: zero that slot on-device, drop the row.
- **Immediate updates — no Save button**: any change (enable toggle, hour/min,
  day cell) **debounced ~500ms per row**, then `set_alarm` for that row;
  failure → error toast + visual mark on the row. Debounce matters: hour
  spinner clicks must not fire a BLE write per click.
- **Read-back caveat**: initial state comes from `get_alarms`; the `get_*`
  read-back is flaky on real devices (open task #20). If `get_alarms` returns
  nothing, fall back to a local cache of the last-written alarm state
  (`~/.config/divoom-control/alarms.json`, written on every successful
  `set_alarm`) so the table isn't empty-by-bug.

Files: `templates_routines.js` (card header buttons + table container),
`settings_features.js` (render table, debounced writers, add/clear/remove),
new CSS in `style_extra.css` or `routines`-scoped block; tests for the
empty-slot predicate + debounce wiring if feasible in the JS-guard style.

## Suggested order
§1 (real bug, likely quick win given the existing `read_timeout` mechanism) →
§2 (tiny) → §3 (small CSS) → §4 (the big one).

## §outcome
- **§1 SHIPPED** (`ade3c0cc`) — root cause confirmed as predicted: `sync_artwork`
  used the 2s quick-command read timeout while the daemon downloads + streams
  over BLE. New `sync_read_timeout` knob (120s) in daemon.ini; `sync_hot_channel`
  now returns a per-file `errors` map. APK protocol diff NOT needed unless real
  device errors remain after this fix — re-check `/tmp/divoom_daemon.log` on the
  next user-run hot-channel sync.
- **§2 SHIPPED** (`a3865133`) — device dots carry `data-value`; `connectDevice`
  adds the existing amber `.transport-dot.connecting` dot-pulse during the
  attempt; cleared on success (re-render) and failure (explicit re-render,
  hue restored). Preview-verified.
- **§3 SHIPPED** (`405dc811`) — Schedule grid 540→760px, rows nowrap, names
  ellipsize (tooltip keeps full name), row padding 6→10px. Preview-verified at
  1080px: long-name row stays single-line (54px).
- **§4 SHIPPED** (`0877db09`) — alarms weekday table (header row + day-cell
  toggles), only non-empty alarms shown, +Add / Clear all / per-row ×, live
  debounced writes (500ms/row, no Save button), `alarms.json` last-written cache
  as get_alarms fallback (task #20 read-back flakiness). Editor split into
  `web_ui/alarms_editor.js` (500-LOC rule). Preview-verified: empty-slot hiding,
  bitmask mapping, add/remove/clear, debounce (3 changes → 1 write).
- **§1b SHIPPED** (`5f419002`) — APK comparison done (user: "do it now").
  Wire format CONFIRMED identical (start `[0][len:4]`, data
  `[1][len:4][idx:2][≤256]`, 256-byte chunks). Flow DIVERGED: the APK is
  device-driven — it waits for the device's 0x8b "send the animation" ACK after
  START and serves `[1][idx]` retransmit requests (`bluetooth/s.java` →
  `startSendAllAni`/`resendBlueData`); we slept 0.5s and blasted, ignoring
  retransmits. Now aligned on BLE with graceful fallback to the legacy sleeps;
  `stream_raw_bin_payload` deduplicated into `stream_animation_8b` so the GIF +
  raw-bin paths share the one streamer. Full comparison table in
  `docs/CHANNEL_ARCHITECTURE.md` (new 0x8b section). +3 tests.
- Suite 1185 / 0 / 75. Remaining: hardware re-test of hot-channel sync by the
  user — both the read-timeout fix (§1) and the ACK/retransmit alignment (§1b)
  land together; the daemon log (`/tmp/divoom_daemon.log`) now shows ACK and
  retransmit activity per upload.

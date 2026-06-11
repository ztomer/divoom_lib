# Backlog / Roadmap

The single living list of open work. (Reconstructed 2026-06 after the R21 doc
cleanup removed `next_phase_requirements.md` / `PLANNED_WORK.md` /
`APP_IMPROVEMENT_PLAN.md` — most of those items had already shipped in R12–R18;
the open remainder lives here now. Recover the originals from git history if
needed.) Update this as items land; record the "why/how" in CHANGELOG + the
round's planning doc.

## Status legend
`DONE` done · `VERIFY` partial / needs verification · `OPEN` open · `HW` needs real hardware ·
`UPSTREAM` blocked on upstream (Divoom cloud)

## Open

### Regressions reported 2026-06-08 — root-caused
- `DONE` **Clock / EQ / Custom Art / Ambient panels were empty** (and VJ "missing").
  Root: a stray duplicate `});` in `channels_grids.js` (R23 web_ui split) was a JS
  **syntax error** that halted the whole file, so every grid builder silently
  never ran. Fixed (one brace) + guarded by `tests/test_web_ui_js_syntax.py`
  (`node --check` all web_ui JS). Verified live: clock-faces grid, 12 EQ effects,
  Custom Art panel all render again. (VJ Effects is *correctly* hidden unless the
  device is a Timebox Evo — `updateChannelButtonsVisibility`; it only showed
  before because the syntax error stopped that filter running.)
- `DONE` **Menubar item didn't appear on launch.** Two bugs: (1) the agent
  crashed at startup — `'super' object has no attribute 'init'`; PyObjC NSObject
  subclasses need `objc.super(...).init()`, not Python `super()`. (2) nothing
  spawned it — `gui_main` now launches the agent on startup (macOS, detached,
  dupe-guarded). Verified live: "Divoom (idle)" status item + menu.
- `VERIFY` **Scan devices** — root cause is macOS TCC, NOT a Python/3.14 bug: BLE crashes/denies based on the *responsible process's* Bluetooth grant + `NSBluetoothAlwaysUsageDescription`. **Verified via System Settings > Privacy > Bluetooth: `python3.14` and the user's terminal (Ghostty) are already GRANTED; there is no `Divoom` entry.** So: (1) the R17 cutover broke scan by spawning the daemon DETACHED -> own unattributed process -> crash/deny; the non-detached spawn fix makes it inherit the launching terminal's grant. (2) The `Divoom.app` bundle (scripts/make_app_bundle.sh) was a wrong turn for this: it re-attributes BLE to a NEW `com.divoom.control` identity that isn't granted, and a background daemon can't raise the grant prompt -> empty scan. **Current fix: `run_gui.sh` launches the GUI directly (attributed to the granted python3.14/terminal) + non-detached daemon.** Must be verified by the USER (launch from the granted terminal, devices powered on) - can't be tested from the Claude harness (its process tree isn't a granted Bluetooth context). make_app_bundle.sh kept for distribution/double-click (would need its own one-time grant).

### Device / protocol
- `DONE` **Custom Art / Design channel switch** (HW-investigated 2026-06-11 on
  Tivoo-Max + Ditoo). The suspected "0x45 rejected after a draw" does NOT
  reproduce — `current_light_effect_mode` (read via 0x46) cleanly tracks every
  switch (clock=0 / design=5 / visualizer=4), after a draw, rapidly, and on the
  Max; the 10-byte payload padding in `show_clock`/`show_design` already fixed
  the original. The REAL current cause (only reproducible now that live jobs
  actually push — they were deadlocked before): a running live widget clobbered
  the switch on its next tick. Fix: a channel/clock/VJ/visualizer/solid-light
  switch now stops the active device's live jobs first (`live_jobs_stop_for`
  RPC + GUI `LightingApi._stop_live_widgets`). HW-confirmed: switch to Clock
  while sysmon ran → mode 0 and stays 0 (was stuck on the sysmon frame).
- `DONE` **`get_*` read-backs** (task #20, HW-verified 2026-06-11 on 4 models).
  Root cause was NOT a timeout — reads return <0.1s. It was a STALE read: the
  device emits an unsolicited 0x46 on state change and the manual readers
  (get_brightness/get_light_mode) skipped the queue drain, so they lagged one
  step behind (set 60 → read 25). Fixed with `Divoom.drain_notifications()`;
  round-trip now exact. The 0x76 get-name query returns only a 2-char suffix on
  every model, so `get_device_name` prefers the advertised name.
- `DONE` **Live-widget on-device sync** (stocks / sysmon / weather, HW-verified
  2026-06-11 on Ditoo). e2e was 100% broken by a DEADLOCK: live jobs run on the
  device loop and await `CommandQueue.submit_async`, whose old impl called the
  blocking `submit()` (`run_coroutine_threadsafe(_add, self._loop).result()`)
  targeting the same loop it was blocking → the push hung forever, no frame, no
  error. Fixed: an on-loop caller now enqueues with a direct `await self._add`.
  All three widgets now stream frames to the device (sysmon/stocks via 0x8B,
  weather via 0x5F).

### GUI / UX
- `VERIFY` **Monthly Best gallery animated previews** — previews should loop, not end on
  a static frame; use first-frame-as-placeholder + background-stream the GIF
  (progressive). Confirm in the live pass.
- `VERIFY` **Custom Art ambient animated previews** — the filmstrip "last 5 pushed"
  history, the 5 named ambient effects, apply-on-select, and the unified
  picker/swatches all ship; confirm the ambient effect previews actually *loop*
  (the one residual of the old "Custom Art polish" item).
- `VERIFY` **Channel panels have large dead space** — the panels container is
  stretched tall to give the Design panel its full-height scroll area, so the
  short panels (clock/EQ/VJ/ambient/scoreboard/text) crammed their content at
  the top with a big void below. 2026-06-11: now vertically CENTER the short
  panels' content (`.channel-panel.active` → flex column + `justify-content:
  center`; `#panel-design.active` override untouched) — reads balanced, no
  clipping on any panel (browser-verified). A richer treatment (live device
  preview filling the slack) is still possible if wanted.
- `VERIFY` **Animated previews** (Monthly Best gallery, Custom Art ambient,
  Live Widgets) — couldn't be checked interactively in the live pass: a
  fullscreen always-on-top overlay app ("Osaurus") intercepted all clicks to the
  pywebview window. Re-run the pass when that overlay is off.

### UI pass — confirmed good (2026-06)
- Settings sits at the sidebar bottom; the 4 transport dots sit bottom-right;
  sidebar + tab icons share one coherent line/Kare style. The theme is flat-dark
  and legible — the earlier "glassmorphism vs legibility" concern (REVIEW §2) is
  largely unfounded in practice.

### Platform / infra
- `UPSTREAM` **Divoom cloud guest auth** fails (`RC=10 "Command is not match"`) → gallery /
  cloud features need a configured account or a refreshed guest flow from a new
  APK capture. Local BLE/LAN control is unaffected. (Handled gracefully; not a
  crash.)
- `HW` **Linux end-to-end**: `divoom_lib` + `divoom_daemon` are Linux-ready
  (R20) but only cross-compile + unit-tested; not run against a real device over
  BlueZ. No Linux notification monitor / now-playing / menu-bar (macOS-only;
  a D-Bus/MPRIS backend would be future work).
- `OPEN` **Optional Rust daemon spike** — measure a minimal Rust daemon (ping/
  device_status over the existing protocol) vs the Python daemon's footprint, to
  inform an embedded/appliance decision. See `REVIEW_2026-06.md` §3.

## Recently shipped (was on the backlog)
- `DONE` Appbar transport tooltips now open upward (were rendering off the bottom
  edge); Settings is last in the sidebar; widget cards are preview-on-top — all
  guarded by `tests/test_appbar_sidebar.py` (R23.1)
- `DONE` Custom Art filmstrip history + 5 ambient effects + apply-on-select +
  unified picker (animation of ambient previews to confirm in the live pass)
- `DONE` Live widgets immediate activation (live-song-sync toggle removed)
- `DONE` System **audio loopback** capture (BlackHole/Loopback) for the EQ visualizer
- `DONE` Real **macOS notification** monitoring + routing (daemon, R16/R17)
- `DONE` Music widget label → "Live cover art"; ambient applies on selection
- `DONE` Weather auto-fetch + IP geolocation; sysmon/stock-ticker frame polish (R18)
- `DONE` Credentials-erase fix; GUI cloud-auth crash-loop fix (R23)
- `DONE` 3-package split + daemon single-owner cutover + network server + Linux compat
- `DONE` Every source file under 500 LOC (R23)

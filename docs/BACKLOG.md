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
- `DONE`/`VERIFY` **Scan devices no longer crashes.** Real root cause (researched + verified live, NOT a Python/3.14 bug): macOS aborts a process (`TCC_CRASHING_DUE_TO_PRIVACY_VIOLATION`) on first CoreBluetooth use if the *responsible process's* on-disk Info.plist lacks `NSBluetoothAlwaysUsageDescription`. A bare `python3` GUI/daemon hits this; it worked from an already-granted terminal. Fix: `scripts/make_app_bundle.sh` builds `Divoom.app` (Info.plist declares the Bluetooth usage); `run_gui.sh` launches via `open Divoom.app` so the app is the responsible process WITH the declaration -> macOS shows the Allow-Bluetooth dialog instead of crashing, and the non-detached daemon inherits it. **Verified live: Scan completes gracefully and the daemon survives.** Remaining: user grants the Bluetooth prompt once (System Settings -> Privacy -> Bluetooth -> Divoom) + a device must be powered/nearby to actually appear.

### Device / protocol
- `OPEN` **Custom Art / Design channel switch** doesn't reliably change the active
  channel on device (esp. **Divoom Max**). Suspected: `0x45` channel-switch is
  rejected while a prior drawing stream is active → clear/interrupt active loops
  first. (Long-standing "Divoom Max channel-switch bug" open thread.)
- `HW` **`get_*` read-backs time out on real devices** (brightness/work-mode/
  scoreboard/volume). Task #20. Affects UI initializing to true device state.
- `HW` **Live-widget on-device sync** (stocks / system-monitor / weather) — the
  backend streams frames; **end-to-end hardware verification still pending**.

### GUI / UX
- `VERIFY` **Monthly Best gallery animated previews** — previews should loop, not end on
  a static frame; use first-frame-as-placeholder + background-stream the GIF
  (progressive). Confirm in the live pass.
- `VERIFY` **Custom Art ambient animated previews** — the filmstrip "last 5 pushed"
  history, the 5 named ambient effects, apply-on-select, and the unified
  picker/swatches all ship; confirm the ambient effect previews actually *loop*
  (the one residual of the old "Custom Art polish" item).
- `OPEN` **Channel panels have large dead space** — e.g. the Clock channel shows
  only a "Clock Color" swatch with ~80% of the panel empty. Rams "useful / as
  little design": either fill the panel (style options + a live device preview)
  or size the window/panel to its content. Audit Clock/Scoreboard/Text/etc.
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

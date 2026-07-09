# Session Handoff — read this first

**Consolidated roadmap**: `docs/ROADMAP.md` — shipped rounds, open workstreams,
and deferred items in one view. This file tracks the per-round state.

This is the **cross-agent session state**. opencode and Claude Code keep their
own conversation stores (they can't share a live session), so THIS FILE + the
git history + CHANGELOG + ROADMAP are the shared memory. Any agent (opencode or
Claude) should read this on entry and **update it at the end of every round**
(see the core rule in `AGENTS.md`).

## How to resume

- **opencode**: `opencode -s ses_184471307ffeCUHgzv9w51O0oA` (or
  `opencode export <id>` to read it as JSON).
- **Claude Code**: reads `CLAUDE.md` → `AGENTS.md` → this file, plus `git log`.
- Both: `git log --oneline`, `CHANGELOG.md`, `docs/PLANNING_ROUND*.md`.

## Current state — _update this section each round_

- **FALSE "SERVICE NOT RUNNING" BANNER + DEVICE-LOCK WEDGE → FIXED v0.21.17
  (2026-07-09).** User hit the daemon-down banner while the daemon WAS running.
  Root-caused live: `device_status`/`device_call` hung 6s+ while
  `get_status`/`get_device_activity` were instant → the daemon's `device` mutex
  was stuck, held by an unbounded BLE write that never returned (write to a
  peripheral that vanished when Bluetooth was toggled mid-op). The liveness probe
  (`daemon_alive`/`_client_alive`) used `device_status` (needs that mutex) → hung
  → false "dead" → banner. Fixes: (1) `ble.rs` bounds the write with `WRITE_TIMEOUT`
  (5s) so a hung write releases the lock and the daemon self-recovers; (2)
  `daemon_client.py` probe switched device_status → **get_status** (cheap,
  LOCK-FREE); (3) `notification_service._state` uses `getattr(mon,"is_running",…)`
  (get_status is now the probe, must not raise on an incomplete monitor — also fixed
  2 daemon_bridge tests). Rust + Python compile/tests green. NOTE: any daemon
  running BEFORE this build (incl. the user's current v0.21.16) can still be
  wedged — needs a daemon restart (quit+reopen app) to pick up the fix.

- **BLE SCAN CoreBluetooth-THROTTLE HARDENING → v0.21.16 (2026-07-09).** The wedge
  that dogged this session (rapid daemon restarts → CoreBluetooth scan-frequency
  throttle → scans return 0 until BT toggle) is now guarded in `native-port/divoomd`:
  (1) `Daemon::stop_scan_cleanup()` called on shutdown in `main.rs` — stops the
  scan on the cached central so a normal quit doesn't leak a scan session to
  bluetoothd; (2) `cmd_scan` caches last result+time (`Daemon.last_scan`) and a
  scan within `MIN_RESCAN_INTERVAL` (3s) returns the cached list (`"cached":true`)
  instead of hitting the radio. Teeth: `rapid_rescan_returns_cached_without_touching_radio`.
  Both feature sets compile. NOTE: `kill -9` still leaks (SIGKILL uncatchable) —
  tests should SIGTERM. Recovery for a wedged stack: BT toggle / `sudo pkill
  bluetoothd`. Functional scan (finds 3) was verified earlier post-BT-reset; this
  round is compile+unit-tested only (user's BT still wedged from prior testing).

- **SCAN TIMEOUT DEFAULT 60→20s → v0.21.15 (2026-07-09).** After the v0.21.14 scan
  guard fix, scans still ran ~80s because they run the full window when device
  count < limit and the default/persisted timeout was long. Lowered the default to
  20s across `scanner_mixin.get_scan_settings`, `presets_manager.load_config`,
  `daemon_config.DEFAULT_SCAN_TIMEOUT`, the Settings input default + JS fallbacks.
  Also reset THIS user's persisted config.ini `[gui] timeout` 120→20. Verified on
  the installed build: scan finds all 3 devices (Pixoo-1, Timoo-light-4,
  Tivoo-Max-light-3) fast. v0.21.14 guard confirmed working end-to-end (after a
  Bluetooth reset — my rapid daemon restarts during testing had wedged
  CoreBluetooth; see the v0.21.14 caveats below).

- **NATIVE DAEMON BLE SCAN CONCURRENCY GUARD → v0.21.14 (2026-07-09).** User: app
  found 2 of 3. Drove the daemon socket: it RELIABLY finds all 3 in isolated scans
  (6/15/60/120s) — BLE/daemon healthy. Root cause: **no scan concurrency guard** —
  overlapping scans share the one adapter and clobber each other (my own probes
  overlapping the GUI scan truncated it). Fix: `Daemon.scanning` flag + `ScanGuard`
  RAII in cmd_scan; concurrent scan rejected. Plus a 90s timeout cap in ble::scan.
  Teeth: `scan_guard_tests`; both feature sets compile.
  **IMPORTANT LESSONS / CAVEATS:**
  (a) I first tried to also make ble::scan incremental (event stream) + early-exit
  at limit — BOTH hung: querying peripheral `properties()` DURING an active scan
  blocks on macOS CoreBluetooth. Reverted to the proven single-window snapshot
  (query only AFTER stop_scan). Do NOT reintroduce during-scan property reads.
  (b) My many rapid daemon kill/restart cycles during testing WEDGED the Mac's
  CoreBluetooth — scans started returning 0 devices (cache went empty). This is
  environmental (not the code); needs a Bluetooth reset / settle to clear. Verify
  on a clean BLE stack. (c) Testing done by hot-swapping the release divoomd into
  the installed .app + re-signing (faster than a full DMG rebuild). The COMMITTED
  DMG still needs a rebuild with the final (reverted) code. (d) connect also scans
  (BleTransport::connect) and isn't under the guard yet — scan-vs-connect is a
  follow-up.


- **DMG BUILD + INSTALL + RUNTIME TEST → PASSED v0.21.13 (2026-07-09).** Built
  `dist/Divoom-v0.21.13.dmg` (38M, adhoc-signed) via `scripts/build_release.sh`
  (had to create `.buildvenv` first). Installed from the mounted DMG to
  `/Applications` (replaced 0.21.7). VERIFIED on the real build:
  (1) **App icon** — `Contents/Resources/Divoom.icns` present, all 10 iconset
  sizes incl @2x, `CFBundleIconFile=Divoom.icns`. (2) **Bundle** ships all web_ui
  changes (daemon-banner, hot-last-checked, loadLastChecked, refreshDaemonHealth)
  and the Rust `hot_state` (strings probe: `hot_update_state.json` + fields +
  `[ Wrn ] hot_state record_check failed:`). (3) **Launch** — dashboard renders;
  native Rust `divoomd` + `divoom-menubar` both spawn; BLE works (4 devices found,
  Timoo-light-4 connected); NO daemon-down banner (healthy). (4) **Daemon
  reliability (v0.21.9)** — `kill -9` the daemon → app STAYED running and a fresh
  daemon respawned within ~1s, device still connected, no banner. LIMITATION:
  couldn't drive the pywebview UI via computer-use — the user's tiling WM
  (`com.zaidenstein.ZoneTilerWM`, not allowlistable) overlays the window and eats
  clicks. So the MCP-card / hot-channel-stamp / banner VISUALS weren't clicked
  through on the DMG (all verified earlier via unit tests + the static web_ui
  preview). Note: stale `~/.config/divoom-control/mcp-server.log` (Jun 10) is
  still on disk — confirms the MCP fix relies on session-gating to not surface it.
  Full test suite can't run clean in this shell (BLE tests SIGSEGV mid-run;
  see [[divoom-pytest-shutdown-segfault]]) — changed-area files all green.


- **HOT CHANNEL "LAST CHECKED" STAMP → ADDED v0.21.12, MADE DAEMON-OWNED v0.21.13
  (2026-07-08).** Per-device dated verdict so "up to date" isn't blind (user's
  follow-up ask). v0.21.12 recorded it GUI-side; v0.21.13 moved the WRITE into the
  daemon (correct owner — it runs the update; daemon is native Rust now). The
  daemon stamps `hot_update_state.json` on completion in BOTH impls
  (`native-port/divoomd/src/hot_state.rs`; Python `owner_art.py` via
  `divoom_lib/hot_update_state.py`); the GUI passes the active device address on
  the write and only READS via `hot_get_check` (resolves the same active-device
  key). `hot_record_check` removed. Store keyed by device address (MAC/`LAN:ip`/
  `MatrixWall`); `>2wk` turns amber. Teeth: 3 Rust + 3 GUI-API + store tests.
  `cargo check` clean; Python suite green; preview re-verified. **Not on DMG.**
  Rationale on record: an undated "up to date" was untrustworthy; now dated +
  daemon-authoritative, captures non-GUI triggers too.

- **MCP CARD STALE TRACEBACK → FIXED v0.21.8 (2026-07-08).** The Settings →
  Connectivity → "MCP Server" card showed a Python traceback even with the toggle
  OFF (the v0.21.7 note flagged it as an open follow-up). Root cause 1: the GUI
  spawns `divoom-control mcp-server` with stdout redirected to a **log file**, but
  an MCP *stdio* server needs client-owned **pipes** — asyncio's write-pipe
  transport rejects a regular file (`ValueError: Pipe transport is only for pipes,
  sockets and character devices`) and crashed at startup, writing a traceback to
  `~/.config/divoom-control/mcp-server.log`. Root cause 2: the card **tailed that
  log unconditionally** (even stopped / never-started), so a crash from a prior
  session persisted. Fix: `run_stdio()` guards non-pipe stdio via
  `_stdio_is_pipe_like()` and exits with one clean diagnostic line
  (`mcp_server.py`); `MCPController` only surfaces the log for a server started
  THIS session and truncates on start (`mcp_control.py`). Real MCP-client launches
  (Claude Desktop/Cursor) were always fine — only the GUI "Start" toggle was
  doomed. Teeth: 3 new tests in `test_mcp_server.py` (33 pass total). **Not yet
  verified on a DMG** (native pywebview app; TCC/BLE harness limit) — confirmed by
  unit tests + direct reproduction of the guard turning the crash into a clean line.

- **DAEMON-DOWN SILENT + UNRECOVERABLE → FIXED v0.21.9 (2026-07-08).** Restart
  left the app unusable with no indication / no reconnect. Root causes: eager
  launch spawn (`gui_main.py`) discarded its client + never surfaced/retried
  failure; no daemon-down UI; `get_connection_state` couldn't tell daemon-down
  from no-device. Fix: eager spawn now assigns `api._daemon_client`; new backend
  `daemon_health()` (no-spawn liveness probe) + `reconnect_daemon()` (reset stale
  client + re-ensure); frontend daemon heartbeat (4s + on open, ungated) that
  auto-reconnects once then shows a **Reconnect banner** (`#daemon-banner` in
  index.html, styled in widgets_extra.css, wired in app_globals.js/app_init.js).
  Teeth: 7 tests in `test_gui_api.py` (52 pass). Banner render verified in the
  static web_ui preview. **Not yet verified on a DMG** (TCC/BLE harness limit).

- **MISSING APP ICON → FIXED v0.21.10 (2026-07-08).** Shipped `Divoom.app` had
  the generic blank icon: `divoom.spec` had `icon=None` and no `.icns` existed
  (only a 1024px JPEG mis-named `app_icon.png`). Fix: `scripts/make_icns.sh`
  builds `packaging/Divoom.icns`; `divoom.spec` points `icon=` at it;
  `build_release.sh` regenerates before packaging; `setup_app.py` gains `iconfile`
  for parity. **Not yet verified on a DMG.**

- **HOT CHANNEL false "up to date" + redundant downloads → FIXED v0.21.11
  (2026-07-08).** (a) UI verdict was `served.length===0` → "up to date"; a partial
  CDN download (files dropped from the advertised manifest) reported a clean
  "up to date" it never verified. Fix: `gallery_hot.js` now uses the engine's
  `manifest`/`downloaded` counts — `downloaded < manifest` → "Checked D/M" +
  amber + warning toast, not "Up to date". (b) manifest+bodies were fetched per
  device inside `update()`; added `_load_hot_files` device_type-keyed cache (5-min
  TTL) in `hot_update.py` so same-size devices reuse one fetch+download. Teeth: 2
  cache tests + guard updated (26 hot tests pass; full suite green). NOTE: did NOT
  add a persisted freshness timestamp — the "up to date" signal is protocol-honest
  once partial-download is surfaced; a dated last-checked marker is a possible
  future nicety (would need a new store; hotchannel.json is the *Monthly Best*
  config, a different subsystem). **Not verified on a DMG.**

- **SETTINGS TOGGLES IGNORED SAVED STATE → FIXED v0.21.7 (2026-07-08).** Caught by
  driving the real dashboard on-screen (computer-use): the Connectivity toggles
  didn't reflect their persisted value when Settings opened — `quit_menubar_on_exit`
  was `true` in config but the toggle rendered OFF. Root cause: the init read
  `api().get_*()` ran at `DOMContentLoaded`, before pywebview injects
  `window.pywebview.api`, so it was silently skipped and the toggle kept its
  unchecked HTML default. (Invisible on `keep_daemon_alive` — default false; exposed
  by `quit_menubar_on_exit` — default true.) Writing was always fine (verified by
  clicking → config flipped). Fix (`settings_notifications.js`): defer the value
  reads to the `pywebviewready` event, the same guard `restoreScanSettings` uses.
  **Verified on-screen on the 0.21.7 DMG:** toggle now shows ON (orange) reflecting
  the true default; Background agent shows off. Also re-confirmed on 0.21.7: dash
  renders, menu bar spawns, clean-quit terminates it, scan finds 4 devices + connect
  Pixoo-1 (brightness 60). NOTE: the MCP Server card shows a Python traceback in the
  UI (mcp_server run_stdio connect_read_pipe) — pre-existing, unrelated, worth a
  separate look. Shipped v0.21.7.

- **MENU BAR MISSING ON NORMAL LAUNCH → FIXED v0.21.6 (2026-07-08).** A clean-room
  install-from-DMG + single `open` launch caught it: the menu-bar agent never
  spawned when the app was started the normal way (Finder/Dock/`open`/cask) — no
  tray icon. `_spawn_menubar_agent`'s dupe-guard used `pgrep -f divoom-menubar`;
  `-f` is a loose substring match over every process's full command line, and under
  LaunchServices a coalition process transiently carries "divoom-menubar" in its
  args, so the guard false-matched → "already running" → skipped the spawn. (Direct
  `Contents/MacOS/Divoom` launches had no such process → looked intermittent.)
  Proven with a decoy: `pgrep -f divoom-menubar` matched `helper
  divoom-menubar-relaunch`; `pgrep -x divoom-menubar` (exact name) did not. Fix:
  use `pgrep -x`. Teeth: `test_menubar_dupe_guard_uses_exact_match`. **Verified
  end-to-end on the 0.21.6 DMG:** fresh install → `open` → menu bar spawns; scan
  finds 4 devices; connect Pixoo-1 (get_brightness → 60). Shipped v0.21.6.

- **CLEAN QUIT → v0.21.5 (2026-07-08): GUI terminates the menu-bar agent.** Root
  cause of the orphan: the native `divoom-menubar` is spawned detached and does NOT
  follow the daemon's `EVENT_SHUTDOWN` broadcast (the Python menubar did), so a
  plain quit left it in the tray. Fix: on a shared-lifecycle quit the GUI now calls
  `gui_main._terminate_menubar_agent()` (`pkill -f divoom-menubar`), gated by a new
  global flag **`quit_menubar_on_exit`** (default True) via
  `lifecycle_config.should_quit_menubar_on_exit(keep_alive, quit_menubar)` —
  `(not keep_alive) and quit_menubar`. New UI toggle: Settings → Connectivity →
  "Quit menu bar with dashboard". The 4 lifecycle API methods moved to
  `divoom_gui/lifecycle_mixin.py` (`LifecycleSettingsMixin`) so they stay
  pywebview-exposed while keeping `gui_api.py` under the 500-line limit (split, not
  trimmed). **Verified end-to-end on the installed 0.21.5 DMG:** default → quit
  kills app+daemon+menu bar (all clean); flag OFF → menu bar survives a quit.
  Tests: `test_should_quit_menubar_on_exit` (+ flag roundtrip). Suite for the
  touched area 49 green. NOTE: menu-bar **auto-spawn on launch** is intermittently
  not firing (pre-existing, unrelated to this change) — worth a separate look.

- **CLEAN HOMEBREW UPGRADE (2026-07-08): cask now stops all processes.** Verified
  the update UX: on `brew upgrade`, the app + `divoomd` + `divoom-menubar` were NOT
  being stopped — the cask had no `uninstall` stanza, and on quit the GUI shuts down
  `divoomd` (sends `shutdown`) but leaves `divoom-menubar` orphaned to launchd. Added
  an `uninstall` stanza to `ztomer/homebrew-tap` Casks/divoom-control.rb:
  `quit: "com.divoom.control"` (graceful GUI quit → daemon shutdown) + a `script:`
  `pkill -f 'Divoom.app/Contents/Frameworks/bin/divoom'` (reaps the orphaned menubar
  + any stubborn daemon); also fixed the stale `zap` socket path (`/tmp/divoom.sock`).
  `brew style` clean. **Proven through brew:** `brew uninstall --cask` prints
  "Quitting application … quit successfully" + "Running uninstall script" → zero
  survivors; reinstall + relaunch scans 4 devices. **KEY GOTCHA (now in RELEASING.md
  §5):** `brew upgrade` runs the *installed* version's uninstall stanza, so the
  0.21.3→0.21.4 hop still swapped the bundle under live processes (0.21.3 had none);
  0.21.4→later is clean. Never drop the stanza. Follow-up (not blocking): the GUI
  could terminate `divoom-menubar` on full quit so non-brew quits are clean too —
  left as-is since the tray agent is meant to persist a window-close (R24).

- **BLE SCAN CRASH FIXED (2026-06-30): disclaim the native daemon.** The bundled
  app "detected no Bluetooth devices" — `divoomd` crashed with a TCC `SIGABRT`
  (`NSBluetoothAlwaysUsageDescription` missing) the moment it scanned. The daemon
  itself was healthy: driven directly over `/tmp/divoom.sock` it returned both
  devices (Ditoo-light-2, Pixoo-1). Root cause was in `spawn_daemon`
  (`divoom_daemon/daemon_client.py`): it disclaimed TCC responsibility only for the
  Python daemon, spawning native `divoomd` as a plain `Popen` child that
  **inherited the launcher's responsible process**. When the `.app` was launched
  under another app (crash report: `responsibleProc: "claude"`, no BT usage
  description), CoreBluetooth SIGABRT'd it mid-scan → empty device list. From
  Finder/Dock it worked (responsible = `Divoom.app`, granted) — hence intermittent.
  **Fix:** disclaim the native daemon too (`use_rust or bundle_py is None`) so it's
  its own responsible process using its embedded `com.divoom.divoomd` plist (the
  `build.rs __TEXT,__info_plist` work, previously embedded but never the
  responsibility basis); `_spawn_disclaimed_macos` now takes an explicit `env` so
  `DIVOOMD_ENCODER_LIB` propagates. **Verified:** a `divoomd` spawned disclaimed
  *from a shell* (the prior SIGABRT context) scans cleanly and finds both devices,
  no crash. Teeth: `test_rust_daemon_is_tcc_disclaimed`. **Verified end-to-end
  through the shipped v0.21.4 DMG:** built → killed all entities → installed from
  `dist/Divoom-v0.21.4.dmg` → launched → the app's daemon scanned **4 devices**
  (Ditoo-light-2, Timoo-light-4, Pixoo-1, Tivoo-Max-light-3) and **connected to
  Pixoo-1** (`get_brightness` → 60 over live BLE), no crash. Shipped v0.21.4.

- **BLANK-GUI FIXED → v0.21.2 (2026-06-30):** the py2app `.app` opened a blank
  dashboard — pywebview's WKWebView won't load the `file://` UI inside a py2app
  bundle (renders fine as loose Python, so `./run.sh` always worked). Root-caused by
  driving the real app (WKWebView `loadRequest:` for file:// is blocked in a signed
  py2app `.app`; encoding/ATS/http-server/loadFileURL didn't help). **Fix: package
  the macOS app with PyInstaller** (`divoom.spec`) — verified end-to-end (dashboard
  renders, bundled `divoomd`+`divoom-menubar` spawn, Pixoo-1 connects).
  - Resolvers (`gui_main` web_ui + menubar binary; `daemon_client` divoomd + encoder
    dylib) are packaging-agnostic: PyInstaller `sys._MEIPASS` → py2app `RESOURCEPATH`
    → dev tree. Menu-bar "Launch Dashboard" works frozen (`launch.rs` empty-script).
  - `scripts/build_release.sh` builds via PyInstaller now; `setup_app.py` (py2app)
    kept for reference. Build venv needs `pyinstaller` + `psutil`.
  - Shipped: GitHub release v0.21.2 + Homebrew cask 0.21.2 (sha verified). v0.21.x
    py2app dmgs are superseded (their GUI was blank).
  - Known minor: web_ui logs a non-fatal `window.loadGalleryFilter is not a function`
    (gallery.js:354) — pre-existing, page still renders.

- **Deterministic mode test:** `scripts/hw_test_modes.py` walks every channel/mode +
  controls over the daemon socket with fixed args + read-back asserts (JSON report to
  test_reports/). Verified on Pixoo-1: full sweep **24/24** (6 clock faces, viz 0-2,
  vj 0-1, ambient r/g/b, scoreboard, solid+gradient image, brightness read-backs).
  `--mac`/`--all`/`--dwell`/`--quick`.
- **HARDWARE-VERIFIED the Rust daemon (2026-06-30):** against real Pixoo-1 over the
  socket — scan → connect → `get_device_name`="Pixoo-1" → `get_brightness`=75 →
  set 30/80 with read-back. (Getters error with a Python `AttributeError` on the
  Python daemon, so this confirmed the Rust path.) The Rust **menubar** also runs
  (spawned by the GUI); its tray visual is the only piece left for the maintainer to
  eyeball.
- **Bugfix:** `divoom_daemon/daemon_client.py` resolved the dev repo root with
  `parents[2]` (one level too high) → dev runs silently used the **Python** daemon;
  fixed to `parents[1]` so `./run.sh` spawns the **Rust** `divoomd`. (Bundle was
  unaffected — it uses `RESOURCEPATH`.)
- **`run.sh`** now kills any existing divoom processes (GUI / Python daemon / Rust
  `divoomd` / menubar) + clears stale sockets before launch.
- **CI fix:** `tests/test_no_emojis.py` diverged from the authoritative
  `tools/check_no_emoji.py` (flagged the permitted Kare icons ✓ ✗ ⚠); reconciled —
  CI green on Python 3.14.


- **ARCHITECTURE PIVOT (2026-06-30):** the egui UI is retired. Shipping stack is now
  **Python pywebview GUI + Rust daemon (`divoomd`) + Rust menubar (`divoom-menubar`)**.
  - New crate `native-port/divoom-menubar` (tao + tray-icon): windowless tray agent;
    polls the daemon socket for status/devices; Launch Dashboard / Open Notifications /
    Start+Stop Notifications / Quit; launches the GUI via `DIVOOM_GUI_PYTHON`/`SCRIPT`;
    Quit honours `keep_daemon_alive`. Ports `divoom_menubar/menubar.py`.
  - `divoom_gui/gui_main.py` spawns the Rust menubar (not the pyobjc one). pyobjc
    `divoom_menubar/` kept in-tree as reference only.
  - `native-port/divoom-ui/` (egui) DELETED; `scripts/build_native_app.sh` removed;
    `divoom-control-native` cask retired (tap pushed).
- **RELEASED v0.21.0 (2026-06-30):** CI bumped to Python 3.14; version 0.20.2 → 0.21.0;
  `scripts/build_release.sh` built `Divoom.app` + `Divoom-v0.21.0.dmg` (bundling +
  re-signing both `divoomd` and `divoom-menubar`); pushed `main` + tag `v0.21.0`;
  GitHub release created with the dmg; `divoom-control` Homebrew cask bumped to
  0.21.0 (sha256 `ede091f3…`, verified against the live asset) + tap pushed. `brew`
  confirms 0.21.0 is published. (Bundle is arm64, built on Apple Silicon — same as
  prior releases.)
  - Packaging: `setup_app.py` + `scripts/build_release.sh` bundle/sign `divoom-menubar`
    next to `divoomd` in the Python `.app`.
- **Dev helpers (root):** `./build.sh` builds the Rust daemon + menubar (+ encoder
  dylib; `--debug` for debug). `./run.sh` launches the Python GUI (which spawns the
  daemon + menubar); `--menubar` runs the tray alone for a smoke. Both source
  `tui/lib.sh` (Kare style). (Shippable `.app`: `scripts/build_release.sh`.)
- **NOT DONE YET:** on-hardware verification of the new stack (GUI ↔ daemon ↔ menubar
  on the 4 devices) — needs the maintainer to start the BLE daemon (TCC). Docs
  (PLANNING_NATIVE_UI / ROADMAP / PARITY_TRACKER) still describe the egui direction
  and need a pass.


- **NATIVE UI PORT — Phase 0 DONE (2026-06-29) — `docs/PLANNING_NATIVE_UI.md`:**
  building a native cross-platform Rust UI to replace the Python presentation
  layer (pywebview GUI + pyobjc menubar), making the shipped app Python-free.
  - **User constraints (locked):** full **native widgets** (NOT a webview — the
    earlier wry/webview plan is superseded, kept in the doc for record);
    **cross-platform** (macOS/Linux/Windows); **permissive licensing** — ship MIT
    now, maybe commercial later, never pay → **rules out Slint** (GPL-or-pay).
    **Toolkit chosen: egui/eframe** (MIT/Apache; picked over iced for pragmatism).
    The current `web_ui/` is the **visual reference only** (read for layout/look),
    not shipped; stays archived in-tree.
  - **VISUAL PARITY COMPLETE (2026-06-29):** every visual element of the current
    Python web UI is now reproduced natively. The last open item, an on-screen audio
    visualizer, was deliberately removed from the Python reference (Rams #10 — see
    `web_ui/widgets.js:15`), so it's N/A. Remaining follow-up (NOT parity): refresh
    the `divoom-control-native` Homebrew cask/dmg to a release when ready to publish
    (outward-facing — needs user go-ahead).
  - **Cloud gallery thumbnails DONE (2026-06-29):** new daemon command
    `get_animated_preview{file_id}` downloads + decodes a cloud file to a base64
    data-url (reuses `media::resolve_to_gif`; offline-tested vs cloud_fixtures).
    The UI gallery (under Pixel Art) renders `fetch_gallery`'s FileList as a grid,
    lazily fetches each tile's preview → texture, and pushes on click via
    `sync_artwork`. Needs cloud login for live data (Settings card exists). Only
    remaining visual-parity gap: the audio visualizer (needs local audio capture).
  - **Live device-screen preview DONE (2026-06-29):** the sidebar now renders the
    device's last-pushed frame (web parity). New `preview.rs` encodes RGB→data-url PNG
    and decodes data-url→egui texture (base64 + `image`); the app polls
    `get_device_activity` (~1.5s) and frames the UI pushes (pixel art) seed a
    client-side preview + persist via `set_device_activity`. Unit-tested +
    screenshot-verified (`DIVOOM_UI_FAKE_PREVIEW` debug seed). No daemon change.
    Remaining visual-parity gaps: gallery thumbnails (needs cloud auth), audio
    visualizer (needs local audio capture).
  - **egui 0.29 → 0.35 migration DONE (2026-06-29):** bumped eframe/egui/egui_extras
    to 0.35; ported the breaking API changes — `Rounding`→`CornerRadius` (u8),
    `Margin` is now `i8`, `painter.rect`/`rect_stroke` take a `StrokeKind`,
    `Frame::none()`→`Frame::NONE`, `FontData` wrapped in `Arc`, `ctx.style()/set_style`
    →`ctx.all_styles_mut`, `ViewportCommand::Screenshot(UserData)`, `TopBottomPanel`/
    `SidePanel` merged into `egui::Panel::{top,left,bottom}(id).exact_size(..).show(ui,..)`,
    and `eframe::App::update`→`logic(ctx)` (non-UI) + `ui(&mut Ui)` (panels). Clean
    debug+release build (only pre-existing dead-code warnings); screenshot-verified the
    Channels tab renders identically.
  - **Built so far** (`native-port/divoom-ui/`, eframe/egui 0.35):
    - `theme.rs` — Braun dark palette copied byte-for-byte from `web_ui/style.css`
      (`#121316` bg, `#ff5a1f` accent, 168px sidebar).
    - `shell.rs` — frameless integrated appbar (window controls + brightness/volume
      sliders + Settings pill + window-drag), sidebar (6 nav tabs w/ active orange
      accent + device panel pinned bottom), content host w/ Channels sub-tab row.
    - `daemon.rs` — NDJSON socket client on a worker thread (UI never blocks);
      `mpsc` to the egui loop. 2s status poll + scan/connect/device_call.
      `DIVOOM_SOCKET` env overrides the path (default `/tmp/divoom.sock`).
    - `app.rs` — state + frame orchestration; self-screenshot debug path
      (`DIVOOM_UI_SCREENSHOT=path` → egui `ViewportCommand::Screenshot`, saves a
      framebuffer PNG and exits; **no OS screen-record permission needed** — use
      this to verify the UI headlessly).
  - **Verified:** compiles clean; renders faithfully to the reference (screenshot);
    "daemon ready" shows live against a **no-BLE** `divoomd`
    (`cargo build --no-default-features`, run with `--socket /tmp/foo.sock`, point
    the UI at it via `DIVOOM_SOCKET`). Probed protocol: `get_status` (state +
    uptime_s), `device_call {method,args:[...]}` routes; `scan` is BLE-gated so the
    no-BLE core returns "not implemented" (expected — UI surfaces it).
  - **Phase 1 DONE** (`daemon.rs`): added a `subscribe` event thread (status
    pushes, auto-reconnect) + `divoomd` auto-spawn when the socket is absent
    (`DIVOOMD_BIN` / sibling-of-exe / PATH resolution + 4s poll-connect). Windows
    TCP transport still deferred to Phase 4 packaging.
  - **Phase 2 DONE** (`channels.rs`, new): the Channels tab now renders real
    per-channel panels reproduced from `web_ui` + `channels_grids.js`, each wired
    to the device_call leaf the Python `LightingApi`/`ToolsApi` use (verified vs
    the Rust dispatch + positional-arg convention):
    clock face → `display.show_clock [style]`; visualizer (12 EQ) →
    `display.show_visualization [n]`; VJ (16) → `display.show_effects [n]`;
    ambient (5 modes + color/swatches) → `display.show_light [hex,brightness,
    true,mode]`; scoreboard → `set_scoreboard [1,red,blue]`. Generic
    `selector_grid`/`cell_button`/`swatch` widgets. `DIVOOM_UI_CHANNEL` env picks
    the initial channel (screenshot aid). **Deferred to Phase 3:** Text push
    (needs the bitmap-font→image render from `LightingApi._render_text_png`) and
    the Sessions panel (Sleep Aid). Clock color uses `set_clock_rich` (face is
    white-only on the device via show_clock).
  - **Verified** by self-screenshots: clock/ambient/scoreboard panels render
    faithfully against a no-BLE daemon (device_call returns "no device" — expected
    without hardware; wiring is correct).
  - **Phase 3a DONE** (`device_settings.rs`, new): the **Device Settings** tab —
    device name, clock format (12/24h), temp unit, power mode, auto power-off,
    orientation (0/90/180/270), mirror/flip, confirm-gated factory reset; each
    wired to the device_call leaf the Python `ToolsApi` uses (verified vs Rust
    dispatch). **`sync_time` is a real daemon gap** (Python uses `DateTimeCommand`
    directly, not a device_call leaf) → button disabled w/ note; **TODO: port
    DateTimeCommand to a `divoomd` device_call leaf** for full parity.
    Added generic `Cmd::Raw`/`Update::Reply` (top-level daemon RPC w/ reply tag,
    stored in `app.replies`) for the remaining tabs; `DIVOOM_UI_TAB` screenshot aid.
  - **GAP-CLOSURE RUN (2026-06-29, "close the gaps across daemon/menubar/app"):**
    closed the daemon gaps + menubar polish. **sync_time** (daemon `set_date_time`
    0x18 + UI button), **cloud login** (daemon `save_credentials` + Settings card,
    unblocks gallery; split cloud_store.rs/cloud_cmds.rs for the 500-line gate),
    **test notification** (was an app gap — leaf existed; added UI control),
    **menubar status-color glyph**. **Sole remaining real gap: a native MCP server
    in divoomd** (the Python MCP is a `divoom_lib.cli mcp-server` subprocess; a
    Python-free bundle needs a Rust MCP stdio JSON-RPC server, ~13 tools → a large
    standalone workstream — needs an explicit go-ahead). Device-dependent niche
    (Custom Art, Hot Channel, audio viz, wall presets) still need hardware.
  - **PHASE 4b DONE — native app verified on hardware + shipped alongside
    (2026-06-29):** drove the real `.app` via computer-use (user approved): launch →
    UI spawns sibling `divoomd` → BLE scan found Tivoo-Max/Timoo/Pixoo (NO TCC
    crash — the embedded Info.plist makes the bundle its own responsible process) →
    connected to Tivoo-Max → UI controls hit the device (Rainbow clock; brightness
    0→read 0→restored 54; volume read back 5/15 on connect). Shipped ALONGSIDE the
    Python app (user picked "both"): `build_native_app.sh` makes
    `Divoom-Native-v0.20.2.dmg`, uploaded to the v0.20.2 release; new cask
    `divoom-control-native` (Projects/homebrew-tap, pushed, brew-style clean,
    brew-fetch verified). Python `divoom-control` cask untouched.
    Install: `brew install --cask ztomer/tap/divoom-control-native`.
  - **NATIVE PACKAGING (2026-06-29, non-destructive part of Phase 4b):**
    `scripts/build_native_app.sh` assembles `dist-native/Divoom Native.app`
    (Python-free: `Contents/MacOS/{divoom-ui, divoomd, libdivoom_compact.dylib}` +
    BT Info.plist, adhoc-signed). The UI spawns the sibling daemon and passes
    `DIVOOMD_ENCODER_LIB` (sibling dylib) so encoding works in the bundle. Separate
    `dist-native/` artifact (gitignored) — does NOT touch the py2app build / cask /
    defaults. Verified assembly+sign+plist; NOT launched (bundled daemon is the BLE
    build → TCC crash from a headless shell). **STILL USER-GATED:** first launch +
    one-time Bluetooth grant, then the actual cutover (flip the default launcher to
    the native app, update the Homebrew cask). Python UI stays the reference.
  - **MCP GAP CLOSED (2026-06-29):** `divoomd mcp` — native MCP stdio JSON-RPC
    server (`native-port/divoomd/src/mcp.rs` + `mcp_tools.rs`), ported from
    `mcp_server.py`/`mcp_tools.py`. Daemon-routed bridge (connects to DIVOOM_SOCKET,
    forwards tools/call → device_call); 13 tools; verified end-to-end + unit-tested;
    added tokio `io-std`. **All daemon/menubar/app parity gaps are now closed.** The
    only un-ported items are device-dependent niche (Custom Art browser, Hot Channel,
    wall presets) + audio-capture (audio visualizer) — need hardware. To use the MCP
    server, point an MCP host at `divoomd mcp` (it needs a running daemon).
  - **FUNCTIONAL PARITY REACHED (2026-06-29, after the /loop-until-parity run, 8
    iterations).** See **`docs/PARITY_TRACKER_NATIVE_UI.md`** for the full per-feature
    record + the "PARITY STATUS" closeout. All portable/verifiable UI features are
    ported (every tab + channel sub-tab, Device Settings+FM, Schedule alarms/
    memorial/timeplan, Live Widgets feeds+temperature, Pixel Art paint+gallery,
    Text push via embedded 5x7 font, read-backs, tray device section). Remaining
    items are BLOCKED, categorized in the tracker: **daemon gaps** (cloud login,
    test notif, sync_time, MCP — need new divoomd commands), **device-dependent
    niche** (Custom Art, Hot Channel, wall presets), **audio capture** (audio viz),
    and **minor polish**. The daemon gaps are the only ones blocking real end-user
    features — they need daemon-side work (user to authorize separately).
  - **EARLIER CORRECTION (2026-06-29):** the initial "Phase 3 complete / feature-
    complete" claim was **overstated** (~1/3 wired); the loop above fixed it. The app shell, most of Channels, and Device Settings are solid; but the
    **Live Widgets tab is mis-mapped** (shows the gallery; should be live data feeds
    — music/stocks/sysmon/weather), the **gallery belongs under Pixel Art**, and
    Sessions/Weather/FM/Memorial/Presets/cloud-login/MCP/notification-routing + many
    read-backs are missing. See **`docs/PARITY_TRACKER_NATIVE_UI.md`** (the live
    "/loop until parity" record). The per-tab bullets below describe what RENDERS,
    not full parity.
  - **Phase 3 (3a/3b/3c)** — all 7 sidebar tabs render (placeholder removed):
    `settings.rs` (notifications start/stop/status, LAN probe/connect, keep-alive,
    MCP deferred), `schedule.rs` (5 alarm slots → `alarm.set_alarm`), `pixel_art.rs`
    (16x16 paint editor → `show_image` rgb kwargs via `Cmd::Raw`), `wall.rs`
    (device slots → `wall_configure`), `widgets.rs` (gallery `fetch_gallery` — item
    count + honest cloud-auth note; thumbnail render deferred). All verified by
    self-screenshot. **Deferred (documented):** gallery thumbnail render + apply
    (needs cloud auth + remote image fetch), Channels Text push (needs bitmap-font
    →image render), Channels Sessions (Sleep Aid), clock color (`set_clock_rich`).
  - **Phase 4a DONE** — `tray.rs`: cross-platform native tray/menubar via
    **tray-icon** (MIT) mirroring `divoom_menubar` — Show Dashboard / Start-Stop
    Notifications (label tracks live state) / Quit. Built lazily on first frame,
    events polled from the eframe loop; same-process (Show Dashboard focuses the
    window). Builds + runs without crash; **the system-menubar item needs USER
    visual confirmation** (can't be captured by the in-app framebuffer screenshot).
  - **REMAINING — Phase 4b (USER-GATED, not done autonomously):** per-OS packaging
    (macOS `.app` + real Info.plist w/ BT strings + `LSUIElement`; codesign; dmg;
    Homebrew cask) and **cutover** (flip the default launcher from the Python GUI to
    `divoom-ui`). Cutover changes what ships + needs the macOS BT grant (physical
    click) + user review — left for the user. Python UI stays the reference, never
    deleted. Also pending: the `sync_time` daemon device_call leaf (task chip
    spawned) to re-enable Device Settings' "Update device time".
  - **How to run/verify the UI:** `cargo build` in `native-port/divoom-ui`; start a
    no-BLE daemon (`divoomd --socket /tmp/x.sock` from a `--no-default-features`
    build) and run `DIVOOM_SOCKET=/tmp/x.sock ./target/debug/divoom-ui`. Headless
    screenshot: add `DIVOOM_UI_SCREENSHOT=out.png` (+ `DIVOOM_UI_TAB=`/`DIVOOM_UI_
    CHANNEL=` to pick the view). Real-device exercise needs the user to start the
    BLE daemon (Claude's shell can't BLE-run it — TCC crash).
  - **Gotcha:** can't BLE-run `divoomd` from Claude's shell (TCC crash) — test the
    UI against the **no-BLE** daemon build. `screencapture` CLI yields a black
    frame (no Screen-Recording grant) → use the in-app self-screenshot instead.
- **PARITY ACHIEVED (2026-06-29, /loop "until parity with Python") — COMPLETE:**
  - **device_call method parity: 54 → 0 gaps** vs the Python Divoom API (excluding
    internal `protocol.*` plumbing). New Rust submodules `device_call/{animation,
    music,drawing}.rs` + additions to basic/system/tools, all ported verbatim from
    `divoom_lib` with wire-byte mock tests pinning payloads + LE/BE orders. Covers
    display channels, control, weather, light/tool read-backs, hot_update, the
    animation gif/user-define primitives, SD-card music, and the drawing-pad
    subsystem (`pic_scan_ctrl` 0x35 ported but flagged UNVERIFIED — no 0x35 in the
    APK). Re-run the audit any time: introspect the Divoom facade, dedupe by
    underlying qualname, diff leaf names vs the Rust `device_call` match arms.
  - **Cloud image decode parity DONE + verified** (the dominant gap): ported
    `media_decoder.resolve_to_gif` — magic 9/18/26 (AES + LZO1X via `minilzo-rs` +
    `_compact_tiles`) + 0xAA → frames → GIF (`src/media.rs`); fixed a real 0xAA bpp
    bug. BYTE-PARITY tests vs Python oracle fixtures (`tests/cloud_fixtures/`).
  - **monthly_best fixed** (connect/disconnect command names) + **gated behind
    `DIVOOMD_MONTHLY_BEST`** (default off; parity with Python's separate opt-in
    daemon).
  - **Rust is now the default daemon** (`DIVOOM_USE_RUST_DAEMON` defaults on when
    `divoomd` is present; Python kept as reference/fallback, **never deleted**).
  - **Device-verified**: the decoded magic-18 cloud animation renders on **Pixoo,
    Tivoo-Max, Timoo** (Ditoo was off-air). `cargo test` 70/70 both matrices; all
    parity verified offline before device pushes.
  - **Open**: re-verify Ditoo when it's back in range; the niche drawing/SD-music/
    animation methods are wire-tested but NOT hardware-verified (no device flows to
    exercise them). The connect-flakiness mitigation (poll-until-found) helps but
    BLE discovery can still miss a sleeping device.
  - **Gotcha:** `tests/test_rust_daemon_parity.py` spawns `target/{debug,release}/
    divoomd` and prefers debug — so `cargo test --no-default-features` (which builds
    a NO-BLE debug binary) makes the BLE/SPP parity tests fail with "BLE support is
    disabled". Run `cargo build` (default features) before the Python parity suite.
  - **Parity verified complete across ALL dimensions:** top-level socket commands
    (0 gaps, Rust superset), device_call methods (0 gaps — leaf + exact dotted
    string; the few client calls to non-existent methods degrade identically),
    LAN methods (0 gaps), cloud decode (byte-verified). The loop's goal is met.

- **NATIVE PORT HARDENING — Phases 1–4 DONE; Phase 5 gated (2026-06-28):**
  Phase 4 Tier B was verified on a **real Timoo over BLE** via the granted `.app`
  (grant persisted, autonomous): scan → connect → brightness round-trip (read-backs
  work) → exclusive gating → MCP-via-Rust `set_brightness(level=65)` → disconnect.
  Two bugs surfaced + fixed HW-verified: BLE `connect` poll-until-found (was a single
  3s window → reconnect misses; 3/3 clean no-pre-scan reconnects now) and a missing
  `shutdown` command (added; clean exit confirmed). Phase 5 is **gated** — see Open
  threads: top-level commands reached parity (`shutdown`/`probe_lan`/`sync_artwork`)
  but verification then exposed a deeper cloud image-decode gap (magic 9/18/26/0xAA),
  and per user directive the Python backend is to be **archived as reference, never
  deleted**.
  - **Phase 1 (commit `f7e0e7c`):** fixed the broken `--no-default-features` build.
    Root cause: the `DeviceTransport` device-I/O method layer was `ble`-gated even
    though it delegates to non-ble Spp/Lan/Mock, and `BleResult` lived in the gated
    `ble` module. Fix: relocated `BleResult` to `transport.rs` (ble.rs re-exports),
    un-gated the method layer + `NativeEncoder`/`encoder()` + `device_call` (gating
    only the inner `DeviceTransport::Ble` arms via `!matches!(Lan)`), and rewrote
    `wall.rs` to use the enum method layer (also fixed a latent Spp/Mock wall
    silent-fail). **`cargo test` = 62 green; `cargo test --no-default-features` = 62
    green.** The full command surface + MockTransport now build/test hardware-free.
  - **Phase 2 (commit `762c6ad`):** added `rust-core` (ubuntu, no-ble gate) and
    `rust-ble` (macos, full ble) jobs to `.github/workflows/tests.yml`. This is the
    gate that would have caught the e4bd424 regression.
  - **Phase 3 (500-LOC):** split `live_jobs.rs` (965) →
    `live_jobs/{mod(428),render(290),music(245)}.rs`; trimmed `daemon.rs` (502→482,
    moved `find_encoder_lib` into `native_encode.rs`). Added
    `tools/check_file_size.py` (500-line gate) → CI + pre-commit. No file violates.
  - **Phase 4 Tier A (hardware-free E2E):** `test_mock_exclusive_mode_gating`
    (Rust: acquire/steal-reject/foreign-token-deny/release/re-acquire + wire bytes)
    and `test_rust_mcp_via_daemon` (Python: MCPServer + DaemonDeviceProxy →
    spawned Rust daemon → `device_call` round-trip). Rust 63/63 both matrices;
    parity suite 12 passed / 1 skipped.
  - **Phase 4 Tier C (best-effort, no Win/Linux hardware):** added
    `rust-ble-linux` + `rust-ble-windows` `continue-on-error` compile-only CI jobs.
    Real-radio on those OSes is explicitly out of scope (no hardware) — never
    claimed verified.

- **Phase 5 commands (2026-06-28 late):** added `probe_lan` + `sync_artwork`
  (HW-verified) — top-level socket commands now match the Python daemon. BUT
  verification exposed a deeper gap below.

### Open threads

- **BLOCKER — cloud image-decode parity (the big one).** The native daemon only
  resolves GIF/PNG/JPG + magic-43; real Pixoo gallery content is dominated by
  **magic 9/18/26 (AES; 18/26 also LZO+tiled) and 0xAA (hot)** containers — 0 of 3
  gallery pages were directly renderable. `sync_artwork`/`monthly_best` now
  honest-error on these (no more device-bricking) but can't render them. Complete
  parity requires porting `media_decoder.resolve_to_gif` fully: decode those
  containers → frames → GIF-encode (image crate) so the unified `show_image` path
  renders them. magic 18/26 needs an **LZO dependency** + `_compact_tiles`. Ground-
  truth oracle available: the Alexlay magic-18 file + Python's decoded 32×32/6f GIF.
  Verify per-format against Python, then on the 4 devices (Ditoo/Tivoo-Max/Timoo/
  Pixoo). **Existing Rust decoders:** `art_codec` has AES-CBC + `decode_cloud_magic9`
  + `decode_hot_file` (raw frames) + `decode_magic43`; MISSING: magic 18/26 LZO,
  frame→GIF encode.
- **device_call method-level parity audit** — top-level commands are at parity;
  still owe a method-by-method diff of `device_call` (Rust `device_call/*` vs the
  Python `Divoom` API surface) to confirm nothing else is missing.
- **Phase 5 default-flip** — gated on the decode parity above; flip
  `DIVOOM_USE_RUST_DAEMON` default on (prefer Rust when the binary exists, else
  Python) in `daemon_client.py`, then soak GUI/menubar/MCP.
- **Phase 5 archival = ARCHIVE, NOT DELETE (user directive 2026-06-28).** Keep the
  Python `divoom_daemon`/`divoom_lib` as the **reference implementation** (it's
  mostly complete and is the parity oracle). Do not delete it. "Archival" means
  marking Rust authoritative in docs while Python stays in-tree for reference +
  fallback.
- **Phase 5 archival (NEEDS USER SIGN-OFF)** — moving/deleting `divoom_daemon/` is
  irreversible and breaks the GUI/menubar/CLI imports; hold until a green soak +
  explicit go. Will NOT be done autonomously.
- _(RESOLVED this round: all of Phase 4 — Tier A, B (real device), C; plus the BLE
  connect-robustness bug and the `shutdown` parity gap.)_

- **DOC CLEANUP — native-port docs retired/pruned (2026-06-28):** Retired the
  obsolete `docs/PLANNING_NATIVE_PORT.md` (original evaluate-and-plan doc, fully
  executed now that the port shipped R54–R56); its decision summary moved into
  `docs/ROADMAP.md` and its 5 source-comment references were repointed there.
  Pruned this handoff's long R53.x-and-older tail (history retained in CHANGELOG +
  git). The active forward plan for the Rust port is
  `docs/PLANNING_NATIVE_PORT_HARDENING.md`.

- **RUST MOCK TRANSPORT & TEST COVERAGE INFRASTRUCTURE (2026-06-28):**
  Implemented MockTransport for offline Rust daemon testing and shipped 4 new E2E mock tests verifying wire byte patterns for core commands. This enables testing device_call serialization without real hardware.

  **Changes shipped:**
  - `src/mock_transport.rs` [NEW]: `MockTransport` struct with `send_command()` that logs `(cmd_id, payload)` tuples into a `Vec<(u8, Vec<u8>)>` and simulates generic ACK responses.
  - `src/mock_device_tests.rs` [NEW]: 4 `#[tokio::test]` E2E tests — `set_clock_rich` (0x45 APK C2 layout), `show_clock` (0x45 hass-divoom layout), `set_brightness` (0x74), `set_volume` (0x08). All assert exact wire byte patterns.
  - `src/transport.rs`: Added `Mock(MockTransport)` variant to `DeviceTransport` enum with delegated trait methods.
  - `src/daemon_connect.rs`: Added `{"mock": true}` connect path + `Mock` arm in `cmd_disconnect`.
  - `src/device_call/mod.rs`: Added `DeviceTransport::Mock(_)` to the BLE-like device gate.
  - `src/wall.rs`, `src/daemon.rs`, `src/macos_notifications.rs`: Added exhaustive `Mock(_)` match arms.
  - `scripts/rust_coverage.sh` [NEW]: Helper script for `cargo-llvm-cov` code coverage reporting.

  **Tests:** Rust **62 tests passed** (11 lib + 46 integration + 4 mock + 1 native-encode); Python **16 passed, 1 skipped** (daemon parity suite).

- **NATIVE PORT: DIVOOM CLOUD AUTHENTICATION, GALLERY SYNC, MONTHLY BEST LOOP, & CLOCK OVERLAY ALIGNMENT (2026-06-28):**
  Successfully completed the remaining native port features in the Rust daemon (`divoomd`) to achieve 100% parity with the authoritative Python daemon and library. The daemon can now run completely standalone, handling cloud logins, category file queries, scheduled monthly best background scrapers, precompiled animation streams, and APK-aligned clock layouts.

  **Changes shipped:**
  - `src/cloud.rs` [NEW]: Ports email login (`POST /UserLogin`), guest HMAC-MD5 signing (`POST /User/NewGuest`), UTC time sync, configuration parser (`config.ini`), cache manager (`auth_token.json` with 0o600 file write), cloud gallery categories retrieval (`/GetCategoryFileListV2`), and failure cooldown mechanism. Contains 5 inline unit tests verifying crypt/cache lifecycles.
  - `src/monthly_best.rs` [NEW]: Ports the background scraper ticker loop which polls `hotchannel.json`, extracts Magic 43 container GIFs, connects to target displays on interval, downsamples files, and streams native animation payloads.
  - `src/device_call/basic.rs`: Implemented `"animation.stream_animation_8b"` for precompiled stream uploads and `"display.set_clock_rich"` for APK C2() aligned clock coordinate layouts.
  - `src/daemon.rs`: Exposed `"get_credentials"`, `"get_cached_credentials"`, and `"fetch_gallery"` socket dispatch endpoints.
  - `src/lib.rs` & `src/main.rs`: Registered new modules and spawned the `monthly_best` background loop task at daemon startup.
  - `Cargo.toml`: Added `md-5` and `hmac` dependencies.
  - `tests/test_rust_daemon_parity.py`: Shipped `test_rust_cloud_auth_endpoints`, `test_rust_fetch_gallery`, and `test_rust_set_clock_rich` integration tests verifying all new socket calls.

  **Tests:** Rust 58 passed; Python 1703 passed, 87 skipped. (Verified with new unit and integration tests).


- **NATIVE PORT: BLUETOOTH CLASSIC SPP INTEGRATION VIA PYTHON SUBPROCESS BRIDGE (2026-06-28):**
  Successfully implemented Bluetooth Classic SPP support in the native Rust daemon (`divoomd`) using a lightweight Python subprocess bridge (`spp_bridge.py`). This allows the native daemon to connect to older classic SPP devices (e.g. Tivoo-Max) by reusing the proven Python `BTSppTransport` stack under the hood, bypassing complex Objective-C/IOBluetooth binding issues.

  **Changes shipped:**
  - `divoom_daemon/spp_bridge.py` [NEW]: Standard JSON-line standard I/O bridge wrapping `BTSppTransport` for classic Bluetooth connection management.
  - `native-port/divoomd/src/spp.rs` [NEW]: Native Rust `SppTransport` implementing tokio process spawning, input/output piping, and `0x8B` animation streaming parity.
  - `native-port/divoomd/src/transport.rs`: Added the `Spp` variant to `DeviceTransport` and delegated all relevant transport calls.
  - `native-port/divoomd/src/daemon_connect.rs`: Routed connection requests to `SppTransport` when `use_ios_le_protocol` is `false`.
  - Exhaustive match coverage updated across `daemon.rs`, `live_jobs.rs`, `wall.rs`, `art.rs`, `art_hot.rs`, and `macos_notifications.rs` to handle `DeviceTransport::Spp` cleanly.
  - `tests/test_rust_daemon_parity.py`: Shipped `test_rust_spp_connect_failure_integration` E2E test verifying dynamic python bridge subprocess spawning/error propagation, and added `test_rust_hardware_parity` executing live scans, connection, get/set brightness, and disconnection on real Divoom hardware (Tivoo-Max).
  - Renamed manual smoke-test `test_display_aliases.py` to `smoke_display_aliases.py` to fix pytest collection.

  **Tests:** Rust 51 passed; Python 1702 passed, 87 skipped. (Verified with new integration and hardware tests).

- **NATIVE PORT: ALIGN NOTIFICATION SERVICE, COMMAND SCHEMAS, TCP/TOKEN AUTH, --mac OPTION & RUST AUTO-SPAWN (2026-06-28):**
  Aligned the native Rust daemon's macOS notification service monitor (`macos_notifications.rs`), routing, and command responses with the ground-truth Python daemon. Ported the headless TCP server listener, token authentication features, and `--mac` option default address configurations. Shipped the `DIVOOM_USE_RUST_DAEMON` auto-spawner integration in the Python clients and GUI launcher.

  **Changes shipped:**
  - `src/macos_notifications.rs`: Refactored to query the Notification Center SQLite DB (Sonoma/Sequoia paths + Group Containers fallback) using a read-only `rusqlite` connection (removing `sqlite3` CLI subprocess calls). Parsed binary plists with the `plist` crate to retrieve `app`, `title`, and `body` fields. Implemented routing and tracking for `seen`, `routed`, and `dropped` counters, duplicate suppression, and health checks.
  - `src/daemon.rs`: Aligned `get_status`, `start_notifications`, `stop_notifications`, `notification_status`, and `set_routing` command payloads and response shapes to be identical to the Python daemon. Exposed status and notification events to socket subscribers. Relocated `DeviceTransport` to `src/transport.rs` and moved argument/blob parsing into `src/device_call/mod.rs` to keep `daemon.rs` strictly under 500 lines. Updated `device_status` to return the stored default MAC when disconnected.
  - `src/main.rs`: Supported `--host`, `--port`, `--token`, and `--mac` CLI flags (with `DIVOOM_DAEMON_TOKEN` env variable fallback). Enforced token requirement when binding to a TCP port, and wired TCP listener concurrently with Unix listener. Passed the default MAC config to the Daemon.
  - `src/socket_server.rs`: Made `serve_connection` generic over the stream type (`AsyncRead + AsyncWrite + Unpin`) to serve both Unix and TCP streams. Added `serve_tcp` and implemented constant-time comparison for token verification.
  - `tests/test_rust_daemon_parity.py`: Shipped a new Python integration test suite verifying the socket response shapes, token auth, and default MAC address config of the compiled Rust daemon subprocess using Python `DaemonClient`.
  - `divoom_daemon/daemon_client.py`: Added support for `DIVOOM_USE_RUST_DAEMON` inside `spawn_daemon()`, enabling Python clients/GUI launcher to dynamically auto-spawn and run the compiled Rust `divoomd` daemon instead of the default Python daemon.

  **Tests:** Rust 51 passed; Python 1711 passed, 87 skipped. (Verified with new integration tests).

- **NATIVE PORT: ART SYNC, HOT-UPDATE, WALL, LIVE JOBS, macOS NOTIFICATIONS + 500 LOC SPLITS (2026-06-26):**
  Ported the remaining high-level subsystems to the native Rust daemon (`divoomd`). All files comply with 500 LOC.

  **New modules shipped:**
  - `art.rs` (331): custom art push/query, cloud CDN download, hot-update dispatch
  - `art_codec.rs` (197): AES-128-CBC (pure Rust), magic-43/9/0xAA frame decoders, image rescale
  - `art_hot.rs` (251): hot-update manifest, SHA-1 verify, BLE chunk streaming
  - `wall.rs` (457): DivoomWall multi-panel coordinator + `cmd_wall_configure` (moved from daemon.rs)
  - `live_jobs.rs`: background widget loops (system monitor, stocks, weather, music album cover)
  - `macos_notifications.rs` (233): SQLite `usernoted` monitor via sqlite3 CLI, ANCS push
  - `daemon_connect.rs` (83): connect/disconnect/scan extracted from daemon.rs

  **Refactored:**
  - `daemon.rs` (498): thin delegations; `tx` field made `pub(crate)`
  - `lib.rs`: all new modules registered
  - `ble.rs`: `wait_for_any_response` for hot-update multiplexing
  - `lan.rs`: `probe()` method for LAN validation

  **Tests:** Rust 51 passed; Python 1686 passed, 87 skipped.
  Playwright UI failures (12 + 6 errors) are pre-existing missing-browser-binary issues, unrelated.

  **Commit:** `7cb5240`

  Modularized the native Rust daemon's (`divoomd`) `device_call` commands logic to strictly adhere to the 500 LOC limit constraint:

  **Modularization:** Extracted all inline command match arms and helper functions out of `daemon.rs` and moved them into submodules inside the `src/device_call/` directory:
  - `src/device_call/basic.rs` (305 lines)
  - `src/device_call/alarm.rs` (254 lines)
  - `src/device_call/sleep.rs` (198 lines)
  - `src/device_call/timeplan.rs` (102 lines)
  - `src/device_call/tools.rs` (150 lines)
  - `src/device_call/text.rs` (150 lines)
  - `src/device_call/game.rs` (90 lines)
  - `src/device_call/design.rs` (120 lines)
  - `src/device_call/system.rs` (285 lines)
  This shrunk `daemon.rs` from 1944 lines down to **317 lines**, bringing the entire daemon repository in line with the 500 LOC rule.

  **Feature Gating & Clean Compilation:** Gated the submodules in `mod.rs` and all BLE-specific imports/fields in `daemon.rs` behind `#[cfg(feature = "ble")]` to ensure warning-free and error-free compilation both with and without default features.

  **E2E & Parity Tests:** All 55 Rust tests pass successfully. Full Python pytest suite passes cleanly with 1706 passed, 87 skipped.

- **NATIVE PORT: SCHEDULING COMMANDS (2026-06-23 14:35 EDT):**
  Ported the alarm, sleep, and timeplan scheduling commands to the native Rust daemon (`divoomd`):

  **Alarm:** Ported `alarm.get_alarm_time`, `alarm.set_alarm`, `alarm.set_alarm_gif`, `alarm.get_memorial_time`, `alarm.set_memorial_time`, `alarm.set_memorial_gif`, `alarm.set_alarm_listen`, `alarm.set_alarm_volume`, and `alarm.set_alarm_volume_control` (with direct name and alias dispatch). Deserialized and parsed 10-byte alarm info blocks and 39-byte memorial blocks.

  **Sleep:** Ported `sleep.show_sleep`, `sleep.get_sleep_scene`, `sleep.set_sleep_scene_listen`, `sleep.set_scene_volume`, `sleep.set_sleep_color`, `sleep.set_sleep_light`, and `sleep.set_sleep_scene` (with direct name and alias dispatch). Deserialized and parsed 10-byte sleep scene status blocks.

  **Timeplan:** Ported `timeplan.set_time_manage_info` and `timeplan.set_time_manage_ctrl` (with direct name and alias dispatch). Mapped to command codes `0x56` and `0x57` respectively.

  **E2E & Parity Tests:** Updated the `ported_commands_route_to_device_call` integration test in `tests/daemon_behavior.rs` to verify that all newly implemented commands and their aliases correctly match in the router and dispatch to the device transport. Verified both compilation and test suite correctness with and without the `ble` feature gate. Full Python pytest suite passes with 1706 passed, 87 skipped.

- **NATIVE PORT: TOOL & NOTIFICATION COMMANDS (2026-06-23 14:30 EDT):**
  Ported the device tool commands (scoreboard, timer, countdown, noise meter) and notification display commands to the native Rust daemon (`divoomd`):

  **Scoreboard:** Ported `"scoreboard.set_scoreboard"`, `"set_scoreboard"`, `"scoreboard.get_scoreboard"`, and `"get_scoreboard"` (0x71/0x72 commands with type 1).

  **Timer:** Ported `"timer.set_timer"`, `"set_timer"`, `"timer.get_timer"`, and `"get_timer"` (0x71/0x72 commands with type 0).

  **Countdown:** Ported `"countdown.set_countdown"`, `"set_countdown"`, `"countdown.get_countdown"`, and `"get_countdown"` (0x71/0x72 commands with type 3).

  **Noise Meter:** Ported `"noise.set_noise"`, `"set_noise"`, `"noise.get_noise"`, and `"get_noise"` (0x71/0x72 commands with type 2).

  **Notification Display:** Ported `"device.show_notification"`, `"show_notification"`, `"notification.show_notification"`, `"device.show_notification_text"`, `"show_notification_text"`, and `"notification.show_notification_text"` (0x50 command handling icon-only and icon+text variations).

  **E2E & Parity Tests:** Updated the `ported_commands_route_to_device_call` integration test in `tests/daemon_behavior.rs` to verify that all newly implemented commands and their aliases correctly match in the router and dispatch to the device transport. Verified both compilation and test suite correctness with and without the `ble` feature gate. Full Python pytest suite passes with 1706 passed, 87 skipped.

- **NATIVE PORT: REMAINING DEVICE CALL COMMANDS (2026-06-23 10:23 EDT):**
  Ported the rest of the high-value `device_call` commands to the native Rust daemon (`divoomd`):
  
  **Volume Control:** Ported `"music.get_volume"`, `"get_volume"`, `"music.set_volume"`, and `"set_volume"` (0x08/0x09 commands).
  
  **FM Radio:** Ported `"radio.set_radio_frequency"`, `"set_radio_frequency"`, `"radio.set_radio"`, and `"set_radio"` (0x61 command) taking a 2-byte little-endian frequency.
  
  **Low Power Switch:** Ported `"device.get_low_power_switch"`, `"get_low_power_switch"`, `"device.get_low_power"`, `"get_low_power"`, `"device.set_low_power_switch"`, `"set_low_power_switch"`, `"device.set_low_power"`, and `"set_low_power"` (0xb2/0xb3 commands).
  
  **Auto Power Off:** Ported `"device.get_auto_power_off"`, `"get_auto_power_off"`, `"sound.get_auto_power_off"`, `"device.set_auto_power_off"`, `"set_auto_power_off"`, and `"sound.set_auto_power_off"` (0xab/0xac commands) taking a 2-byte little-endian minutes.
  
  **E2E & Parity Tests:** Added the `ported_commands_route_to_device_call` integration test to verify that all newly implemented commands are correctly matched in the router and dispatch to the device transport (failing honestly with "no device connected"). Verified both compilation and test suite correctness with and without the `ble` feature gate. Full Python pytest suite passes with 1706 passed, 87 skipped.

- **NATIVE PORT: EVENT SUBSCRIPTION & DEVICE NAME COMMANDS (2026-06-23 10:15 EDT):**
  Four changes in the native Rust daemon (`divoomd`):

  **Event Subscription & Broadcast:** Extended the socket server with support for the
  `"subscribe"` command. When a client connects and subscribes, the server immediately
  replies with the initial status snapshot (`{"type":"status", "state":"idle"}` or `"active"`)
  and then holds the connection open, streaming real-time broadcast events (such as BLE
  connection state changes). We use `tokio::select!` to multiplex socket reading (to detect
  peer disconnects) and event broadcasting (from a shared `tokio::sync::broadcast::Sender`),
  achieving self-cleaning, resource-safe event delivery.
  
  **Friendly Name Cache:** Added a thread-safe `device_name` cache (`Mutex<Option<String>>`)
  to `BleTransport` to avoid redundant BLE name queries (0x76 read is slow/flaky on some models).
  The cache is populated from peripheral advertisement properties on connect.
  
  **New Device Commands:** Ported `"device.get_device_name"` (retrieves from cache, falling back
  to 0x76 BLE query) and `"device.set_device_name"` (writes via 0x75 BLE command and updates cache).
  
  **E2E & Parity Tests:** Added `subscription_and_event_broadcast` integration test to verify the
  subscriber socket, and `device_name_commands_route_to_device_call` to check command dispatch.
  All Rust tests pass (with and without `ble` feature). E2E-smoke-tested `test_subscribe.py` against
  real Divoom hardware: successfully subscribed, connected, and observed the broadcasted status
  transition (`idle` -> `active`). Python suite: 1706 passed, 87 skipped.

- **FEISHIN + KASET + CARD PADDING ROUND (2026-06-23 00:45 EDT):** Three changes.

  **Feishin album art integration:** Added `/Applications/Feishin.app` (Electron-based
  Navidrome client) as the first-checked now-playing source in
  `media_source.py:get_current_playing_track()`. The integration works by:
  1. Checking if Feishin is running via `pgrep`
  2. Extracting Navidrome Subsonic API credentials from Feishin's Chromium Local
     Storage (LevelDB files at `~/Library/Application Support/Feishin/Local Storage/leveldb/`)
  3. Querying the Navidrome `/rest/getNowPlaying.view` Subsonic API endpoint
  4. Building a cover art URL from `/rest/getCoverArt.view` when available
  Credentials are cached for 60s to avoid repeated LevelDB file scans. The Navidrome
  server URL + auth params (`u=...&s=...&t=...`) are extracted via regex scanning of
  the LevelDB .ldb/.log files. Tests: 4 new Feishin-specific tests + updated Spotify
  test for the new check order (12 total, all pass).

  **Kaset album art integration:** Added `/Applications/Kaset.app` (YouTube Music
  client for macOS) as a now-playing source (checked second). Kaset's AppleScript
  `get player info` returns a JSON blob with an `artworkURL` (YouTube thumbnail),
  so callers skip the iTunes Search API for Kaset-originated tracks. All three callers
  (`live_jobs.py:run_music()`, `media_sync.py:get_current_track_info()`,
  `media_sync.py:push_music_cover_now()`) fall back to the iTunes API when no direct
  URL is provided (Spotify/Apple Music paths unchanged).

  **Card padding tightened:** `.card` padding reduced from `20px` → `12px`,
  `--panel-gap` from `20px` → `12px`, `.card-header` margin-bottom from `15px` → `10px`
  in `style.css`. This brings general tab panels (settings, routines, tools) to the same
  density as tile components.

- **TIVOO-MAX SPP ROUTING FIX (2026-06-22 23:45 EDT):** Debugged why Tivoo-Max BLE
  connections fail. Investigation found 2 bugs in the SPP routing code:

  **Bug 1: `owner_connect.py:_ensure_device_async` (line 118)** — hardcoded
  `use_ios_le_protocol=False` for ALL devices on the daemon's auto-reconnect path.
  When a Tivoo-Max is auto-discovered (no specific mac requested), the daemon creates
  a `Divoom` with `use_ios_le_protocol=False`. The SPP routing code (`connection.py:82`)
  sees this falsy value and, because the device name contains "tivoo", switches to
  Bluetooth Classic SPP transport instead of BLE. SPP on macOS has a known "Tahoe
  reconnection bug" that produces opaque timeouts. Fix: changed to `use_ios_le_protocol=None`
  so the autoprobe dynamically determines the correct BLE protocol.

  **Bug 2: `connection.py:connect` (line 82)** — SPP routing condition was
  `not self.use_ios_le_protocol`, which fires for BOTH `False` (explicit Basic protocol)
  AND `None` (unknown/unprobed). When protocol is unknown, `BLETransport.connect()` runs
  the autoprobe to determine iOS-LE vs Basic over BLE — SPP should NOT pre-empt that.
  Fix: changed to `self.use_ios_le_protocol is False` so SPP routing only fires when
  explicitly set to Basic protocol.

  Also added `test_spp_not_routed_for_unknown_protocol` to codify the fix. Updated
  `test_spp_connection_resolution` to use explicit `use_ios_le_protocol=False`.
  Suite: 1701 passed, 87 skipped.

- **CASK RELEASE / SCAN-TIMEOUT BACKSTOP FIX ROUND (2026-06-22 23:30 EDT):** After the
  cask install, `brew reinstall --cask divoom-control` succeeded but the user reported
  the app "can't detect any device — connects to one device (Tivoo) then gets stuck".
  Investigation found 3 bugs:

  **Bug 1: Backstop doesn't cancel the coroutine.** `owner_loop.py:_run_on_loop` runs
  scan coroutines on the device loop via `asyncio.run_coroutine_threadsafe`. The 90s
  backstop (`_SCAN_RESULT_TIMEOUT`) fires with a `TimeoutError` but the Future was never
  saved — so `future.cancel()` was unreachable. The scan coroutine kept running for the
  full user-configured timeout (e.g. 360s), consuming BLE resources and blocking
  subsequent operations. Fix: save the Future and cancel on backstop timeout.

  **Bug 2: Scan timeout > backstop = guaranteed failure.** The user's `config.ini`
  had `timeout = 360s`. The daemon `owner_connect.py:scan()` passed it straight to
  the BLE scan, but `_run_on_loop` only waits 90s. Every scan with timeout > 90s was a
  guaranteed failure (backstop fires, scan reported as failed, but coroutine runs for
  remaining 270s). Fix: cap scan timeout to `_SCAN_RESULT_TIMEOUT` (90s) at the daemon
  level, with a warning log.

  **Bug 3: HTML input max bypassed by JS config load.** The `<input id="scan-timeout"
  max="120">` was bypassed when `app_init.js:load_config()` set `el.value = conf.timeout`
  (e.g. 360). HTML `max` only applies to user interaction, not programmatic `.value`
  assignment. Fix: clamp to `el.max` before setting the value.

  The stale `last_connected_device` UUID (not in scan results) causes a 16s auto-connect
  timeout before the daemon falls back to a 3s reconnect scan and connects to the first
  available device (Timoo). The Tivoo connection timeout is a separate BLE issue
  (device-specific, not a code regression). Suite: 1700 passed, 87 skipped.

- **RELEASE CUT ROUND (2026-06-22 21:58 EDT): Cut release v0.20.0 (Claude).**
  Cut the `v0.20.0` release including the startup packaging fix and native Rust daemon port (Phase 2 progress).
  - Version bumped to `0.20.0` in `pyproject.toml` and documented in `CHANGELOG.md` and `docs/release_notes_v0.20.0.md`.
  - Rebuilt the app bundle (`dist/Divoom-v0.20.0.dmg`) and pushed `main` branch + tag `v0.20.0` to GitHub.
  - Updated the Homebrew cask with the new `.dmg` SHA-256 (`42bb39b1...`) in `homebrew-tap` and pushed.
  - Note: GitHub release creation via `gh` CLI failed with 401 Bad Credentials in this environment, so the user needs to execute the `gh release create` command manually (see details in final output).

- **HW ROUND (2026-06-22 17:10 EDT): native C image encoder — divergence FIXED + revived (Claude).**
  Two bugs: (1) `image_encode.c` static header was 6 bytes — the NN palette-count byte at
  `out_buf[6]` got clobbered by the palette memcpy (palette landed on byte 6), diverging from
  Python's correct 7-byte header; fix `static_header_size = 7`. (2) Both `image_encoder.py` wrappers
  allocated `(w*h+7)//8` (1 BIT/pixel) but the C worst-case check needs `w*h` (8 bits/pixel), so the
  C returned -1 for any real frame → silent Python fallback (native image encode was DEAD for
  16x16+). Fix: allocate `7 + 256*3 + w*h`. Now byte-identical to Python across all sizes/colours
  (static AND frame) AND actually reached. Dylib rebuilt + committed. HW: pushed the test animation
  to Pixoo-1 via the revived native path → `result:true`, identical behaviour. Teeth: direct-C-path
  tests (`test_c_static_*`) that bypass the wrapper fallback — 17 fail against the pre-fix dylib.
  **ALL named HW-deferred items are now cleared.** Remaining NOT-testable-on-this-fleet: SPP
  transport + live-job-double-poller (BLE-only Pixoo/Timoo/Tivoo; no RFCOMM/SPP device). R45 #1
  "Custom Art channel empty" still needs eyes on the device screen (can't validate headless).

- **HW ROUND (2026-06-22 12:43 EDT): 0x8B animation retransmit dead-path FIXED (Claude).** The
  0x8B streamer set the response scalar to 0x8B before START, but the start-ACK wait CLEARS it —
  so for the chunk loop + retransmit window the scalar was None and 0x8B isn't a generic-ACK, so
  the handler DROPPED every unsolicited retransmit request; `_serve_8b_retransmits` then timed out
  "done" and a lost chunk was silently unrecoverable (stream still returned True). Fix:
  `stream_animation_8b` adds 0x8B to `_listen_commands` for the stream (removed in finally) so the
  handler's is_listened branch queues retransmit frames without consuming the scalar. HW-validated:
  pushed a 2-frame test GIF to Pixoo-1 (`display.show_image`) — device start-ACKed, chunk streamed,
  retransmit phase quiet, push True; the working push is NOT perturbed. Teeth: wiring + handler-
  mechanism tests (the old retransmit test mocked wait_for_response, never hit the real handler).
  Remaining HW-deferred: native C static-encoder; SPP/live-job-double-poller NOT testable on this
  BLE-only fleet.

- **HW ROUND (2026-06-22 12:40 EDT): ACK ≠ device-confirmed honesty (Claude).** custom-art and
  hot-update both reported `success:True` on bare GATT write-ACKs with no device confirmation.
  HW-confirmed on Pixoo-1 that the only verification channel is unusable — **0x8E query_page
  times out at 4 s on every page, returns empty** — so we can't verify and won't add a 4 s dead
  wait. Fix surfaces honest status: `custom_art_push` returns `device_confirmed:False` (GUI toast
  "sent" not "pushed"); `hot_update._stream_file` now returns `(ok, confirmed)` and each `served`
  entry + a top-level `confirmed` count distinguishes device-confirmed files from streamed-but-
  silent ones. Teeth: `test_silent_device_file_marked_unconfirmed`. NOT verified via 0x8E (HW-
  unreliable). NOTE: the deeper R45 #1 "Custom Art channel empty" functional regression needs eyes
  on the device screen (can't validate headless) — still open. Remaining HW-deferred: 0x8B
  retransmit dead path, native C static-encoder, push smoke.

- **HW ROUND (2026-06-22 12:25 EDT): exclusive steal-reject — hang-then-steal FIXED (Claude).**
  Validating the deferred exclusive-mode item on the live Pixoo-1 surfaced a real bug: a
  competing `exclusive_start` hung exactly 30 s (the `exclusive_timeout`) then SILENTLY STOLE
  the lock and reported success. Root cause: `exclusive_start` acquired by submitting
  `acquire(token)` through the GATED queue — a lock-acquire gated by the lock it seeks. The
  foreign-token `acquire` never dispatched (the gate only runs the owner's items), so the clean
  "held by another session" reject was unreachable; the G3 idle deadline force-released the real
  owner and the waiter stole. Fix: `CommandQueue.acquire_now(token)` runs `acquire` straight on
  the loop (off the dispatch queue — no device I/O in `acquire`). `exclusive_start` uses it and
  returns the honest error. HW re-validated: steal rejects in 0.00 s; idempotent re-acquire +
  post-release acquire still work. Teeth: `test_acquire_now_rejects_steal_immediately`. Suite
  1680 green. ALSO HW-validated (no change): the **wrong-device guard** — a `device_call` with a
  mac different from the held device does NOT silently read/write the cached device; it releases
  + attempts the requested target and fails honestly if unreachable (`get_brightness(mac=BOGUS)`
  → `success:false "timed out"`, never the held Pixoo's 60). **Working harness: the dev-daemon `.app` (`open "dist/Divoom Dev Daemon.app"`)
  runs live repo code under its own BLE grant — restart it to load each fix, then drive it over
  `/tmp/divoom.sock` with `DaemonClient`.** Remaining HW-deferred queue: custom-art ACK≠success,
  hot_update ACK≠success, 0x8B retransmit dead path, native C static-encoder, push smoke.

- **HARDWARE VALIDATION (2026-06-22 12:07 EDT): R53.35 iOS-LE ACK change REVERTED — read-backs
  fixed on the real Pixoo (Claude).** Commit `b1e9770`. On a live Pixoo-1, ALL read-backs
  (`device.get_brightness`, `device.get_device_name`) had regressed to a 5.26 s timeout → `null`
  while writes worked. Root cause: R53.35 made `_handle_ios_le_notification` KEEP the
  `_expected_response_command` scalar on the generic 0x33 ACK. Clearing it is **load-bearing** for
  the protocol autoprobe — `ble_probe` sends a 0x46 query (0x46 ∈ GENERIC_ACK_COMMANDS); keeping
  the scalar let the iOS-LE probe spuriously "succeed" on the Basic-only Pixoo → mis-detected as
  iOS-LE → every read-back timed out. The revert restores `self._expected_response_command = None`
  on the ACK; the 0x46 probe now correctly fails over to Basic. **Re-validated on hardware via the
  granted dev-daemon `.app`** (`dist/Divoom Dev Daemon.app`, thin launcher → live repo code, owns
  the Bluetooth TCC grant): `device.get_brightness` → `60` in **0.06 s** (was 5.26 s → null);
  `device.get_device_name` → fast 0.06 s response. Lesson: 1679 mocked unit tests can't catch an
  autoprobe regression that only manifests against real BLE framing — a Hyrum's-law case where the
  scalar-clear was load-bearing for protocol detection. The R53.35 "two-frame iOS-LE read-back" the
  change targeted remains unverified on ANY real device. NB: to drive HW from Claude, launch the
  dev-daemon `.app` (`open "dist/Divoom Dev Daemon.app"`) — it runs BLE under its own grant, unlike
  the Bash tool (TCC SIGABRT).

### Earlier rounds (pruned 2026-06-28)

The full round-by-round log that used to follow here — the R53.x adversarial-loop
rounds, the R45–R52 GUI/arch rounds, and the R7–R15 backfill (~1.4k lines of
superseded detail) — was pruned from this handoff on 2026-06-28. The authoritative
history lives in `CHANGELOG.md`, `docs/PLANNING_ROUND*.md`, and `git log`; recover
any entry from the git history of this file.

## Hardware note

macOS Bluetooth TCC is per responsible-process; drive real BLE by launching via
Terminal (`open *.command`). Device UUIDs + method in `docs/DEVICE_VALIDATION_PLAN.md`.

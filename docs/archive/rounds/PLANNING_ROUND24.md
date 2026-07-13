# Round 24 — UI/UX refinement batch + BLE attribution debug

Tools available for this round: **Unix socket** (`DaemonClient` on `/tmp/divoom.sock`
to drive/inspect the daemon directly) and **computer-use** (drive the running GUI,
screenshot, pixel-measure). Use screenshots to make spacing changes pixel-perfect.

## Carried-over: BLE scan from the GUI (debug in progress)
- PROVEN working from the user's granted terminal: direct discovery (4 devices),
  background-thread scan (4), full daemon-subprocess scan (4).
- The GUI spawns the daemon with the **granted** `python3.14` binary, non-detached
  (verified in `/tmp/divoom_daemon.log`: `Spawning daemon (detach=False):
  …/python@3.14/bin/python3.14`). Daemon boots + listens fine.
- Hypothesis: macOS TCC attributes the GUI-spawned daemon's Bluetooth to the
  pywebview app's *responsible process*, not the granted `python3.14`/terminal.
  Only reproducible in the user's GUI context (the Claude harness process tree is
  not a granted BT context, so my own scans always fail — not the code).
- Next: have the user run the real GUI from their granted terminal with a FRESH
  daemon (kill stale first), Scan, and paste `/tmp/divoom_daemon.log`. If the
  daemon logs "Discovered N" but the GUI shows empty → comm/serialization. If it
  crashes/denies → spawn the daemon detached so it runs as its own granted
  `python3.14` responsible process.

## UI/UX task list (user, 2026-06-08)
1. **Single-instance.** "Launch Dashboard" from the menubar spawns another
   dashboard which spawns another menubar → runaway. The GUI AND the menubar must
   each be **at most one instance** in all launch paths (menubar "Launch
   Dashboard", `run_gui.sh`, GUI auto-spawn of menubar). Use a lock / pgrep /
   `open -a` semantics so re-launch focuses the existing one.
2. **Menubar not in the Dock** — it's a status-bar agent; set `LSUIElement` /
   `NSApp.setActivationPolicy(.accessory)` so it has no Dock icon.
3. **Tab → content spacing (pixel-perfect, screenshot-driven).**
   - Channels: spacing to the widgets below + the separator = perfect (reference).
   - Tools: too far (visible gap above Alarms) — tighten.
   - Settings: a tiny bit too close — loosen slightly.
   Make all three match the Channels reference exactly.
4. **Center the tab rows horizontally** (macOS convention) across Channels /
   Tools / Settings.
5. **FM Radio visibility** — only show the FM Radio card when the active device
   model supports FM (capability-gated, like VJ Effects for Timebox Evo).
6. **Sidebar device-preview/selector card** — the glass card at the bottom is a
   touch too tall; raise it a bit, add a little vertical spacing above the
   Settings button (reduce its horizontal padding to gain that vertical room).
7. **Custom Art channel.**
   - Add a **search** box (is there enough metadata? can we persist it from the
     Monthly Best gallery cache?).
   - Scrollbar should belong to the **gallery list only** — Browse-File +
     Favorites sections shouldn't scroll with it.
   - Bump favorites **5 → 10**.
8. **Starting window width 1000 → 1080** (fits 3 columns in Monthly Best).
9. **Stocks/Crypto tickers** — the "+ Save" button is taller than "Display".
   Rename "+ Save" → **"Add"**, **remove the Display button**; auto-display when a
   symbol is typed into the box or selected from the saved list.
10. **Weather** — (item left incomplete by the user; confirm intent).

## Round-2 UI feedback (2026-06-08, with screenshots) — DEFERRED until daemon works
(User: "write these down … focus FIRST on the daemon/gui + device detection
without user intervention; polish UI afterwards.")
- **#3-redo (tabs STILL inconsistent) — RESOLVED** (commit `5b70646b`). Final
  direction (user, 2026-06-08): the OPPOSITE of the earlier "bare tabs" call —
  *all three* tab rows should sit on a **glass background** with consistent
  spacing. Implemented one model everywhere: `.tabs-section` is now a glass panel
  (same tokens as `.glass-card`) holding the centered tab row, with a uniform
  `margin-bottom` gap to the content cards. Channels' tab row was moved OUT of the
  content card-header into its own `.tabs-section` strip above the content card
  (channel-switch JS untouched — it selects `.tab-btn[data-channel]` globally).
  Tools dropped its `max-width:600px` so the strip is full-width like the others.
- **#6-redo (device preview).** Do NOT shrink the preview image. Instead: shrink
  the **glass panel** it sits on a little *vertically*, and **center** both the
  preview and the "Select Screen…" selector within it. (Revert the 100px preview
  shrink back toward 120, fix the panel padding + centering instead.)
- Screenshots provided in chat: (1) Channels/Clock, (2) Tools/Alarms, (3)
  Settings/Devices showing "No Bluetooth screens found." (Can't write chat images
  to disk from here; described above.)

## PRIORITY: daemon/GUI device detection without user intervention
Confirmed: Settings → Scan → "No Bluetooth screens found", but the terminal
diagnostics find all 4 screens and `python3.14` IS granted Bluetooth. Prime
suspect: the GUI (pywebview hosts it as `Python.app`, NOT in the BT-granted list)
spawns the daemon non-detached, so the daemon inherits `Python.app`'s ungranted
TCC identity → silent denial. Fix to try: spawn the daemon DETACHED under the
explicit granted `python3.14` binary (its own responsible process), + log
`CBCentralManager.authorization()` from the daemon's scan so the next run is
definitive. (May also bump the 2s default scan timeout.)

## §outcome
- **BLE detection from the GUI — RESOLVED** (commit `70e69ee0`). Two root causes:
  (1) macOS TCC attributed the GUI-spawned daemon to pywebview's ungranted
  `Python.app`, not the granted `python3.14` → `CBauth` 0/2, empty scans. Fix:
  `spawn_daemon` now uses `responsibility_spawnattrs_setdisclaim` (libc
  `posix_spawn`, new `_spawn_disclaimed_macos`) so the daemon is its OWN
  responsible process under the granted `python3.14`. (2) The `DaemonClient` read
  timeout (2s) was shorter than the scan duration, so the successful reply
  surfaced as "timed out" — `send_command` now takes a `read_timeout` and `scan`
  waits `timeout + 10s`. Verified `CBauth==3` + all 4 devices end-to-end via the
  exact GUI startup sequence. The earlier "harness can't be a granted BT context"
  note is moot — the disclaim makes BLE work from any parent.
- **#1 SHIPPED** — single-instance GUI (flock) + menubar (pgrep); a 2nd dashboard
  exits before spawning a menubar, killing the runaway.
- **#2 SHIPPED** — menubar uses `NSApplicationActivationPolicyAccessory` (no Dock).
- **#3 SHIPPED** — shared `.tabs-section` gives Tools + Settings the Channels
  card-header spacing (mb:15/pb:10/1px). Verified identical via computed styles.
- **#4 SHIPPED** — `.tabs-row` centers (margin-inline auto); equal 87px L/R margins.
- **#5 SHIPPED** — FM Radio card gated to Tivoo/Ditoo (connect-time, like VJ).
- **#6 SHIPPED** — sidebar device-preview card trimmed (100px preview, less
  padding, margin-bottom) so it sits higher with more room above Settings.
- **#7 SHIPPED** — Custom Art: name search, gallery-only scrollbar, history 5→10.
- **#8 SHIPPED** — window starts 1080 wide.
- **#9 SHIPPED** — stocks: removed Display, "+ Save"→"Add", auto-display on
  type/select via `window.displayTicker`.
- **#10 — INCOMPLETE in the user's message ("Weather —"); awaiting the actual ask.**

Verification note: the visual items (#3/#4/#6) were verified via computed styles
+ headless measurement; live screenshot clicks on the sidebar weren't landing
(coordinate/focus quirk), so the user should eyeball #6's sidebar spacing.

BLE: the Divoom.app bundle (R24 BLE debug) was a WRONG turn — it re-attributes BT
to an ungranted `com.divoom.control` identity. Reverted `run_gui.sh` to a direct
launch. System Settings confirmed `python3.14` + the terminal ARE granted. Still
needs the user to verify the real GUI scan from their granted terminal (the
harness can't be a granted BT context). make_app_bundle.sh kept for distribution.

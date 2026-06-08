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

## §outcome
(fill in as items land — commit each, keep `pytest` green, screenshot-verify the
visual ones.)

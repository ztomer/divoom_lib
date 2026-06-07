# Session Handoff — read this first

This is the **cross-agent session state**. opencode and Claude Code keep their
own conversation stores (they can't share a live session), so THIS FILE + the
git history + CHANGELOG are the shared memory. Any agent (opencode or Claude)
should read this on entry and **update it at the end of every round** (see the
core rule in `AGENTS.md`).

## How to resume

- **opencode**: `opencode -s ses_184471307ffeCUHgzv9w51O0oA` (or
  `opencode export <id>` to read it as JSON).
- **Claude Code**: reads `CLAUDE.md` → `AGENTS.md` → this file, plus `git log`.
- Both: `git log --oneline`, `CHANGELOG.md`, `docs/PLANNING_ROUND*.md`.

## Current state — _update this section each round_

- **Last round shipped:** Round 13 (capability detection + examples/CLI + macOS
  notifications). Three deliverables, all on the kill-criterion-aware path:

  - **§1 — Capability detection** (`167a1019`): hardware-derived identifier
    hierarchy (explicit `device_type` → MAC registry → `manufacturer_data`
    fingerprint → baseline). New `divoom_lib/models/capabilities.py` (RENAMED
    `screensize` → `panel_resolution` per user — disambiguates per-panel
    pixels from wall composite). `Divoom.capabilities` property.
    `DeviceRegistry` saves to `~/.config/divoom-control/devices.json`.
    `divoom_lib/wall.py:wall_resolution()` helper. **CI fix**:
    `tests/test_live_widgets_diagnostic.py` now `pytest.importorskip`s
    playwright instead of `sys.exit(2)`. +33 tests (26 capabilities + 7
    wall helper).
  - **§2 — `examples/` + `divoom-control` CLI** (`16cb8b8`): 6 example
    scripts + 10-subcommand CLI + shell wrapper. **Weather example
    deferred** — `TempWeatherCommand` (0x5F) is not wired to the Divoom
    facade; small R14 follow-up. **CLI entry point is a shell wrapper,
    not `pyproject.toml`** — that repo has no `setup.py`/`pyproject.toml`
    today; adding it is a packaging change, deferred to R14. +22 CLI tests.
  - **§3 — macOS notification mirroring** (uncommitted, ready to commit):
    `gui/macos_notifications.py` — `MacNotificationMonitor` polls the
    macOS Notification Center SQLite DB (the same approach used by
    `mac-notification-forwarder`, Hammerspoon, etc. — Apple's public
    notification API only fires for *our own* app's notifications;
    DB-poll bypasses TCC). `MacAppRouter` (14 default rules,
    substring-matched, case-insensitive). `gui_api` integration with
    fire-and-forget `_schedule_async` so the polling thread never
    blocks on BLE. **GUI Settings card DEFERRED to R14** — the lib + tests
    are the high-value part of §3; the Settings toggle is a 30-line
    `templates.js`/`settings.js` follow-up that needs visual layout
    decisions. Setup guide in `docs/NOTIFICATIONS_SETUP.md`. +23 tests
    (18 macOS notifications + 5 gui_api).

  Suite: **755 passed / 0 failed / 74 skipped** (up from R12's 677;
  the +1 skip is the macOS-only test that's now actually skipped at
  collection time). Zero regressions across R8→R13.

- **Earlier rounds:** R12 §A P7 (Tools sub-tab rename to **Sessions**),
  §D audit (5 features deferred with rationale), §E pushed; R11 push-path
  bug fixes; R10 ANCS notifications; R9 screen orientation + factory reset
  (0xBD EXT); R8 device settings/FM/weather/memorial + Tools sub-tabs;
  R7 surfaced text/alarms/sleep/tools. See `CHANGELOG.md` +
  `docs/PLANNING_ROUND*.md`.
- **Git:** R8→R13 arc **PUSHED to origin** through R13 §2
  (`16cb8b8c`). R13 §3 is in the working tree, ready to commit.
  Branch is in sync with `origin/main` as of 2026-06-06 except for
  the uncommitted R13 §3 work.

## Open threads / next up (see docs/PLANNING_ROUND13.md for the full plan)

1. **R13 §3 — commit + push** (current working tree): macOS notification
   monitor + gui_api integration + tests + `docs/NOTIFICATIONS_SETUP.md`.
   GUI Settings card UI is deferred to R14.
2. **R12 §A visual pass pending** (user-run `python3 gui/gui_main.py`):
   verify appbar corner transports, scoreboard restyle, wall toolbar,
   font sweep, segmented-pill, tools regroup, sub-tab rename to "Sessions".
3. **R12 §B hardware verification pending** (user-run): album cover renders
   un-distorted; custom-art/live push end-to-end.
4. **get_* read-back times out on real devices** (task #20): get queries
   0x42/0x46/0x13 get no parseable response (likely query-framing mismatch).
   Gates every "read from device". See `docs/DEVICE_VALIDATION_PLAN.md`.
5. **Channel-switch hardware bug (Divoom Max):** first switch works, rest don't;
   not root-caused. All switches are `set light mode` (0x45) fire-and-forget.
6. **R13 follow-ups for R14:** (a) wire `TempWeatherCommand` to the Divoom
   facade (`divoom.weather.send()`), (b) add `pyproject.toml` with
   `[project.scripts]` for a real installable `divoom-control` entry
   point, (c) add the GUI Settings → Devices card for the notification
   mirror toggle + per-app checkboxes, (d) load custom routing JSON
   (`~/.config/divoom-control/notification_routing.json`) — currently
   the defaults are used; the JSON loader is a 10-line follow-up.
7. **Deferred features** (R12 §D): see `docs/PLANNING_ROUND12_D_AUDIT.md` —
   Timeplan UI blocked on unverified `mode`/`type` semantics; SD player
   blocked on task #20; Game has no host UX; Drawing needs a non-trivial
   UI per mode; Cloud HTTP is its own round (auth broken).

## Hardware note

macOS Bluetooth TCC is per responsible-process; drive real BLE by launching via
Terminal (`open *.command`). Device UUIDs + method in `docs/DEVICE_VALIDATION_PLAN.md`.

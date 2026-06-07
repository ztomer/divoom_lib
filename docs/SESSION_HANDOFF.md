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

- **Last round shipped:** Round 14 (R13 follow-ups §1-§4). Four
  deliverables, all on the kill-criterion-aware path:

  - **§1 — `Weather` facade** (`<commit>`): new
    `divoom_lib/system/weather.py` with `Weather.set()`,
    `set_temperature()`, `set_weather()`. Wired to the Divoom
    facade as `divoom.weather`. The old `TempWeatherCommand` in
    `divoom_lib/system/temp_weather.py` is now a thin shim that
    delegates — fixes the latent `number2HexString()` bug (the
    function lives in `divoom_lib/utils/converters.py`, not on
    the Divoom instance) and unblocks the `examples/set_weather.py`
    deferred from R13 §2. CLI `set-temperature` subcommand added
    with `--weather` choice. +27 tests (21 weather + 4 CLI + 2
    legacy regression checks). Encodes temperatures using
    `(256 + c) & 0xFF` for negatives; range -127..128 (R14
    `[+-]0x7F|0x80` — the 0x5F command uses a signed byte).
  - **§2 — Custom routing JSON loader** (`<commit>`): new
    `load_routing_table(path)` / `save_routing_table(rules, path)`
    in `gui/macos_notifications.py`. Path resolves via
    `DIVOOM_CONTROL_ROUTING` env var, falling back to
    `~/.config/divoom-control/notification_routing.json`
    (XDG-convention, same dir as `devices.json`). Corrupt-file
    tolerant: warns + falls back to `DEFAULT_ROUTING`. Validates
    app_type ∈ NOTIFICATION_APPS (1-14) — bad entries are dropped
    with a warning, not crashed. Atomic save via `.tmp` + rename.
    `MacAppRouter.from_file(path)` classmethod. `MacNotificationMonitor`
    now loads from the custom file by default. +19 tests.
  - **§3 — GUI Settings → Devices card** (`<commit>`): new
    "macOS Notifications" card under Settings → Devices with
    toggle (start/stop listener), live status (running / stopped /
    error / unsupported), counters (seen / routed / dropped), and
    a routing-rules JSON editor (textarea + Save / Reset to
    defaults). `gui_api` adds `get_notification_listener_status()`
    and `save_notification_routing(json_text)` with hot-reload
    (the running monitor's router is replaced, no listener
    restart required). Status pill uses `--font-mono`. +5
    `test_gui_api` tests. **Note:** per-app checkboxes were
    considered but the JSON editor is more honest (the rules
    ARE JSON, the user is a developer) and avoids a parallel
    state to keep in sync. Card is keyboard-accessible.
  - **§4 — `pyproject.toml`** (`<commit>`): first packaging
    file in the repo. setuptools backend, PEP 621 metadata,
    version `0.14.0`, Python `>=3.10`. Core deps (`bleak`,
    `aiohttp`, `pillow`, `tomli`/`tomli-w`) match
    `requirements.txt`. `[gui]` extra: `pywebview` + `pyobjc`
    (darwin-only). `[test]` / `[dev]` extras. `[project.scripts]`
    registers the `divoom-control` entry point → `divoom_lib.cli:main`.
    `tool.setuptools.package-data` ships the dylib + `web_ui/`
    with the `gui` package. Verified `pip install -e .` succeeds
    + `divoom-control --help` works. **The legacy
    `./divoom-control` shell wrapper is KEPT** for in-tree dev
    without an editable install. +12 packaging tests.

  Suite: **829 passed / 0 failed / 75 skipped** (up from R13's
  755; the +1 skip is the live playwright diagnostic that
  depends on optional deps). **+74 tests across R14 §1-§4**
  (27 weather, 19 routing, 5 gui_api, 12 pyproject, 11 misc
  incidental). Zero regressions across R8→R14.

  Pre-existing in R13: **§5 — Fonts SHIPPED** (`10a29f64`): one
  CSS variable per font family; `style.css` is single source of
  truth; `tests/test_fonts.py` guards the rule.
  **§6 — No emojis SHIPPED** (`10a29f64`):
  `scripts/remove_emojis.py` swept 365 emojis; `tests/test_no_emojis.py`
  guards it.

- **Earlier rounds:** R13 (capability detection + examples/CLI +
  macOS notifications); R12 §A P7 (Tools→Sessions sub-tab rename),
  §D audit, §E pushed; R11 push-path bug fixes; R10 ANCS; R9 screen
  orientation + factory reset (0xBD EXT); R8 device settings/FM/weather
  /memorial + Tools sub-tabs; R7 surfaced text/alarms/sleep/tools.
  See `CHANGELOG.md` + `docs/PLANNING_ROUND*.md`.
- **Git:** R8→R14 arc is in the working tree, ready to commit + push.

## Open threads / next up (see docs/PLANNING_ROUND14.md for the full plan)

1. **R14 §1-§4 — commit + push** (current working tree): all four
   R13 follow-up sections complete and green.
2. **R12 §A visual pass pending** (user-run `python3 gui/gui_main.py`):
   verify appbar corner transports, scoreboard restyle, wall toolbar,
   font sweep, segmented-pill, tools regroup, sub-tab rename to
   "Sessions", **and the new macOS Notifications card under
   Settings → Devices** (R14 §3).
3. **R12 §B hardware verification pending** (user-run): album cover
   renders un-distorted; custom-art/live push end-to-end; weather
   push via `divoom-control set-temperature 18 --weather clear`.
4. **get_* read-back times out on real devices** (task #20): get
   queries 0x42/0x46/0x13 get no parseable response (likely
   query-framing mismatch). Gates every "read from device". See
   `docs/DEVICE_VALIDATION_PLAN.md`.
5. **Channel-switch hardware bug (Divoom Max):** first switch works,
   rest don't; not root-caused. All switches are `set light mode`
   (0x45) fire-and-forget.
6. **Deferred features** (R12 §D): see
   `docs/PLANNING_ROUND12_D_AUDIT.md` — Timeplan UI blocked on
   unverified `mode`/`type` semantics; SD player blocked on task
   #20; Game has no host UX; Drawing needs a non-trivial UI per mode;
   Cloud HTTP is its own round (auth broken).
7. **R14 §3 — verify the new card on a real Mac** with notifications
   actually firing; routing JSON editor parses + saves +
   hot-reloads the live monitor without restart.

## Hardware note

macOS Bluetooth TCC is per responsible-process; drive real BLE by launching via
Terminal (`open *.command`). Device UUIDs + method in `docs/DEVICE_VALIDATION_PLAN.md`.

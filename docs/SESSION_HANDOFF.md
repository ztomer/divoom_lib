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

- **Last round shipped:** Round 10 (notification mirroring / ANCS). New lib:
  cmd `"set android ancs": 0x50`, `NOTIFICATION_APPS`, `divoom_lib/tools/
  notification.py` (`d.notification.show_notification` / `_text`). GUI:
  `send_notification` bridge + Tools→Device **Notification** card. Manual trigger
  only — auto-sourcing macOS notifications deferred. Protocol re-verified
  (cmd 0x50, single-byte ≥8 skip OR type+len+utf8; report's 0x60/RGB were wrong).
  See `docs/PLANNING_ROUND10.md` §5. Suite: **538 passed / 0 failed / 73 skipped**.
- **Earlier:** Round 9 (screen orientation + factory reset, 0xBD EXT;
  `docs/PLANNING_ROUND9.md`). Round 8 (device settings/FM/weather/memorial +
  Tools sub-tabs; timeplan UI deferred). Round 7 + 7.1.
  - R7: surfaced un-exposed `divoom_lib` modules in the GUI — Text Channel,
    Alarms, Sleep Aid, Tools (timer/countdown/noise). Bridges in
    `gui/gui_api.py`, UI + unit tests.
  - R7.1: moved Alarms/Sleep/Tools into a dedicated **Tools** sidebar tab;
    added `AGENTS.md` cross-session core rule.
- **Tests:** full suite **513 passed / 0 failed / 73 skipped**
  (`python3 -m pytest`). Hardware tests skip by default.
- **Git:** `main` is **ahead of `origin/main` by 4** commits (not yet pushed):
  checkpoint `7b69a5b3`, Text `f223a0b3`, Alarms/Sleep/Tools `19beb1fa`,
  Tools-tab+AGENTS `f3579dac`.

## Open threads / next up

1. **Channel-switch hardware bug (Divoom Max):** first channel switch
   (watchface) works, subsequent switches don't. Not yet root-caused on
   hardware. All switches are `set light mode` (0x45) fire-and-forget.
2. **get_* read-back times out on real devices** (task: `divoom_lib` get
   queries 0x42/0x46/0x13 get no parseable response — likely query-framing
   mismatch: query sent iOS-LE while device is Basic). Also gates the Alarms
   "Read from device" button. See `docs/DEVICE_VALIDATION_PLAN.md`.
3. **Next excavation frontier (R10 candidates):** R8 closed lib→GUI; R9 shipped
   the screen-orientation 0xBD EXT work. Remaining APK-only items needing new lib
   code (catalogued in `docs/PLANNING_ROUND9.md` §1): **ANCS notification
   mirroring** (cmd 80, 14 app types — high value, needs macOS notification
   plumbing → own round), the 200+ **cloud HTTP** endpoints (clock-face store /
   weather city search / pomodoro / white-noise / TTS), SD player, game, drawing.
   Timeplan UI still deferred (bridge exists, semantics unverified).
4. Round 7 Phase 2/3 backlog also catalogued in `docs/PLANNING_ROUND7.md`.

## Hardware note

macOS Bluetooth TCC is per responsible-process; drive real BLE by launching via
Terminal (`open *.command`). Device UUIDs + method in `docs/DEVICE_VALIDATION_PLAN.md`.

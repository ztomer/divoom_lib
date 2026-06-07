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

- **Last round shipped:** Round 11 (push-path bug fixes) + docs. Fixed the live
  image push end-to-end (cover art / custom art / gallery / wall) — three root
  causes, all now aligned to the futpib reference: (1) resize-to-device-grid
  before encoding (the "int too big to convert" crash); (2) 0x8B = 256-byte
  chunks + chunk-index offset id (the transfer stall); (3) continuous LSB-first
  pixel packing (the distortion). Also: cover art auto-pushes on track change +
  immediately on enable (manual button removed); native C encoder had the same
  packing bug → fixed + dylib rebuilt; **both C and Python encoders are now held
  to one correctness suite** (`tests/test_encoder_both_impls.py`); `conftest.py`
  auto-rebuilds a stale dylib; added `Makefile` + GitHub Actions; README rewritten.
  See `docs/PLANNING_ROUND11.md`. Suite: **614 passed / 0 failed / 73 skipped**.
- **In progress:** Round 12 (consolidation + continuation), order C→A→D→E→B.
  See `docs/PLANNING_ROUND12.md`. Done so far: lessons consolidated in
  `docs/ENGINEERING_NOTES.md` (linked from AGENTS.md); stale state pruned; **§C**
  shipped — framing dual-impl correctness test, which caught + fixed two real
  Python-fallback crashes (list→memoryview in `encode_basic_payload` escape +
  `encode_ios_le_payload`). Suite **666 passed / 0 failed**. Next: §A Phase 2
  (quick GUI wins) — sticky push footer, ambient color visibility + drop
  "Custom", scoreboard reset.
- **Earlier:** R10 ANCS notifications; R9 screen orientation + factory reset
  (0xBD EXT); R8 device settings/FM/weather/memorial + Tools sub-tabs; R7 surfaced
  text/alarms/sleep/tools. See `CHANGELOG.md` + `docs/PLANNING_ROUND*.md`.
- **Git:** the R8→R11 arc (~25 commits) is **not yet pushed to origin** (push
  pending user confirmation — §E of Round 12).

## Open threads / next up (see docs/PLANNING_ROUND12.md for the full plan)

1. **R11 GUI overhaul Phases 2–7 not done** (§A): sticky push footer, ambient
   color visibility + drop "Custom", scoreboard reset+restyle, appbar tweaks,
   virtual-wall toolbar (icons+labels), font sweep, tools regroup + unified
   segmented-pill tabs.
2. **Hardware verification pending** (§B, user-run): album cover renders
   un-distorted; custom-art/live push end-to-end.
3. **get_* read-back times out on real devices** (task #20): get queries
   0x42/0x46/0x13 get no parseable response (likely query-framing mismatch).
   Gates every "read from device". See `docs/DEVICE_VALIDATION_PLAN.md`.
4. **Channel-switch hardware bug (Divoom Max):** first switch works, rest don't;
   not root-caused. All switches are `set light mode` (0x45) fire-and-forget.
5. **Deferred features** (§D): Timeplan UI (semantics unverified); SD player /
   game / drawing (lib→GUI exposure); auto-source real macOS notifications; the
   200+ cloud HTTP endpoints (own round).

## Hardware note

macOS Bluetooth TCC is per responsible-process; drive real BLE by launching via
Terminal (`open *.command`). Device UUIDs + method in `docs/DEVICE_VALIDATION_PLAN.md`.

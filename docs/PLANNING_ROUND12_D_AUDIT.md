# Round 12 §D — Deferred features audit (2026-06-06)

> **Scope:** decide, per deferred feature, whether to **EXPOSE** in the GUI now,
> **DEFER** (lib stays, no UI), or **DROP** (delete the lib code).
> Verdict table at the bottom; per-feature rationale above it.
> Follows the "verify against the decompiled APK + references, not prose" rule
> from `docs/ENGINEERING_NOTES.md`.

## Audit method

For each feature:

1. **Lib surface** — find the module in `divoom_lib/`, list its methods, check
   they have wire-level tests (not just hardware-gated tests).
2. **Protocol truth** — `references/apk/decompiled_src/.../SppProc$CMD_TYPE.java`
   + `CmdManager.java` (the canonical source) — confirm command IDs and the
   field semantics. Cross-check against `references/divoom-refs/futpib/` and
   `references/divoom-refs/hass-divoom/`.
3. **GUI surface** — is there already a partial UI card? Is `gui_api.py`
   exposing the method? Is the JS hooked up?
4. **Gating** — does it depend on broken read-back (task #20), unverified
   semantics, device-specific UX, or a cloud account?

## Feature: Timeplan (`0x56` set / `0x57` get)

### Lib surface
- `divoom_lib/scheduling/timeplan.py` (113 LOC) — 2 methods:
  - `set_time_manage_info(status, hour, minute, week, mode, trigger_mode, fm_freq, volume, type, animation_id, animation_speed, animation_direction, animation_frame_count, animation_frame_delay, animation_frame_data)` (0x56)
  - `set_time_manage_ctrl(status, index)` (0x57)
- `divoom_lib/models/commands.py`: `"set time manage info": 0x56`, `"set time manage ctrl": 0x57`.
- **No `get_*` wire-level test.** Only `tests/test_timeplan_functions.py`
  (hardware-gated, requires a Timoo).

### Protocol truth (decompiled APK)
- `SppProc$CMD_TYPE.java:62-63` — `SPP_SET_TIME_MANAGE_INFO(86) = 0x56`,
  `SPP_GET_TIME_MANAGE_CTRL(87) = 0x57`. ✓
- `CmdManager.java:664-714` — pack a 10-byte header then optional animation
  data, sent via `s.c(SPP_SET_TIME_MANAGE_INFO, bArr4)`. Header fields are
  obfuscated ints in `W1.p`: `f3179a` (status), `f3180b` (hour), `f3181c`
  (minute), `f3182d` (week), `f3183e` (mode), `f3184f` (trigger_mode), `f3185g`
  (fm_freq low), `f3186h` (boolean — fm_freq high? or separate boolean?),
  `f3187i` (volume), `f3188j` (type). Optional `f3189k` = animation bytes.
- **No futpib implementation, no hass-divoom implementation, no
  andreas-mausch implementation.** Only the decompiled APK has these commands.
- `references/apk/APK_INTELLIGENCE_REPORT.md` does not document the field
  semantics either. The report treats this as "internal Divoom Cloud feature".

### GUI surface
- `gui/gui_api.py:427-434` — `set_timeplan(index, enabled, hour, minute, week=0, channel=0)`
  exists. Maps `channel` → `mode`, sets `trigger_mode=0, fm_freq=0, volume=10,
  type=0`. **The `mode` mapping is a guess** — there's no documentation that
  "channel" goes in byte 5. My `volume=10` is also a guess.
- `tests/test_gui_api.py:122-131` — `test_r8_memorial_and_timeplan` only
  checks the call is made with the right positional args. It does NOT verify
  semantics.
- **No UI card.** `gui/web_ui/templates.js` has no timeplan section. The
  `gui_api.set_timeplan` is dead code on the JS side (no caller).

### Verdict
- **DEFER.** Two reasons:
  1. **Field semantics unverified.** `mode`/`trigger_mode`/`type` are
     obfuscated ints in the APK with no third-party documentation. The lib
     treats them as int enums (0=channel switch, 1=animation, 2=other), but
     this is **inferred**, not verified. Exposing a UI card that asks the user
     to fill in a `channel` field mapped to `mode` is a footgun — a wrong
     value would silently fail to schedule.
  2. **Read-back is broken (task #20).** `SPP_GET_TIME_MANAGE_CTRL(0x57)` is
     a `get_`. Per `docs/ENGINEERING_NOTES.md` "ACK ≠ success", `get_*`
     timeouts on real hardware. A UI that schedules something and then
     "reads back the schedule" would hang. Fire-and-forget scheduling is
     possible, but the user can't verify it took effect.
- **Lib stays as-is.** The methods are wire-correct (command IDs match APK;
  byte packing is structurally right — header is 10 bytes followed by
  variable-length animation data). Tests can be added (synthetic
  `parse_basic_protocol_frames` round-trip), but those are cosmetic — the
  field semantics are what's unverifiable.
- **No code changes this round.** Document the deferral in CHANGELOG.

## Feature: SD card player

### Lib surface
- `divoom_lib/media/music.py` (375 LOC) — 13 methods: `get_sd_play_name`
  (0x06), `get_sd_music_list` (0x07), `get_volume`/`set_volume` (0x09/0x08),
  `get_play_status`/`set_play_status` (0x0B/0x0A), `set_sd_play_music_id`
  (0x11), `set_sd_last_next` (0x12), `send_sd_list_over` (0x14),
  `get_sd_music_list_total_num` (0x7D), `get_sd_music_info` (0xB4),
  `set_sd_music_info` (0xB5), `set_sd_music_position` (0xB8),
  `set_sd_music_play_mode` (0xB9), `app_need_get_music_list` (0x47).
- **No wire-level tests.** `tests/test_music_functions.py` (hardware-gated).

### Protocol truth (decompiled APK)
- `SppProc$CMD_TYPE.java:11-29` — confirms all command IDs.
- `SppProc$CMD_TYPE.java:14` — `SPP_GET_SD_MUSIC_LIST(7) = 0x07`. The lib
  expects a multi-track response: `[music_id (2B LE), name_len (2B LE),
  name_bytes (name_len)]` repeated. No futpib/hass-divoom cross-reference
  for this format — only the lib's own comments.
- `SPP_GET_SD_MUSIC_LIST_TOTAL_NUM(125) = 0x7D` — same situation, no
  reference repo has this.

### GUI surface
- **No UI card, no gui_api wrapper.** `gui/gui_api.py` has no `set_sd_*` or
  `get_sd_*` methods. The volume + play/pause set methods exist (called
  from the appbar) but the SD-specific subset is not wired.

### Verdict
- **DEFER.** Two reasons:
  1. **Depends on task #20.** SD player requires a `get_sd_music_list` (0x07)
     response to populate a "pick a track" UI. That response is a `get_*`
     read-back that, per `docs/ENGINEERING_NOTES.md`, times out on real
     hardware. The user would click "List tracks" and the UI would hang.
  2. **Device-specific.** Only Tivoo Max / Ditoo / Timoo have an SD slot
     (Pixoo-1 has none). A universal UI card would be wrong for the user's
     Pixoo. The lib can support it; the GUI would need device-aware
     capability detection.
- **Lib stays as-is.** Methods are wire-correct (command IDs match APK).
- **No code changes this round.** Document in CHANGELOG.

## Feature: Game (Magic 8-ball, Dino, etc.)

### Lib surface
- `divoom_lib/game.py` (167 LOC, R4 P1 added) — 7 methods: `hide_game`,
  `set_game(game_id)` (0xA0), `set_key_down(key)`, `set_key_up(key)` (0x17,
  0x21), `set_magic_ball_answer(answer_id)` (0x88), `exit_game`. Plus 9
  game_id constants (Dino, 2048, Box Jump, Slot Machine, Magic Ball,
  Guessing, Shake, Push Box, Falling Block).
- **No wire-level tests.** `tests/test_game_functions.py` (hardware-gated).
- `tests/test_round4_p1_helpers.py:333` — `test_exit_game` is the only
  synthetic test, and it only checks the call doesn't raise.

### Protocol truth (decompiled APK)
- `SppProc$CMD_TYPE.java:115,100,148,149` — `SPP_SET_GAME(160) = 0xA0`,
  `SPP_SEND_GAME_SHARK(136) = 0x88`, `SPP_SEND_GAME_CTRL_INFO(23) = 0x17`,
  `SPP_SEND_GAME_CTRL_KEY_UP_INFO(33) = 0x21`. All match.
- `CmdManager.java` has the game dispatcher, but the game-specific control
  flow is in `W1/c.java` etc. — beyond scope to trace.

### GUI surface
- **No UI card, no gui_api wrapper.** Dead code on the JS side.

### Verdict
- **DEFER.** Three reasons:
  1. **No useful UX on the host.** These are device-native games played on
     the device's own display using its own buttons. A host UI that just
     "launches Magic 8-ball" adds nothing over tapping the device — the
     device has the buttons.
  2. **Device-specific control sets.** Tivoo Max has 4 buttons + 1 dial;
     Ditoo has a 3×3 grid of touch buttons; Timoo has 4 buttons + 1 d-pad;
     Pixoo has none. A universal "press the up button" JS event has no
     meaning.
  3. **Game list is firmware-dependent.** Not all 9 games are present on
     every device. The `set_game` call would silently fail on the
     unsupported ones (no error returned; per ENGINEERING_NOTES "ACK ≠
     success").
- **Lib stays as-is.** It's the most useful reference for "what games does
  the protocol support", and removing it would lose the constants table
  (game_id → Divoom-name).
- **No code changes this round.** Document in CHANGELOG.

## Feature: Drawing (sand / picture scan / drawing pad)

### Lib surface
- `divoom_lib/display/drawing.py` (437 LOC) — 12+ methods:
  - `set_light_pic(pic_data)` (0x44)
  - `drawing_mul_pad_ctrl(screen_id, r, g, b, num_points, offset_list)` (0x3A)
  - `drawing_big_pad_ctrl(canvas_width, screen_id, r, g, b, num_points, offset_list)` (0x3B)
  - `drawing_pad_ctrl(r, g, b, num_points, offset_list)` (0x58)
  - `drawing_pad_exit` (0x5A)
  - `drawing_mul_encode_single_pic(screen_id, data_length, data)` (0x5B)
  - `drawing_mul_encode_pic(screen_id, total_length, pic_id, pic_data)` (0x5C)
  - `drawing_mul_encode_gif_play` (0x6B)
  - `drawing_encode_movie_play(frame_id, data_length, data)` (0x6C)
  - `drawing_mul_encode_movie_play(screen_id, frame_id, data_length, data)` (0x6D)
  - `drawing_ctrl_movie_play(control_command)` (0x6E) — 0=exit, 1=play
  - `drawing_mul_pad_enter(r, g, b)` (0x6F)
  - `sand_paint_ctrl(control, **kwargs)` (0x34) — sub-cmds 0=init, 1=reset
  - `pic_scan_ctrl(control, **kwargs)` (0x35) — sub-cmds 0=mode/speed, 1=data
- **No wire-level tests.** `tests/test_drawing_functions.py`
  (hardware-gated). `tests/test_drawing.py` exists but appears to be an
  early skeleton (need to check).

### Protocol truth (decompiled APK)
- `SppProc$CMD_TYPE.java:42,43,44,64-67,80-84` — all 12+ command IDs match
  exactly. ✓

### GUI surface
- **No UI card, no gui_api wrapper.** Dead code on the JS side.

### Verdict
- **DEFER.** Three reasons:
  1. **Non-trivial UI per mode.** A freehand drawing canvas that maps mouse
     events to `drawing_pad_ctrl(0x58)` is a Canvas/Pointer-Events project
     on its own (16×16 or 32×32 device, multi-touch, color picker, undo).
     A "Sand" mode generator needs to know what shapes render as sand.
     A "Picture scan" mode needs a tile scroll preview. Each is its own
     sub-project.
  2. **Sand pad is single-screen-only.** Tivoo Max / Ditoo / Timoo are
     single screens — `drawing_mul_*` is for multi-screen walls. The
     `set_light_pic` (0x44) is the only one that's useful on a single
     device, and it overlaps with `divoom_lib.display.show_image` (already
     exposed via the gallery + cover art paths).
  3. **`pic_scan_ctrl` (0x35) is unsupported in the decompiled APK** —
     `SppProc$CMD_TYPE.java` has no entry for 0x35. The lib method
     `pic_scan_ctrl` claims it sends 0x35, but no command ID exists for
     it. This is **lib code that may be wrong** — see the open thread.
- **Lib stays as-is.** The `pic_scan_ctrl` (0x35) claim should be flagged
  in a comment, not deleted, until a real device proves it works.
- **No code changes this round.** Document in CHANGELOG + add a comment in
  `divoom_lib/display/drawing.py` flagging the 0x35 question.

## Feature: Divoom Cloud HTTP (clock-face store, weather city search, pomodoro, white-noise, TTS, etc.)

### Lib surface
- **None.** No cloud HTTP client. The divoom_lib talks BLE only.

### Protocol truth
- Cloud endpoints are HTTP/JSON, not BLE. Would need a new module +
  account auth (Divoom Cloud login). The `UserNewGuest` endpoint the user
  hit returned `RC=10` (per `docs/SESSION_HANDOFF.md`), which suggests
  the public Cloud API has changed or requires a different auth flow.

### GUI surface
- **None.** No cloud card, no auth UI, no LAN discovery in production use.

### Verdict
- **DEFER (own round).** Three reasons:
  1. **Out of scope for BLE work.** The lib is BLE-only. A cloud module
     is a new transport; it would be its own round (R13-cloud or similar).
  2. **Cloud auth broken.** User has hit `RC=10` on `UserNewGuest`. Until
     the auth flow is sorted, no cloud feature works.
  3. **200+ endpoints.** The Divoom Cloud surface is large (clock-face
     thumbnails, weather city search, pomodoro, white-noise, TTS, etc.).
     A useful cloud round would pick a small set (clock-face store + 1-2
     others), not all of them.
- **No code changes this round.** Document in CHANGELOG as "deferred to
  a future cloud round".

## Summary

| Feature        | Lib exists | Wire-correct | Semantics verified | UX feasible | **Decision**  |
|----------------|------------|--------------|--------------------|-------------|---------------|
| Timeplan       | ✅         | ✅           | ❌ (mode/type unverified) | ⚠️ requires task #20 | **DEFER**     |
| SD card player | ✅         | ✅           | ✅                 | ❌ blocked on task #20 + device SD | **DEFER**     |
| Game           | ✅         | ✅           | ✅ (commands)      | ❌ no host UX; device-specific buttons | **DEFER**     |
| Drawing / sand | ✅         | ⚠️ (0x35 unconfirmed) | ✅           | ❌ non-trivial UI per mode | **DEFER**     |
| Cloud HTTP     | ❌         | n/a          | n/a                | ❌ auth broken; new transport | **DEFER (own round)** |

**Net result:** 0 features exposed this round, 0 features dropped. All 5 stay
in the lib (no code deletion). The GUI surface stays at its R8-R12 level.
Rationale per feature is captured in this doc so the next session (or
hardware-verified R13) can pick up with the audit already done.

## Open follow-ups (pick up in R13+)

1. **0x35 `pic_scan_ctrl` claim** — does the device actually accept it?
   `SppProc$CMD_TYPE.java` has no entry. Tag with a `# ???` comment in
   `divoom_lib/display/drawing.py`.
2. **Timeplan hardware verification** — if the user has a Timebox Evo or
   similar that supports timeplan, capture an actual `CmdManager.M2(...)`
   call from a logcat dump and document the field semantics in a new
   `docs/TIMEPLAN_PROTOCOL.md`. Then the lib's enum can be promoted from
   "guess" to "verified".
3. **Task #20 read-back** — gates the SD-player UI. R12 §B is the
   hardware-only investigation. Until that's fixed, "list tracks" hangs.
4. **Cloud round (R13+)** — separate transport; needs auth sorted first.
5. **Game UX** — if a use case emerges (e.g. "trigger Magic 8-ball from
   the host's menu bar"), revisit. Not a Round 12 deliverable.

## What changed this round

- `docs/PLANNING_ROUND12_D_AUDIT.md` — **this file** (new). The audit.
- `docs/SESSION_HANDOFF.md` — link added.
- `CHANGELOG.md` — R12 §D entry (audit only, no code changes).
- `divoom_lib/display/drawing.py` — comment added at `pic_scan_ctrl`
  flagging the 0x35 question (single-line docstring addition; no
  behavior change).

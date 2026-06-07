# Planning: Round 9 excavation — the APK-only frontier _(2026-06-06)_

> **Input:** "Do another round of feature excavation from the references and the
> apk." → "first write everything down to an md file, then go step by step."
>
> R8 closed the **lib→GUI** gap (library had ~140 methods, GUI exposed ~58 → now
> surfaces device settings / FM / weather / memorial). R9 targets a *different*
> frontier: capabilities the **APK/references have but `divoom_lib` does NOT
> implement at all** — these need *new lib code*, not just a GUI bridge.

---

## §1 Full APK-only command inventory (the "everything" dump)

Source: `references/apk/APK_INTELLIGENCE_REPORT.md` +
`references/apk/decompiled_src/sources/com/divoom/Divoom/bluetooth/`
(`SppProc$CMD_TYPE.java`, `SppProc$EXT_CMD_TYPE.java`, `CmdManager.java`, `s.java`).

### A. `SppProc$EXT_CMD_TYPE` — sub-commands of the 0xBD wrapper

The app sends these via `SPP_DIVOOM_EXTERN_CMD` (our `COMMANDS["set design"]`,
**0xBD**), payload = `[ext_id, ...args]`. Our `divoom_lib/display/design.py`
(`Design`) already wraps a few (0x14/0x15 user-define-time, 0x1E EQ, 0x26 lang).

| Ext (dec / hex) | Name | Confirmed payload (from CmdManager.java) | In lib? | R9? |
|---|---|---|---|---|
| 16 / 0x10 | SppExtCarMode | `[16, 1, on]` | no | later |
| 17 / 0x11 | SET_KEY_PIC | `[17, …]` | no | later |
| 18 / 0x12 | SET_KEY_FUNC | `[18, 0]` | no | later |
| 19 / 0x13 | SET_GIF_TYPE | `[19, 1]` | no | later |
| 20 / 0x14 | SET_USER_DEFINE_TIME | `[20, lo, hi]` | **yes** | — |
| 21 / 0x15 | GET_USER_DEFINE_TIME | `[21]` | **yes** | — |
| 26 / 0x1a | SET_AUTO_CONNECT_CFG | `[26, on]` | no | later |
| 27 / 0x1b | SET_GIF_PLAY_TIME_CFG | `[27, lo, hi]` | no | later |
| 28 / 0x1c | SET_MUSIC_NAME_CFG | `[28, 1, b,b,b,b]` / `[28,0]` | no | later |
| 29 / 0x1d | RECORD_CTRL | `[29, 0]` | no | later |
| 30 / 0x1e | KARAOKE_CTRL (≠ our EQ?) | `[30, …]` | partial | verify |
| 32 / 0x20 | WIRELESS_MIC_CTRL | `[32, 0]` | no | later |
| 33 / 0x21 | TOUCH | input event | no | n/a |
| **35 / 0x23** | **SET_SCREEN_DIR_CFG** | **`[35, dir]`** (0xFF = query) | no | ** Pick A** |
| **36 / 0x24** | **SET_SCREEN_MIRROR_CFG** | **`[36, on]`** (0xFF = query) | no | ** Pick A** |
| **37 / 0x25** | **CLEAR_SYS_CFG** (factory reset) | **`[37, 1]`** | no | **️ Pick D (gated)** |
| 38 / 0x26 | SET_LANGUAGE | `[38, lang]` | **yes** | — |
| 39 / 0x27 | SUPPORT_MORE_ANCS | `[39]` | no | with ANCS |
| 47 / 0x2f | OPEN_SCREEN_CTRL (screen on/off) | `[47, on]` | check | maybe |
| 50 / 0x32 | SEND_DEVICE_EQUALIZER_CTRL | `[50, …]` | no | later |
| 51 / 0x33 | SEND_DEVICE_LIGHT_EFFECT_CTRL | `[51, …]` | no | later |

**Confirmed call sites** (`CmdManager.java`):
- `Y2(int i9)` → `[SET_SCREEN_DIR_CFG, (byte)i9]` (line 1050); query variant
  sends `[…, -1]` (line 1395). Parser reads it back in `s.java:938`.
- `Z2(byte b9)` → `[SET_SCREEN_MIRROR_CFG, b9]` (line 1078); query `[…,-1]`
  (1423); parser `s.java:942`.
- factory reset → `[CLEAR_SYS_CFG, 1]` (line 968).

### B. `SppProc$CMD_TYPE` — top-level commands NOT in `models/commands.py`

| Cmd (dec) | Name | Status in lib | Note |
|---|---|---|---|
| 5 | CHANGE_MODE (BT/FM/LineIn/SD/UAC) | **have** `set work mode` 0x05 | needed for FM |
| 49 | LIGHT_CURRENT_LEVEL (get brightness) | have via 0x46 light read | — |
| 50 | LIGHT_ADJUST_LEVEL | no | low |
| **116** | **SET_SYSTEM_BRIGHT** | **HAVE** = `set brightness` **0x74** (`device.set_brightness`) | **GUI-expose** |
| 80 | SET_ANDROID_ANCS (notif mirror) | no | **Pick C (own round)** |
| 52 | SAND_PAINT_CTRL | have `sand paint ctrl` 0x34 | display |
| 88/90/91/92 | DRAWING_PAD_* | have drawing.py | display |
| 137 | SEND_GAME_SHARK | have `send game shark` 0x88 | game |
| 163-167 | SCENE/ALARM listen + sound ctrl | have (sound.py) | — |
| 173/174 | SLEEP_COLOR / SLEEP_LIGHT | have 0xad/0xae | sleep |

> **Key correction discovered while excavating:** `SPP_SET_SYSTEM_BRIGHT` (116) =
> **0x74**, which the lib already implements as `device.set_brightness(0-100)`.
> So "system brightness" is a **GUI-exposure** task (like R8), not new lib code.

### C. Notification mirroring (`SPP_SET_ANDROID_ANCS`, cmd 80)

Payload `[notif_type, R, G, B]`; 14 app types (Kakao=1 … WhatsApp=6, SMS=7 …
OK=14). On Android the OS feeds notifications; on macOS we'd need to source from
host notifications (Notification Center has no clean public push-observer API) →
**expensive, its own round.** Deferred.

### D. Cloud HTTP surface (200+ endpoints)

Out of scope for BLE-first R9 (clock-face store, weather city search, pomodoro,
white-noise, TTS, etc.). Catalogued in the APK report §2 for a future cloud round.

## §2 R9 scope decision

| Pick | What | New lib code? | Risk | Ship in R9 |
|---|---|---|---|---|
| **A. Screen orientation** | `set_screen_dir`, `set_screen_mirror` | yes (3 EXT subcmds in design.py) | LOW | **YES** |
| **B. System brightness** | expose `device.set_brightness` (0x74) | no (GUI only) | LOW | **YES** |
| **D. Factory reset** | `factory_reset` (EXT 37) | yes (1 subcmd) | **DESTRUCTIVE** | YES, behind double-confirm |
| C. Notification mirror | ANCS push | yes + macOS plumbing | HIGH | **defer** |

Rationale (Kare + Rams): A and B are honest, everyday controls with low risk and
high value; the only genuinely new plumbing is the three 0xBD EXT subcmds (the
wrapper already exists). D is cheap to add but destructive, so it ships *only*
behind an explicit double-confirm and is never auto-invoked.

## §3 Step-by-step implementation plan

**Step 1 — lib (`divoom_lib/display/design.py`)**
- Add sub-cmd constants: `SUB_SCREEN_DIR = 0x23`, `SUB_SCREEN_MIRROR = 0x24`,
  `SUB_CLEAR_SYS = 0x25`.
- `async def set_screen_dir(self, direction: int) -> bool` → `_send_subcmd(0x23,
  [direction & 0xFF])`. Accept 0–3 (0°/90°/180°/270°); clamp/validate.
- `async def set_screen_mirror(self, on: bool) -> bool` → `_send_subcmd(0x24,
  [1 if on else 0])`.
- `async def factory_reset(self) -> bool` → `_send_subcmd(0x25, [1])`.
- Confirm the `Design` facade is reachable as `d.design` (check `divoom.py` /
  `__init__`); if not, note the access path used by the bridge.
- Unit tests in `tests/` asserting the exact bytes via a fake `CommandSender`
  (or the mock device): `0xBD 23 dd`, `0xBD 24 0/1`, `0xBD 25 01`.

**Step 2 — GUI bridges (`gui/gui_api.py`)**
- `set_screen_dir(self, direction)` → `_tool_call(lambda d: d.design.set_screen_dir(int(direction)), "screen direction")`.
- `set_screen_mirror(self, on)` → `… d.design.set_screen_mirror(self._as_bool(on))`.
- `set_brightness(self, level)` → `… d.device.set_brightness(max(0,min(100,int(level))))` (wraps existing 0x74).
- `factory_reset(self, confirm)` → require `confirm == "RESET"` (string) else
  return False without sending; only then `d.design.factory_reset()`. (Belt &
  suspenders behind the UI double-confirm.)
- Unit tests in `tests/test_gui_api.py` (mock device; assert call + the
  confirm-guard rejects a missing/wrong token).

**Step 3 — GUI UI (Tools → Device sub-tab)**
- `templates.js`: new **Display** card in `tools-device`:
  - Orientation `<select>` (0°/90°/180°/270°) → `set_screen_dir`.
  - Mirror toggle → `set_screen_mirror`.
  - **Brightness** slider (0–100, live value) → `set_brightness` (debounced).
  - **Factory reset** button → JS `confirm()` + typed "RESET" prompt →
    `factory_reset("RESET")`. Styled as destructive (red), set apart.
- `settings.js`: wire the new controls (delegated, in the existing R8 block).
- `settings.css`: minor styles for slider + destructive button if needed.

**Step 4 — verify + close round (core rule)**
- `python3 -m pytest` → full suite green; record pass/skip counts.
- Update `docs/SESSION_HANDOFF.md` (Current state + Open threads),
  `CHANGELOG.md` (R9 entry), this file §5 (outcome).
- Commit with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Do **not** push unless the user asks.

## §4 Risk / caveats

- Screen dir/mirror are **device-capability-dependent** (Times Gate / multi-panel
  vs. a single 16×16). Send is fire-and-forget; the get/0xFF query path depends on
  the broken read-back (task #20) so the UI is **set-oriented**, no pre-populate.
- Factory reset is irreversible on the device → double-confirm, never auto, and
  the bridge refuses without the explicit "RESET" token.
- Direction byte semantics (which value = which rotation) are inferred (0–3); the
  app's `Y2` just forwards the int. Verify exact mapping on hardware later; UI
  labels can be corrected without protocol change.

## §5 Implementation outcome — shipped 2026-06-06

Picked A (screen orientation) + D (gated factory reset). **B (system brightness)
was dropped from R9**: excavation revealed it already exists as
`device.set_brightness` (0x74) with a full LAN/multi-target `gui_api.set_brightness`
bridge + appbar slider — re-adding it would have shadowed the richer impl (caught
by a failing test mid-implementation). So R9 = the genuinely-new 0xBD EXT work.

Shipped (step by step):
1. **lib** `divoom_lib/display/design.py`: `set_screen_dir` (0xBD 0x23),
   `set_screen_mirror` (0xBD 0x24), `factory_reset` (0xBD 0x25,1). 5 unit tests
   asserting exact bytes (`tests/test_round4_p1_helpers.py`).
2. **bridges** `gui/gui_api.py`: `set_screen_dir`, `set_screen_mirror`,
   `factory_reset(confirm)` — refuses unless `confirm == "RESET"`. 3 unit tests
   incl. the token guard (`tests/test_gui_api.py`).
3. **UI** Tools→Device **Display** card: orientation `<select>`, mirror toggle,
   `.danger-zone` factory-reset button with `confirm()` + typed-"RESET" prompt.
   `settings.js` wiring; `settings.css` danger styles. 3 static UI/exposure tests
   (`tests/test_round6_layout_and_exposure.py`).

Full suite: **527 passed / 0 failed / 73 skipped**.

Deferred: C (ANCS notification mirroring) — own round; CMD-type top-level
commands + 200+ cloud endpoints catalogued in §1 / APK report for later.

Hardware to verify: exact direction-byte→angle mapping; whether the target
device supports orientation/mirror at all (capability-gated; UI is set-only since
read-back still times out, task #20).

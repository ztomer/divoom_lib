# Planning: Round 9 excavation — the APK-only frontier _(2026-06-06)_

> **Input:** "Do another round of feature excavation from the references and the apk."
>
> R8 closed the **lib→GUI** gap (library had ~140 methods, GUI exposed ~58 →
> now surfaced device settings/FM/weather/memorial). The remaining frontier is
> different: capabilities the **APK/references have but `divoom_lib` does NOT
> implement at all** — these need *new lib code*, not just a GUI bridge.

---

## §1 Finding — APK-only commands (no lib yet)

From `references/apk/APK_INTELLIGENCE_REPORT.md`:

- **~60 BLE commands** in `SppProc$CMD_TYPE` + `SppProc$EXT_CMD_TYPE` are absent
  from `divoom_lib/models/commands.py`.
- **EXT commands** (sent via `SPP_DIVOOM_EXTERN_CMD` = 0xBD wrapper):
  - `SPP_SECOND_SET_SCREEN_DIR_CFG` (35) — **screen rotation** (direction byte).
  - `SPP_SECOND_SET_SCREEN_MIRROR_CFG` (36) — **screen mirror / flip**.
  - `SPP_SECOND_CLEAR_SYS_CFG` (37) — **factory reset** (destructive).
- **Notification mirroring** — `SPP_SET_ANDROID_ANCS`, 14 app types
  (WhatsApp/Instagram/…) + RGB colors. High value, but Android-notification
  semantics; on macOS we'd source from host notifications (complex).
- **System brightness** — `SPP_SET_SYSTEM_BRIGHT` (116),
  `SPP_LIGHT_ADJUST_LEVEL` (50), `SPP_LIGHT_CURRENT_LEVEL` (49 query).

## §2 Candidate picks (Kare + Rams)

| Pick | Scope | Risk | Value |
|---|---|---|---|
| **A. Screen orientation** | EXT 0xBD wrapper + `set_screen_dir` / `set_screen_mirror`; small "Display" controls in Tools→Device | LOW (new lib code, but simple one-shot) | HIGH (common need) |
| **B. System brightness** | `set_system_brightness(0-100)`; slider in Control Center / Device | LOW | MED-HIGH |
| **C. Notification mirroring** | host→device ANCS push, 14 app types + color | HIGH (macOS notification plumbing) | HIGH but expensive |
| **D. Factory reset** | EXT 37; heavily gated, double-confirm | **DESTRUCTIVE** | LOW (rare) |

## §3 Recommendation

**Phase 1 (R9):** Pick A (screen rotate/mirror) + Pick B (system brightness) —
both are small new-lib-code additions (the 0xBD EXT framing wrapper is the only
genuinely new plumbing) with everyday value and low risk. Verify framing against
the smali (`SppProc$EXT_CMD_TYPE`) and node/fhem refs before wiring UI.

**Defer:** C (notification mirroring) = its own round; D (factory reset) only on
explicit request, behind a double-confirm, never auto.

## §4 Open question for the user

Pick the R9 scope (default: A + B). **Stop and ask** — see accompanying
AskUserQuestion.

## §5 Implementation outcome

_(filled after shipping)_

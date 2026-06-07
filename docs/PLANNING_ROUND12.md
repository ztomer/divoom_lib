# Planning: Round 12 — consolidation + continuation _(2026-06-06)_

> **Input:** "C, A, D, E then B. Write down the plan. Consolidate lessons learned
> where agents can read them. Remove stale items. Plan. Implement."

Execution order (user-specified): **C → A → D → E → B**. B (hardware verification)
is last and not code-actionable by an agent — it stays a checklist for the user.

---

## §0 Consolidate lessons + prune stale (do first)

- **Lessons** → new `docs/ENGINEERING_NOTES.md`, linked from `AGENTS.md` so every
  agent reads it on entry. Captures the image-pipeline invariants, the
  dual-impl anti-drift rule, "ACK ≠ success", and "verify protocol against the
  decompiled APK + `references/`, not prose."
- **Stale removal:** refresh `docs/SESSION_HANDOFF.md` (it still lists R10 as last
  shipped); prune resolved open threads; delete stale/duplicate planning notes;
  clean the task list.

## §C — Anti-drift / infra follow-ups (FIRST)

1. **Framing encoders dual-impl test.** `encode_basic_payload` /
   `encode_ios_le_payload` have C + Python twins but only the live (C) path is
   tested. Add `tests/test_framing_both_impls.py`: parametrize impl over
   {c, python-forced via `framing.lib=None`}, assert **correctness**
   (encode → `parse_basic_protocol_frames` round-trips; checksum/length/escape
   correct), not mutual agreement.
2. **CI sanity.** The committed `.github/workflows/tests.yml` is untested on
   GitHub. Keep it; verify on first push (part of §E).

## §A — R11 GUI overhaul, Phases 2–7

Design decisions already locked (R11): wall toolbar = icons **+ labels**; unified
sub-tab style = **segmented pill**; volume slider stays **plain**.

- **Phase 2 (quick wins):** 1a sticky push footer (custom-art gallery, reuse the
  Monthly-Best pattern); 3a ambient color controls only for "Plain color"; 3b
  drop "Custom"; 5a scoreboard Reset.
- **Phase 3 (appbar):** 4a unify volume-slider font w/ light slider; 4b connection
  indicators → bottom-right; 4c sliders → right; 4d slider-drag `no-drag` fix;
  4e light-slider thumb brightness mapping.
- **Phase 4:** 5b scoreboard restyle (large, centered, blue-over-red).
- **Phase 5:** 6 virtual-wall toolbar (icons+labels: add / clear / preset name /
  save / load).
- **Phase 6:** 7 font sweep — global `font-family: var(--font-sans)` so nothing
  falls back; remove ad-hoc font decls.
- **Phase 7:** 8 tools regroup (Time = alarms+anniversary; Sleep → Tools; FM →
  Tools; Weather → Live Widgets; Device settings → Settings → Devices) + 8f one
  segmented-pill sub-tab component everywhere. Update R8/R9/R10 UI-presence tests
  to new locations.

## §D — Deferred features

- **Timeplan UI** (R8): bridge exists + tested; protocol mode/type unverified →
  needs hardware before a real UI card. Keep deferred unless verified.
- **R9 deferred:** SD player, game/magic-8-ball, drawing/sand — lib→GUI exposure
  (lib methods exist). Medium effort each; own sub-tasks.
- **R10 deferred:** auto-source real macOS notifications (own project); the 200+
  cloud HTTP endpoints (clock-face store w/ real thumbnails, weather city search,
  pomodoro, white-noise, TTS) — a separate "cloud" round, not BLE.

## §E — Housekeeping (after C/A/D)

- Update `SESSION_HANDOFF.md` + `CHANGELOG.md` for everything shipped.
- Push the R8→R12 arc to origin (confirm with user).

## §B — Hardware verification (LAST; user-run)

- Album cover renders un-distorted; custom-art GIF + live cover/stocks/sysmon
  push end-to-end.
- `get_*` read-back timeout (task #20) — gates read-from-device everywhere.
- Channel-switch bug (Divoom Max): first works, rest don't.

## §outcome

- **§0 done:** lessons → `docs/ENGINEERING_NOTES.md` (linked from AGENTS.md);
  AGENTS.md APK-path fixed; SESSION_HANDOFF refreshed to R11/R12; 35 stale
  completed tasks pruned.
- **§C done:** `tests/test_framing_both_impls.py` (correctness on both C +
  Python framing encoders). It caught **two real Python-fallback bugs**
  (list→memoryview TypeError in `encode_basic_payload` escape branch and
  `encode_ios_le_payload` header) that would crash framing on any platform
  without the dylib — both fixed. Suite 666 passed / 0 failed.
- **§A Phase 2 done:** 1a custom-art "Push to Device" is now a pinned footer
  (`#panel-design.active` flex column + sticky button); 3a ambient color
  controls (+favorites) hidden unless mode = Plain Color
  (`updateAmbientColorVisibility`); 3b "Custom" label removed; 5a scoreboard
  Reset button. +3 UI-presence tests. Suite 669 passed / 0 failed.
- **§A Phases 3–7 / §D / §E:** not started — staged below.

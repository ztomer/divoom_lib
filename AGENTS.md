# Agent rules — divoom-control

Shared rules for any coding agent working in this repo (opencode, Claude, etc.).

## CORE RULE: keep the session handoff updated after every round

This project is worked across multiple agents/sessions (opencode + Claude) that
**share this git working tree**. They CANNOT share a live session (separate
conversation stores), so the handoff is file-based. **On entry, read
`docs/SESSION_HANDOFF.md`.** After **each round of work**, before you stop, you
MUST update the handoff so the *next* session — including the opencode session
`ses_184471307ffeCUHgzv9w51O0oA` — can pick up without re-deriving state:

1. **docs/SESSION_HANDOFF.md** — update "Current state" + "Open threads / next
   up". This is the canonical living state both tools read first.
2. **CHANGELOG.md** — add/extend the round's entry (what shipped, where, why).
3. **docs/PLANNING_ROUNDn.md** — fill the "outcome / what shipped" section of the
   current round's plan (and create the next round's plan when starting one).
4. **Commit** the work with a clear, scoped message (one logical change per
   commit) so `git log` is a faithful, readable history of the round.
5. **Tests green** before you call a round done (`python3 -m pytest`), and state
   the pass/skip counts in the handoff + CHANGELOG.

The git history + `docs/SESSION_HANDOFF.md` + CHANGELOG ARE the cross-session
memory. Treat them as the source of truth; do not rely on conversation context
surviving. (Claude Code reads `CLAUDE.md` which points here; opencode reads this
`AGENTS.md` directly.)

> To resume the opencode session for context: `opencode export <sessionID>`
> dumps it as JSON (`info` + `messages`).

## Project conventions

- **Device protocol truth**: `divoom_lib/` + `apk/APK_INTELLIGENCE_REPORT.md` +
  `references/`. Don't invent command IDs/enums — cite the source.
- **GUI**: PyWebView. Python bridge in `gui/gui_api.py` (+ mixins); web UI in
  `gui/web_ui/` (modular css/js; large views live in `templates.js`).
- **Hardware**: macOS Bluetooth TCC is per responsible-process; drive real BLE
  by launching via Terminal (`open *.command`). See `docs/DEVICE_VALIDATION_PLAN.md`.
- **Tests**: hardware tests are gated/skip by default (`tests/conftest.py`);
  prefer the mock-device E2E (`tests/test_e2e_mock_device.py`) for wire checks.
- **Build discipline**: delete dead code; document the decision, not just the
  code; foundation before cutover; test before you trust.

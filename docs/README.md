# docs/ index

## Current / canonical (read these)
- **[../README.md](../README.md)** — project overview, install, run.
- **[../ARCHITECTURE.md](../ARCHITECTURE.md)** — system map (3 packages + daemon +
  protocols + transports + platform support).
- **[REVIEW_2026-06.md](REVIEW_2026-06.md)** — latest code/architecture (Linus +
  Uncle Bob), UI/UX (Rams + Kare), and "rewrite in Rust?" review.
- **[SESSION_HANDOFF.md](SESSION_HANDOFF.md)** — live cross-session state + open
  threads. Update every round.
- **[BACKLOG.md](BACKLOG.md)** — the single living roadmap of open features/fixes.
- **[../CHANGELOG.md](../CHANGELOG.md)** — shipped milestones.
- **[../AGENTS.md](../AGENTS.md)** / **[../CONTRIBUTING.md](../CONTRIBUTING.md)** —
  conventions for agents + humans.
- **[../CLAUDE.md](../CLAUDE.md)** — Claude-specific project instructions.

## Reference
- **[DIVOOM_PROTOCOL_SUMMARY.md](DIVOOM_PROTOCOL_SUMMARY.md)** — protocol cheat
  sheet.
- **[DIVOOM_API_DOC.md](DIVOOM_API_DOC.md)** — fuller protocol/API notes.
- **[MCP_SERVER.md](MCP_SERVER.md)** — the MCP server (daemon-routed, R28).
- **[NOTIFICATIONS_SETUP.md](NOTIFICATIONS_SETUP.md)** — macOS notification setup.
- **Device bitmap font** — `divoom_lib/fonts/` + `scripts/extract_apk_font.py`
  (APK-derived 1-bit font for crisp device text; R28).
- **[TESTING_STRATEGY.md](TESTING_STRATEGY.md)** — test approach.
- **[divoom_docs/](divoom_docs/)** — captured upstream/device docs.

## Historical audit trail (planning rounds — kept, not maintained)
`PLANNING_ROUND3.md` … `PLANNING_ROUND28.md` record each round's plan + outcome.
They are point-in-time records; for current state read SESSION_HANDOFF + the
canonical docs above. Notable: R16 (daemon), R17 (3-package split + single-owner
cutover), R19 (network server), R20 (Linux compat), R26 (channel/weather fix),
R28 (MCP-via-daemon, scan filter, tab layout, device bitmap font). (R27 command
queue has no planning doc — see CHANGELOG + SESSION_HANDOFF.)

> Stale docs (CODE_REVIEW, APP_IMPROVEMENT_PLAN, PLANNED_WORK,
> next_phase_requirements, DESKTOP_GUI, ENGINEERING_NOTES, brightness_investigation,
> DRAG_FIX_HISTORY, DEVICE_VALIDATION_PLAN, PLANNING_ROUND2_CONTINUATION) were
> removed in the 2026-06 doc cleanup — recover from git history if needed.

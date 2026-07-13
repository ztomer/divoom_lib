# Next phase — roadmap after the REVIEW_2026-06 cleanup

**Written 2026-06-09.** The cleanly-codeable review items are shipped (coverage,
§1.2 notifications Phase 1, dead CSS, asyncio, §2.3 `!important`). What remains is
browser-observable UI work and two larger architectural arcs. This doc sequences
them so the next session can start cold.

## Where we are

Pushed to `origin/main` through `d871c350`. Suite **1158 passed / 75 skipped**
on `/opt/homebrew/bin/python3.14` (the only interpreter with pytest here).

Review scorecard: §0.5 #1–#3 done, #4 Phase 1 done, #6 done. Open: **#4 Phases
2–3**, **#5 inline styles**. Plus two never-scheduled big-ticket items the review
raised: **§1.5 `DivoomGuiAPI` split** and **§4.2 event bus**.

## Recommended order (value ÷ risk)

### 1. Inline-style migration — batch 1 only, first. LOW RISK.
`docs/PLANNING_inline_styles.md`. **Batch 1 is a pure addition** to
`style_extra.css` (utility classes `.row/.col/.gap-*`, `.label-sm/.text-sm`,
`--warn`/`--error` tokens) with **no template edits** — nothing can visually
break, and it unblocks every later batch. Do this even if nothing else.
Acceptance: utilities exist, suite still green, no template references them yet.

### 2. Notification Phases 2–3. MEDIUM. Finishes a half-done feature.
`docs/PLANNING_daemon_ownership.md`. Phase 1 (the double-route fix) shipped;
2–3 make the Settings toggle reflect the daemon's *broadcast* state (so the UI is
truthful when the daemon auto-started the listener before the GUI opened) and
move routing config fully daemon-side. Touches `settings_features.js` + the
`DaemonClient.subscribe` event stream. **Needs the live GUI to verify** the
toggle reacts to broadcasts — schedule with the app running.

### 3. Inline-style batches 2–5. MEDIUM, browser-observable.
After batch 1 lands: `templates_tools.js` + `templates_monthly_best.js` →
`routines` → `widgets` → `settings` (sub-batched). One commit per file, visual
verify each via the static-server + preview harness (proven on the §2.3 fix;
`.claude/launch.json` already has `web_ui-static` on :8799). ~90 of 138 styles
migrate; ~50 stay inline per §2.1's exception.

### 4. (Stretch) §1.5 `DivoomGuiAPI` split + §4.2 event bus. LARGE.
Not blocking anything. The collaborator pattern (`divoom_gui/api/`) is already the
on-ramp — `gui_api.py` is now 454→~400 lines after this session's deletions.
Continue extracting per-concern APIs only when a feature touch makes it natural;
don't do a big-bang refactor. The event bus (§4.2) is largely moot now that the
daemon broadcasts events and owns the device — re-evaluate whether it's still
worth it before investing.

## Standing conventions for whoever picks this up
- Run tests on `/opt/homebrew/bin/python3.14`. Coverage:
  `python3.14 -m coverage run -m pytest && python3.14 -m coverage report`
  (config now in `pyproject.toml`).
- No emojis anywhere in the repo (`tests/test_no_emojis.py` enforces it).
- Update `SESSION_HANDOFF.md` + `CHANGELOG.md` + the relevant `PLANNING_*.md`
  each round; commit per logical change; keep the suite green.
- For UI changes: verify with the static-server + preview tools, don't eyeball.
- `/zreview` (`.claude/commands/zreview.md`) re-runs the four-lens review with
  mandatory per-finding verification — run it again before the next big push.

## Suggested first commit of next session
Batch 1 of `PLANNING_inline_styles.md` (utility layer). Self-contained,
zero-risk, unblocks the rest.

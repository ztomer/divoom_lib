# PLANNING_ROUND61 — doc cleanup, 95% coverage, cloud API, loose ends, device verify, release

**Date:** 2026-07-12/13
**Head before round:** `af9fcd4` (feat(cloud): fix UserNewGuest RC=10 + clock-face store +
weather-city search) + 4 uncommitted "R61 coverage push" test files found on entry
(`tests/test_device.py`, `test_device_settings.py`, `test_mcp_tools.py`,
`test_tools_small.py` — 86 tests, all green, untracked).

## Goal (user-directed order, 2026-07-12)

0. Update stale documents, remove obsolete ones.
1. Reach **95% test coverage**.
2. Finish the Cloud API work.
3. Chase the loose ends (Timoo-light-4 re-verify, user-POV physical-screen visuals).
4. Verify device detect + connect works end-to-end from **both** the UI and the daemon.
5. Cut a release.

Run via `/loop` (self-paced, no fixed interval) until every item below is checked off.
Each iteration: pick the next unchecked item, do real work (not just planning), verify
with actual commands/tests/hardware where applicable, commit, update this file's
checkboxes + `SESSION_HANDOFF.md` + `CHANGELOG.md`, then continue.

---

## 0. Doc cleanup

- [x] Commit the 4 untracked "R61 coverage push" test files (86 tests green) — done,
      commit `c851811`; also untracked the stray `.coverage` binary artifact.
- [x] Inventory `docs/*.md` (was 25 files, now 14 at top level). Archived 9 fully-shipped
      docs to `docs/archive/` (rounds 57-60, BLE/socket hardening, daemon ownership,
      native-port hardening, next-phase, arch-gap-scan, native-UI parity tracker) via
      `git mv`, each cross-checked shipped first — commit `6941e5f`. Fixed a stale
      "TODO: not implemented" claim in `CUSTOM_CHANNEL_VS_APK.md` (6 rows actually
      shipped). Reference docs (APK_COMPARISON, CUSTOM_CHANNEL_VS_APK, CHANNEL_ARCHITECTURE,
      DIVOOM_API_DOC, DIVOOM_PROTOCOL_SUMMARY, MCP_SERVER, NOTIFICATIONS_SETUP,
      RELEASING, TESTING_STRATEGY, README) kept as-is — load-bearing, no false claims.
- [x] `ROADMAP.md` refreshed: planning-doc index repointed to archive paths; added the
      stalled inline-style migration (batch 2/5) as a live backlog line.
- [x] `grep -rn "not ported\|TODO\|FIXME\|deferred" docs/` checked — the one stale hit
      (CUSTOM_CHANNEL_VS_APK) fixed above; rest are intentional/accurate.
- [ ] `SESSION_HANDOFF.md` is 1280+ lines of accreted history — still needs a trim to
      current state + open threads (deep history already lives in git log / CHANGELOG).
      Deferred: risky to do while the file is being actively appended to mid-round;
      revisit once items 1-5 are closed and no more entries are landing.
- **Kill:** `docs/` tree matches reality; no doc contradicts current code state. (Mostly
  met — SESSION_HANDOFF trim is the one remaining sub-item, explicitly deferred above.)

## 1. Coverage >= 95%

- [x] Baseline: 69% (13831 stmts, 3941 missed) — but a full-suite `pytest --cov` run
      couldn't even complete before this round: `tests/test_spp_integration.py` let a
      real `BleakClient.connect()` reach CoreBluetooth, SIGABRTing the interpreter.
      Fixed (commit `e26fc6d`) by mocking at the correct call-time import site
      (`divoom_lib.divoom.BleakClient`, not the `ble_transport` module-level name —
      BLETransport re-imports it locally at call time).
- [x] Wave 1 (commit `a15a628`): 6 parallel agents closed the 6 biggest gaps —
      cli_commands.py, monthly_best_daemon.py, presets_manager.py, media_sync.py,
      gallery_hot_api.py, gallery_sync.py — all 20-61% -> 98-100%. TOTAL 69% -> **76%**
      (3941 -> 3043 missed). Full suite: 2184 passed, 0 failed, 91 skipped.
- [x] Wave 2 (commit `11d5beb`): scanner_mixin.py, utils/media_source.py,
      bt_spp_rfcomm.py, bt_spp_transport.py, api/tools.py, api/lighting.py,
      media/music.py, device_owner.py, audio_visualizer.py all -> 99-100%;
      gui_main.py -> 99% with two narrow individually-justified `# pragma: no cover`
      lines (documented in the commit). TOTAL 76% -> **83%** (3043 -> 2051 missed).
      Full suite: 2499 passed, 0 failed, 91 skipped.
- [ ] Wave 3 in flight (8 agents): animation_user.py, media_decoder.py,
      api/connection.py + gui_api.py, daemon owner_live/owner_connect/owner_art.py,
      mcp_control.py + mcp_server.py, connection.py + ble_transport.py (highest BLE-
      hazard files, explicitly briefed on the test_spp_integration.py crash class),
      spp_bridge.py + divoom_auth.py, native/image_encoder.py + daemon_client.py +
      tools/hot_update.py.
- [ ] Further waves as needed on the next-biggest remaining gaps until >= 95%.
- [ ] Add defensible `[tool.coverage.report] exclude_lines` / `[tool.coverage.run] omit`
      only for genuinely untestable surface (CLI entrypoints, `__main__` blocks,
      platform-only branches, `web_ui/*.js`, hardware-gated paths) — list what's omitted
      and why, not a cover for laziness.
- **Kill:** `coverage report` TOTAL >= 95% on the configured source; omit list stated
  honestly in this file.

## 2. Cloud API work

- [x] `UserNewGuest` `RC=10` fixed (commit `af9fcd4`).
- [x] Clock-face store + weather-city search added (commit `af9fcd4`).
- [ ] Verify parity: Python `divoom_lib` cloud client vs Rust `divoomd/src/cloud*.rs` —
      same request/response shapes, both tested.
- [ ] Confirm what's left of the "finish cloud API work" ask beyond `af9fcd4` — check
      `SESSION_HANDOFF.md`/`CHANGELOG.md` for any cloud endpoint still stubbed/deferred
      and close it, or explicitly document it as out-of-scope-for-now.
- **Kill:** cloud client covered by tests (offline/mock mode), Python+Rust agree, no
  silent stub left in the cloud path.

## 3. Loose ends

- [ ] Timoo-light-4 re-verify (R60 #2): scan, connect, `display.show_image` with a
      cloud-decoded payload, post-push `get_brightness` read-back confirming no
      device-stick. If still out of BLE range, state that plainly — don't fabricate.
- [ ] User-POV pass on physical-screen visuals for the R60 show_clock canonical fix
      (real device, real screen, light+dark check per [[user-pov-debug]]).
- [ ] Re-scan `SESSION_HANDOFF.md`/`ROADMAP.md` for any other open thread not already
      captured above (e.g. Cloud HTTP round remainder, R12 visual/hardware arc) and
      either close it or explicitly re-defer with a reason.
- **Kill:** every loose end from R60 is closed, verified-false, or explicitly
  re-deferred with a stated reason (not silently dropped).

## 4. Device detect + connect verification (UI + daemon)

- [ ] Daemon: drive `divoomd` directly over the Unix socket — `scan` finds all
      reachable devices, `connect` succeeds per device, read-back (`get_device_name`/
      `get_brightness`) confirms the link.
- [ ] UI: launch the real `Divoom.app`/`./run.sh` GUI, drive scan + connect from the
      dashboard (browser/computer-use POV), confirm the device chip appears, connects,
      and a control (brightness/clock) round-trips.
- [ ] Confirm the daemon-down banner / reconnect path still behaves (regression check
      from R57-59 event-driven work) while doing this pass.
- **Kill:** both surfaces (daemon socket + UI) independently confirmed to detect and
  connect to every device currently in range, with real hardware evidence recorded
  here (not assumed from old rounds).

## 5. Release

- [ ] All of 0-4 committed and green (`python3 -m pytest`, `cargo test`, no-emoji gate).
- [ ] Bump `pyproject.toml` version; tag; `scripts/release.sh` (DMG build + GitHub
      release + Homebrew cask bump); `brew audit` clean.
- [ ] `git merge-base --is-ancestor <prior_release_tag> HEAD` sanity check before
      tagging (standing rule from the v0.22.0 divergence incident).
- **Kill:** new tag pushed, GitHub release published, Homebrew cask updated + verified.

---

## Loop progress log

_Each /loop iteration appends one line here: date, item worked, outcome._

- 2026-07-12: Plan written (this file), superseding the prior draft ordering to match
  the user's explicit 0→5 sequence. Found 4 uncommitted coverage-push test files on
  entry (86 tests, green) — folded into item 0.

## Risks / open questions (carried from prior draft)

- **95% coverage** across a GUI + BLE + daemon tree is a large test-writing effort;
  omit list must stay defensible.
- **Timoo** may again be out of range — re-run later, don't fabricate a pass.
- Device verification (item 4) needs a free BLE adapter and devices actually in range;
  if none are reachable this iteration, state that and retry later rather than
  skipping silently.

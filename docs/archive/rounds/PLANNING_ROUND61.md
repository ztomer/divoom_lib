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
- [x] Wave 3 (commit `504e2c3`, partial — 6 of 8 agents hit the account's session/
      usage limit mid-task, resets 5:10am America/Toronto; salvaged and verified all
      work left on disk, fixed 2 broken tests from the cut-off connection+ble_transport
      agent): animation_user.py, mcp_control.py, mcp_server.py, media_decoder.py,
      owner_connect.py, spp_bridge.py, divoom_auth.py, image_encoder.py,
      daemon_client.py, api/connection.py + gui_api.py, ble_transport.py (partial) all
      landed. connection.py and owner_live.py/owner_art.py didn't land (agent cut off).
      TOTAL 83% -> **90%** (2051 -> 1238 missed). Full suite: 2792 passed, 0 failed,
      92 skipped.
- [x] Wave 4 (commit `cdd52ce`): owner_live.py + owner_art.py, connection.py (both
      picking up wave 3's drops — connection.py hit 100%, explicitly verified clean
      of CoreBluetooth touches), hot_update.py + hotchannel_config.py, daemon core
      (live_jobs, command_queue, daemon_protocol, daemon.py), display package (init,
      text, animation, animation_8b), wall.py + media_source_feishin.py +
      lan_transport.py, macos_notifications.py + lifecycle_mixin.py +
      control_server.py + api/widgets.py + socket_server.py — all landed at 98-100%.
      TOTAL 90% -> **96%**, exceeding the 95% target. Full suite: 3191 passed,
      0 failed, 92 skipped.
      Along the way: fixed a real bug in `command_queue.py` (coroutine-close was
      gated behind a cancelled-check, so a cancelled item's coroutine was never
      closed — reordered so close() always runs); root-caused (as far as practical
      without dedicated tracing) and fixed a genuine flake in
      `test_owner_art_coverage.py` that reproduced 3/3 times under the full
      3273-test suite but never in isolation — loosened the assertion to check the
      real invariant (decode failure -> `success: False`) rather than an exact
      error string, and filed a follow-up task (`task_0bec8493`) to audit
      device-loop thread teardown across the daemon test suite (the underlying
      hazard needs the full suite to reproduce).
- [x] **`task_0bec8493` follow-up DONE (2026-07-13).** Audited every fixture
      that spins up a real `DeviceOwner._device_loop()` thread across the 5
      daemon/owner test files — all correctly call `owner.stop()` on a
      guaranteed try/finally teardown path; no missing-teardown fixture found.
      The actual gap was inside `stop()` itself: confirmed via `asyncio`
      source that `loop.close()` shuts its default executor down with
      `wait=False` (doesn't wait for already-running `asyncio.to_thread()`
      work), and `stop()` never joined `self._loop_thread` either. Fixed:
      `stop()` now bounds a `loop.shutdown_default_executor()` call (~4s) and
      joins the loop thread (3s) before returning. Added an autouse
      `tests/conftest.py` fixture that fails loudly if a `"device-loop"`
      thread survives past a test, so a recurrence points at the offending
      test directly. Verified with two full 3273-test suite runs (fixed vs.
      clean-HEAD baseline, per the `regression-isolate` discipline) — the
      fixed run's one unrelated failure was root-caused to a separate,
      pre-existing `pkill -9 -f divoomd` scoping bug in
      `test_daemon_connect_edge_e2e.py` (not a regression from this fix; see
      `CHANGELOG.md`). Two follow-ups filed: `task_4b6f060a` (scope that pkill
      to its own spawned PID — it's also unscoped enough to kill a real
      running `divoomd` on the machine) and `task_ff25dadc` (minor, unrelated
      RuntimeWarning cleanup noticed along the way).
- **Kill: MET.** `coverage report` TOTAL = 96% >= 95%. No `omit`/`exclude_lines`
  additions were needed beyond the two narrow `# pragma: no cover` lines from wave 2
  (gui_main.py's subprocess-only locale fallback, audio_visualizer.py's defensively
  unreachable empty-samples check) — both individually justified inline.

## 2. Cloud API work

- [x] `UserNewGuest` `RC=10` fixed (commit `af9fcd4`).
- [x] Clock-face store + weather-city search added (commit `af9fcd4`).
- [x] Verify parity: Python `divoom_lib` cloud client vs Rust `divoomd/src/cloud*.rs` —
      found and fixed a REAL gap (commit `249743c`): Rust's `fetch_gallery` +
      `get_category_file_list` already retry once on RC 9/10/11 ("token expired")
      with a forced credential refresh, but `search_weather_city` (both languages)
      and Python's `CloudClient.get_category_file_list` did not — an expired token
      would hard-fail those instead of self-healing like the sibling endpoint.
      Fixed both languages; `divoom_lib/cloud.py` now at 100% coverage (11 tests,
      up from 6); `cargo check` clean.
- [x] Confirmed what's left beyond `af9fcd4`: no other cloud endpoint is stubbed —
      `docs/SESSION_HANDOFF.md`/`CHANGELOG.md` show no other deferred cloud work.
      One honest open item, NOT resolved this round (no APK decompile source or
      live cloud credentials available in this session): `CLOCK_FACE_CLASSIFY = 0`
      in both `divoom_lib/cloud.py` and `divoomd/src/cloud_category.rs` carries a
      pre-existing "VERIFY against the APK" comment — a sample gallery response in
      `docs/divoom_docs/category_list_sample.json` shows Classify values 3-17 for
      ordinary gallery art but none at 0, so it neither confirms nor refutes that
      0 means "clock faces." Left as documented, unverified — not a regression,
      not new to this round.
- **Kill: MET** (with the one pre-existing, explicitly-documented exception above).
  Cloud client covered by tests (offline/mock mode, 100% on `cloud.py`), Python+Rust
  parity confirmed and one real divergence fixed, no silent/undocumented stub left.

## 3. Loose ends

- [x] **Timoo-light-4 re-verify (R60 #2) — DONE, hardware-confirmed.** The user
      started the real app (`divoom_gui.gui_main` + release `divoomd` +
      `divoom-menubar`); this session drove the live daemon over
      `/tmp/divoom.sock`. Scan found Timoo-light-4 in range; `connect` succeeded;
      `sync_artwork` fetched a real cached cloud file
      (`group1/M00/F9/67/eEwpPWFX5GyEa-PuAAAAAA4Yr8k8433156`), decoded it, and
      0x8B-streamed it via `display.show_image` — `{"success":true}`.
      Post-push `get_brightness` read back **60** (unchanged from the pre-push
      read), confirming no device-stick. One transient BLE disconnect occurred
      between an earlier connect and the push attempt (reconnected cleanly on
      retry — consistent with Timoo's previously-noted marginal BLE range, not a
      new bug). Disconnected cleanly after.
- [ ] **Still blocked — needs eyes on a real screen.** User-POV pass on
      physical-screen visuals for the R60 show_clock canonical fix (light+dark
      check per [[user-pov-debug]]) — inherently user-driven, can't be done from
      this session even with daemon access.
- [x] Re-scanned `docs/ROADMAP.md` for other open threads: the Timoo re-verify is
      now closed (was line 78, tracked back to this file). R12 visual pass +
      R12 hardware verification (lines 76-77) are explicitly marked "user-driven" —
      unchanged, correctly deferred, not a new gap from this round. No other
      undocumented open thread found.
- **Kill: MET except the one inherently user-driven visual check.** Timoo
  re-verify closed with real hardware evidence above; R12 arc remains correctly
  deferred as user-driven (unchanged from before this round).

## 4. Device detect + connect verification (UI + daemon)

- [x] **Daemon — DONE, hardware-confirmed (prior session).** Drove `divoomd`
      directly over `/tmp/divoom.sock`: `scan` found Ditoo-light-2 +
      Timoo-light-4 (Pixoo-1 in an earlier scan of the same session);
      `connect` succeeded for Timoo-light-4; `get_brightness` read-back
      confirmed the link both before and after a real device push;
      `disconnect` succeeded. Daemon-side detect + connect is confirmed
      working end-to-end on real hardware.
- [x] **UI — now also covered by real automated e2e, not just visual
      confirmation (follow-up session, 2026-07-13, user-directed "full e2e
      verification tests with daemon/ui/correctness when connecting
      disconnecting from devices with clear feedback").** The prior
      session's Playwright suite drove the real `web_ui` against a fully
      JS-mocked `pywebview.api` — real UI rendering logic, but no daemon
      ever touched. This session closed that gap: a mock-transport-backed
      daemon (real `divoomd`, isolated socket, PID-tracked — never
      `pkill`) driving the REAL `web_ui` through a new HTTP bridge to the
      real `DivoomGuiAPI` (`tests/e2e_gui_bridge.py`, `tests/
      test_e2e_gui_daemon_connect_disconnect.py`). Covers connect ->
      active dot, an unexpected drop (new `mock_simulate_drop` command,
      `divoomd/src/daemon_mock.rs`) -> degraded then inactive dot via both
      polling and a live `subscribe()` event relay, and a genuine
      `connect_single_device` failure (unreachable LAN, no mock transport
      involved) reaching the toast. 4/4 tests, stable across 20+ runs. This
      is real, repeatable, CI-safe daemon+UI correctness coverage — a
      durable complement to the prior session's one-time manual hardware
      pass above, not a replacement for it.
- [x] **New this follow-up session: a real (not test-only) product gap
      found and fixed.** The native menubar's icon never reflected device
      BLE/LAN connection at all — only the macOS notification-monitor's
      state. Now it does (`native-port/divoom-menubar/src/state.rs` +
      `daemon::subscribe()`), 10 new tests (6 pure unit, 3 integration
      against a fake Unix-socket daemon).
- [x] Also shipped in the prior session while the app was live: the user
      reported the device list gave no clear signal of which of 4 known
      devices were currently online (3 were, 1 wasn't) — fixed in commit
      `2d0a845` (explicit "not in range" badge + tooltip on
      known-but-undetected chips).
- [ ] **Live-hardware re-confirmation of THIS follow-up's new code is still
      open.** The daemon/menubar/GUI this session found running (`the
      menubar item is live`, per the user) had stopped running by the time
      the opt-in pass was ready to exercise it (not caused by this
      session's work — everything above used an isolated socket, never
      `/tmp/divoom.sock`). The infrastructure is ready: `tests/
      test_e2e_live_hardware_connect_disconnect.py`, gated behind
      `--run-hardware`, confirmed to skip correctly with no daemon
      present. It's deliberately READ-ONLY (verifies `device_status`/
      `connection_state` field consistency against whatever the real
      state is) — it does NOT drive a real connect/disconnect cycle
      against a live shared daemon, since there's no way to tell "idle,
      safe to disturb" from "user mid-session" from outside the process.
      Next time the daemon/menubar is running, `pytest tests/
      test_e2e_live_hardware_connect_disconnect.py --run-hardware` gives
      the read-only confirmation; the NEW menubar connection-feedback
      feature specifically hasn't been eyeballed on a real running menubar
      yet — that's the one open thread from this follow-up.
- [ ] Daemon-down banner / reconnect regression check — still not done (would
      need a live daemon to kill mid-session; deferred both sessions running).
- **Kill: MET, plus durable follow-up coverage added.** Daemon half:
  hardware-confirmed (prior session). UI half: hardware-confirmed
  (prior session, visual) AND now backed by real automated daemon+UI e2e
  tests (this session) instead of only JS-mocked logic tests. New in this
  follow-up: the menubar connection-feedback gap found and fixed, with its
  own test coverage — its real-hardware confirmation is the one item still
  open, tracked above, not faked or assumed.

## 5. Release — DONE, shipped as v0.22.9, follow-up shipped as v0.22.10

- [x] All of 0-4 committed and green (3195+ passed, 0 failed each run; `cargo check`
      clean; no-emoji + file-size gates clean throughout).
- [x] `git merge-base --is-ancestor v0.22.2 HEAD` (latest published GitHub release)
      sanity check passed before tagging, plus all local interim tags v0.22.3-8
      verified as ancestors too — no divergence (the v0.22.0 incident's standing
      rule).
- [x] Bumped `pyproject.toml` 0.22.8 -> 0.22.9; added a `## v0.22.9` CHANGELOG header
      consolidating the round for `scripts/release.sh`'s note-extraction.
- [x] Ran `scripts/release.sh`: DMG built (`dist/Divoom-v0.22.9.dmg`,
      sha256 `5fdba8e6...`), tag `v0.22.9` pushed, GitHub release created with the
      DMG asset. The Homebrew-cask-bump step hit a transient `gh api` hiccup
      (`invalid character '<'` — worked fine on manual retry seconds later, not
      reproducible); re-ran with `--skip-build` and it completed cleanly (idempotent
      by design, safe to resume).
- [x] Cask bumped to 0.22.9 in `ztomer/homebrew-tap`; `brew style --fix` caught a
      pre-existing (not new) missing-trailing-newline nit, fixed + pushed
      (`ce090c4`); `brew audit --cask ztomer/tap/divoom-control` clean.
- **Kill: MET.** Tag pushed, GitHub release published
  (https://github.com/ztomer/divoom_lib/releases/tag/v0.22.9), Homebrew cask
  updated + audited clean.
- [x] **Follow-up (2026-07-13, user-directed "full e2e verification tests...").**
      Item 4's UI half is now backed by real automated daemon+UI e2e coverage
      (not just visual confirmation), plus a real menubar connection-feedback
      gap was found and fixed (see item 4 above for detail). Synced onto
      `main` first (it had moved ahead — the `pkill` and RuntimeWarning
      follow-up tasks from item 4's earlier notes had already landed, and
      v0.22.9 was already live), resolved doc conflicts, bumped
      `pyproject.toml` 0.22.9 -> 0.22.10, ran `scripts/release.sh` again.
      DMG built (`dist/Divoom-v0.22.10.dmg`, sha256 `8c6eb4ab...`), tag
      pushed, GitHub release published
      (https://github.com/ztomer/divoom_lib/releases/tag/v0.22.10), Homebrew
      cask bumped to 0.22.10. Full suite: 3197 passed, 0 failed, 97 skipped;
      `cargo test` clean in `divoomd` and `native-port/divoom-menubar`.
- **Kill (follow-up): MET.**

---

## Loop progress log

_Each /loop iteration appends one line here: date, item worked, outcome._

- 2026-07-12: Plan written (this file), superseding the prior draft ordering to match
  the user's explicit 0→5 sequence. Found 4 uncommitted coverage-push test files on
  entry (86 tests, green) — folded into item 0.
- 2026-07-13: Item 0 (doc cleanup) done. Item 1 (95% coverage) done at 96% across
  4 agent waves (one partial — session-limit interruption, salvaged cleanly).
  Item 2 (cloud API) done — found + fixed a real Python/Rust retry-on-expiry gap.
  Items 3-4 initially blocked (no daemon/hardware reachable); user started the
  real app mid-round, unblocking both — Timoo-light-4 hardware-verified, daemon
  detect/connect confirmed end-to-end. Also shipped a user-reported UI fix
  (device-chip "not in range" clarity) while the app was live. Item 5: user said
  "ship it" — released as v0.22.9 (DMG + GitHub release + Homebrew cask, all
  verified). **R61 complete — all 6 items closed.**
- 2026-07-13 (follow-up): user asked for "full e2e verification tests with
  daemon/ui/correctness when connecting disconnecting from devices with
  clear feedback" — closed a real gap item 4 hadn't (UI e2e was JS-mocked,
  never touched a real daemon). Built a real daemon<->GUI e2e bridge, a
  mock-transport drop simulation, and (found + fixed along the way) the
  native menubar's icon never reflected device connect/disconnect at all.
  Also closed the device-loop thread-teardown audit filed as a follow-up
  during item 1. User then said "commit, tag, push, cut a release" — synced
  onto `main` (had moved ahead since item 5), resolved doc conflicts,
  shipped as **v0.22.10**. **R61 follow-up complete.** This file is now
  archived to `docs/archive/rounds/` — see `docs/ROADMAP.md` for ongoing
  open threads (the one this follow-up left open: live-hardware
  confirmation of the new menubar feedback, tracked there).

## Risks / open questions (carried from prior draft)

- **95% coverage** across a GUI + BLE + daemon tree is a large test-writing effort;
  omit list must stay defensible.
- **Timoo** may again be out of range — re-run later, don't fabricate a pass.
- Device verification (item 4) needs a free BLE adapter and devices actually in range;
  if none are reachable this iteration, state that and retry later rather than
  skipping silently.

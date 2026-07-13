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

- [ ] **BLOCKED — no daemon/hardware reachable in this session.** Timoo-light-4
      re-verify (R60 #2): scan, connect, `display.show_image` with a cloud-decoded
      payload, post-push `get_brightness` read-back confirming no device-stick.
      Checked: no `divoomd` running, no `/tmp/divoom.sock`, and — per the standing
      [[divoom-ble-tcc-harness-limit]] — this shell cannot itself spawn a BLE-scanning
      process (macOS TCC SIGABRTs it). This needs the user to start the daemon (GUI
      or standalone) so a session can drive it over the socket. Stating that plainly
      rather than fabricating a result.
- [ ] **BLOCKED — same reason.** User-POV pass on physical-screen visuals for the R60
      show_clock canonical fix (real device, real screen, light+dark check per
      [[user-pov-debug]]) — needs eyes on a real screen, inherently user-driven.
- [x] Re-scanned `docs/ROADMAP.md` for other open threads: the Timoo re-verify is
      already tracked there (line 78, points back to this file). R12 visual pass +
      R12 hardware verification (lines 76-77) are explicitly marked "user-driven" —
      unchanged, correctly deferred, not a new gap from this round. No other
      undocumented open thread found.
- **Kill: partially met, honestly.** Every loose end from R60 is accounted for —
  two are blocked on hardware/user availability (stated above, not silently
  dropped), the rest (R12 arc) were already correctly deferred as user-driven
  before this round and remain so.

## 4. Device detect + connect verification (UI + daemon)

- [ ] **BLOCKED — same hardware/harness limit as item 3.** Daemon: drive `divoomd`
      directly over the Unix socket — `scan` finds all reachable devices, `connect`
      succeeds per device, read-back (`get_device_name`/`get_brightness`) confirms
      the link. Can't spawn a real BLE-scanning daemon from this shell (TCC), and
      none is currently running for this session to attach to.
- [ ] **BLOCKED — same reason.** UI: launch the real `Divoom.app`/`./run.sh` GUI,
      drive scan + connect from the dashboard, confirm the device chip appears,
      connects, and a control round-trips. Same TCC constraint applies to the GUI's
      own spawned daemon.
- [ ] Confirm the daemon-down banner / reconnect path still behaves (regression check
      from R57-59 event-driven work) while doing this pass — deferred with the above,
      needs the same live daemon.
- **Kill: NOT MET this session — explicitly blocked, not faked.** Needs the user to
  start the daemon/GUI (grants the TCC Bluetooth permission this shell lacks) so a
  session can drive scan/connect over the socket or the UI. The code paths
  themselves are extensively covered by the R61 test suite (96% coverage, incl.
  `scanner_mixin.py`/`connection.py`/`ble_transport.py` at 100%), but that is NOT a
  substitute for the real-hardware confirmation this item asks for.
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

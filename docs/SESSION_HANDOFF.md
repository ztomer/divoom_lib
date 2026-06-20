# Session Handoff — read this first

**Consolidated roadmap**: `docs/ROADMAP.md` — shipped rounds, open workstreams,
and deferred items in one view. This file tracks the per-round state.

This is the **cross-agent session state**. opencode and Claude Code keep their
own conversation stores (they can't share a live session), so THIS FILE + the
git history + CHANGELOG + ROADMAP are the shared memory. Any agent (opencode or
Claude) should read this on entry and **update it at the end of every round**
(see the core rule in `AGENTS.md`).

## How to resume

- **opencode**: `opencode -s ses_184471307ffeCUHgzv9w51O0oA` (or
  `opencode export <id>` to read it as JSON).
- **Claude Code**: reads `CLAUDE.md` → `AGENTS.md` → this file, plus `git log`.
- Both: `git log --oneline`, `CHANGELOG.md`, `docs/PLANNING_ROUND*.md`.

## Current state — _update this section each round_

- **R53 round 18 — BASIC-PROTOCOL RX PARSER BOUNDS THE LENGTH FIELD SHIPPED (2026-06-20).**
  Second fresh-re-read find. `parse_basic_protocol_frames` (shared by BLE notify RX +
  SPP `_on_data`) trusted the 2-byte length unboundedly → a corrupt length stalled all
  RX waiting for ~64KB that never arrives. Bounded by `MAX_BASIC_FRAME=8192`: over-long
  decoded length → resync (drop start byte). Mirrors the SPP iOS-LE bound (R53.13). Test
  with teeth. Full suite green (1555 passed). 18 rounds total today; both fresh-re-read
  rounds (R53.17, R53.18) found REAL bugs the original review missed. The two fresh
  findings are recorded under a new "FRESH RE-READ FINDINGS" section in the review doc.

- **R53 round 17 — RECONNECT CLEARS STALE OS-DROP FLAG SHIPPED (2026-06-20).** Fresh
  adversarial re-read found a bug the original review missed: after an OS drop,
  `_on_os_disconnect` sets `_connection_likely_broken=True`, but `connect()` never
  cleared it on reconnect — and autoprobe is a no-op on reconnect (framing already
  known → sends nothing), so `is_alive` lied `False` from reconnect until the next
  successful send (false DEGRADED dot; live-jobs/wall treat the live link as dead →
  rebuild churn). Fix: `connect()` clears the flag on a successful (re)connect. Test
  with teeth (`test_reconnect_clears_stale_os_drop_flag`). Full suite green (1554);
  HW-checked. This was a genuine NEW find — the BLE subsystem is now hardened beyond
  the original review's scope. Only documented item left: SPP connect preflight (niche,
  untestable with the all-BLE fleet).

- **R53 round 16 — discover_device EARLY-EXIT SHIPPED (2026-06-20).** `discover_device`
  (live via `monthly_best_daemon` reconnect) waited the full 10s/3s `BleakScanner.discover`
  window even after the target appeared; rewrote it on the detection-callback + early-exit
  + guaranteed-stop pattern (same as `discover_all_divoom_devices` R53.6). Returns on first
  name/address match. Scan windows are now module constants (`NAME_SCAN_TIMEOUT`/`ADDR_SCAN_TIMEOUT`).
  Empties the "discovery scans unbounded" review finding. Full suite green (1553 passed).
  **BLE review High+Medium fully done; Low down to ONE niche item:** SPP connect
  preflight/FailureReason (untestable with the all-BLE fleet). The deferred list is
  effectively exhausted — the BLE subsystem is as hardened as this review identified.

- **R53 round 15 — EXCLUSIVE DEADLINE RE-ARMS ON COMPLETION SHIPPED (2026-06-20).**
  The command-queue exclusive auto-release re-armed its deadline only on dequeue; a
  long-running exclusive item (animation/custom-art push) or a gap before the next
  owner item could let the deadline lapse mid-session → next `_dequeue` force-releases
  an actively-working session. Worker now re-arms on item COMPLETION too. Test verified
  to fail without the fix. LAN per-request aiohttp session reviewed → **WONTFIX** (async
  with-scoped, no leak; reuse would couple session to loop lifecycle for marginal gain).
  Full suite green (1553 passed). **BLE review deferred list is now down to 2 low/niche
  items:** discovery `discover_device(address=...)` stop-on-first-match (legacy/maybe-unused
  path), and SPP connect preflight/FailureReason (untestable with the all-BLE fleet). The
  High+Medium tiers and nearly all Low are DONE across R53.1–15.

- **R53 round 14 — REGISTRY EVICTION HONESTY + LOOP-TEARDOWN RESET SHIPPED (2026-06-20).**
  `ble_registry.evict` now WARNs on a failed disconnect (was silent debug → a failed
  eviction looked successful while the OS link survived → next-connect stall). And
  `device_owner.stop()` resets per-loop BLE state: `ble_connection.forget_loop(loop)`
  (pops the `id(loop)`-keyed connect lock — id reuse hazard) + `ble_registry.reset()`,
  then nulls `_loop`/`_cmd_queue`/`_loop_thread` so `_device_loop()` rebuilds cleanly.
  Tests: `test_ble_registry.py` (+3). Full suite green (1552 passed). Remaining deferred
  (all Low): discovery scan stop-on-first-match, exclusive-deadline re-arm-on-completion,
  LAN per-request session reuse, SPP connect preflight/FailureReason.

- **R53 round 13 — SPP SEND RETRIES + CORRUPT-LENGTH PARSER RESYNC SHIPPED (2026-06-20).**
  `send_payload` now honours `max_retries` (bounded backoff, bails on a dead link) — was
  accepted-but-ignored. `_on_data` bounds the iOS-LE frame length (`_MAX_IOS_LE_FRAME=8192`)
  so a corrupt length RESYNCS (drop a byte) instead of stalling RX forever. Tests:
  `test_spp_robustness.py`. Full suite green (1549 passed). SPP Medium tier essentially
  done; only low-value SPP item left = no preflight/FailureReason for SPP connect. Next:
  the remaining Low deferred items (discovery scan stop-on-first-match, registry-evict
  swallow, `_connect_locks` reset on loop teardown, exclusive deadline re-arm-on-completion,
  LAN per-request session reuse).

- **R53 round 12 — SPP DEATH-AWARE LIVENESS + DEAD-CODE PURGE + SPLIT SHIPPED (2026-06-20).**
  Medium-tier SPP hardening. `_serial_read_loop` could die silently leaving
  `is_connected==True` forever; added an honest `is_alive` (parity with BLE, requires
  the reader thread live on the serial path) + logs the previously-swallowed read error.
  Deleted dead `spp_connection.read_spp_notifications_loop`/`disconnect_spp`. Split the
  macOS IOBluetooth RFCOMM backend + `BtSppNotification` into `bt_spp_rfcomm.py`
  (`_SppRfcommMixin`); `bt_spp_transport.py` 500→363 LOC. SPP is unhittable with the
  all-BLE fleet → unit-tested (`test_spp_liveness.py`). Full suite green (1544 passed).
  Remaining SPP Medium items: `max_retries` ignored, no preflight/FailureReason, corrupt
  iOS-LE length stalls the parser. Other remaining deferred: discovery scan
  stop-on-first-match, registry-evict swallow, `_connect_locks` reset, exclusive deadline
  re-arm-on-completion, LAN session reuse (all Low).

- **R53 round 11 — BLE RESPONSE-PATH LOCK + ble_notify SPLIT SHIPPED (2026-06-20).**
  Closes the LAST High deferred BLE finding (shared-response cross-talk).
  `send_command_and_wait_for_response` now holds `_response_lock` across
  drain→set-scalar→send→wait so two callers can't drain each other's frames / clobber
  `_expected_response_command`; contended entry logs a warning (future off-queue
  regression visible, not silent). Chose the lock over a per-command-id Future refactor
  to protect the working 0x8B path. Also split the notification/response methods into
  `ble_notify.py` (`BleNotifyMixin`); `ble_transport.py` 516→384 LOC. HW-verified the
  0x8E response path + a normal device call post-split. Test: `test_ble_response_lock.py`.
  **The BLE review's entire High deferred list is now empty** — remaining deferred items
  are Medium/Low (SPP weaknesses, discovery scan early-exit-on-match, registry evict
  swallow, _connect_locks reset, exclusive deadline re-arm-on-completion, LAN session reuse).

- **R53 round 10 — LIVE-JOB vs EXCLUSIVE-PUSH ANTI-CLOBBER SHIPPED (2026-06-20).**
  Closed a High deferred BLE finding. During an exclusive push (animation/custom-art,
  `proxy.exclusive(token)`) a live job's TOKENLESS frames queued (exclusive mode only
  dispatches matching-token items) and burst out on release, clobbering the push.
  `exclusive_start` now stops the active device's live jobs first (`live_jobs_stop_for({})`,
  stop-before-acquire); background-device jobs survive. HW-verified both. Test:
  `test_exclusive_stops_jobs.py`. Review doc item struck. Remaining High deferred BLE
  item: shared notification_queue + scalar `_expected_response_command` cross-talk (only
  safe today because nothing else runs via `_run_on_loop`). CI is green again after the
  R53.9-era flaky-fixture fix (6a8512f).

- **R53 round 9 — DISCONNECT STOPS ACTIVE LIVE JOBS SHIPPED (2026-06-20).** HW
  edge-probe: a sysmon job on the active device survived `disconnect()` as a live
  task (`done:false`), spinning on the released link (could resurrect it). `disconnect()`
  now stops the active device's live jobs first (`live_jobs_stop_for({})`, like the
  channel-switch path); background jobs on OTHER devices untouched — both HW-verified.
  Test: `test_disconnect_stops_jobs.py`. ALSO **R53.8: split `device_owner.py`** (was
  pinned at 500 LOC) → new `owner_connect.py` (OwnerConnectMixin: acquisition/discovery)
  + `owner_util.py` (`_json_safe`); device_owner.py 500→239, no behavior change. Both
  on main (latest c38455e + this round). OPEN: the deferred live-job↔exclusive 0x8B
  interleave is still next on the BLE review list.

- **R53 round 7 — EMPTY-TARGET CONNECT REJECT SHIPPED (2026-06-20).** Edge-probe
  sweep over the daemon socket. Bug: `connect(mac="")` returned success and grabbed
  an arbitrary/last device (`""` falsy → scan-first `devs[0]` fallback). `connect()`
  now rejects an explicitly-empty `mac`/`lan_ip` (`reason=invalid_target`); `mac=None`
  (absent) still = "use active". HW-verified clean in the same sweep: bogus MAC fails
  bounded (16.4s, no hang) and doesn't poison the next connect; rapid re-grab ×5 on
  the 0.0s fast-path; scan `limit=-1/999` degrade to no-cap. Test:
  `test_daemon_connect_identity`. Pushed to main (3b61d86). Both R53.6+R53.7 on main.

- **R53 round 6 — SCAN SPEED + CONNECTED-DEVICE VISIBILITY SHIPPED (2026-06-20).**
  HW-driven via the dev-daemon socket + a new stress loop
  (`scripts/hw_smoke.py --phase stress [--churn]`) that hammers connect/disconnect/
  evict and flags anomalies (identity mismatch, degraded-but-connected, duration
  spikes, fleet-count drops, stale-after-disconnect). **(1)** Scan is now
  early-exit: `discover_all_divoom_devices` uses a detection callback + returns the
  instant `expected` devices are seen (guaranteed `scanner.stop()` in `finally`) —
  HW **15.0s → ~2s** for a 4-device scan. **(2)** A connected peripheral stops
  advertising and was being dropped from the selector ("should be 4, found 3");
  `device_owner.scan` now **unions owned devices** (active + live jobs) back in,
  with names from a `mac->name` scan cache. Churn stress now 40/40 connects clean,
  scans 4/4, zero anomalies. **(3)** `query_page` (0x8E) bounded 10s→4s (Pixoo
  never answers it). Tests: `test_scan_owned_union.py`, `test_discovery.py` (now
  callback-based), `test_custom_art_push.TestQueryPage`. Full suite green; files
  ≤500 LOC (`device_owner.py` trimmed to exactly 500). **OPEN follow-ups:** when a
  device is held, the scan can't early-exit (only N-1 advertise) so it waits the
  full window (~8s) before unioning — could subtract owned-count from `expected`;
  and the deferred ACK≠success fix must downgrade `success` honesty (NOT verify via
  0x8E, which is unreliable on HW) — see `docs/BLE_HARDENING_REVIEW_2026-06.md`.

- **R50 SPECIFIC PREVIEWS SHIPPED (2026-06-14).** Three preview-fidelity fixes
  on top of R49. **(1)** Device preview now renders the SPECIFIC channel face
  (6 clock styles, in the chosen color) instead of a generic glyph —
  `_channelPreviewSVG`/`_clockFaceSVG` + `applyClockStyle` refreshes on apply;
  selected style tracked on `DivoomState.selectedClockStyle`. **(2)** Removed the
  redundant device-name label under the preview (active chip carries it; label is
  now empty-state-only). **(3)** Menubar tiles show the real device face: GUI
  rasterizes the preview SVG→PNG (`_rasterizeToPng`), pushes it via
  `set_device_activity(..., preview)`; daemon stores it; menubar `_menu_thumbnail`
  decodes PNG→NSImage with SF-Symbol fallback (can't regress). Empty `kind` =
  thumbnail-only update (don't clobber live-job kind). Tests added (daemon
  storage + menubar decode). **OPEN: native NSMenu tile render needs a real
  menubar smoke test** — verified the decode + rasterize + storage chain headless,
  but not the on-screen `setImage_` result. NOTE: `app_globals.js` now 490 LOC
  (cap 500) — next addition there needs an extraction.

- **R49 SIDEBAR DEVICE CLUSTER REDESIGN SHIPPED (2026-06-14).** Rams/Kare pass
  over the device selector, Virtual Wall button, and preview (four-lens review →
  `docs/REVIEW_2026-06.md` not regenerated; design captured in CHANGELOG R49).
  **(1)** Device dots → **named chips** (color dot + name + state text); active =
  green border, connecting = amber pulse, streaming = breathing dot, degraded =
  amber + "reconnecting". `device_selector.js` + `sidebar.css`. **(2)** Wall glyph
  was identical to the Pixel Art tab — now a distinct "joined panels" glyph, dashed
  border, count in label ("Wall (3)"). **(3)** Device PNGs had the transparency
  **checkerboard baked into RGB pixels** (asset-gen artifact) — re-keyed to real
  RGBA transparency via border flood-fill (preserves interior detail). **(4)**
  Device preview → **flat face-on screen panel**: the 3/4 product photos made
  composited live frames land crooked; dropped the photo, the frame renders
  straight in a neutral bezel (any model, no per-model rect — removed
  `_DEVICE_SCREEN_RECTS`/`_applyDeviceScreenRect`), device name shown below.
  Suite green (see CHANGELOG). Also: homebrew-tap README updated (divoom-control
  added to the cask table + per-cask detail sections).

- **ARCH GAP SCAN #2 SHIPPED (2026-06-13)** — `docs/ARCH_GAP_SCAN_2_2026-06.md`,
  A1–A4. **A1**: shared `divoom_lib/utils/atomic_io.py` (atomic_write_text /
  atomic_write_config) applied across ALL config writers — only `save_preset` was
  crash-safe before. **A4**: `config.ini` + `auth_token.json` now `0o600`.
  **A3**: `gui_api._run_async` bounded at 120 s (was unbounded → frozen GUI on a
  wedged op). **A2 (HW-verified)**: live jobs persist to `live_jobs.json` and the
  daemon `rehydrate_live_jobs()` on boot — a killed daemon's streaming widgets
  resume (HW: sysmon on Ditoo survived a daemon kill+respawn). Teardown keeps the
  file (clean restart resumes); user-stop removes a job.

- **ARCH GAP SCAN COMPLETE (2026-06-13).** All of `docs/ARCH_GAP_SCAN_2026-06.md`
  resolved: G1–G5 + G7 shipped, G6 closed won't-fix. **G7 (HW-verified)**:
  `wall_configure` now reconfigures by delta — transplant the connected screens
  shared with the old layout (fast-verify), only (dis)connect the delta; disjoint
  layouts still full-rebuild. HW (Ditoo/Pixoo/Timoo): ADD a 3rd screen **3.9 s
  (was ~14 s)**, REMOVE **0.0 s**, wall lit throughout, removed screen freed.
  Wall ownership extracted to `divoom_daemon/owner_wall.py` (device_owner.py now
  430 LOC). G6 = won't-fix (the no-mac auto-discovery scan path the indicator
  would cover is never triggered by the GUI). Still want a real HW pass for G2
  (scan during streaming) + the G3 exclusive force-release path.

- **ARCH GAP FIXES G4–G5 SHIPPED + HW-VERIFIED (2026-06-13).** **G4**: active
  device + wall could double-own one MAC → daemon kept a dead `_device` handle
  that timed out ~5s and FAILED on every active call. Fixed —
  `wall_configure` relinquishes the active device when its mac is a wall slot;
  `connect()` drops the wall when the target is a current slot. HW: clean
  ownership transfer both ways, all calls fast (vs old 5s-fail). **G5**: background
  live-device health now stamped onto the activity entry
  (`owner_live._stamp_live_health`); selector dot shows an amber "reconnecting"
  ring when a streaming device is degraded. HW: background sysmon on Ditoo reports
  `state: connected`. Only **G6** (scan indicator on reconnect/auto-discovery
  scans) remains open from the arch scan. G2 + G3 still want their HW pass.

- **ARCH GAP FIXES G1–G3 SHIPPED (2026-06-13).** From the architecture scan
  `docs/ARCH_GAP_SCAN_2026-06.md`. **G1**: prune `_device_activity` (forget on
  disconnect/wall-teardown, idle on stop-all, 10-min TTL skipping active +
  live-job macs) — kills R47 ghost devices. **G3**: command-queue
  `exclusive_timeout` (30 s on the device queue) auto-releases a dead client's
  exclusive session so one crashed push can't wedge the device forever; deadline
  re-arms on owner progress. **G2**: BLE scan runs on the device loop
  (`_run_on_loop`) instead of the serialized command queue, so a 60 s scan no
  longer freezes live widgets / hangs user actions. Extracted device-loop
  plumbing → `divoom_daemon/owner_loop.py` (OwnerLoopMixin) to keep
  `device_owner.py` < 500 LOC. **Open:** G4 (registry eviction vs wall same-MAC),
  G5 (background live-device health), G6 (scan indicator on reconnect scans) —
  still `OPEN` in BACKLOG. HW pass pending for G2 + the G3 force-release.

- **R47 SHIPPED (2026-06-13): daemon-owned devices stay selectable + scan
  indication.** Fixes "device shows connected but I can't do anything with it":
  a daemon-owned/streaming device doesn't advertise, so a scan missed it and it
  had no selector dot. Now the daemon resolves a friendly `name` for activity
  (`owner_live._resolve_device_name`), the GUI pulls `get_device_activity` on a
  4 s heartbeat (`device_selector.refreshOwnedDevices`) and unions owned macs
  into the selector with a breathing "streaming" ring, and a `#scan-indicator`
  shows scans in the main UI. Selector logic split into `device_selector.js`
  (500-LOC cap). Suite 1461 passed / 75 skipped. **Open:** live GUI + menubar
  visual pass (names resolve only while the daemon owns the device; SF Symbols
  need macOS 11+).

- **SOCKET INTERFACE HARDENING SHIPPED (2026-06-11).** Plan
  `docs/PLANNING_SOCKET_HARDENING.md`. The daemon socket is a privilege boundary
  (owns BLE + reads notifications). Landed: Unix socket `chmod 0600`; max
  message-size cap (server read + client reply, 16 MiB); total read deadline
  (30 s, kills slow-loris); handler exception safety (generic "internal error",
  detail logged not leaked, thread survives); bounded concurrent connections
  (32, "server busy") + subscriber cap (16); request validation (command str /
  args dict). Limits are `SocketServer` params w/ safe defaults; TCP token auth
  unchanged. +11 real-socket tests (`tests/test_socket_hardening.py`).

- **BLE HARDENING P1–P6 + daemon-socket SHIPPED (2026-06-11).** Plan
  `docs/PLANNING_BLE_HARDENING.md` (all phases marked SHIPPED inline). Commits
  156857bd (P1), be12e0dc (P2), d7036cf1 (P3), 516995fb (daemon-socket),
  a815eed9 (P4), 4ff73ec9 (P5), +P6. New modules: `ble_connection.py`
  (honest typed connect, never a dead handle; per-loop connect lock;
  `derive_connection_state`), `ble_preflight.py` (P4 permission preflight →
  typed cause for empty scan), `ble_reads.py` (P5 `read_with_retry` + last-good
  cache + typed unknown). P2 OS `disconnected_callback` + `is_alive`; P3 wall
  per-slot typed results + self-heal; P6 `device_status.connection_state`
  (DISCONNECTED/CONNECTED/DEGRADED) + transition logging; extracted
  `OwnerNotifyMixin`. Daemon socket: bind+listen-before-publish race fix +
  client connect-retry. Full suite **1398 passed / 75 skipped**. HW-verified on
  Ditoo (connect 2.4s + push).
  GUI DEGRADED dot SHIPPED: appbar 4s heartbeat polls `connection_state`
  (`get_connection_state` → `refreshConnectionState`) → amber dot / drop
  (`#global-status-dot.degraded`).
  task #20 (get_* reads) ROOT-CAUSED + FIXED on HW (4 models): not a timeout —
  a STALE read. Device emits an unsolicited 0x46 on state change; manual readers
  skipped the queue drain → lagged one behind (set 60 → read 25). Added
  `Divoom.drain_notifications()`, called by get_brightness/get_light_mode;
  round-trip now exact. 0x76 get-name returns a 2-char suffix on every model →
  `get_device_name` prefers the advertised name. +9 tests.
  Wall HW-VERIFIED (4 screens): all-real wall 4/4 connect+push; partial wall
  (3 real + 1 bogus) 3/4 + pushes to the 3, dead slot captured per-slot. Fixed a
  wall lifecycle leak HW surfaced (`wall_configure` dropped `_wall` without
  disconnecting → reconfigure timed out; now `_drop_current_wall` disconnects).
  **Open follow-ups (deferred, not blocking):** mid-session per-slot wall
  reconnect stays unit-tested (can't force a real drop without power-cycling);
  P6 physical flag-consolidation is cleanup, not correctness (flags already
  honest). Remaining `get_*` reads can adopt the drain / `read_with_retry`.

- **R43 SHIPPED (2026-06-10) — Permissions Dialog, Settings Backup/Restore, Preset Files, and Wall Split Cache.** Plan+outcome
  `docs/PLANNING_ROUND43.md`. Highlights: macOS Notification Permissions step-by-step instructions popup and red status indicator; unified settings Backup & Restore (export/import entire configurations, presets, alarms to/from JSON files); Virtual Wall presets save/load file buttons and immediate sync dropdown behavior; downscale, crop, split, and cache quadrants under `~/.config/divoom-control/cache_wall/` to prevent redundant resizing and fix routing target crash; Custom Art empty screen race condition fix in `custom_art.js` (element check bootstrap); custom art push/query unawaited coroutine warning fixes.
  Suite passed cleanly locally and on GitHub CI (1331 passed, 75 skipped, 0 warnings).

- **R42 SHIPPED (2026-06-10) — 9-item bug batch.** Plan+outcome
  `docs/PLANNING_ROUND42.md`; commits e2029fd7..33dba70f. Highlights: scan
  settings persist; macOS 26 NC db found in `group.com.apple.usernoted` (+
  actionable Full Disk Access error — USER ACTION: grant FDA to python3 for
  notification mirroring); Pixel Art custom-art/hot loaders fixed (dead
  function name + missing window exposure); preset wipe-hazard + silent-save
  fixed (cocoa pywebview has no window.prompt; atomic writes); **virtual wall
  pushes HW-verified on Ditoo+Pixoo** (client read-timeouts on
  wall_configure/device_call + un-awaited proxy coroutine in previews).
  Suite 1327/75 (+7 tests; 1 pre-existing local-only playwright fail).

- **R41 SHIPPED (2026-06-10) — UI, Startup, Reconnect, Virtual Wall & CI Fixes.** Plan+outcome `docs/PLANNING_ROUND41.md`. Local suite **1321/75** passed cleanly. Key changes:
  - Fixed duplicate `#panel-design` and custom art layout height constraints.
  - Constrained `.gallery-split-card` and `.gallery-split-layout` to support internal grid scrolling.
  - Spaced and aligned targets list, Routines schedule layout, and Anniversary/Alarms order.
  - Shrunk Device Settings card and removed card-header.
  - Configured startup auto-scan and auto-connect with 60s BLE scan timeout fallback.
  - Handled cloud credentials expiry automatically (re-login + retry once) and fixed gallery.js syntax error.
  - Recognized Tivoo Max speaker capability in regex checks.
  - Propagated listener errors to menu bar disabled item and tooltips.
  - Adjusted `is_free_form` calculation on Virtual Wall, captured crops, and rendered previews on Arranger Canvas.
  - Respects custom `DIVOOM_TEST_SEED` env var for downscaler stress test replication.

- **R40 SHIPPED (2026-06-10) — UI batch items 2-9.** Plan+outcome
  `docs/PLANNING_ROUND40.md`. Local suite **1319/75** (2 playwright tests need a
  viewport-height chain → skip in CI). Custom-art 0xAA push crash fixed
  (`resolve_to_gif`), header toggles for sysmon/weather/macnotif/anniversary,
  gallery 128px cap + scroll fix, sticky settings tabs, schedule spacing, new
  **Device Settings** sidebar section (segmented pills, danger at bottom),
  **keep-daemon-alive** lifecycle (event-driven shutdown broadcast). Item 7
  (Pixel Art sidebar) was already shipped by the user's R37-R39 work.
  **CI: R40 fixed 4/5 pre-existing failures + the daemon-socket flakiness. ONE
  pre-existing CI failure remains, OUT OF SCOPE:**
  `test_native_downscaler::test_stress_random` (LANCZOS 1-LSB C-vs-PIL diff on
  `300x2->7x1`) — byte-exact 60/60 LOCALLY, fails only on the CI runner's
  clang/libm, was failing in CI before R40. `-ffp-contract=off` didn't resolve
  it. Needs a focused native-parity round (reproduce on CI arch, or a ≤1 LSB
  tolerance for the random stress shapes) — do NOT blind-edit the C kernel.

- **R39b SHIPPED (2026-06-10) — UI polish part 2, browser-preview verified (1307/75/0).**
  1. Custom art: tabs + slot strip + Push button now ALWAYS visible — root
     cause was `.channel-panels` breaking the flex height chain under
     `#control-panel .card-body { overflow-y:auto }`; fixed in
     style_extra.css. Slots are one row of 12 (6×2 <900px). Drag & drop:
     slot↔slot swap + library→slot placement (verified with synthetic
     DataTransfer events in the preview).
  2. Hot channel: tiles image-only (tooltip holds name/version), empty
     card-header removed.
  3. Gallery: sort + size controls right-aligned on the controls row.
  4. channels.css split → custom_art.css (@import in style.css);
     `_channels_css()` in test_round6 reads both. `.claude/launch.json`
     serves web_ui statically for preview verification.
  Open: same HW verifies as R39 (custom art full-page push, alarm read-back).

- **R39 SHIPPED (2026-06-10) — UI polish round, suite fully green (1306/75/0).**
  Five user-reported items fixed in one pass (see CHANGELOG R39 for detail):
  1. Hot channel: thumbnails 2× (112px, `image-rendering: pixelated`), file
     counter removed, preview grid fills the card (dead space above the
     Update button gone). Washed-out colors were `.hot-preview-item-uncached
     { opacity: 0.55 }` — removed.
  2. Custom art overhaul: fixed header (page tabs + 12 slots, same tile size
     as library), scrolling library, click-to-assign with auto-advance, ×
     to clear, assigned tiles dimmed. Backend now takes a `{slot: file_id}`
     page mapping and pushes the page ONCE (old per-file `push_slot` wiped
     the other 11 slots each call). Also fixed a `renderCustomArtHistory`
     ReferenceError left from R37 that broke channels_grids wiring.
  3. Alarms: phantom rows root-caused — 0x42 response records are 10 bytes
     INCLUDING a leading alarm-index byte (APK `u1/b.a()`); our 9-byte-stride
     parser misaligned everything after record 0. Fixed in
     `divoom_lib/scheduling/alarm.py` + constants. "On" column is now a
     toggle switch. NEEDS HW VERIFY: clear alarms, re-open tab, list should
     be empty.
  4. Routines→Schedule narrowed 760 → 560px.
  5. 500-LOC splits: `divoom_daemon/owner_art.py` (from device_owner),
     `divoom_gui/gallery_hot_api.py` (from gallery_sync). Emoji cleanup in
     docs/CUSTOM_CHANNEL_VS_APK.md. Both prior failures green.
  Open: hardware verify custom-art slot push (full-page mapping) and alarm
  read-back on the Ditoo.

- **0xAA hot-file decoder FIXED — garbage frames resolved (2026-06-09, late).**
  The first 0xAA reverse-engineering ("10-byte header, byte 6 = frame count, raw
  768-byte RGB frames") was WRONG → previews decoded to noise. Correct format
  (validated frame-exact on 6 live CDN files, 186–463 frames each, 0 errors):
  concatenated palette-indexed frames `0xAA len(u16 LE) time_ms(u16 LE) flag
  n_colors [palette] [pixels]`. `flag` 0 = keyframe (palette reset, n_colors RGB
  entries, 0 → 256); `flag` 1 = delta frame (APPENDS n_colors to the running
  palette). Pixels = full 256 indices into the cumulative palette, LSB-first at
  `ceil(log2(palette_size))` bpp, omitted while palette size is 1 (solid frame).
  New `tests/test_hot_file_decoder.py` (11 tests). Stale garbage preview GIFs
  purged from `~/.config/divoom-control/cache_gallery/` (27 files) so the UI
  re-decodes. NOTE: this decoder is preview-only — `hot_update.py` still sends
  containers AS-IS (firmware decodes them itself). Suite 1304/75/2-failed (the
  2 failures are emoji/file-size violations in the uncommitted R37 docs).

- **Hot channel animated previews SHIPPED + 0xAA decoder in library (2026-06-09).**
  Fixed hot channel showing only placeholders: hot CDN files use format **0xAA** (magic
  byte 170) — completely different from gallery's magic-43/9/18/26. (Format details
  corrected later the same day — see the entry above.)
  - `divoom_lib/media_decoder.py`: new `decode_hot_file_format()` (returns 768B RGB
    frames + per-frame durations) and `decode_hot_file_to_gif()` (saves upscaled
    128×128 animated GIF).
  - `gallery_sync.py` `get_animated_preview()`: uses library decoder instead of inline
    code. Hot channel JS `renderHotPreview` now calls `get_animated_preview` for ALL
    items (was gated on `has_cache`). Added PIL `Image.open()` as ultimate catch-all.
  - Removed header text "Divoom's Curated Hot Set" and "Hot Channel Preview" from
    template. Gallery sidebar width reduced 160px → 112px.
  - Tests: 1291 passed, 75 skipped (pre-existing `test_file_size.py` + `test_no_emojis.py`).

- **Custom Art Push (Phase 3 Web UI) SHIPPED (2026-06-09) — page tabs + slot grid + gallery cache multi-select.**
  Phase 3 of the custom art slot-based push implementation: replaced the old file-browser
  (browse + preview + history filmstrip) with APK-matching UI — 3 page pill tabs, 12-slot
  grid, gallery cache checkbox multi-select, and a single "Push Selected to Page" button.
  - New `divoom_gui/web_ui/custom_art.js`: page tab switching via `device_call`, slot
    grid with click-to-select, push button wiring to daemon RPC.
  - `channels_grids.js`: `renderCustomArtCacheGrid` now renders each cache item with a
    checkbox + `data-file-id` for multi-select.
  - `gui_api.py`: added `device_call(method, args, ...)` thin wrapper (exposed to JS).
  - Removed dead code: old custom-art file browser (`#browse-custom-art-btn`,
    `#custom-art-path-input`, `#custom-art-preview-container`, `#apply-custom-art-btn`,
    `#custom-art-history-container/filmstrip`, `renderCustomArtHistory`,
    `addCustomArtToHistory`).
  - Remaining: test on real hardware; Phase 4 (monthly best → hot channel push).

- **R36b SHIPPED (2026-06-09) — the REAL hot-channel update.** (`b85004b5`)
  User feedback after R36: images displayed on the CUSTOM channel, not the hot
  channel. Correct — `show_image` is drawing-send. Reverse-engineered the APK's
  `HotUpdateHandle` and implemented the device-driven hot file STORE:
  HTTP `Hot/GetHotFiles32` → 0x9B manifest → device 0xF7 file requests → 0x9D
  info (byte-sum checksum) → 0x9E 256B packets + resends → done acks → HOT mode
  switch. Raw cloud containers sent AS-IS (<128px firmware decodes hot files).
  New `divoom_lib/tools/hot_update.py`, transport `wait_for_any_response` +
  `_listen_commands`, daemon `hot_update` RPC, GUI "Update Hot Channel" button
  (`gallery_hot.js`). **HW-verified on Ditoo with real device acks** (v1099
  served + confirmed, idempotent re-run). Suite **1223/75/0**. Protocol details
  in `docs/PLANNING_ROUND36.md` R36b section.

- **R36 SHIPPED (2026-06-09) — hot-channel now renders on the Ditoo.**
  (`4d7aae3d` fix, `6937a468` suite green; plan+runlog
  `docs/PLANNING_ROUND36.md`.) Root cause: magic 9/18/26 cloud files are
  AES-CBC ciphertext; we raw-streamed them over 0x8B — device ACKs everything
  (false-positive "success") but can't decode. Now: decode
  (`media_decoder.decode_cloud_frames`) → GIF → `show_image`. HW-verified on
  Ditoo via daemon RPCs (24-frame GIF, start-ACK, 3/3 batch). Suite
  **1216/75/0**. KEY LESSON: transfer-level PASS (incl. `test_hardware_smoke`)
  is NOT render-level proof — only eyes on the device confirm pixels.
  AWAITING: user glance at the Ditoo after an "Update Device" run.

- **R35 SHIPPED (2026-06-09) — APK encoding parity + terminate removal + UI polish.**
  Plan + outcomes: `docs/PLANNING_ROUND35.md`.
  - **R35a — CRITICAL FIX**: `_handle_ios_le_notification` dropped the device's
    `[0]→ready` ACK because `_expected_response_command` was `None` (sent via
    `send_command` which doesn't set it). Fix: set before START. Previously the
    ACK was silently lost → `_await_8b_device_ready` blocked 3s → 0.5s sleep →
    3.5s dead air → device internal timeout (~1-2s) → permanent spinner.
  - **R35b — Upload progress**: `sync_hot_channel` fires
    `window.onGallerySyncProgress` after each file. JS handler shows three
    states (updating, synced, error). Double-press guarded.
  - **R35c — APK comparison doc + parity tests**: 815-line `docs/APK_COMPARISON.md`
    with byte-level comparison of 0x8B, 0x49, 0x44, frame body, BLE framing,
    color palette, pixel packing. 25 parity tests. Verified two UNVERIFIED items:
    (1) 32×32 pre-frames NOT IN APK, (2) 32×32 RR=0x03 NOT IN APK (uses same
    AA format as 16×16). 0x49 counter CONFIRMED 0-based in APK. APK has separate
    BlueHigh encoding path.
  - **R35d — TERMINATE removal (key finding)**: APK `CmdManager.n()` does NOT
    send CW=2. Hardware-verified on 4 devices (Timoo SPP, Ditoo BLE, Tivoo Max
    BLE, Pixoo BLE) — **all PASS both with and without TERMINATE**. Permanently
    removed, saving ~0.5s per upload.
  - **UI polish**: device dot pulse uses CSS var `--dot-pulse-color` set per
    device accent color. Gallery Select All/Clear buttons use `.gallery-select-btn`
    (solid background). `test_hardware_smoke.py` for quick HW verification.
  - Tests: **210 pass** (31 parity + 8b stream + e2e mock + monthly best daemon + HW smoke).

- **R34 §1b SHIPPED (2026-06-09) — APK-aligned 0x8b upload flow.** (`5f419002`)
  Compared our chunked upload against the decompiled APK: wire format identical;
  flow diverged (APK is device-driven). `stream_animation_8b` now waits for the
  device's "send it" ACK after START (3s, falls back to legacy 0.5s sleep) and
  serves `[1][idx]` retransmit requests until quiet; `stream_raw_bin_payload`
  deduplicated into it. Comparison documented in `docs/CHANNEL_ARCHITECTURE.md`
  (new 0x8b section). Suite **1185/75/0**. Hardware re-test of hot-channel sync
  still pending (now carries §1 timeout fix + §1b together).

- **R34 SHIPPED (2026-06-09) — hot-channel sync fix + Routines polish.**
  Plan + outcomes: `docs/PLANNING_ROUND34.md`. Suite **1182/75/0**.
  - §1 (`ade3c0cc`): hot-channel "failed to upload" was the client read timeout
    (2s) vs. the daemon's download+BLE-stream; new `sync_read_timeout` (120s) in
    daemon.ini; `sync_hot_channel` returns per-file `errors`. **User should
    re-run a hot-channel sync** — if anything still fails, `/tmp/divoom_daemon.log`
    now shows the real reason; only then is the APK protocol diff warranted.
  - §2 (`a3865133`): sidebar device dot pulses amber (existing dot-pulse) while
    connecting; clears on success/failure.
  - §3 (`405dc811`): Auto-Sync Gallery rows single-line (grid 540→760px, nowrap,
    name ellipsis).
  - §4 (`0877db09`): alarms = weekday TABLE (header row + day-cell toggles),
    only non-empty shown, +Add/Clear all/per-row ×, live debounced writes (no
    Save button), `alarms.json` last-written cache backs get_alarms (task #20
    read-back flakiness). New `web_ui/alarms_editor.js` (500-LOC split).
  - All UI verified headlessly via the static-server + preview technique
    (stubbed `window.pywebview.api`).

- **Downscaler kernel normalization + 22 edge case tests SHIPPED (2026-06-09).**
  Fixed root cause of the 1 LSB RGB parity bug: `kernel1d_init` used
  quantize-then-normalize while PIL uses normalize-then-quantize. Changed to
  match PIL's `normalize_coeffs_8bpc` (Resample.c): normalize double weights to
  sum 1.0, then quantize with round-half-up. Also removed unused `ROUND_HALF_POS`
  define and cleaned leftover debug printf. The `!= 0` → `< 0` check and RGBA
  fallback from the prior session remain.
  **Added 22 new tests**: degenerate dims (1×N, N×1, 1×1), extreme aspect
  ratios (300×1→2×2, 100×4→2×2), non-square identity, odd primes (13×17→5×7),
  asymmetric output (16×16→4×12), checkerboard, gradients, impulse, constant
  channels. **60/60 tests pass** (was 38). Suite ~1170/75 (estimate).

- **Inline-style batch 2 SHIPPED (2026-06-09).** Migrated `templates_monthly_best.js`:
  L15→`row gap-8`, L32→`flex gap-10` (added bare `.flex` — `.row` includes
  align-items:center). L13/L28 inline styles were **redundant** with the
  ID-scoped `#monthly-best .card.glass-card`/`.card-body` rules → deleted them
  (a class can't out-specify an ID rule anyway). Left inline per §2.1: tools.js
  `padding:24px`, L20 `margin:0`, L29 unique. Verified equivalence via preview;
  suite green. **Lesson: grep ID-scoped rules before migrating — many inline
  styles are redundant with existing CSS.**

- **Inline-style batch 1 SHIPPED (2026-06-09).** Added the utility/token layer
  to `style_extra.css` (`.row/.col/.row-between/.wrap/.gap-*`,
  `.label-sm/.label-xs/.text-sm/.text-mono-sm`, `.text-warn/.text-error`) + the
  `--warn`/`--error` tokens in style.css `:root`. Pure addition — no template
  references them yet; `.flex-row` untouched. Verified via preview that rules
  parse + compute correctly. Next: batch 2 (templates_tools + monthly_best) per
  `docs/PLANNING_inline_styles.md`.

- **Inline-style migration scoped (2026-06-09).** `docs/PLANNING_inline_styles.md`
  — REVIEW §2.1. Real count is **138** (4 of "142" were `data-style="…"` false
  matches). ~50 are genuinely-unique (per §2.1's own exception → leave inline);
  ~90 repeated patterns map to a small utility layer (`.row/.col/.gap-*`,
  `.label-sm/.label-xs/.text-sm`, `--warn`/`--error` tokens) added to
  `style_extra.css` (where `.flex-row` already lives). 5 batches, one template
  file each, visual-verify between (the static-server + preview technique from
  the §2.3 fix works headlessly). NOT started. Batch 1 (add utilities) is a
  zero-risk pure addition.

- **appbar.css `!important` cleanup (2026-06-09).** Removed the 6 `!important`
  flags on `#global-status-dot.*` (REVIEW §2.3) — they were unnecessary (the
  ID+class state selectors already out-rank the base rule; JS clears inline
  styles). Verified all 5 dot states (ble/lan/wall/connecting/inactive) compute
  identical colours in a static browser harness via the preview tools. The lone
  remaining `!important` is `.transport-dot.connecting` (equal-specificity
  competitor in sidebar.css — left as-is). Suite green.

- **Notifications single-owner — Phase 1 SHIPPED (2026-06-09).** The §1.2
  double-route is fixed: the GUI no longer runs its own `MacNotificationMonitor`.
  `start/stop_notification_listener`, `is_notification_listener_running`,
  `get_notification_listener_status`, `save_notification_routing` now delegate to
  the daemon over new `DaemonClient` RPCs (`start_notifications`/
  `stop_notifications`/`notification_status`/`set_routing`). Deleted GUI monitor
  machinery (`_notification_monitor`/`_notification_sink`/`_send_notification_async`/
  `_schedule_async`). Regression test asserts the GUI never instantiates
  `MacNotificationMonitor`. Also fixed a flaky pre-existing test
  (`test_routing_loader`) that read the user's real `~/.config` file. Suite
  **green** on py3.14. Phases 2-3 (UI reflects daemon state via broadcasts) still
  open — see `docs/PLANNING_daemon_ownership.md`.

- **Daemon-ownership investigation (2026-06-09).** Scoped REVIEW §1.3/§4.1/§1.2
  read-only → `docs/PLANNING_daemon_ownership.md`. **Key correction:** the
  device-access migration is essentially DONE — there is NO direct BLE in
  `divoom_gui/`; `current_divoom` is a `DaemonDeviceProxy` (scanner_mixin.py:119)
  and the daemon's `DeviceOwner` is the single connection owner. So §1.3 is a
  false-positive and §4.1's "biggest risk" is largely resolved. The ONE genuine
  remaining duplication is notifications (§1.2): the GUI runs its own
  `MacNotificationMonitor` (gui_api.py:226) alongside the daemon's auto-started
  `NotificationService` (daemon.py:145) → double-routed notifications. Fix is
  cheap: GUI should call the daemon's existing `start_notifications` RPC instead
  of polling locally. Phase 1 of the plan is low-risk; NOT started yet.

- **Housekeeping (2026-06-09).** Removed 3 confirmed-dead CSS classes
  (`.color-picker-grid`, `.channel-grid` in channels.css; `.range-slider`
  +thumb in style.css) — `.color-swatch` was KEPT (still used). Cleaned the
  `mcp_server.run_stdio` asyncio usage: dropped the deprecated `StreamReader(loop=)`
  kwarg, documented why `FlowControlMixin` stays (no public equivalent, stable on
  3.14). Verified: neither symbol emits a DeprecationWarning on 3.14, so REVIEW
  §1.8's "will break on 3.14" is overstated. Remaining in §0.5 #6: the 7
  `!important` flags in `appbar.css` (left — needs the specificity chain reworked,
  which is browser-observable and riskier than a grep-delete).

- **tool.py + drawing.py coverage (2026-06-09).** Extended `tests/test_drawing.py`
  (+19 tests, all 14 Drawing builders incl. sand_paint/pic_scan dispatch) and
  added `tests/test_tool_mock.py` (18 tests, timer/score/noise/countdown). Both
  used to skip without hardware. Now: `display/drawing.py` 20%→**100%**,
  `tool.py` 18%→**97%** (remaining branches are unreachable defensive len-checks).
  All four REVIEW §0.5 thin areas now covered.

- **Scheduling coverage (2026-06-09).** Added `tests/test_scheduling_mock.py`
  (24 mock-sender tests). The pre-existing scheduling tests require a real device
  and skip, which is why `scheduling/` sat at 17-23%. Now: `alarm.py` 98%,
  `sleep.py` 100%, `timeplan.py` 100% (remaining alarm branches are defensive
  loop-continues that exact-length responses can't trigger). Suite **1118/75/0**.
  Next thin areas from REVIEW §0.5: `display/drawing.py` (20%), `tool.py` (18%).

- **Review verification pass (2026-06-09).** Verified the DeepSeek multi-lens
  review in `docs/REVIEW_2026-06.md` against the code; added **§0**. Key
  corrections: §1.1 `cmd_push_gif` is **not** a bug (`show_image` *is* the
  animation path); the §3 coverage table is wrong (CLI/MCP/LAN are 38/66/52%,
  not 0%; `framing.py` is 92%, not 13%; real TOTAL **62%**). Suite runs only on
  `/opt/homebrew/bin/python3.14` (**1094/75/0**). Added `/zreview` slash command
  (`.claude/commands/zreview.md`) that encodes the four-lens + coverage review
  *with mandatory per-finding verification*. Real coverage to chase:
  `scheduling/`, `display/drawing.py`, `tool.py`. No coverage config in
  `pyproject.toml` yet (the one §3 rec worth keeping).

- **R33 — Sidebar reorg + Settings polish + per-device gallery style SHIPPED.**
  Suite **1094 / 75 / 0** (0 regressions). Full write-up: `docs/PLANNING_ROUND33.md`.

  **A — Sidebar reorg**: removed Tools nav button; added Routines nav button
  (Schedule + Time sub-tabs). Sessions moved to Channels as a sub-tab
  (`data-channel="sessions"`, overflow:visible, Sleep Aid / Tools / FM Radio
  static cards). Device dots live outside the glass card, tooltip text `#e8e9eb`.

  **B — Routines — Schedule tab**: global gallery-style tab selector removed.
  Each device row in `#sync-targets-list` now has its own inline gallery-style
  tab selector (Recommend/Cartoon/Creative/Nature) + toggle switch. Persisted
  per-device in `hotchannel_config.json` under `device_galleries`. Daemon uses
  `get_device_classify()` to fetch per-classify groups. Interval tab selector
  (1h/6h/12h/24h/7d/30d), auto-save on any change, "Sync devices now" button.

  **C — Settings polish**: checkboxes → toggle switches (hour24, tempf, lowpower,
  mirror); orientation `<select>` → 4-way tab selector (0°/90°/180°/270°); MCP
  stop/start → toggle switch. `scrollbar-gutter:stable` prevents centered-tab
  shift when panel scrollbar toggles.

  **D — App window**: `min_size=(1050, 400)` prevents resize below 1050px wide.
  Tab rows (Channels, Routines, Settings) centered with `margin: auto`.

  **E — Multi-perspective review**: code/architecture/design/coverage review
  documented at `docs/REVIEW_2026-06.md`.

  **R33 in git**: multiple commits on `main` — see `git log` for the full trail.

- **R32 — Monthly Best reorg + Routines + device selector + Text fix SHIPPED.**
  Suite **1094 / 75 / 0** (+1). Full write-up: `docs/PLANNING_ROUND32.md`.

  **A — Monthly Best** is now a single full-width multi-select gallery. The
  devices/sync-targets panel moved to Settings → Routines (§A1). The ghost Fetch
  button is gone; gallery style is remembered **per device** in `config.ini`
  `[gallery]` (`get_gallery_style`/`set_gallery_style`) and restored on startup
  (§A2). Per-tile checkboxes (default all checked) + Select All / Clear; "Update
  Device" pushes every checked image (§A3).

  **B — Routines card**: device selector | gallery-style selector, macOS-style
  toggle (`.switch`), interval, the moved devices list, Save Schedule + "Sync
  devices now". Auto-sync stays daemon-driven via `hotchannel_config.json`.

  **C — Device selector**: stripped `BLE:`/`LAN:` prefix (§C1); sidebar preview
  mirrors the **last image pushed** per device, persisted in localStorage (§C2 —
  user confirmed no live framebuffer readback); dropdown replaced by per-device
  **dots** in a glass pill **below** the preview (recycles the corner
  connectivity-dot chrome, per-device colors, wraps for >4 devices, rebuilds on
  add/remove), color-coded + tooltipped + click-to-switch, `<select>` kept hidden
  as state (§C3).

  **D — Channels → Text FIXED** ("nothing appeared"): the 0x87 LPWA sequence does
  not render on the Pixoo-class LED matrices. `push_text` now renders the text
  with our bitmap font to a device-sized image and pushes via
  `display.show_image()` (matches hass-divoom/futpib). **Static image only**;
  scrolling + hardware verification are follow-ups.

  **E**: removed the Connectivity & Privacy explainer legend.

  **Post-R32 follow-up (user feedback)**: device dots moved into a glass pill
  *below* the preview (recycling the corner connectivity-dot chrome, wraps for
  >4 devices, rebuilds on add/remove). **Settings moved to an appbar gear pill**
  (`#appbar-settings-btn`, right of the brightness/volume bars) — the Settings
  nav button was removed from the sidebar, and the device-selector panel is
  pinned to the sidebar bottom (where Settings was). `?tab=settings` deep-link
  now matches any `[data-tab]`.

  Also removed the bottom-right connectivity indicator pill
  (`.corner-transports` + the four `#tr-*-dot` dots) — no longer relevant; took
  the dead transport-status 5s poll (`refreshTransportStatus`) with it.

  Browser-preview + fresh-Playwright verified the dots, gear (opens Settings,
  28px round pill), gallery multi-select, and Routines card.

- **R31 — Font improvement + CJK infrastructure + warning fixes SHIPPED.**
  Suite **1093 / 75 / 0** (+3).

  **Half-font downsampling improved**: changed from OR rule (any-of-4) to
  majority (≥2-of-4). B/8 and other glyph pairs are now distinguishable at
  ~5px. Regenerated `divoom_fond16_default_half.bin`.

  **CJK font infrastructure**: `APK_RANGES` table added to `bitmap_font.py`
  (18 Unicode ranges from the APK's CmdManager). `from_apk_asset()` classmethod
  loads raw APK font blobs with range-table glyph lookup — supports CJK
  (0x4E00-0x9FA5), Hangul, Greek, Arabic, etc. `_find_glyph_offset()` method
  implements the range-table walk. Backward compatible: existing ASCII-only fonts
  continue to use flat-lookup fast path.

  **Warning fixes**: closed orphaned coroutines in `CommandQueue` (submit, _add,
  _dequeue timeout, _cancel_worker). Fixed test mock that created dangling
  coroutines. Suite now clean with `-Werror::RuntimeWarning` (0 warnings).

  Full write-up: `docs/PLANNING_ROUND31.md` (to be created).

- **R30 — Animation streaming (MCP tool + proxy exclusive context) SHIPPED.**
  Suite **1090 / 75 / 0** (+5).

  `DaemonDeviceProxy.push_animation(file_or_data, *, token)` — convenience
  method that calls `display.show_image()` inside an exclusive-mode session.
  Accepts file path or raw bytes.

  MCP `push_animation` tool (13th tool) — accepts `file` (local path) or
  `data` (base64). Uses exclusive mode when connected through daemon proxy.

  Full write-up: `docs/PLANNING_ROUND30.md`.

- **R29 — Exclusive mode through daemon RPC SHIPPED. Suite 1085 / 75 / 0.**

  The command queue's exclusive mode (R27) is now wired through `device_call`
  so daemon clients can run atomic multi-phase sequences. Full write-up:
  `docs/PLANNING_ROUND29.md`.

  **New RPCs**: `exclusive_start(token)` / `exclusive_end(token)` call
  `CommandQueue.acquire(token)` / `.release(token)` on the daemon's loop.
  `device_call` now accepts a `token` param → forwarded to `_run_device()`.

  **`DaemonDeviceProxy.exclusive(token)`** context manager issues the RPCs
  and tags nested calls with the token.

  **Files**: `daemon_protocol.py`, `device_owner.py`, `daemon.py`,
  `daemon_client.py`. Tests: 6 new in `test_daemon_bridge.py`.

  Commits: (current round, not yet committed)

- **R28 — MCP-via-daemon + scan filter + tab layout + device bitmap font
    SHIPPED. Suite 1079 / 75 / 0.** Full write-up: `docs/PLANNING_ROUND28.md`.
    Commits: `517d9ca0` (MCP daemon-route + scan), `6aa8c747` (tab spacing
    tokens), `eb9169ea` (bitmap font), `27892d5a` (tab layout fixes),
    `fe36661a` (half font).
  - **Device text now uses a real bitmap font (no anti-aliasing).** Was PIL
    `ImageFont.load_default(size=…)` (AA TrueType → mush at 16/32/64px). RE'd the
    APK font format (`F2/d.smali`: 32B/glyph 16×16@1bpp, offset `(cp-0x21)*32`,
    stored rotated 270°). `scripts/extract_apk_font.py` extracts the
    printable-ASCII subset → `divoom_lib/fonts/divoom_fond16_default_ascii.bin`
    (95 glyphs). New `divoom_lib/fonts/` (`BitmapFont`/`get_default_font`):
    proportional, pixel-exact, `max_width` drops whole glyphs. `media_source.py`
    rewired (ImageFont/`_tiny_font` gone); pyproject ships `fonts/*.bin`.
    +10 tests incl. a guard that media_source uses no AA font. **Only ASCII is
    extracted** — CJK ranges exist in the APK file if ever needed (the full
    `references/apk/.../divoom_fond16_*.bin` files have them).
  - **r3: device font halved.** Full glyphs (~9px) dominated the 16px matrix;
    added a half-size variant (`divoom_fond16_default_half.bin`, ~5px) — each
    glyph 2×-OR-downsampled into the same 16-cell format. `get_small_font()`;
    `media_source.py` uses it for all device text. Verified live (16px tile fits
    ~3 chars, still crisp).
  - **Tab spacing centralised.** Each tab area (Channels/Tools/Settings) sits on
    its own glass pane: `[2px] tabs [2px]` vertical padding + `1px` gap to the
    cards below. Tokens `--tab-pane-pad-y/-pad-x/-gap` in `style.css :root` are
    the single source of truth; `.tabs-section` consumes them and
    `#control-panel .grid-layout` has `gap:0` so the grid doesn't double-space
    (was 36px in Channels vs 16px in Tools/Settings). Verified live (pane→card
    gap = 1px in all three). +3 guardrail tests.
  - **Tab layout fixes (r2).** (1) Channels giant empty glass pane → grid
    `grid-template-rows: auto 1fr` (default align-content was stretching the tab
    row to ~217px). (2) Tools/Settings 21px gap below the pane → `.tab-content`
    flex `gap` tokenised as `--panel-gap`; `.tab-content > .tabs-section` margin
    `calc(--tab-pane-gap - --panel-gap)` nets 1px in flex (matches grid). (3) Tab
    row no longer centered (`margin auto`) — left-anchored so it aligns with cards
    and doesn't shift as the scrollbar toggles between sub-tabs. (4) Settings
    `.tabs-section` was never closed in `templates_settings.js` (wrapped the whole
    panel) → added the missing `</div>`. Verified live in all 3 panels
    (pane→card = 1px, zero sub-tab shift). Suite 1077 / 75 / 0.
  - **MCP server no longer opens its own BLE connection.** It was calling
    `_resolve_device()` → a 2nd BLE connect to the daemon-owned device (R17
    single-owner) → `DeviceConnectionError: ... was not found`, shown as a
    Python traceback in the GUI's MCP card (the subprocess logs to
    `~/.config/divoom-control/mcp-server.log`, which the card tails; that's why
    it was in the panel but not the terminal). `cmd_mcp_server` now builds the
    catalog against a `DaemonDeviceProxy` via `ensure_daemon()`. `--mac`
    optional; `--socket/--host/--port/--token` added (local or remote daemon).
  - **Plumbing moved** `divoom_gui/daemon_bridge.py` →
    `divoom_daemon/daemon_client.py` (lib can use it without a lib→gui dep);
    `daemon_bridge.py` is a re-export shim. `mcp_control.start` /
    `gui_api.start_mcp_server` no longer require a MAC (the confusing
    CoreBluetooth UUID in the card is gone). `get_capabilities` awaits the
    proxy's `to_dict()`.
  - **Scan returns Divoom-only.** Removed the `discover_all_divoom_devices`
    fallback that returned ALL named BLE devices when no Divoom matched; new
    `is_divoom_name()` + `DIVOOM_NAME_KEYWORDS`.
  - **`webview` ModuleNotFoundError was stale** — pywebview 6.2.1 + pyobjc are
    installed for the Homebrew python3.14; `./run_gui.sh` imports clean now.
  - See `CHANGELOG.md` (Round 28).

- **R27 — Command queue SHIPPED.**
  Suite **1055 passed / 75 skipped / 0 failed** (+30 from 1025).

  **New module: `divoom_daemon/command_queue.py`**
  - `CommandQueue` class with `_Ring` pre-allocated ring buffer (O(1) FIFO,
    no reallocation). When `maxsize > 0` the backing array is pre-allocated
    and never grows.
  - `submit()` / `submit_async()` — thread-safe coroutine submission.
    Sync `submit()` blocks briefly to raise `QueueFull`/`QueueStopped`
    synchronously (not asynchronously on the future).
  - `maxsize` (constructor, 0 = unbounded): bounded queue with
    `QueueFull` exception at capacity.
  - `item_timeout` (constructor) + `timeout` (submit param): items that sit
    too long in the queue are transparently rejected with `TimeoutError`
    at dequeue time. `None` disables per-item.
  - Exclusive mode (`queue.exclusive(token)` context manager): atomic
    multi-phase scopes where only matching-token items are dispatched.
  - Worker lifecycle: `start()` / `stop()`. `stop()` drains pending items
    with `RuntimeError`, cancels stuck worker after 2s timeout.

  **Integration: `divoom_daemon/device_owner.py`**
  - `_run_device()` now routes through `self._cmd_queue.submit()` instead
    of direct `asyncio.run_coroutine_threadsafe`. Lazily initialises the
    queue via `_device_loop()` if not yet set (fixes regression).
  - `DeviceOwner.stop()` stops the queue before the loop, eliminating
    "Task was destroyed" warnings.

  **Tests: `tests/test_command_queue.py`** — 30 tests (was 14):
  - FIFO, result/exception propagation, exclusive mode (multi-token,
    deferral, token=None), concurrent submisssions (10-way, 50-way,
    30-thread sync), lifecycle (stop drain, idempotent start, start/stop
    cycle, submit-after-stop), maxsize (full rejection, active-item
    exclusion), item timeout (stale expiry, per-submit override, explicit
    None), stress (100-item burst, exclusive+deferred), edge cases
    (cancel non-blocking, empty queue survival, exception types, None
    result).

  **See** `CHANGELOG.md`, `docs/PLANNING_ROUND27.md`.

- **R26 — Daemon channel-switch API + weather fix SHIPPED. Suite 1025 / 75 / 0.**
  Library: `Display.set_temperature_channel()`, `set_clock_rich()`,
  `TEMPRETURE_CHANNEL`. Weather fix: `push_weather()` two-step (0x45 channel
  switch + 0x5F data push). GUI: Push to Device button on weather card.
  See `CHANGELOG.md`, `docs/LLD_R26.md`, `docs/PLANNING_ROUND26.md`.

- **R23 — 500-LOC debt FULLY RETIRED. Suite 994 / 0 / 75; allow-list empty.**
  opencode did the big REVIEW §1 splits (gui_api→`divoom_gui/api/*`, daemon→
  DeviceOwner/NotificationService/SocketServer + command registry, DeviceSlot,
  web_ui splits, menubar→daemon client). This session finished the long tail:
  - `cli.py` 521 → `cli.py` 212 + `cli_commands.py` 352. (Also fixed a test-only
    crash: `test_cli` patched `cli._resolve_device`; handlers now resolve it from
    `cli_commands`, so patch the latter — else the real BLE scan ran and aborted
    the interpreter on py3.14.)
  - `constants.py` 517 → 393 + `constants_scheduling.py` 136 (re-exported via
    `from .constants_scheduling import *`; `divoom_lib.models.*` unchanged).
  - `media_sync.py` 593 → 459 + `audio_visualizer.py` (extracted
    AudioVisualizerWorker).
  - `downsample.c` 522 → 392 + `downsample_kernel.{c,h}` (LANCZOS weight
    precompute as its own TU). **Byte-identical output verified** via the
    dual-impl `test_encoder_both_impls` against a fresh build + x86_64
    cross-compile. build_libdivoom.sh + conftest compile the new TU.
  - `tests/test_file_size.py` ALLOWLIST is now empty → the 500-LOC rule is fully
    enforced and clean.


- **GUI crash-loop on cloud-auth failure FIXED. Suite 994 / 0 / 75.**
  (`./run_gui.sh` was spamming `RuntimeError: UserNewGuest failed: RC=10` on
  every transport-status poll.)
  - Root: `api/connection.get_transport_status` (polled) called
    `divoom_auth.get_credentials()` → network guest login → fail → exception into
    the pywebview bridge, retried every poll. Fixed: cache-only
    `divoom_auth.get_cached_credentials()` (no network, never raises) + a 120s
    failure cooldown in `get_credentials()`; status guards the call. Cloud auth
    now happens lazily only when a real cloud op needs it.
  - Retired obsolete `gui_api._push_menubar_status` (imported the deleted
    `divoom_daemon.menubar_status`; R22 moved the menubar to a daemon-subscribing
    client in `divoom_menubar/`). Staged opencode's menubar-move deletions.
  - +`tests/test_auth_resilience.py`.
  - **OPEN — Divoom guest auth (RC=10 "Command is not match") is an upstream
    issue.** Guest login (`_login_guest`, body carries `Command: "User/NewGuest"`)
    is rejected; email login (`_login_email`) uses the path-only `UserLogin`
    endpoint (no `Command` field) and is the working surface. **Cloud features
    (gallery) need a configured Divoom email/password** in
    `~/.config/divoom-control/config.ini` `[divoom]`, OR the guest flow updated
    from a fresh APK capture. Local BLE/LAN control is unaffected.
  - opencode executed the R21 review refactors: gui_api split into `divoom_gui/
    api/` (connection/lighting/tools/widgets/window), daemon split into
    DeviceOwner/NotificationService/SocketServer + command registry, DeviceSlot
    dataclass, web_ui splits, menubar → daemon client.


- **R23 — REVIEW §1.2 + §1.3 + §1.4 + §1.5 SHIPPED. Suite 980 / 0 / 75.**
  - **§1.2** — `gui_api.py` refactored from 891 → 444 LOC by composing 5 `ApiBase`
    collaborators (`ConnectionApi`, `LightingApi`, `ToolsApi`, `WidgetsApi`,
    `WindowApi`). Every bridge method that existed in a collaborator now
    delegates to it; all logging + error handling lives in collaborators.
    `AsyncLoopThread` moved from inline definition to `divoom_gui.api`.
    Removed dead code: `_device_status()`, `_target()`, `_dispatch()`,
    `_tool_call()`, `_as_bool()` — all now in collaborators.
    `send_notification` added to `ToolsApi`. `set_brightness`, `set_volume`,
    `display_wall_image`, `display_custom_art` added to `LightingApi`.
    File-size guardrail: `gui_api.py` removed from ALLOWLIST (444 ≤ 500).
  - **§1.3** — daemon.py 4-wave extraction:
    - Wave 1 (5d3f7d1): command registry (if-ladder → dict).
    - Wave 2 (7c0cc31): `SocketServer` → `divoom_daemon/socket_server.py`.
    - Wave 3 (73b39bd): `NotificationService` → `divoom_daemon/notification_service.py`.
    - Wave 4 (e3612b0): `DeviceOwner` → `divoom_daemon/device_owner.py`.
    - daemon.py: 730 → 132 LOC; removed from ALLOWLIST (10 entries).
    - New modules: 3 (socket_server, notification_service, device_owner).
  - **§1.4** — `DeviceSlot` dataclass shipped (c29c715):
    - `divoom_lib/models/device_slot.py` with `@dataclass DeviceSlot(device, x, y, size, width, height)`.
    - Exported from `divoom_lib/models/__init__.py`.
    - Replaced all ad-hoc 6-tuple construction/destructuring in `wall.py` and `device_owner.py`.
  - **§1.5** — 6 web_ui files > 500 LOC split into 14 files:
    - `templates.js` (718) → 4 files: `templates_tools.js` (124), `templates_monthly_best.js` (64), `templates_widgets.js` (200), `templates_settings.js` (330).
    - `app.js` (619) → `app_globals.js` (196) + `app_init.js` (425).
    - `channels.js` (578) → `channels_core.js` (149) + `channels_grids.js` (436).
    - `settings.js` (745) → `settings_hardware.js` (344) + `settings_features.js` (404).
    - `widgets.css` (524) → `widgets_base.css` (301) + `widgets_extra.css` (224).
    - `style.css` (510) → `style.css` (279) + `style_extra.css` (236).
    - ALLOWLIST shrunk from 10 → 4 entries (`media_sync.py`, `downsample.c`, `constants.py`, `cli.py`).
    - `index.html` + `style.css` @import chain updated; 8 test files updated.
  - Suite 980 passed / 75 skipped (zero regressions across §1.2–§1.5).

- **R22 — menubar refactor: top-level package + daemon client. Suite 944 / 0 / 75.**
  - New `divoom_menubar/` package (menubar_client.py, menubar.py) at repo root.
  - Menubar rewritten as pure daemon client: connects to daemon's Unix socket,
    subscribes to EVENT_STATUS events for real-time status updates. **No BLE,
    no socket server** — respects R17 single-owner rule (daemon owns device +
    notification monitor).
  - Event-driven: daemon pushes EVENT_STATUS on listener start/stop/error +
    every routed notification. Menubar title updates instantly — zero polling
    (user explicitly rejected polling for both MCP toggle and menubar).
  - Menu: Start/Stop Notifications → daemon commands; "Open Notifications..."
    deep-links GUI to `--tab data-sources --card notifications`.
  - CLI: `divoom-control menubar` (sync handler, blocks on Cocoa loop).
  - `tests/test_menubar.py` (6 tests, pure logic, no AppKit).
  - Deleted `divoom_daemon/menubar.py` + `menubar_status.py` (had own BLE +
    server, violating single-owner).

- **R21 — review + doc overhaul. Suite 993 / 0 / 75.**
  - `docs/REVIEW_2026-06.md`: full code/architecture review (Linus + Uncle Bob),
    UI/UX review (Rams + Kare), and the "rewrite lib+daemon in Rust?" analysis.
    Key findings: 11 files >500 LOC (rule regressed); `gui_api.py` (921) is a God
    Object with ~150 LOC of duplicated wall/single branching; `daemon.py` (730) is
    an if-ladder dispatch + 4 responsibilities; wall 6-tuple should be a dataclass.
    Rust verdict: don't rewrite the lib; the *daemon* is the only defensible Rust
    candidate, and only with an embedded/footprint driver.
  - **Executed in R21:** `tests/test_file_size.py` (500-LOC guardrail with a
    shrink-only allow-list of the 11 current offenders); README + ARCHITECTURE
    rewritten; docs index; removed 10 stale docs.
  - **Executed in R22:** menubar refactor into `divoom_menubar/` (daemon client).
  - **Executed in R23:** gui_api collaborator integration (API split into 5
    collaborators, gui_api.py 891→444 LOC, removed from ALLOWLIST).
  - **Executed in R23 (§1.3):** daemon.py 4-wave extraction (command registry
    + SocketServer + NotificationService + DeviceOwner; daemon.py 730→132 LOC;
    removed from ALLOWLIST).
  - **Staged (still need doing):** REVIEW §1.4 (DeviceSlot dataclass), §1.5
    (web_ui splits).

- **R20 — Linux compatibility (daemon + libraries) SHIPPED. Suite 991 / 0 / 75.**
  `divoom_lib` + `divoom_daemon` run on Linux; BLE via bleak/BlueZ; the R19
  network server is platform-neutral. See `docs/PLANNING_ROUND20.md`.
  - `divoom_lib/native_lib.py` resolves `libdivoom_compact.{dylib|so|dll}`; all 4
    ctypes loaders use it. `build_libdivoom.sh` is cross-platform (clang/.dylib on
    macOS, cc/.so on Linux). `compact.c` NEON now guarded (`DIVOOM_HAVE_NEON`),
    x86_64 uses byte-identical memcpy — both paths verified to compile.
  - Daemon notification monitoring is macOS-only; off macOS `_cmd_start` returns
    a clean `unsupported`/idle state (no Mac monitor built). `media_source`
    now-playing returns None off macOS.
  - **Not run on real Linux hardware yet** (cross-compile + platform-guard unit
    tests only). Gaps by design: no Linux notification monitor / now-playing /
    menu-bar (macOS-only); a D-Bus/MPRIS backend would be future work.

- **R19 — daemon as a headless NETWORK server SHIPPED. Suite 986 / 0 / 75.**
  (User: "why JSON for on-device RPC? + I want the daemon to run headless over
  the network." Decisions: TCP alongside Unix · LAN + token · ship image bytes.)
  - JSON answer: NDJSON is the *control plane* (small, debuggable, transport-
    agnostic); device pixels/GIFs are the *data plane*, kept out of JSON (binary
    needs base64). See `docs/PLANNING_ROUND19.md`.
  - `DivoomDaemon(host, port, token)`: binds Unix (always) + an AF_INET listener
    when host/port set. TCP requests need a token (`hmac.compare_digest`); Unix
    stays trusted (no token). **Fail-closed**: TCP without a token won't start.
    Token falls back to `DIVOOM_DAEMON_TOKEN`. CLI: `divoom-control daemon
    --host 0.0.0.0 --port 9009 --token <secret>`.
  - Binary over the wire: `device_call` gained `blobs={argIdx: b64bytes}`; the
    daemon writes each to a temp file and substitutes the path. `DaemonClient`
    encodes blobs; `DaemonDeviceProxy` auto-ships local-file args as blobs when
    `is_remote` (TCP) — so media/gallery/cover-art work remotely with no call-site
    changes. `DaemonClient.from_env()` + `ensure_daemon()` target a remote daemon
    when `DIVOOM_DAEMON_HOST` is set (and never spawn).
  - +7 tests (`tests/test_daemon_network.py`). **Not hardware-verified; token is
    plaintext over TCP (add TLS for untrusted nets — follow-up).**

- **R17 P5 — FULL CUTOVER SHIPPED. The daemon is the sole BLE owner; the GUI is
  a thin client. Suite 980 / 0 / 75.** (User chose "do the full flip now.")
  - Daemon (`9cd76a73`, `abc83a20`, `8cb8e10e`): `device_call` (dotted dispatch,
    target device|wall), enriched `connect` (BLE+LAN+auto), `device_status`
    {connected,mac,lan_ip,wall}, `scan`, `wall_configure` (idempotent),
    `probe_lan`, `sync_artwork` (download+decode+resize+stream daemon-side); a
    dedicated device asyncio loop that survives across calls.
  - GUI (`divoom_gui/daemon_bridge.py` + scanner_mixin + gui_api + gallery_sync):
    `ensure_daemon()` auto-spawns a detached daemon; `DaemonDeviceProxy` routes
    `proxy.x.y(...)` through `device_call` and answers is_connected/lan/_conn from
    `device_status`. `current_divoom`/`wall_instance` are proxies — so media_sync
    (live widgets) routes through the daemon with NO rewrite. No `Divoom(`/
    `DivoomWall(` construction left in the GUI.
  - Library: `DivoomWall` gained switch_channel/push_text/set_brightness/
    set_volume; `media_decoder` moved divoom_gui→divoom_lib.
  - **AFTER P5 the daemon MUST be running for the GUI to control the device**
    (the GUI auto-spawns it via `divoom-control daemon`).
  - **Remaining (needs the live app + hardware — NOT verified, unit-green only):**
    (1) runtime-drive every GUI path against a real device; (2) menubar still
    uses `gui_api._push_menubar_status` → should subscribe to the daemon's status
    stream instead (the daemon already owns the monitor + broadcasts); (3)
    save_lan_config no longer hot-attaches LAN to a live device (applies on next
    connect). See `PLANNING_ROUND17.md §outcome P5`.

- **R18 — live-widgets + tabs fixes SHIPPED** (user feedback). Weather card
  auto-populates on load; weather location now IP-geolocated via wttr.in (no more
  hardcoded "Berlin"); weather 10-min poll re-pushes to the device; sysmon lost
  its grey gauge-track box; stock ticker got a smaller arrow + small font so the
  acronym fits; Tools/Settings sub-tabs got `.tab-icon` SVGs; the pill row +
  theme selector size to content. Suite **963 / 0 / 75**. *(item: weather
  device-sync still needs hardware verification.)*
- **Credentials-erased bug FIXED:** the settings form never re-populated the
  password field, so a plain re-save wrote `password=""`; the 23h token-cache
  expiry then degraded the account to a guest token. `save_credentials` now keeps
  a stored password on blank re-saves. +3 regression tests.
- **R17 (3-way split) — PHYSICAL split DONE (P1-P4, P6).** `divoom_lib` /
  `divoom_daemon` / `divoom_gui` are three top-level packages; the daemon core +
  notifications + menubar live in divoom_daemon; the dylib in divoom_lib; gui/ is
  renamed divoom_gui/. pyproject finds all three; entry points verified. Suite
  **963 / 0 / 75** (Playwright DOM tests browser-verify the rename). **P5 (the
  behavioural daemonisation) is the one remaining large piece** — see below.
  - **P5 blocker/decision:** the BLE connection is single-owner, so the daemon
    and GUI can't both hold the device. Correct model = **daemon owns the device;
    GUI is a thin RPC client** (generic `device_call` RPC + `gui_api` proxies, no
    direct BLE in the GUI; scanning/wall/LAN move to the daemon). It's a large,
    high-risk rewrite of the 935-line `gui_api` — needs its own tested program.
    See `docs/PLANNING_ROUND17.md` §outcome P5.

- **In flight — R16 daemon (P1+P2 shipped) → folding into R17 (3-way split).**
  Architecture correction from the user: the macOS notification monitor + ALL
  background device-driving must live in a **headless daemon**, not the GUI
  (presentation only). R16 P1 (`gui/daemon_protocol.py` — NDJSON command +
  subscribe/stream + `DaemonClient`) and P2 (`gui/daemon.py` — `DivoomDaemon`
  owns device + monitor + routing + event socket; `divoom-control daemon` CLI;
  monitor/device-sender injectable) are SHIPPED + tested (13 daemon tests).
  Suite **959 passed / 0 failed**.
  - **R17 — 3-way package split IN PROGRESS** (`divoom_lib`/`divoom_daemon`/
    `divoom_gui`). **P1–P3 SHIPPED**: `divoom_daemon/` package created; daemon
    core + `macos_notifications` + `menubar*` moved there; the native dylib +
    `compact.c` moved into `divoom_lib/` (all 9+ refs fixed, rebuilt, green).
    Suite **959 / 0 / 75**. **Next = P4**: rename `gui/` → `divoom_gui/` (move
    gui_main/gui_api/presets_manager/web_ui; the background modules ride along
    until P5), fix the **10 test `sys.path` hacks** + menubar's `../gui/gui_main`
    path + pyproject `gui`→`divoom_gui`. Then **P5** behavior migration (media_sync
    /gallery/scanner → daemon; gui_api+menubar become DaemonClients; removes R15
    §6 GUI-push), **P6** pyproject finalize, **P7** close. See
    `docs/PLANNING_ROUND17.md` §outcome. R16 P3/P4 are folded into P5.

- **Last round shipped:** Round 15 (§1+§7, §2, §3, §4, §5, §6 SHIPPED —
  round complete). 829 → 946 passed, +117 tests, zero regressions.
  **§6 menubar (event-driven, no polling):** the menubar status item shows
  `Divoom (active|idle|error)` with a green/grey/amber tint + an "Open
  Notifications..." item; the GUI pushes status to the menubar's Unix socket on
  start/stop/error (`gui_api._push_menubar_status`); AppKit-free logic in new
  `gui/menubar_status.py`; `gui_main --tab/--card` URL params honored by
  `settings.js`. `tests/test_menubar_ipc.py` (14). The plan's "poll every 5s"
  was dropped — user rejected polling twice. **MCP server live** — `divoom-control mcp-server
  --mac <MAC>` exposes 12 tools over stdio JSON-RPC. GUI toggle in
  Settings → Connectivity with **no background polling** (initial
  fetch + tab-activation + click-driven refresh only — user
  explicitly rejected 5s polling as "notifications every 5s").

  - **§1+§7 — Tab style unification** (`2c819325`): single source
    of truth `gui/web_ui/tabs.css` (`.tabs-row` / `.tab-btn` /
    `.tab-icon`); segmented-pill across Channel/Tools/Settings/Theme
    rows; Kare 16×16 SVG icon prefix optional. +16 tests. **Lesson
    learned:** backticks in template-literal comments break JS
    parsing — use plain text in inline comments inside template
    strings.
  - **§2 — Monthly Best auto-fetch** (`0e23253f`): `window.loadGallery()`
    auto-fires on tab activation + classify change. Renamed "Push
    Selected to Device" → "Update Device"; dropped "Refresh" button.
    Box cap `minmax(110px, 168px)`. +10 tests.
  - **§4 — Settings refactor** (`24f95690`): `.danger-zone` extracted
    to own `card.glass-card.danger-card` (red border via `settings.css`).
    Added 7d (`604800`) and 30d (`2592000`) to routines; `MAX_INTERVAL
    = 2592000` clamp in `hotchannel_config._normalize()`. +10 tests.
  - **§3 — Live Widgets weather card + Notifications move**
    (`b7c1e4d7`): new `divoom_lib/weather_provider.py` (WTTrIn +
    Stub + auto-fallback; env `DIVOOM_CONTROL_WEATHER_{PROVIDER,
    LAT, LON, LOCATION}`; default Berlin). Weather card has 128×128
    preview + 16×16 SVG icon + 7-segment temp; auto-push on select +
    10-min poller. Notification manual + mirror cards moved from
    Settings → Devices to Live Widgets. +41 tests (30 + 11).
  - **§5 — MCP server + GUI toggle** (`121d0b5`): new
    `divoom_lib/mcp_server.py` (MCPServer, Tool dataclass, JSON-RPC
    per spec 2024-11-05; methods: `initialize`, `tools/list`,
    `tools/call`, `ping`; std codes: `-32700`/`-32600`/`-32601`/
    `-32602`/`-32603`; notifications get no reply). 12 tools in
    `divoom_lib/mcp_tools.py`: `set_volume` (0-15),
    `set_brightness` (0-100), `set_light_mode` (named→channel),
    `set_weather` (-127..128, named→WeatherType), `set_alarm`
    (10 slots, weekday_mask 0-127), `set_radio` (875-1080),
    `set_low_power` (bool), `set_screen_orientation` (0/90/180/270 +
    mirror), `show_image` (local path), `play_sound` (100-3000ms
    best-effort via set_hot), `get_capabilities` (read-only),
    `get_device_state` (read-only with safe fallback). CLI
    `divoom-control mcp-server --mac <MAC>` runs the stdio loop.
    `gui/mcp_control.py` spawns `python -m divoom_lib.cli mcp-server`
    as a subprocess (new process group for clean SIGTERM); logs to
    `~/.config/divoom-control/mcp-server.log`. Settings → Connectivity
    card with Start/Stop buttons + status pill + log tail (20 lines /
    16 KB). **No 5s polling** — initial fetch + tab-activation + click
    refresh only. `docs/MCP_SERVER.md` ships with config snippets
    for Claude Desktop, Cursor, Cline, Continue. +25 tests. **The
    AsyncMock lesson:** auto-spy on `MagicMock` does NOT return
    AsyncMocks for sub-attributes; you must explicitly set
    `d.music.set_volume = AsyncMock(return_value=...)` to get
    `assert_awaited_*_with` assertions working.

  Suite: **946 passed / 0 failed / 75 skipped** (up from R15 start
  at 829). **+117 tests across R15 §1-§6**. Zero regressions
  across R8→R15.

- **Earlier rounds:** R14 (weather facade, routing JSON, GUI card,
  pyproject.toml); R13 (capability detection + examples/CLI +
  macOS notifications); R12 §A P7 (Tools→Sessions sub-tab rename),
  §D audit, §E pushed; R11 push-path bug fixes; R10 ANCS; R9 screen
  orientation + factory reset (0xBD EXT); R8 device settings/FM/weather
  /memorial + Tools sub-tabs; R7 surfaced text/alarms/sleep/tools.
  See `CHANGELOG.md` + `docs/PLANNING_ROUND*.md`.
- **Git:** R8→R15 arc is in the working tree, ready to push.

## Hardware note

macOS Bluetooth TCC is per responsible-process; drive real BLE by launching via
Terminal (`open *.command`). Device UUIDs + method in `docs/DEVICE_VALIDATION_PLAN.md`.

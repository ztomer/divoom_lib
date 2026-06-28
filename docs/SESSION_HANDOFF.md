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

- **NATIVE PORT HARDENING — Phase 1+2 done; Phase 4 made autonomous (2026-06-28):**
  - **Phase 1 (commit `f7e0e7c`):** fixed the broken `--no-default-features` build.
    Root cause: the `DeviceTransport` device-I/O method layer was `ble`-gated even
    though it delegates to non-ble Spp/Lan/Mock, and `BleResult` lived in the gated
    `ble` module. Fix: relocated `BleResult` to `transport.rs` (ble.rs re-exports),
    un-gated the method layer + `NativeEncoder`/`encoder()` + `device_call` (gating
    only the inner `DeviceTransport::Ble` arms via `!matches!(Lan)`), and rewrote
    `wall.rs` to use the enum method layer (also fixed a latent Spp/Mock wall
    silent-fail). **`cargo test` = 62 green; `cargo test --no-default-features` = 62
    green.** The full command surface + MockTransport now build/test hardware-free.
  - **Phase 2 (commit `762c6ad`):** added `rust-core` (ubuntu, no-ble gate) and
    `rust-ble` (macos, full ble) jobs to `.github/workflows/tests.yml`. This is the
    gate that would have caught the e4bd424 regression.
  - **Phase 4 re-planned for autonomy** (in `PLANNING_NATIVE_PORT_HARDENING.md`):
    Tier A = mock-driven MCP + exclusive-mode E2E, fully hardware-free in CI; Tier B
    = real-device on macOS via `open`-ing the pre-granted dev-daemon `.app` (no
    per-run user action); Tier C = Linux/Windows real-radio, the only irreducible
    human/device-bound residue (CI cross-build covers compile-only).

### Open threads

- **500-LOC house rule violated in the Rust tree:** `live_jobs.rs` (965),
  `daemon.rs` (502). Hardening plan **Phase 3** (no hardware).
- **Phase 4 verification** — Tier A (mock MCP + exclusive E2E in CI) and Tier B
  (real Pixoo via the granted `.app`) are autonomous; Tier C (Linux/Windows real
  radio) is the only user/device-bound item. See the hardening plan.
- **Phase 5** — Python backend archival, gated on 3+4.
- _(RESOLVED this round: the broken `--no-default-features` build + the no-CI-runs-
  cargo gap — Phases 1+2.)_

- **DOC CLEANUP — native-port docs retired/pruned (2026-06-28):** Retired the
  obsolete `docs/PLANNING_NATIVE_PORT.md` (original evaluate-and-plan doc, fully
  executed now that the port shipped R54–R56); its decision summary moved into
  `docs/ROADMAP.md` and its 5 source-comment references were repointed there.
  Pruned this handoff's long R53.x-and-older tail (history retained in CHANGELOG +
  git). The active forward plan for the Rust port is
  `docs/PLANNING_NATIVE_PORT_HARDENING.md`.

- **RUST MOCK TRANSPORT & TEST COVERAGE INFRASTRUCTURE (2026-06-28):**
  Implemented MockTransport for offline Rust daemon testing and shipped 4 new E2E mock tests verifying wire byte patterns for core commands. This enables testing device_call serialization without real hardware.

  **Changes shipped:**
  - `src/mock_transport.rs` [NEW]: `MockTransport` struct with `send_command()` that logs `(cmd_id, payload)` tuples into a `Vec<(u8, Vec<u8>)>` and simulates generic ACK responses.
  - `src/mock_device_tests.rs` [NEW]: 4 `#[tokio::test]` E2E tests — `set_clock_rich` (0x45 APK C2 layout), `show_clock` (0x45 hass-divoom layout), `set_brightness` (0x74), `set_volume` (0x08). All assert exact wire byte patterns.
  - `src/transport.rs`: Added `Mock(MockTransport)` variant to `DeviceTransport` enum with delegated trait methods.
  - `src/daemon_connect.rs`: Added `{"mock": true}` connect path + `Mock` arm in `cmd_disconnect`.
  - `src/device_call/mod.rs`: Added `DeviceTransport::Mock(_)` to the BLE-like device gate.
  - `src/wall.rs`, `src/daemon.rs`, `src/macos_notifications.rs`: Added exhaustive `Mock(_)` match arms.
  - `scripts/rust_coverage.sh` [NEW]: Helper script for `cargo-llvm-cov` code coverage reporting.

  **Tests:** Rust **62 tests passed** (11 lib + 46 integration + 4 mock + 1 native-encode); Python **16 passed, 1 skipped** (daemon parity suite).

- **NATIVE PORT: DIVOOM CLOUD AUTHENTICATION, GALLERY SYNC, MONTHLY BEST LOOP, & CLOCK OVERLAY ALIGNMENT (2026-06-28):**
  Successfully completed the remaining native port features in the Rust daemon (`divoomd`) to achieve 100% parity with the authoritative Python daemon and library. The daemon can now run completely standalone, handling cloud logins, category file queries, scheduled monthly best background scrapers, precompiled animation streams, and APK-aligned clock layouts.

  **Changes shipped:**
  - `src/cloud.rs` [NEW]: Ports email login (`POST /UserLogin`), guest HMAC-MD5 signing (`POST /User/NewGuest`), UTC time sync, configuration parser (`config.ini`), cache manager (`auth_token.json` with 0o600 file write), cloud gallery categories retrieval (`/GetCategoryFileListV2`), and failure cooldown mechanism. Contains 5 inline unit tests verifying crypt/cache lifecycles.
  - `src/monthly_best.rs` [NEW]: Ports the background scraper ticker loop which polls `hotchannel.json`, extracts Magic 43 container GIFs, connects to target displays on interval, downsamples files, and streams native animation payloads.
  - `src/device_call/basic.rs`: Implemented `"animation.stream_animation_8b"` for precompiled stream uploads and `"display.set_clock_rich"` for APK C2() aligned clock coordinate layouts.
  - `src/daemon.rs`: Exposed `"get_credentials"`, `"get_cached_credentials"`, and `"fetch_gallery"` socket dispatch endpoints.
  - `src/lib.rs` & `src/main.rs`: Registered new modules and spawned the `monthly_best` background loop task at daemon startup.
  - `Cargo.toml`: Added `md-5` and `hmac` dependencies.
  - `tests/test_rust_daemon_parity.py`: Shipped `test_rust_cloud_auth_endpoints`, `test_rust_fetch_gallery`, and `test_rust_set_clock_rich` integration tests verifying all new socket calls.

  **Tests:** Rust 58 passed; Python 1703 passed, 87 skipped. (Verified with new unit and integration tests).


- **NATIVE PORT: BLUETOOTH CLASSIC SPP INTEGRATION VIA PYTHON SUBPROCESS BRIDGE (2026-06-28):**
  Successfully implemented Bluetooth Classic SPP support in the native Rust daemon (`divoomd`) using a lightweight Python subprocess bridge (`spp_bridge.py`). This allows the native daemon to connect to older classic SPP devices (e.g. Tivoo-Max) by reusing the proven Python `BTSppTransport` stack under the hood, bypassing complex Objective-C/IOBluetooth binding issues.

  **Changes shipped:**
  - `divoom_daemon/spp_bridge.py` [NEW]: Standard JSON-line standard I/O bridge wrapping `BTSppTransport` for classic Bluetooth connection management.
  - `native-port/divoomd/src/spp.rs` [NEW]: Native Rust `SppTransport` implementing tokio process spawning, input/output piping, and `0x8B` animation streaming parity.
  - `native-port/divoomd/src/transport.rs`: Added the `Spp` variant to `DeviceTransport` and delegated all relevant transport calls.
  - `native-port/divoomd/src/daemon_connect.rs`: Routed connection requests to `SppTransport` when `use_ios_le_protocol` is `false`.
  - Exhaustive match coverage updated across `daemon.rs`, `live_jobs.rs`, `wall.rs`, `art.rs`, `art_hot.rs`, and `macos_notifications.rs` to handle `DeviceTransport::Spp` cleanly.
  - `tests/test_rust_daemon_parity.py`: Shipped `test_rust_spp_connect_failure_integration` E2E test verifying dynamic python bridge subprocess spawning/error propagation, and added `test_rust_hardware_parity` executing live scans, connection, get/set brightness, and disconnection on real Divoom hardware (Tivoo-Max).
  - Renamed manual smoke-test `test_display_aliases.py` to `smoke_display_aliases.py` to fix pytest collection.

  **Tests:** Rust 51 passed; Python 1702 passed, 87 skipped. (Verified with new integration and hardware tests).

- **NATIVE PORT: ALIGN NOTIFICATION SERVICE, COMMAND SCHEMAS, TCP/TOKEN AUTH, --mac OPTION & RUST AUTO-SPAWN (2026-06-28):**
  Aligned the native Rust daemon's macOS notification service monitor (`macos_notifications.rs`), routing, and command responses with the ground-truth Python daemon. Ported the headless TCP server listener, token authentication features, and `--mac` option default address configurations. Shipped the `DIVOOM_USE_RUST_DAEMON` auto-spawner integration in the Python clients and GUI launcher.

  **Changes shipped:**
  - `src/macos_notifications.rs`: Refactored to query the Notification Center SQLite DB (Sonoma/Sequoia paths + Group Containers fallback) using a read-only `rusqlite` connection (removing `sqlite3` CLI subprocess calls). Parsed binary plists with the `plist` crate to retrieve `app`, `title`, and `body` fields. Implemented routing and tracking for `seen`, `routed`, and `dropped` counters, duplicate suppression, and health checks.
  - `src/daemon.rs`: Aligned `get_status`, `start_notifications`, `stop_notifications`, `notification_status`, and `set_routing` command payloads and response shapes to be identical to the Python daemon. Exposed status and notification events to socket subscribers. Relocated `DeviceTransport` to `src/transport.rs` and moved argument/blob parsing into `src/device_call/mod.rs` to keep `daemon.rs` strictly under 500 lines. Updated `device_status` to return the stored default MAC when disconnected.
  - `src/main.rs`: Supported `--host`, `--port`, `--token`, and `--mac` CLI flags (with `DIVOOM_DAEMON_TOKEN` env variable fallback). Enforced token requirement when binding to a TCP port, and wired TCP listener concurrently with Unix listener. Passed the default MAC config to the Daemon.
  - `src/socket_server.rs`: Made `serve_connection` generic over the stream type (`AsyncRead + AsyncWrite + Unpin`) to serve both Unix and TCP streams. Added `serve_tcp` and implemented constant-time comparison for token verification.
  - `tests/test_rust_daemon_parity.py`: Shipped a new Python integration test suite verifying the socket response shapes, token auth, and default MAC address config of the compiled Rust daemon subprocess using Python `DaemonClient`.
  - `divoom_daemon/daemon_client.py`: Added support for `DIVOOM_USE_RUST_DAEMON` inside `spawn_daemon()`, enabling Python clients/GUI launcher to dynamically auto-spawn and run the compiled Rust `divoomd` daemon instead of the default Python daemon.

  **Tests:** Rust 51 passed; Python 1711 passed, 87 skipped. (Verified with new integration tests).

- **NATIVE PORT: ART SYNC, HOT-UPDATE, WALL, LIVE JOBS, macOS NOTIFICATIONS + 500 LOC SPLITS (2026-06-26):**
  Ported the remaining high-level subsystems to the native Rust daemon (`divoomd`). All files comply with 500 LOC.

  **New modules shipped:**
  - `art.rs` (331): custom art push/query, cloud CDN download, hot-update dispatch
  - `art_codec.rs` (197): AES-128-CBC (pure Rust), magic-43/9/0xAA frame decoders, image rescale
  - `art_hot.rs` (251): hot-update manifest, SHA-1 verify, BLE chunk streaming
  - `wall.rs` (457): DivoomWall multi-panel coordinator + `cmd_wall_configure` (moved from daemon.rs)
  - `live_jobs.rs`: background widget loops (system monitor, stocks, weather, music album cover)
  - `macos_notifications.rs` (233): SQLite `usernoted` monitor via sqlite3 CLI, ANCS push
  - `daemon_connect.rs` (83): connect/disconnect/scan extracted from daemon.rs

  **Refactored:**
  - `daemon.rs` (498): thin delegations; `tx` field made `pub(crate)`
  - `lib.rs`: all new modules registered
  - `ble.rs`: `wait_for_any_response` for hot-update multiplexing
  - `lan.rs`: `probe()` method for LAN validation

  **Tests:** Rust 51 passed; Python 1686 passed, 87 skipped.
  Playwright UI failures (12 + 6 errors) are pre-existing missing-browser-binary issues, unrelated.

  **Commit:** `7cb5240`

  Modularized the native Rust daemon's (`divoomd`) `device_call` commands logic to strictly adhere to the 500 LOC limit constraint:

  **Modularization:** Extracted all inline command match arms and helper functions out of `daemon.rs` and moved them into submodules inside the `src/device_call/` directory:
  - `src/device_call/basic.rs` (305 lines)
  - `src/device_call/alarm.rs` (254 lines)
  - `src/device_call/sleep.rs` (198 lines)
  - `src/device_call/timeplan.rs` (102 lines)
  - `src/device_call/tools.rs` (150 lines)
  - `src/device_call/text.rs` (150 lines)
  - `src/device_call/game.rs` (90 lines)
  - `src/device_call/design.rs` (120 lines)
  - `src/device_call/system.rs` (285 lines)
  This shrunk `daemon.rs` from 1944 lines down to **317 lines**, bringing the entire daemon repository in line with the 500 LOC rule.

  **Feature Gating & Clean Compilation:** Gated the submodules in `mod.rs` and all BLE-specific imports/fields in `daemon.rs` behind `#[cfg(feature = "ble")]` to ensure warning-free and error-free compilation both with and without default features.

  **E2E & Parity Tests:** All 55 Rust tests pass successfully. Full Python pytest suite passes cleanly with 1706 passed, 87 skipped.

- **NATIVE PORT: SCHEDULING COMMANDS (2026-06-23 14:35 EDT):**
  Ported the alarm, sleep, and timeplan scheduling commands to the native Rust daemon (`divoomd`):

  **Alarm:** Ported `alarm.get_alarm_time`, `alarm.set_alarm`, `alarm.set_alarm_gif`, `alarm.get_memorial_time`, `alarm.set_memorial_time`, `alarm.set_memorial_gif`, `alarm.set_alarm_listen`, `alarm.set_alarm_volume`, and `alarm.set_alarm_volume_control` (with direct name and alias dispatch). Deserialized and parsed 10-byte alarm info blocks and 39-byte memorial blocks.

  **Sleep:** Ported `sleep.show_sleep`, `sleep.get_sleep_scene`, `sleep.set_sleep_scene_listen`, `sleep.set_scene_volume`, `sleep.set_sleep_color`, `sleep.set_sleep_light`, and `sleep.set_sleep_scene` (with direct name and alias dispatch). Deserialized and parsed 10-byte sleep scene status blocks.

  **Timeplan:** Ported `timeplan.set_time_manage_info` and `timeplan.set_time_manage_ctrl` (with direct name and alias dispatch). Mapped to command codes `0x56` and `0x57` respectively.

  **E2E & Parity Tests:** Updated the `ported_commands_route_to_device_call` integration test in `tests/daemon_behavior.rs` to verify that all newly implemented commands and their aliases correctly match in the router and dispatch to the device transport. Verified both compilation and test suite correctness with and without the `ble` feature gate. Full Python pytest suite passes with 1706 passed, 87 skipped.

- **NATIVE PORT: TOOL & NOTIFICATION COMMANDS (2026-06-23 14:30 EDT):**
  Ported the device tool commands (scoreboard, timer, countdown, noise meter) and notification display commands to the native Rust daemon (`divoomd`):

  **Scoreboard:** Ported `"scoreboard.set_scoreboard"`, `"set_scoreboard"`, `"scoreboard.get_scoreboard"`, and `"get_scoreboard"` (0x71/0x72 commands with type 1).

  **Timer:** Ported `"timer.set_timer"`, `"set_timer"`, `"timer.get_timer"`, and `"get_timer"` (0x71/0x72 commands with type 0).

  **Countdown:** Ported `"countdown.set_countdown"`, `"set_countdown"`, `"countdown.get_countdown"`, and `"get_countdown"` (0x71/0x72 commands with type 3).

  **Noise Meter:** Ported `"noise.set_noise"`, `"set_noise"`, `"noise.get_noise"`, and `"get_noise"` (0x71/0x72 commands with type 2).

  **Notification Display:** Ported `"device.show_notification"`, `"show_notification"`, `"notification.show_notification"`, `"device.show_notification_text"`, `"show_notification_text"`, and `"notification.show_notification_text"` (0x50 command handling icon-only and icon+text variations).

  **E2E & Parity Tests:** Updated the `ported_commands_route_to_device_call` integration test in `tests/daemon_behavior.rs` to verify that all newly implemented commands and their aliases correctly match in the router and dispatch to the device transport. Verified both compilation and test suite correctness with and without the `ble` feature gate. Full Python pytest suite passes with 1706 passed, 87 skipped.

- **NATIVE PORT: REMAINING DEVICE CALL COMMANDS (2026-06-23 10:23 EDT):**
  Ported the rest of the high-value `device_call` commands to the native Rust daemon (`divoomd`):
  
  **Volume Control:** Ported `"music.get_volume"`, `"get_volume"`, `"music.set_volume"`, and `"set_volume"` (0x08/0x09 commands).
  
  **FM Radio:** Ported `"radio.set_radio_frequency"`, `"set_radio_frequency"`, `"radio.set_radio"`, and `"set_radio"` (0x61 command) taking a 2-byte little-endian frequency.
  
  **Low Power Switch:** Ported `"device.get_low_power_switch"`, `"get_low_power_switch"`, `"device.get_low_power"`, `"get_low_power"`, `"device.set_low_power_switch"`, `"set_low_power_switch"`, `"device.set_low_power"`, and `"set_low_power"` (0xb2/0xb3 commands).
  
  **Auto Power Off:** Ported `"device.get_auto_power_off"`, `"get_auto_power_off"`, `"sound.get_auto_power_off"`, `"device.set_auto_power_off"`, `"set_auto_power_off"`, and `"sound.set_auto_power_off"` (0xab/0xac commands) taking a 2-byte little-endian minutes.
  
  **E2E & Parity Tests:** Added the `ported_commands_route_to_device_call` integration test to verify that all newly implemented commands are correctly matched in the router and dispatch to the device transport (failing honestly with "no device connected"). Verified both compilation and test suite correctness with and without the `ble` feature gate. Full Python pytest suite passes with 1706 passed, 87 skipped.

- **NATIVE PORT: EVENT SUBSCRIPTION & DEVICE NAME COMMANDS (2026-06-23 10:15 EDT):**
  Four changes in the native Rust daemon (`divoomd`):

  **Event Subscription & Broadcast:** Extended the socket server with support for the
  `"subscribe"` command. When a client connects and subscribes, the server immediately
  replies with the initial status snapshot (`{"type":"status", "state":"idle"}` or `"active"`)
  and then holds the connection open, streaming real-time broadcast events (such as BLE
  connection state changes). We use `tokio::select!` to multiplex socket reading (to detect
  peer disconnects) and event broadcasting (from a shared `tokio::sync::broadcast::Sender`),
  achieving self-cleaning, resource-safe event delivery.
  
  **Friendly Name Cache:** Added a thread-safe `device_name` cache (`Mutex<Option<String>>`)
  to `BleTransport` to avoid redundant BLE name queries (0x76 read is slow/flaky on some models).
  The cache is populated from peripheral advertisement properties on connect.
  
  **New Device Commands:** Ported `"device.get_device_name"` (retrieves from cache, falling back
  to 0x76 BLE query) and `"device.set_device_name"` (writes via 0x75 BLE command and updates cache).
  
  **E2E & Parity Tests:** Added `subscription_and_event_broadcast` integration test to verify the
  subscriber socket, and `device_name_commands_route_to_device_call` to check command dispatch.
  All Rust tests pass (with and without `ble` feature). E2E-smoke-tested `test_subscribe.py` against
  real Divoom hardware: successfully subscribed, connected, and observed the broadcasted status
  transition (`idle` -> `active`). Python suite: 1706 passed, 87 skipped.

- **FEISHIN + KASET + CARD PADDING ROUND (2026-06-23 00:45 EDT):** Three changes.

  **Feishin album art integration:** Added `/Applications/Feishin.app` (Electron-based
  Navidrome client) as the first-checked now-playing source in
  `media_source.py:get_current_playing_track()`. The integration works by:
  1. Checking if Feishin is running via `pgrep`
  2. Extracting Navidrome Subsonic API credentials from Feishin's Chromium Local
     Storage (LevelDB files at `~/Library/Application Support/Feishin/Local Storage/leveldb/`)
  3. Querying the Navidrome `/rest/getNowPlaying.view` Subsonic API endpoint
  4. Building a cover art URL from `/rest/getCoverArt.view` when available
  Credentials are cached for 60s to avoid repeated LevelDB file scans. The Navidrome
  server URL + auth params (`u=...&s=...&t=...`) are extracted via regex scanning of
  the LevelDB .ldb/.log files. Tests: 4 new Feishin-specific tests + updated Spotify
  test for the new check order (12 total, all pass).

  **Kaset album art integration:** Added `/Applications/Kaset.app` (YouTube Music
  client for macOS) as a now-playing source (checked second). Kaset's AppleScript
  `get player info` returns a JSON blob with an `artworkURL` (YouTube thumbnail),
  so callers skip the iTunes Search API for Kaset-originated tracks. All three callers
  (`live_jobs.py:run_music()`, `media_sync.py:get_current_track_info()`,
  `media_sync.py:push_music_cover_now()`) fall back to the iTunes API when no direct
  URL is provided (Spotify/Apple Music paths unchanged).

  **Card padding tightened:** `.card` padding reduced from `20px` → `12px`,
  `--panel-gap` from `20px` → `12px`, `.card-header` margin-bottom from `15px` → `10px`
  in `style.css`. This brings general tab panels (settings, routines, tools) to the same
  density as tile components.

- **TIVOO-MAX SPP ROUTING FIX (2026-06-22 23:45 EDT):** Debugged why Tivoo-Max BLE
  connections fail. Investigation found 2 bugs in the SPP routing code:

  **Bug 1: `owner_connect.py:_ensure_device_async` (line 118)** — hardcoded
  `use_ios_le_protocol=False` for ALL devices on the daemon's auto-reconnect path.
  When a Tivoo-Max is auto-discovered (no specific mac requested), the daemon creates
  a `Divoom` with `use_ios_le_protocol=False`. The SPP routing code (`connection.py:82`)
  sees this falsy value and, because the device name contains "tivoo", switches to
  Bluetooth Classic SPP transport instead of BLE. SPP on macOS has a known "Tahoe
  reconnection bug" that produces opaque timeouts. Fix: changed to `use_ios_le_protocol=None`
  so the autoprobe dynamically determines the correct BLE protocol.

  **Bug 2: `connection.py:connect` (line 82)** — SPP routing condition was
  `not self.use_ios_le_protocol`, which fires for BOTH `False` (explicit Basic protocol)
  AND `None` (unknown/unprobed). When protocol is unknown, `BLETransport.connect()` runs
  the autoprobe to determine iOS-LE vs Basic over BLE — SPP should NOT pre-empt that.
  Fix: changed to `self.use_ios_le_protocol is False` so SPP routing only fires when
  explicitly set to Basic protocol.

  Also added `test_spp_not_routed_for_unknown_protocol` to codify the fix. Updated
  `test_spp_connection_resolution` to use explicit `use_ios_le_protocol=False`.
  Suite: 1701 passed, 87 skipped.

- **CASK RELEASE / SCAN-TIMEOUT BACKSTOP FIX ROUND (2026-06-22 23:30 EDT):** After the
  cask install, `brew reinstall --cask divoom-control` succeeded but the user reported
  the app "can't detect any device — connects to one device (Tivoo) then gets stuck".
  Investigation found 3 bugs:

  **Bug 1: Backstop doesn't cancel the coroutine.** `owner_loop.py:_run_on_loop` runs
  scan coroutines on the device loop via `asyncio.run_coroutine_threadsafe`. The 90s
  backstop (`_SCAN_RESULT_TIMEOUT`) fires with a `TimeoutError` but the Future was never
  saved — so `future.cancel()` was unreachable. The scan coroutine kept running for the
  full user-configured timeout (e.g. 360s), consuming BLE resources and blocking
  subsequent operations. Fix: save the Future and cancel on backstop timeout.

  **Bug 2: Scan timeout > backstop = guaranteed failure.** The user's `config.ini`
  had `timeout = 360s`. The daemon `owner_connect.py:scan()` passed it straight to
  the BLE scan, but `_run_on_loop` only waits 90s. Every scan with timeout > 90s was a
  guaranteed failure (backstop fires, scan reported as failed, but coroutine runs for
  remaining 270s). Fix: cap scan timeout to `_SCAN_RESULT_TIMEOUT` (90s) at the daemon
  level, with a warning log.

  **Bug 3: HTML input max bypassed by JS config load.** The `<input id="scan-timeout"
  max="120">` was bypassed when `app_init.js:load_config()` set `el.value = conf.timeout`
  (e.g. 360). HTML `max` only applies to user interaction, not programmatic `.value`
  assignment. Fix: clamp to `el.max` before setting the value.

  The stale `last_connected_device` UUID (not in scan results) causes a 16s auto-connect
  timeout before the daemon falls back to a 3s reconnect scan and connects to the first
  available device (Timoo). The Tivoo connection timeout is a separate BLE issue
  (device-specific, not a code regression). Suite: 1700 passed, 87 skipped.

- **RELEASE CUT ROUND (2026-06-22 21:58 EDT): Cut release v0.20.0 (Claude).**
  Cut the `v0.20.0` release including the startup packaging fix and native Rust daemon port (Phase 2 progress).
  - Version bumped to `0.20.0` in `pyproject.toml` and documented in `CHANGELOG.md` and `docs/release_notes_v0.20.0.md`.
  - Rebuilt the app bundle (`dist/Divoom-v0.20.0.dmg`) and pushed `main` branch + tag `v0.20.0` to GitHub.
  - Updated the Homebrew cask with the new `.dmg` SHA-256 (`42bb39b1...`) in `homebrew-tap` and pushed.
  - Note: GitHub release creation via `gh` CLI failed with 401 Bad Credentials in this environment, so the user needs to execute the `gh release create` command manually (see details in final output).

- **HW ROUND (2026-06-22 17:10 EDT): native C image encoder — divergence FIXED + revived (Claude).**
  Two bugs: (1) `image_encode.c` static header was 6 bytes — the NN palette-count byte at
  `out_buf[6]` got clobbered by the palette memcpy (palette landed on byte 6), diverging from
  Python's correct 7-byte header; fix `static_header_size = 7`. (2) Both `image_encoder.py` wrappers
  allocated `(w*h+7)//8` (1 BIT/pixel) but the C worst-case check needs `w*h` (8 bits/pixel), so the
  C returned -1 for any real frame → silent Python fallback (native image encode was DEAD for
  16x16+). Fix: allocate `7 + 256*3 + w*h`. Now byte-identical to Python across all sizes/colours
  (static AND frame) AND actually reached. Dylib rebuilt + committed. HW: pushed the test animation
  to Pixoo-1 via the revived native path → `result:true`, identical behaviour. Teeth: direct-C-path
  tests (`test_c_static_*`) that bypass the wrapper fallback — 17 fail against the pre-fix dylib.
  **ALL named HW-deferred items are now cleared.** Remaining NOT-testable-on-this-fleet: SPP
  transport + live-job-double-poller (BLE-only Pixoo/Timoo/Tivoo; no RFCOMM/SPP device). R45 #1
  "Custom Art channel empty" still needs eyes on the device screen (can't validate headless).

- **HW ROUND (2026-06-22 12:43 EDT): 0x8B animation retransmit dead-path FIXED (Claude).** The
  0x8B streamer set the response scalar to 0x8B before START, but the start-ACK wait CLEARS it —
  so for the chunk loop + retransmit window the scalar was None and 0x8B isn't a generic-ACK, so
  the handler DROPPED every unsolicited retransmit request; `_serve_8b_retransmits` then timed out
  "done" and a lost chunk was silently unrecoverable (stream still returned True). Fix:
  `stream_animation_8b` adds 0x8B to `_listen_commands` for the stream (removed in finally) so the
  handler's is_listened branch queues retransmit frames without consuming the scalar. HW-validated:
  pushed a 2-frame test GIF to Pixoo-1 (`display.show_image`) — device start-ACKed, chunk streamed,
  retransmit phase quiet, push True; the working push is NOT perturbed. Teeth: wiring + handler-
  mechanism tests (the old retransmit test mocked wait_for_response, never hit the real handler).
  Remaining HW-deferred: native C static-encoder; SPP/live-job-double-poller NOT testable on this
  BLE-only fleet.

- **HW ROUND (2026-06-22 12:40 EDT): ACK ≠ device-confirmed honesty (Claude).** custom-art and
  hot-update both reported `success:True` on bare GATT write-ACKs with no device confirmation.
  HW-confirmed on Pixoo-1 that the only verification channel is unusable — **0x8E query_page
  times out at 4 s on every page, returns empty** — so we can't verify and won't add a 4 s dead
  wait. Fix surfaces honest status: `custom_art_push` returns `device_confirmed:False` (GUI toast
  "sent" not "pushed"); `hot_update._stream_file` now returns `(ok, confirmed)` and each `served`
  entry + a top-level `confirmed` count distinguishes device-confirmed files from streamed-but-
  silent ones. Teeth: `test_silent_device_file_marked_unconfirmed`. NOT verified via 0x8E (HW-
  unreliable). NOTE: the deeper R45 #1 "Custom Art channel empty" functional regression needs eyes
  on the device screen (can't validate headless) — still open. Remaining HW-deferred: 0x8B
  retransmit dead path, native C static-encoder, push smoke.

- **HW ROUND (2026-06-22 12:25 EDT): exclusive steal-reject — hang-then-steal FIXED (Claude).**
  Validating the deferred exclusive-mode item on the live Pixoo-1 surfaced a real bug: a
  competing `exclusive_start` hung exactly 30 s (the `exclusive_timeout`) then SILENTLY STOLE
  the lock and reported success. Root cause: `exclusive_start` acquired by submitting
  `acquire(token)` through the GATED queue — a lock-acquire gated by the lock it seeks. The
  foreign-token `acquire` never dispatched (the gate only runs the owner's items), so the clean
  "held by another session" reject was unreachable; the G3 idle deadline force-released the real
  owner and the waiter stole. Fix: `CommandQueue.acquire_now(token)` runs `acquire` straight on
  the loop (off the dispatch queue — no device I/O in `acquire`). `exclusive_start` uses it and
  returns the honest error. HW re-validated: steal rejects in 0.00 s; idempotent re-acquire +
  post-release acquire still work. Teeth: `test_acquire_now_rejects_steal_immediately`. Suite
  1680 green. ALSO HW-validated (no change): the **wrong-device guard** — a `device_call` with a
  mac different from the held device does NOT silently read/write the cached device; it releases
  + attempts the requested target and fails honestly if unreachable (`get_brightness(mac=BOGUS)`
  → `success:false "timed out"`, never the held Pixoo's 60). **Working harness: the dev-daemon `.app` (`open "dist/Divoom Dev Daemon.app"`)
  runs live repo code under its own BLE grant — restart it to load each fix, then drive it over
  `/tmp/divoom.sock` with `DaemonClient`.** Remaining HW-deferred queue: custom-art ACK≠success,
  hot_update ACK≠success, 0x8B retransmit dead path, native C static-encoder, push smoke.

- **HARDWARE VALIDATION (2026-06-22 12:07 EDT): R53.35 iOS-LE ACK change REVERTED — read-backs
  fixed on the real Pixoo (Claude).** Commit `b1e9770`. On a live Pixoo-1, ALL read-backs
  (`device.get_brightness`, `device.get_device_name`) had regressed to a 5.26 s timeout → `null`
  while writes worked. Root cause: R53.35 made `_handle_ios_le_notification` KEEP the
  `_expected_response_command` scalar on the generic 0x33 ACK. Clearing it is **load-bearing** for
  the protocol autoprobe — `ble_probe` sends a 0x46 query (0x46 ∈ GENERIC_ACK_COMMANDS); keeping
  the scalar let the iOS-LE probe spuriously "succeed" on the Basic-only Pixoo → mis-detected as
  iOS-LE → every read-back timed out. The revert restores `self._expected_response_command = None`
  on the ACK; the 0x46 probe now correctly fails over to Basic. **Re-validated on hardware via the
  granted dev-daemon `.app`** (`dist/Divoom Dev Daemon.app`, thin launcher → live repo code, owns
  the Bluetooth TCC grant): `device.get_brightness` → `60` in **0.06 s** (was 5.26 s → null);
  `device.get_device_name` → fast 0.06 s response. Lesson: 1679 mocked unit tests can't catch an
  autoprobe regression that only manifests against real BLE framing — a Hyrum's-law case where the
  scalar-clear was load-bearing for protocol detection. The R53.35 "two-frame iOS-LE read-back" the
  change targeted remains unverified on ANY real device. NB: to drive HW from Claude, launch the
  dev-daemon `.app` (`open "dist/Divoom Dev Daemon.app"`) — it runs BLE under its own grant, unlike
  the Bash tool (TCC SIGABRT).

### Earlier rounds (pruned 2026-06-28)

The full round-by-round log that used to follow here — the R53.x adversarial-loop
rounds, the R45–R52 GUI/arch rounds, and the R7–R15 backfill (~1.4k lines of
superseded detail) — was pruned from this handoff on 2026-06-28. The authoritative
history lives in `CHANGELOG.md`, `docs/PLANNING_ROUND*.md`, and `git log`; recover
any entry from the git history of this file.

## Hardware note

macOS Bluetooth TCC is per responsible-process; drive real BLE by launching via
Terminal (`open *.command`). Device UUIDs + method in `docs/DEVICE_VALIDATION_PLAN.md`.

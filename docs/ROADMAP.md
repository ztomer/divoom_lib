# Roadmap — divoom-control

Consolidated view of shipped rounds, current state, and future work.
See `docs/PLANNING_ROUND*.md` for detailed scope per round.

---

## Shipped

| Round | Summary | Suite | Key files |
|-------|---------|-------|-----------|
| **R3** | BLE connection scaffolding + first commands | — | `divoom_lib/connection.py`, `divoom_lib/divoom.py` |
| **R4** | Extended command set (0xBD system cmds) + models | — | `divoom_lib/models.py`, `divoom_lib/display/` |
| **R5** | Image rendering pipeline + GIF animation | — | `divoom_lib/renderer/`, `divoom_lib/encoder/` |
| **R7** | Digital clock command + time sync + BLE stability | — | `divoom_lib/display/clock.py` |
| **R8** | Layout framework + PyWebView GUI + sidebar | — | `divoom_gui/` (greenfield) |
| **R9** | Screen orientation, system brightness, factory reset | — | `divoom_lib/display/design.py`, `divoom_lib/device.py` |
| **R10** | Notification mirroring (macOS → device) | — | `divoom_lib/notification.py` |
| **R11** | Weather + scoreboard + noise meter + stopwatch | — | `divoom_lib/tools/` |
| **R12** | GUI polish: glass tabs, appbar, hardware verification plan | — | `divoom_gui/web_ui/` |
| **R13** | Calendar + memorial countdown + time-plan | — | `divoom_lib/tools/calendar.py` |
| **R14** | Hot-channel scheduling + notification preferences | — | `divoom_lib/hotchannel.py` |
| **R15** | MCP server (stdio JSON-RPC, tools/list + tools/call) | — | `divoom_lib/mcp_server.py` |
| **R16** | Daemon HTTP JSON-API + menubar app | — | `divoom_daemon/daemon.py`, `divoom_gui/menubar/` |
| **R17** | Daemon single-owner (R17 P5) — daemon owns BLE, GUI is client | — | `divoom_daemon/device_owner.py`, `divoom_gui/daemon_bridge.py` |
| **R19** | Timer/countdown/noise controls + cloud-connection monitor | — | `divoom_lib/tools/timer.py` |
| **R20** | `tmp`→`divoom_lib` migration + C downsampler | — | `divoom_lib/encoder/downsample.c` |
| **R23** | 500-LOC debt retired (all files <500 lines) | 994/0/75 | (many splits) |
| — | GUI crash-loop on cloud-auth failure fixed | 994/0/75 | `divoom_auth` caching |
| **R24** | connect-timeout fix, toast removal, glass tab strip | — | `divoom_daemon/device_owner.py` |
| **R26** | Daemon channel-switch API + weather push fix | 1025/75/0 | `set_temperature_channel()`, `push_weather()` |
| **R27** | Command queue (ring buffer, maxsize, item timeout) | 1055/75/0 | `divoom_daemon/command_queue.py` |
| **R28** | MCP-via-daemon, scan filter, tab layout, bitmap font | 1079/75/0 | `daemon_client.py`, `fonts/`, `tabs.css` |
| **R29** | Exclusive mode wired through daemon RPC | 1085/75/0 | `device_call(token)`, `DaemonDeviceProxy.exclusive()` |
| **R30** | Animation streaming — MCP tool + proxy exclusive context | **1090/75/0** | `push_animation()`, MCP 13th tool |
| **R31** | Font improvement + CJK infrastructure + warning fixes | **1093/75/0** | majority-rule half-font, CJK `from_apk_asset()`, coroutine cleanup |
| **R32** | Monthly Best reorg + Routines + device selector + Text fix | **1094/75/0** | gallery multi-select, per-device gallery style, 0x87→image text push |
| **R33** | Sidebar reorg + Settings polish + per-device gallery style | **1094/75/0** | Routines nav, device dots, toggle-switch settings, appbar gear |
| **R34** | Hot-channel sync fix + Routines polish + APK-aligned 0x8b upload | **1185/75/0** | `sync_read_timeout`, device-dot pulse, alarms week-table, device-driven 0x8b flow |
| **R54** | Notifications, schemas, TCP/token auth & Rust auto-spawn | **1185/75/0** | `macos_notifications.rs`, `socket_server.rs`, `daemon_client.py` |
| **R55** | Bluetooth Classic SPP subprocess bridge integration | **1185/75/0** | `spp_bridge.py`, `spp.rs`, `transport.rs`, `daemon_connect.rs` |
| **R56** | Cloud Auth, Category Gallery API & Monthly Best Loop | **1703/87/0** | `cloud.rs`, `monthly_best.rs`, `daemon.rs`, `basic.rs` |
| **R57** | Daemon connect-robustness (dead CoreBluetooth wedge) + bulletproof tests | — | `scanner_mixin.py`, `daemon_connect.rs` |
| **R58+R59** | `divoomd` rename + daemon hardening + **event-driven UI** (broadcast/subscribe: `status`/`owned_devices`/`notif_status`/`hot_progress`/`degraded`) | — | `socket_server.rs`, `daemon_connect.rs`, `connection_events.js` |
| **R60** | Open-thread verification: docstring strip, durable `device_call` parity test (caught + closed 15 key-alias gaps), `show_clock()` realigned to APK `C2()` canonical, `get_*` read-back timeouts bounded+cached, Python daemon marked REFERENCE/FALLBACK, Ditoo soak, cloud-decode push (3/4 devices) | — | `tests/test_device_call_parity.py`, `display/__init__.py`, `divoom_daemon/*` |
| **R61** | Release v0.22.9 + doc prune + **Cloud HTTP** (`UserNewGuest` RC=10 fix + clock-face store) + coverage gate (≥95%, hit 96%) + hardware-verified device detect/connect | — | `divoom_auth.py`, `cloud.py`, `cloud_cmds.rs` |
| **R61 follow-up** | Release v0.22.10 — real daemon+UI e2e connect/disconnect verification (mock-transport drop simulation, `tests/e2e_gui_bridge.py`) + **native menubar now shows device connect/disconnect/degraded** (previously only reflected the notification monitor) + device-loop thread-teardown hardening | 3197/97/0 | `divoomd/src/daemon_mock.rs`, `native-port/divoom-menubar/src/state.rs`, `tests/test_e2e_gui_daemon_connect_disconnect.py` |

Suite: Rust 63+ passed / Python 3197 passed / 97 skipped (see `CHANGELOG.md` + CI).

---

## Current debt & quality

- **500-LOC rule**: fully enforced, ALLOWLIST empty (R23).
- **Font**: APK bitmap font extracted (ASCII + CJK via `from_apk_asset()`), half-size variant with majority-rule downsampling.
- **Tests**: hardware tests gated/skip by default; 60 native-downscaler parity tests; alarms editor JS guard; 18 E2E mock-device.
- **C module**: `libdivoom` (LANCZOS downsampler) compiled via `build_libdivoom.sh`; normalize-then-quantize kernel matches PIL byte-for-byte (60/60 parity tests).

---

## Open workstreams

### Near-term (next round)

Native-port hardening (Phases 1-4 + Phase-5 command parity) shipped; see
`docs/archive/superseded/PLANNING_NATIVE_PORT_HARDENING.md` for the historical
record. Phase 5 step 5.3 (the irreversible `divoom_daemon/` server archival)
shipped 2026-07-13 on explicit user sign-off — see the "Native Rust daemon"
section below for detail. No remaining thread here.

### Short-to-medium term

| Workstream | Depends on | Notes |
|-----------|-----------|-------|
| **`show_clock()` overlay reorder** | — | **DONE (R60)** — realigned to APK `C2()` canonical `[0x00, t, style, 0x01, humidity, weather, date, R,G,B]`; wire-byte test added. |
| **`get_*` read-back timeouts** | — | **DONE (R60)** — bounded + cached in both Python (`ble_reads.read_with_retry` 2.5s + last-good cache) and Rust (every `get_*` uses `ctx.timeout`; daemon wraps call in `tokio::time::timeout` 30s clamped [1,120]). |
| **R12 visual pass** | user-driven | Glass tab strip, appbar corners, etc. |
| **R12 hardware verification** | user-driven | Album cover, custom-art/live/weather on real device. |
| **Menubar connection-feedback: live-hardware confirmation** | — | **DONE (2026-07-13, real hardware).** Launched the packaged v0.22.10 app (`dist/Divoom.app`), confirmed a real device (Pixoo-1) auto-connected, then verified the menubar icon via `screencapture` (computer-use MCP was disconnected — native CLI fallback): connected → green, `disconnect` command → orange (idle) within one poll cycle, reconnected → green again. Full round-trip confirmed on real hardware, not just the mock-transport test suite. |
| **Daemon-down banner / reconnect regression check** | — | **DONE (2026-07-13, real hardware).** With the packaged app running and a real device connected: `kill -9` the daemon → auto-reconnect self-healed in ~1s (GUI correctly updated to reflect the dropped device). Re-ran with the daemon binary renamed away (forcing respawn to fail) → the "Background service isn't running" banner correctly appeared; restored the binary and clicked the banner's Reconnect button → banner cleared, daemon respawned and confirmed responsive. Both the auto-heal and manual-reconnect paths verified working. |
| **Inline-style → CSS-token migration, batches 3-5** | — | **DONE (2026-07-13).** `templates_routines.js` (10 of 21 migrated/removed, 11 left inline per the plan's one-off-sizing/display:none exceptions), `templates_widgets.js` (31 of 51), `templates_settings.js` (15 of 39, plus 8 more deleted as redundant with the global reset) — the remainder in each file is deliberately-inline one-off/unique styling, not unmigrated debt. 8 new utility classes added to `style_extra.css` (`.mb-12/.mb-18/.mt-6/.clip-shrink/.label-caption/.text-12/.grid-layout.single-col`, plus reuse of existing ones). Verified via `getComputedStyle()` diffing (Playwright, real `index.html`) against the pre-migration box model for every migrated element — zero divergences — plus the full `test_e2e_*` GUI suite (50 tests) green. |

### Divoom Cloud HTTP (200+ endpoints)

**Status: UNBLOCKED (2026-07-13) — user provided the decompiled APK source**
at `references/apk/decompiled_src/` (`com/divoom/Divoom/http/HttpCommand.java`
is the master list of all ~230 server command name constants; request/response
field shapes live under `http/request/` and `http/response/`). This resolves
the prior "next step needs the user" ask.

**Concrete fix landed this round: the clock-face store was calling the wrong
endpoint entirely.** `list_clock_faces()`/`CLOCK_FACE_CLASSIFY` previously
called `GetCategoryFileListV2` with an assumed `Classify` value — confirmed
via source to be the PIXEL-ART/monthly-best gallery endpoint (its only real
callers are `CloudGalleriaFragment`/`CloudVerify*`/`FillGameModel`, none
clock-related). The actual clock-face store is a dedicated two-call flow —
`Channel/StoreClockGetClassify` (category list) then `Channel/StoreClockGetList`
(clocks for one category id) — confirmed against
`WifiChannelModel.java`'s `R()` method and the
`MyClockStoreClockGet{Classify,List}{Request,Response}.java` field classes.
Implemented in both `divoom_lib/cloud.py` (`get_clock_classify_list`/
`get_clock_list`/`list_clock_faces`) and `divoomd/src/cloud_category.rs`
(+ wired into `cloud_cmds.rs`/`daemon.rs` dispatch), with mocked-shape tests.
**Still open**: a live round-trip against `Channel/StoreClockGetClassify`
returns `RC=12` (`HTTP_REQUEST_EMPTY`) — reproduced with both a real logged-in
account and guest auth (not a token problem; `GetCategoryFileListV2`/
`Weather/SearchCity` both succeed with the same credentials in the same
session), and `BaseParams._postSync` — the method that builds the actual
generic POST — is a JADX "Method not decompiled" stub, so the exact wire gap
can't be confirmed from source. The code is correct per the app's own
request/response *classes*; end-to-end proof against the real server is
unresolved (see the comment at `divoom_lib/cloud.py`'s clock-store section for
the full writeup). Not wired to any GUI action either way (neither was the
old, wrong version) — no user-visible regression risk either direction.

**The other ~225 endpoints**: still not implemented — the APK source removes
the "we don't know the shapes" blocker, but implementing them blind, without a
GUI hook or defined purpose, still isn't a good use of unattended effort (per
the prior assessment). **Ask still open**: name which endpoints matter for a
real feature (the `HttpCommand.java` catalog covers alarms, forum/social,
messaging, playlists, sleep-aid sync, pomodoro/Tomato timers, calendar
integrations, and more) and they can be implemented against real request
shapes now, or point at a specific feature gap to close.

**Shipped (R61 + follow-up):**
1. ~~Cloud auth broken (`RC=10`)~~ — fixed R61.
2. `get_category_file_list`, `search_weather_city` — shipped, Python+Rust parity, tested.
3. `get_clock_classify_list`/`get_clock_list`/`list_clock_faces` — corrected to the real clock-face-store endpoints (2026-07-13); live end-to-end unresolved (RC=12, see above).
4. New transport: `divoom_lib/cloud.py` module (library was BLE-only + device LAN) — shipped.

### Deferred (R12 §D)

See `docs/archive/rounds/PLANNING_ROUND12_D_AUDIT.md` for the full audit:
- `pic_scan_ctrl` 0x35 claim — **partially resolved (2026-07-13, real hardware).**
  Hardware-tested on a real Pixoo-1: both `control=0` (mode/speed) and
  `control=1` (image-data) GATT writes for 0x35 ACK cleanly — no rejection,
  error, or disconnect, device stays responsive after. This is transport-level
  confirmation only (ACK != device-confirmed semantic handling — a firmware
  can silently ACK-and-drop an unrecognized opcode); no visual on-device
  effect was confirmed (no camera on the physical device). Upgraded from
  "wholly untested" to "accepted without error by the device's BLE stack,"
  not fully verified as functionally correct. See the comment at
  `divoom_lib/display/drawing.py::pic_scan_ctrl` / `divoomd/src/device_call/
  drawing.rs` for the full writeup.
- Cloud HTTP surface (above, now active in R61).

---

## Native Rust daemon (`divoomd/`)

**Goal: ACHIEVED.** The Python daemon backend was deprecated in favor of the
compiled Rust daemon (100% socket + hardware parity reached 2026-06-29) and
archived 2026-07-13 — see "Archived" below.

**Decision: Rust** (over C / C++ / Zig). `btleplug` is the one mature
cross-platform BLE API (the bleak analog); `tokio` maps the asyncio-heavy daemon
1:1; compile-time memory/thread safety suits a 24/7 hardware-owning binary frame
parser; `serde` covers the NDJSON socket protocol. Footprint and single-device
perf were a wash across all four candidates — cross-platform BLE + async broke the
tie. The full language evaluation + phased plan lived in
`docs/PLANNING_NATIVE_PORT.md`, removed 2026-06-28 once the port shipped; recover
from git history if needed.

**Architecture:** daemon-only port behind the unix-socket NDJSON seam — the Python
GUI / menubar / CLI are unchanged clients, the Python daemon stays ground truth
until parity, and the C encoders (`libdivoom`) are reused via FFI.

**Status (2026-06-28): functionally complete + hardware-verified.** Shipped R54–R56
— full `device_call.*` surface, cloud auth, gallery sync, monthly-best loop, macOS
notifications, wall, live jobs, art/hot-update, SPP bridge, TCP+token auth, Python
auto-spawn (`DIVOOM_USE_RUST_DAEMON`). Hardening Phases 1–4 done: hardware-free core
build restored + CI-gated (both feature matrices), 500-LOC compliance gated, E2E
verified hardware-free (CI) and on a **real Timoo over BLE** (connect/brightness/
exclusive/MCP/disconnect). `cargo test` 63/63 both matrices.

**Parity (2026-06-29): COMPLETE.** Full `device_call` method parity (54 → 0 gaps vs
the Python Divoom API) + full cloud image-decode parity (magic 9/18/26 AES/LZO +
0xAA → GIF, byte-verified vs the Python oracle, rendered on Pixoo/Tivoo-Max/Timoo).
The Rust daemon became the **default** (`DIVOOM_USE_RUST_DAEMON` on when `divoomd`
is present); the Python backend was **kept as the reference/fallback implementation**
at the time (per user directive then in force) until the archival below
superseded that directive. Niche subsystems (drawing-pad, SD-music, animation
gif-chunk primitives) are wire-tested but not hardware-verified.

**Remaining (optional): DONE (2026-07-13, real hardware).** Ditoo-light-2 was back
in range — connected, fetched a real cloud gallery file (`fetch_gallery`
classify=18), pushed it via `sync_artwork` (`success:true`), and a post-push
`get_brightness` read-back matched the pre-push value — no device-stick,
matching the same pattern already confirmed on Pixoo/Timoo. Niche subsystems
hardware-exercised: `music.app_need_get_music_list` (SD music query) and
`drawing.drawing_mul_pad_enter`/`drawing_pad_exit` (drawing-pad round-trip)
both ACK cleanly; `animation.app_get_user_define_info` (0x8e read-back)
timed out with no reply on this Ditoo — inconclusive (unsupported vs. no
saved slot to report) but confirmed non-destructive: no crash/wedge, device
stayed responsive to further calls. Findings documented inline at each
call site.

### Archived: Python daemon server (2026-07-13, explicit user sign-off)

`divoomd` (Rust) is now the **sole shipping daemon** — no fallback, no
`DIVOOM_USE_RUST_DAEMON` opt-out. The Python daemon *server* implementation was
moved (not deleted — `git mv`, full history preserved) from `divoom_daemon/` to
`archive/divoom_daemon/`:

- **Moved:** `daemon.py`, `device_owner.py`, `socket_server.py`,
  `command_queue.py`, `notification_service.py`, `live_jobs.py`, and the
  `owner_*.py` handler modules (art/connect/live/loop/notify/wall/util) — 13
  files, internal cross-imports rewritten to `archive.divoom_daemon.*`.
- **Stayed active** in `divoom_daemon/` (client-side infra every consumer
  still needs, regardless of which daemon implementation is running):
  `daemon_client.py` (spawn/find/`ensure_daemon()`), `daemon_protocol.py` (the
  NDJSON wire client), `daemon_config.py`, `spp_bridge.py`,
  `macos_notifications.py`/`notification_router.py` (GUI Settings still calls
  these directly). `divoom_daemon/__init__.py` now documents the
  client-library-only role.
- **`daemon_client.spawn_daemon()`** no longer has a `-m divoom_lib.cli daemon`
  Python-fallback branch — it raises a clear `RuntimeError` if no `divoomd`
  binary resolves, instead of emitting a command that no longer works.
- **`divoom-control daemon`** (the CLI subcommand, `cli_commands.cmd_daemon()`)
  now prints a pointer at `divoomd` and returns 1, rather than importing the
  archived server module.
- **Tests:** 47 test files that exercised only the archived server code moved
  to `archive/tests/` (excluded from `pytest`'s `testpaths = ["tests"]`, so no
  longer run by default/CI — same treatment as the source); 6 of those were
  *split* file-by-file where some tests needed the archived server
  (`DivoomDaemon`/`DeviceOwner`/`SocketServer` fixtures) and others tested
  still-active client code (`spawn_daemon`, `bundle_python`, TCC-disclaim,
  `DaemonDeviceProxy`'s status cache) — the client-side tests stayed in
  `tests/`. `archive/tests/conftest.py` is a copy of `tests/conftest.py` so the
  archived suite is still independently runnable/collectible on request.
- **Verified:** full `tests/` suite green post-move (2731 passed, 97 skipped);
  `archive/tests/` collects cleanly (469 tests, zero collection errors, not run
  by default); `check_no_emoji.py`/`check_file_size.py` gates clean (the one
  file-size violation, `divoomd/src/macos_notifications.rs`, predates this
  change and is untouched by it).
- **Docs updated:** `README.md` (package description, requirements, "Run the
  daemon" instructions now point at `divoomd` directly, project layout).

### Native menubar (done) + UI decision (2026-06-30)

**Final architecture:** the desktop **UI stays the Python pywebview GUI**; the
**daemon is Rust** (`divoomd`); the **menubar is a standalone Rust agent**
(`native-port/divoom-menubar/`) that replaces the pyobjc menubar. The Python `.app`
bundles both Rust binaries. The native-egui-UI effort below (and its full
Python-free goal) was **explored and then retired** — `native-port/divoom-ui/` is
deleted. The text below is historical.

### (Historical) Next: native UI + menubar (planned) — `docs/PLANNING_NATIVE_UI.md`

With the daemon ported, the last Python surfaces are the **pywebview GUI** and
**pyobjc menubar**. Plan: replace both with a single native Rust binary
(`native-port/divoom-ui/`) so the shipped bundle is Python-free. **Decision:
Rust-hosted webview** (`wry`/`tao`/`tray-icon`/`muda`, à la carte — no Node)
keeping the existing 9,172-LOC static `web_ui/` frontend **verbatim** and
reimplementing the ~70-method `gui_api` bridge in Rust (mostly thin daemon-
forwarders; UI stays a socket client of `divoomd`). 6 phases, gated on a Phase-0
`window.pywebview.api`-shim spike. The Python UI is archived in-tree, never
deleted. Independent of the parked v0.21.0 release (daemon BT grant).

---

## Planning docs by round

Historical round plans (R3–R61) are archived under `docs/archive/rounds/`, and
fully-shipped/superseded workstream plans under `docs/archive/superseded/`
(recover either from git history if needed). No active planning doc at repo
root right now — the open items above are small/independent enough not to
need one; start a new `PLANNING_ROUND62.md` when the next round's scope
needs its own plan.

Archived in R61 (#0, all fully shipped or superseded — see each file's own
status header for detail): `PLANNING_ROUND57.md`/`58`/`59`/`60`,
`PLANNING_BLE_HARDENING.md`, `PLANNING_SOCKET_HARDENING.md`,
`PLANNING_daemon_ownership.md`, `PLANNING_NATIVE_PORT_HARDENING.md`,
`PLANNING_NEXT_PHASE.md`, `PLANNING_inline_styles.md` (batches 3-5 tracked above
instead), `ARCH_GAP_SCAN_2026-06.md`, `PARITY_TRACKER_NATIVE_UI.md`.
Archived after R61 shipped (v0.22.9) and its e2e-verification follow-up
shipped (v0.22.10): `PLANNING_ROUND61.md`.




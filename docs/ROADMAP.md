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
| **R12 visual pass** | — | **DONE (2026-07-14).** User: "use gemini." Captured real screenshots (dashboard, appbar close-up, tab-strip close-up) and sent them to Gemini Pro (`gemini-bridge` skill, Chrome transport) for a Rams/Kare critique. Verified each finding against the actual source before applying — 3 of 5 were false positives from the test-harness screenshot (headless-Chromium font fallback rendered `{}%`/`{}/15` icon glyphs as literal braces; the appbar already had `align-items:center`; inactive-tab contrast was already borderline-passing WCAG AA). 2 were real, verified, and fixed: (1) the tab strip's active state used a solid saturated `--primary` fill + white text, a different "selected" visual language than the sidebar's own established translucent-tint pattern (`.nav-btn.active` — `rgba(255,90,31,0.12)` bg + primary text + tinted border) — unified `tabs.css`'s `.tab-btn.active` to match; (2) the sidebar's device chips (`.device-chips`) had their text starting 2px off from the nav-item text's left edge (12px sidebar + 12px nav-btn padding = 24px vs. 12px + 2px + 8px = 22px) — bumped `.device-chips` padding 2px→4px to land both at the same 24px offset. `tests/test_tabs_chrome.py` updated to pin the new contract; full GUI e2e suite green. |
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

**Clock-face store: fixed, working live, and wired into the GUI (2026-07-13).**
`list_clock_faces()`/`CLOCK_FACE_CLASSIFY` originally called
`GetCategoryFileListV2` with an assumed `Classify` value — confirmed via
source to be the PIXEL-ART/monthly-best gallery endpoint (its only real
callers are `CloudGalleriaFragment`/`CloudVerify*`/`FillGameModel`, none
clock-related). A phone-app-internal replacement,
`Channel/StoreClockGetClassify` + `Channel/StoreClockGetList` (per
`WifiChannelModel.java`'s `R()` method), was tried next and abandoned: it
returns `RC=12` (`HTTP_REQUEST_EMPTY`) against the real server for a reason
`BaseParams._postSync` (a JADX "not decompiled" stub) can't confirm from
source — though `OkHttpUtils.postSyncInternal`, which it calls into, IS fully
decompiled and confirms no hidden headers/signing, so the gap is specific to
that endpoint's body/account requirements, not the transport.

The actual fix: `Channel/GetDialType` + `Channel/GetDialList`, Divoom's
**public, unauthenticated developer API** (doc.divoom-gz.com/web/#/12?
page_id=190 — not in `HttpCommand.java`'s phone-app-internal catalog at all;
found via the independent `r12f/divoom` Rust crate on GitHub, which documents
the same official page). **Confirmed live** — real category names and
`ClockId`/`Name` data, no credentials needed. Implemented in
`divoom_lib/cloud.py` (`get_dial_types`/`get_dial_list`/`list_clock_faces`)
and `divoomd/src/cloud_category.rs` (parity, wired into `cloud_cmds.rs`/
`daemon.rs` dispatch) — end-to-end-tested against the real daemon socket, not
just mocked.

**Wired into the GUI**: a new "Cloud Clock Faces" browser in the Clock channel
panel (`divoom_gui/web_ui/cloud_clock_faces.js` + `index.html`, backend
`divoom_gui/clock_faces.py`) — pick a category, browse the list, Apply. No
new device-apply plumbing needed: `display.show_clock(clock=clock_id)`
already routed large ids through `lan.set_clock()`
(`Channel/SetClockSelectId` to the device's own LAN IP) when the device has
WiFi connectivity, so Apply reuses the existing `set_clock()` API verbatim.
4 new Playwright e2e tests (`tests/test_e2e_clock_faces.py`) cover: initial
load without a tab click (the panel is active by default), switching
categories, the existing "connect a device first" guard, and applying with
the correct `ClockId` reaching `set_clock()`.

**The other ~500 `HttpCommand.java` endpoints: fully cataloged (2026-07-14),
still not implemented.** User: "do research, search the web, if not found,
write it down into a separate md file (unknown commands)." Full research
sweep of all 533 command constants — purpose, request/response field shapes
(from decompiled `http/request/**`/`http/response/**` classes), relevance
(`device-control` vs. Divoom's own `account/social`/`internal/moderation`
layer), and source confidence, dispatched as 16 parallel research batches by
domain. Result: **`docs/cloud_api/README.md`** (index + the full catalog) and
**`docs/cloud_api/UNKNOWN_COMMANDS.md`** (commands with zero signal beyond
the bare string — 8 of 502 documented so far, most of the API resolved
cleanly from the decompiled source even with no public docs). Three genuine
new-feature leads surfaced (documented in the catalog's README, not yet
implemented): **AidSleep browse+play** (cloud-hosted sleep-sound library,
same shape as the shipped clock-face browser), **Playlist browse+push**
(`Playlist/SendDevice`, confirmed live in the decompiled app), and
`Cloud/ToDevice` (unconfirmed semantics, no live caller found — needs more
digging before treating as real). Implementing them blind, without a GUI hook
or defined purpose, still isn't a good use of unattended effort. **Ask still
open**: pick one of the three leads, or name a different endpoint/feature to
prioritize, and it can be implemented against real request shapes now.

**Shipped (R61 + follow-up):**
1. ~~Cloud auth broken (`RC=10`)~~ — fixed R61.
2. `get_category_file_list`, `search_weather_city` — shipped, Python+Rust parity, tested.
3. `get_dial_types`/`get_dial_list`/`list_clock_faces` — the real, working, public clock-face endpoints (2026-07-13); confirmed live and wired into the GUI's Clock channel panel.
4. New transport: `divoom_lib/cloud.py` module (library was BLE-only + device LAN) — shipped.
5. `search_weather_city` remains implemented but NOT GUI-wired — the weather widget uses system/OS location, not a Divoom device-weather-city search; wiring it needs a UX decision (what does picking a city actually do?) that wasn't made this round.

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




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
| **R61** | Release v0.22.9 + doc prune + **Cloud HTTP** (`UserNewGuest` RC=10 fix + clock-face store) + coverage gate (≥95%) | — | `divoom_auth.py`, `cloud.py`, `cloud_cmds.rs` |

Suite: Rust 63 passed / Python ~1750 passed / ~140 skipped (see `CHANGELOG.md` + CI).

---

## Current debt & quality

- **500-LOC rule**: fully enforced, ALLOWLIST empty (R23).
- **Font**: APK bitmap font extracted (ASCII + CJK via `from_apk_asset()`), half-size variant with majority-rule downsampling.
- **Tests**: hardware tests gated/skip by default; 60 native-downscaler parity tests; alarms editor JS guard; 18 E2E mock-device.
- **C module**: `libdivoom` (LANCZOS downsampler) compiled via `build_libdivoom.sh`; normalize-then-quantize kernel matches PIL byte-for-byte (60/60 parity tests).

---

## Open workstreams

### Near-term (next round)

Native-port hardening is the active near-term track — see
`docs/PLANNING_NATIVE_PORT_HARDENING.md`. The two hardware-verify items
(MCP-via-Rust, exclusive-mode-via-Rust) moved there as Phase 4.

### Short-to-medium term

| Workstream | Depends on | Notes |
|-----------|-----------|-------|
| **`show_clock()` overlay reorder** | — | **DONE (R60)** — realigned to APK `C2()` canonical `[0x00, t, style, 0x01, humidity, weather, date, R,G,B]`; wire-byte test added. |
| **`get_*` read-back timeouts** | — | **DONE (R60)** — bounded + cached in both Python (`ble_reads.read_with_retry` 2.5s + last-good cache) and Rust (every `get_*` uses `ctx.timeout`; daemon wraps call in `tokio::time::timeout` 30s clamped [1,120]). |
| **R12 visual pass** | user-driven | Glass tab strip, appbar corners, etc. |
| **R12 hardware verification** | user-driven | Album cover, custom-art/live/weather on real device. |
| **Timoo-light-4 re-verify (R60 #2)** | device in range | Timoo was out of BLE range in R60 and R61; re-run cloud-decode `show_image` push + no-stick when reachable. |

### Divoom Cloud HTTP (200+ endpoints)

**Status: IN PROGRESS (R61).** Stand up a thin cloud HTTP client + fix `UserNewGuest`
`RC=10` (auth flow changed — see `divoom_lib/divoom_auth.py` vs decompiled
`LoginServer.java`). First slice: **clock-face store** (browse clock faces from the
cloud) + 1–2 dependent endpoints, with Python + `divoomd` Rust parity and tests.
Remaining 200+ endpoints are follow-on rounds.

**Blockers (R9 §D, R12_D_AUDIT):**
1. ~~Cloud auth broken (`RC=10`)~~ — being addressed in R61.
2. Scope: 200+ endpoints — R61 picks clock-face store + 1–2 others.
3. New transport: `divoom_lib/cloud.py` module (library was BLE-only + device LAN).

### Deferred (R12 §D)

See `docs/archive/superseded/PLANNING_ROUND12_D_AUDIT.md` for the full audit:
- `pic_scan_ctrl` 0x35 claim — lib says it sends 0x35 but the decompiled APK has no such command ID.
- Cloud HTTP surface (above, now active in R61).

---

## Native Rust daemon (`divoomd/`)

**Goal:** deprecate and archive the Python daemon backend in favor of the compiled
Rust daemon, at 100% socket + hardware parity.

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
The Rust daemon is now the **default** (`DIVOOM_USE_RUST_DAEMON` on when `divoomd`
is present); the Python backend is **kept as the reference/fallback implementation,
never deleted** (per user directive). Niche subsystems (drawing-pad, SD-music,
animation gif-chunk primitives) are wire-tested but not hardware-verified.

**Remaining (optional):** re-verify Ditoo when in range; hardware-exercise the niche
subsystems if/when those device flows are available.

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

Historical round plans (R3–R56) are archived under `docs/archive/rounds/` (recover
from git history if needed). Active planning docs at repo root:

- `PLANNING_ROUND57.md`, `PLANNING_ROUND58.md`, `PLANNING_ROUND59.md` — native-port
  hardening + event-driven UI.
- `PLANNING_ROUND60.md` — open-thread verification (DONE).
- `PLANNING_ROUND61.md` — this round (release + doc prune + Cloud HTTP + coverage).
- `PLANNING_NATIVE_PORT_HARDENING.md` — Phase 5 (Python daemon archive, not delete).
- `PLANNING_inline_styles.md`, `PLANNING_daemon_ownership.md` — next-phase UI work
  (from `PLANNING_NEXT_PHASE.md`).
- `PLANNING_BLE_HARDENING.md`, `PLANNING_SOCKET_HARDENING.md` — hardening reference.




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

Suite: Rust 58 passed / Python 1703 passed / 87 skipped.

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
| **`show_clock()` overlay reorder** | — | Align overlay positions with APK C2() layout (current has mismatched humidity/weather/date coords). |
| **`get_*` read-back timeouts** | — | Real hardware read-back commands time out (mitigated: alarms `alarms.json` cache). |
| **R12 visual pass** | user-driven | Glass tab strip, appbar corners, etc. |
| **R12 hardware verification** | user-driven | Album cover, custom-art/live/weather on real device. |

### Divoom Cloud HTTP (200+ endpoints)

**Status: DEFERRED** (R9 §D, R12_D_AUDIT). Would be its own round.

The official Divoom app communicates with `appin.divoom-gz.com` via HTTP/JSON for:
- Clock-face store (browse, download, upload)
- Weather city search
- Pomodoro timer presets
- White-noise tracks
- TTS (text-to-speech)
- Community gallery (browse, upload, like, comment)

**Blockers:**
1. **Cloud auth broken**: `UserNewGuest` returns `RC=10` (the public API may have changed or requires a different flow).
2. **Scope**: 200+ endpoints. A useful round would pick a small set (clock-face store + 1-2 others), not all of them.
3. **New transport**: requires a new `divoom_lib/cloud/` module — the library is currently BLE-only + device LAN.

### Deferred (R12 §D)

See `docs/PLANNING_ROUND12_D_AUDIT.md` for the full audit:
- `pic_scan_ctrl` 0x35 claim — lib says it sends 0x35 but the decompiled APK has no such command ID.
- Cloud HTTP surface (above).

---

## Native Rust Port (`native-port/divoomd`)

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

**Remaining → `docs/PLANNING_NATIVE_PORT_HARDENING.md`** (Phase 5, gated): close the
last command-parity gaps (`probe_lan`, `sync_artwork`; `shutdown` done), flip the
Rust default after a soak, then archive the Python daemon backend — the irreversible
archival held for explicit user sign-off.

---

## Planning docs by round

| Round | Doc | Status |
|-------|-----|--------|
| R3 | `docs/PLANNING_ROUND3.md` | archived |
| R4 | `docs/PLANNING_ROUND4.md` | archived |
| R5 | `docs/PLANNING_ROUND5.md` | archived |
| R7–8 | `docs/PLANNING_ROUND7.md`, `docs/PLANNING_ROUND8.md` | archived |
| R9 | `docs/PLANNING_ROUND9.md` | archived |
| R10 | `docs/PLANNING_ROUND10.md` | archived |
| R11 | `docs/PLANNING_ROUND11.md` | archived |
| R12 | `docs/PLANNING_ROUND12.md` | archived |
| R12_D | `docs/PLANNING_ROUND12_D_AUDIT.md` | current |
| R13 | `docs/PLANNING_ROUND13.md` | archived |
| R14 | `docs/PLANNING_ROUND14.md` | archived |
| R15 | `docs/PLANNING_ROUND15.md` | archived |
| R16–17 | `docs/PLANNING_ROUND16.md`, `docs/PLANNING_ROUND17.md` | archived |
| R19–20 | `docs/PLANNING_ROUND19.md`, `docs/PLANNING_ROUND20.md` | archived |
| R23–24 | `docs/PLANNING_ROUND23.md`, `docs/PLANNING_ROUND24.md` | archived |
| R26 | `docs/PLANNING_ROUND26.md` | current |
| R27 | *(missing — only CHANGELOG + SESSION_HANDOFF)* | backfill wanted |
| R28 | `docs/PLANNING_ROUND28.md` | current |
| R29 | `docs/PLANNING_ROUND29.md` | current |
| R30 | `docs/PLANNING_ROUND30.md` | current |
| R31 | `docs/PLANNING_ROUND31.md` | current |
| R32 | `docs/PLANNING_ROUND32.md` | current |
| R34 | `docs/PLANNING_ROUND34.md` | archived |
| R46 | `docs/PLANNING_ROUND46.md` | archived |
| R54 | `docs/PLANNING_ROUND54.md` | archived |
| R55 | `docs/PLANNING_ROUND55.md` | archived |
| R56 | `docs/PLANNING_ROUND56.md` | archived |


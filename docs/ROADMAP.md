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

| Workstream | Depends on | Notes |
|-----------|-----------|-------|
| **MCP hardware-verify** | R28 (MCP-via-daemon) | Drive a real device through `divoom-control mcp-server` end-to-end. |
| **Exclusive-mode hardware verify** | R29 | Drive a real multi-step sequence through the proxy exclusive context. |

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

## Native Rust Port Roadmap (Goal: Complete Parity & Python Archival)

To deprecate and archive the Python daemon (`divoom_daemon`) and library backend in favor of the compiled Rust daemon (`divoomd`), the following items must be implemented in the Rust port:

### 1. Divoom Cloud Authentication [SHIPPED]
- **Port Auth Endpoints**: Ported `/UserLogin`, `/User/NewGuest`, and `/APP/GetServerUTC` HTTP API requests.
- **Credential Storage & Caching**: Ported HMAC-MD5 signing, configuration loading from `config.ini`, and session token caching/validation logic.

### 2. Gallery Browsing & Community API [SHIPPED]
- **Gallery Integration**: Ported `/GetCategoryFileListV2` (fetching, sorting, filtering, and page streaming of animation files from Divoom community).
- **Monthly Best Ticker**: Ported the background polling scheduler loop (`monthly_best_daemon.py`) to Rust to periodically download and cycle monthly best animations on connected displays.

### 3. Verification & Cleanup
- **Cross-Platform Verification**: Verify `btleplug` BLE stability on non-macOS platforms (Windows/Linux) under various network environments.
- **Python Backend Deprecation**: Switch all default commands/launchers to target the Rust binary by default, eventually dropping/archiving the Python daemon and helper source trees.

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


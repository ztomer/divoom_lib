# Planning — Daemon ownership (REVIEW_2026-06 §1.3 / §4.1 / §1.2)

**Status: Phase 1 SHIPPED 2026-06-09** (GUI delegates notifications to the daemon;
the double-route is gone). Phases 2-3 still open. Read-only investigation +
correction below.

## TL;DR — the "biggest risk" is mostly already fixed

REVIEW §4.1 calls the "half-migrated daemon architecture … the single biggest
risk" and lists five symptoms. Investigation shows the **device-access migration
is essentially complete**, so most of §4.1 is outdated. One genuine duplication
remains: **notification monitoring (§1.2)**. That is the only thing this plan
needs to act on.

## What I verified

### Device access (§1.3) — DONE, not dual

- There is **no direct BLE construction anywhere in `divoom_gui/`**
  (`grep` for `Divoom(`, `BleakClient`, `ble_transport`, `.connect()` → none).
- `current_divoom` is assigned exactly once, to
  `DaemonDeviceProxy(client, target="device")` — [scanner_mixin.py:119](divoom_gui/scanner_mixin.py:119).
- `DaemonDeviceProxy` ([daemon_bridge.py](divoom_gui/daemon_bridge.py)) builds a
  dotted method path (`display.show_light`, `notification.show_notification_text`)
  and issues a `device_call` RPC. Root-level reads (`is_connected`/`lan`/`_conn`)
  are answered synchronously from `device_status`.
- The daemon's `DeviceOwner` ([device_owner.py:28](divoom_daemon/device_owner.py:28))
  is the **single owner** of the real BLE/LAN connection + wall, run on its own
  dedicated asyncio loop behind the command queue.

So both GUI access styles —
1. proxy: `self._current_divoom.display.show_light(...)` (api/tools.py, api/widgets.py)
2. direct: `self._client.device_call(...)` / `client.wall_configure(...)`

— route **exclusively through the daemon**. There is no BLE-vs-daemon split. The
"two paths" are two ergonomic wrappers over the same RPC, not a consistency hazard.

### Notification monitoring (§1.2) — GENUINELY DUAL, the real item

Two independent `MacNotificationMonitor(poll_interval=1.0)` instances can run at
once against the same macOS Notification Center SQLite DB:

| Owner | Where | Routes via |
|---|---|---|
| **Daemon** `NotificationService` | [daemon.py:65](divoom_daemon/daemon.py:65), **auto-started** at [daemon.py:145](divoom_daemon/daemon.py:145) | `device_owner.send_notification` (correct single-owner path) |
| **GUI** `_notification_monitor` | [gui_api.py:226](divoom_gui/gui_api.py:226), started by `start_notification_listener` (called from [settings_features.js:332](divoom_gui/web_ui/settings_features.js:332)) | `current_divoom.notification.show_notification_text` → `device_call` |

When the daemon is up (it always is — the GUI spawns it) **and** the user enables
the GUI listener, both pollers fire every second and both forward each
notification to the device → **double-routed notifications + redundant DB
contention**. This is exactly the §1.2 hazard, confirmed live.

The fix is cheap because the daemon already exposes the right RPCs:
`start_notifications`, `stop_notifications`, `set_routing`
([daemon.py:77-79](divoom_daemon/daemon.py:77)).

## Plan — single-owner notifications

**Phase 1 — GUI delegates instead of polling (the fix). DONE 2026-06-09.**
- `start_notification_listener` / `stop_notification_listener` /
  `is_notification_listener_running` / `get_notification_listener_status` /
  `save_notification_routing` now call the daemon's
  `start_notifications` / `stop_notifications` / `notification_status` /
  `set_routing` RPCs (new wrappers on `DaemonClient`, daemon_protocol.py).
- Deleted the GUI-side monitor machinery: `_notification_monitor`,
  `_notification_sink`, `_send_notification_async`, `_schedule_async`.
- The web UI toggle (`settings_features.js`) keeps the same JS API surface
  (`{running, db_path?, error?}`); only the Python implementation changed.
- Regression test: `test_gui_does_not_instantiate_local_monitor`.

**Phase 2 — surface daemon notification state to the GUI.**
- The daemon `NotificationService` is wired to `broadcast=self._socket_server.broadcast`
  and exposes `status_event()` / `notification_status`. Have the settings toggle
  reflect the daemon's reported running state (via `get_status` /
  `notification_status`) instead of a local flag, so the UI is truthful when the
  daemon auto-started the listener before the GUI opened.

**Phase 3 — routing config.**
- The per-app routing map should live with the daemon (it owns the monitor).
  Point the GUI routing editor at `set_routing` RPC; drop any GUI-local copy.

### Tests
- Daemon `NotificationService` start/stop/route can be unit-tested with a mock
  monitor + mock `send_notification` (no macOS DB) — `tests/test_daemon_server.py`
  already mocks the device owner; extend it.
- GUI: assert `start_notification_listener` issues the RPC and does **not**
  import/instantiate `MacNotificationMonitor` (mock the client, assert call).

### Risk / sequencing
- Low blast radius: one RPC already exists; the change is "stop doing the second
  thing." Do Phase 1 alone first (kills the double-route), ship, then 2/3.
- macOS-only path; the daemon listener is best-effort/idle on non-mac, so CI is
  unaffected.

## Not doing (review items that are already resolved)
- §1.3 dual device access — resolved (no direct BLE in GUI).
- §4.1 "daemon owns the device" boundary — already true via `DeviceOwner`.
- §1.7 shutdown `time.sleep(0.25)` — still present ([daemon.py:99](divoom_daemon/daemon.py:99))
  but it's the *reply-then-stop* ack delay, not a BLE-write race; low priority,
  separate from this plan.

# Round 16 — extract a headless daemon; GUI/menubar become event clients

> **Input (user):** "We don't want the IPC and the events in the GUI — the GUI is
> just a presentation layer. We already have a headless daemon. Shouldn't it live
> there? The GUI will listen on events, and the daemon will listen on events as
> well."

## The layering bug

Today the macOS **notification monitor + device routing lives in the GUI
process** (`gui_api._mac_monitor` + `_notification_sink`). So the always-on
"mirror notifications to the device" feature only runs **while the pywebview
window is open**. The presentation layer owns a background, device-driving job.
R15 §6 compounded it: the GUI *pushed* status outward to the menubar — backwards.

## Target architecture (decisions locked with the user)

- **New dedicated daemon** (`divoom-control daemon`, `gui/daemon.py`) — the single
  owner of the device connection + `MacNotificationMonitor` + routing. It listens
  to the OS notification stream, routes to the device, and **emits events**.
- **Transport: extend the Unix socket** (`/tmp/divoom.sock`) with a
  subscribe/stream mode. Existing request/response commands stay; a client may
  send `{"command":"subscribe"}` and then the daemon streams newline-delimited
  JSON events on that held-open connection.
- **GUI = pure presentation.** No local monitor. It sends intents
  (start/stop/get_status/set_routing/device commands) as request/response, and
  *subscribes* for live notification/status events to render. 
- **Menubar = client too.** Subscribes for status → updates its title; menu items
  send commands. It stops running the socket *server* (the daemon owns it).

Two layers of "listening": **daemon listens to the OS → re-emits; GUI + menubar
listen to the daemon.**

## Event + command protocol (`gui/daemon_protocol.py`, pure/testable)

- Framing: **newline-delimited JSON** (`encode_message(obj) -> bytes`,
  `iter_messages(buf) -> (msgs, remainder)`).
- Request: `{"command": str, "args": {...}}` → response `{"success": bool, ...}`.
- Subscribe: `{"command": "subscribe"}` → connection held open; daemon streams
  events until the client disconnects.
- Event shapes:
  - `{"type":"status","state":"active|idle|error","counters":{seen,routed,dropped}}`
  - `{"type":"notification","app_type":int,"title":str,"body":str,"routed":bool}`
- `DaemonClient`: `send_command(cmd, args, socket_path)` one-shot;
  `subscribe(socket_path, on_event)` streaming (used by menubar/GUI).

## Phases

1. **Protocol core** (`gui/daemon_protocol.py`) + tests — framing, shapes, client. *(this round, first)*
2. **Daemon server** (`gui/daemon.py`): owns device + monitor; socket server with
   request/response + subscribe/stream + event broadcast; `divoom-control daemon`
   CLI. Tests with a temp socket + a fake monitor (no AppKit/BLE).
3. **Menubar → client**: stop running the server; subscribe to the daemon, update
   title from `status` events; menu commands go to the daemon; spawn the daemon if
   not running. **Removes R15 §6's `gui_api._push_menubar_status`.**
4. **GUI → client**: `gui_api` notification methods proxy to the daemon (no local
   `_mac_monitor`); the Notifications card subscribes for live events.
5. **Close**: handoff + CHANGELOG + push.

## Compatibility / migration notes

- `menubar_status.py` helpers (derive_state / format_status_title / status_color)
  survive — the menubar still formats its title, just from daemon events.
- The daemon reuses `gui/macos_notifications.py` (monitor + router + routing JSON)
  and the device-command handling currently in `menubar.execute_ipc_command`.
- Single-user macOS, per-uid socket = the trust boundary (same as today). No auth.

## §outcome

- **P1 SHIPPED** (`gui/daemon_protocol.py`): NDJSON framing, command/event
  shapes, `DaemonClient` (send_command + subscribe). 8 tests.
- **P2 SHIPPED** (`gui/daemon.py` + `divoom-control daemon` CLI): `DivoomDaemon`
  owns device + macOS monitor + routing; Unix-socket server with request/response
  + subscribe/stream + event broadcast; sink routes to device (preserving the
  GUI's title-first behavior) + counts + broadcasts. Monitor + device-sender are
  injectable → 5 tests with a fake monitor over a temp socket (no AppKit/BLE).
  Suite 946 → 959.
- **P3 / P4 / P5 — not started.** P3 migrates the menubar to a daemon *client*
  (subscribe → title; commands → daemon; spawn daemon if absent) and **removes
  R15 §6's `gui_api._push_menubar_status`**. P4 migrates the GUI (`gui_api`
  notification methods proxy to the daemon; remove `_mac_monitor`; card
  subscribes). These touch the live menubar + GUI processes — own focused pass,
  user should visually verify. Until P3 lands, don't run the daemon and the old
  menubar simultaneously (both bind `/tmp/divoom.sock`).

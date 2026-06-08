# Round 23 — REVIEW §1.2–§1.5: gui_api collaborators, daemon extraction, DeviceSlot dataclass, web_ui splits

**Date:** 2026-06-07
**Status:** shipped
**Predecessor:** R22 (menubar refactor)

REVIEW §1.3 addresses `divoom_daemon/daemon.py` (730 LOC) — a class with
four responsibilities and an if-ladder dispatch. Priority order per
`REVIEW_2026-06.md §1.7` step 4.

---

## Design rationale

### Wave 1 — command registry

Replace the if-ladder in `handle_command()` with a dict-based registry.
Purely additive; no behavior change. Handlers remain methods on
`DivoomDaemon` for now; they move when their owning class is extracted.

### Wave 2 — SocketServer

Server lifecycle, accept loop, subscriber management, auth, broadcast.
Extracted into `divoom_daemon/socket_server.py` and composed into
`DivoomDaemon` with getter callbacks for `handle_command` and
`status_event`.

### Wave 3 — NotificationService

Notification monitoring lifecycle: start, stop, routing, sink.
Extracted into `divoom_daemon/notification_service.py`.

### Wave 4 — DeviceOwner

Device lifecycle: connect, disconnect, device_call, scan, wall_configure,
sync_artwork, probe_lan. Extracted into `divoom_daemon/device_owner.py`.

---

## Outcome / what shipped

### Wave 1 — command registry (5d3f7d1)

`handle_command()` if-ladder → dict-based `_init_registry()`.
Lazy-init on first call; shared handlers via alias (`get_status` = `notification_status`).
No behavior change. Suite: 989/75.

### Wave 2 — SocketServer (7c0cc31)

Extracted `divoom_daemon/socket_server.SocketServer` — Unix + TCP listener
lifecycle, accept loop, subscriber fan-out, token auth. Composed into
DivoomDaemon with `command_handler` + `status_event_factory` callbacks.
Removed unused imports (`hmac`, `socket`, `SUBSCRIBE_COMMAND`, `encode_message`).
Suite: 989/75.

### Wave 3 — NotificationService (73b39bd)

Extracted `divoom_daemon/notification_service.NotificationService` —
notification monitoring lifecycle (start/stop/set_routing), status derivation,
sink + broadcast. Composed into DivoomDaemon with `broadcast` and
`send_notification` callbacks. `DivoomDaemon._cleanup()` now calls
`_notifier.stop_monitor()`. Removed unused imports (`sys`,
`make_status_event`, `make_notification_event`).
Updated `test_daemon_platform.py` to use `_notifier` interface.
Suite: 989/75.

### Wave 4 — DeviceOwner (e3612b0)

Extracted `divoom_daemon/device_owner.DeviceOwner` — device lifecycle
(connect, disconnect, device_call, scan, wall, sync, probe_lan) and
notification BLE sender. All device command handlers registered via
`DivoomDaemon._init_registry()` from `_device_owner`. DivoomDaemon reduced
from 730→132 LOC; removed from `test_file_size.py` ALLOWLIST (10 entries).
Suite: 989/75.

### §1.4 — DeviceSlot dataclass (c29c715)

- **`divoom_lib/models/device_slot.py`** — `@dataclass DeviceSlot(device, x, y, size, width, height)`.
- Exported from `divoom_lib/models/__init__.py`.
- Replaced all ad-hoc 6-tuple construction/destructuring in `wall.py` (`DivoomWall`) and
  `device_owner.py`. Suite: 989/75.

### §1.5 — web_ui >500-LOC file splits

- **6 oversized files split into 14 files**, all under 500 LOC:
  - `templates.js` (718) → `templates_tools.js`, `templates_monthly_best.js`, `templates_widgets.js`, `templates_settings.js`.
  - `app.js` (619) → `app_globals.js` + `app_init.js`.
  - `channels.js` (578) → `channels_core.js` + `channels_grids.js`.
  - `settings.js` (745) → `settings_hardware.js` + `settings_features.js`.
  - `widgets.css` (524) → `widgets_base.css` + `widgets_extra.css`.
  - `style.css` (510) → `style.css` (279) + `style_extra.css`.
- **ALLOWLIST shrunk from 10 → 4** (`media_sync.py`, `downsample.c`, `constants.py`, `cli.py` remain).
- `index.html` script + CSS loading updated. `style.css` @import chain updated.
- 8 test files updated with `_cat()` path helper; regex patterns fixed for split template structure.
- Suite: 980 passed / 75 skipped (zero regressions on relevant tests).

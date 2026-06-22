"""R53 round 34 — persona pass (Bob+Linus CONVERGED on the mcp NameError; Hashimoto
found 3 lifecycle bugs).

- mcp_tools.get_capabilities referenced `dataclasses` with no module-level import →
  NameError for a real Divoom (whose Capabilities dataclass has no to_dict).
- The macOS notification monitor swallowed a SUSTAINED DB-read failure as "no new
  rows", so status kept reporting ACTIVE while the feature was silently deaf. Now a
  failure streak surfaces health_error → STATE_ERROR.
"""
import asyncio
import dataclasses
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))


# ── Bob+Linus: get_capabilities dataclass fallback ──────────────────────────

def test_get_capabilities_handles_real_dataclass_without_to_dict():
    from divoom_lib.mcp_tools import _make_handlers

    @dataclasses.dataclass
    class _Caps:
        size: int = 16
        model: str = "Pixoo"

    class _Divoom:
        capabilities = _Caps()

    handlers = _make_handlers(_Divoom())
    res = asyncio.run(handlers["get_capabilities"]())
    assert res == {"size": 16, "model": "Pixoo"}, "real-device dataclass fallback must work, not NameError"


# ── Hashimoto: notification monitor health surfaces a sustained DB failure ───

def test_notification_health_error_after_sustained_db_failure(tmp_path):
    from divoom_daemon.macos_notifications import MacNotificationMonitor, MacAppRouter
    from divoom_daemon.notification_service import NotificationService, STATE_ERROR

    bad_db = tmp_path / "no_such.db"  # sqlite makes the file but there's no 'record' table
    mon = MacNotificationMonitor(router=MacAppRouter(rules=[]), poll_interval=1.0, db_path=bad_db)

    mon._fetch_new()
    assert mon.health_error is None, "a single failure must not flip health (could be a transient lock)"

    for _ in range(mon._DB_ERROR_HEALTH_THRESHOLD):
        mon._fetch_new()
    assert mon.health_error is not None, "a sustained DB failure must surface health_error"

    svc = NotificationService(
        broadcast=lambda e: None, send_notification=lambda *a: None, monitor=mon)
    assert svc._state() == STATE_ERROR, "service must report STATE_ERROR, not lie ACTIVE"
    assert svc.status_event().get("error"), "the error text must reach the status event"

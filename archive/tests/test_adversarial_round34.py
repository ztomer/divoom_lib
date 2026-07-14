"""R53 round 34 — persona pass (Hashimoto found 3 lifecycle bugs).

- The macOS notification monitor swallowed a SUSTAINED DB-read failure as "no new
  rows", so status kept reporting ACTIVE while the feature was silently deaf. Now a
  failure streak surfaces health_error → STATE_ERROR.

Split out of tests/test_adversarial_round34.py: this test depends on the
archived divoom_daemon.notification_service server module (the other test in
that file, covering divoom_lib.mcp_tools, stayed in tests/ since it has no
dependency on the archived daemon server).
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))


# ── Hashimoto: notification monitor health surfaces a sustained DB failure ───

def test_notification_health_error_after_sustained_db_failure(tmp_path):
    from divoom_daemon.macos_notifications import MacNotificationMonitor, MacAppRouter
    from archive.divoom_daemon.notification_service import NotificationService, STATE_ERROR

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

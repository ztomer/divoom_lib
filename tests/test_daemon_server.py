"""R16 Phase 2 — daemon server (divoom_daemon/daemon.py).

Drives a real DivoomDaemon over a temp Unix socket with a FAKE monitor and an
injected device-sender, so no AppKit/BLE is needed. Covers command dispatch,
status, the notification sink (device routing + counters), and the
subscribe/stream + broadcast path.
"""
import os
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "divoom_gui"))

from divoom_daemon.daemon import DivoomDaemon, STATE_ACTIVE, STATE_IDLE
from divoom_daemon.daemon_protocol import DaemonClient, EVENT_STATUS, EVENT_NOTIFICATION


class FakeMonitor:
    def __init__(self):
        self.is_running = False
        self.records_seen = 0
        self.records_routed = 0
        self.records_dropped = 0
        self.db_path = "/tmp/fake.db"
        self._sink = None

        class _Router:
            rules = [("whatsapp", 6)]
        self._router = _Router()

    def start(self, sink):
        self.is_running = True
        self._sink = sink

    def stop(self):
        self.is_running = False

    def fire(self, app_type, title, body):
        self.records_seen += 1
        self.records_routed += 1
        if self._sink:
            self._sink(app_type, title, body)


@pytest.fixture
def daemon_ctx():
    sp = f"/tmp/divoom_daemon_{os.getpid()}.sock"
    if os.path.exists(sp):
        os.remove(sp)
    monitor = FakeMonitor()
    sent = []
    d = DivoomDaemon(socket_path=sp, monitor=monitor,
                     device_sender=lambda a, t: sent.append((a, t)))
    t = threading.Thread(target=d.serve_forever, daemon=True)
    t.start()
    # wait for bind
    for _ in range(50):
        if os.path.exists(sp):
            break
        time.sleep(0.02)
    try:
        yield d, monitor, sent, sp
    finally:
        d.stop()
        t.join(timeout=3.0)
        if os.path.exists(sp):
            os.remove(sp)


def test_get_status_idle(daemon_ctx):
    d, monitor, sent, sp = daemon_ctx
    reply = DaemonClient(sp).send_command("get_status")
    assert reply["success"] is True
    assert reply["state"] == STATE_IDLE
    assert reply["counters"] == {"seen": 0, "routed": 0, "dropped": 0}


def test_start_and_stop(daemon_ctx):
    d, monitor, sent, sp = daemon_ctx
    c = DaemonClient(sp)
    r1 = c.send_command("start_notifications")
    assert r1["success"] is True and r1["state"] == STATE_ACTIVE
    assert monitor.is_running is True
    r2 = c.send_command("stop_notifications")
    assert r2["success"] is True and r2["state"] == STATE_IDLE
    assert monitor.is_running is False


def test_unknown_command(daemon_ctx):
    d, monitor, sent, sp = daemon_ctx
    reply = DaemonClient(sp).send_command("frobnicate")
    assert reply["success"] is False
    assert "unknown command" in reply["error"]


def test_sink_routes_to_device_and_counts(daemon_ctx):
    d, monitor, sent, sp = daemon_ctx
    DaemonClient(sp).send_command("start_notifications")
    # Preserves the original GUI sink behavior: text = (title or body), first line.
    monitor.fire(6, "WhatsApp", "Hello there\nsecond line")
    assert sent == [(6, "WhatsApp")]
    status = DaemonClient(sp).send_command("get_status")
    assert status["counters"]["routed"] == 1


def test_subscribe_receives_status_then_broadcasts(daemon_ctx):
    d, monitor, sent, sp = daemon_ctx
    events = []
    stop = threading.Event()
    sub = threading.Thread(
        target=lambda: DaemonClient(sp).subscribe(events.append, should_stop=stop.is_set),
        daemon=True,
    )
    sub.start()
    time.sleep(0.2)  # let the subscription register + receive initial status

    # initial status event arrives on subscribe
    assert events and events[0]["type"] == EVENT_STATUS

    # a command-driven broadcast reaches the subscriber
    DaemonClient(sp).send_command("start_notifications")
    time.sleep(0.2)
    assert any(e["type"] == EVENT_STATUS and e["state"] == STATE_ACTIVE for e in events)

    # a notification fires -> notification event + status event broadcast
    monitor.fire(6, "WhatsApp", "ping")
    time.sleep(0.2)
    notifs = [e for e in events if e["type"] == EVENT_NOTIFICATION]
    assert notifs and notifs[0]["app_type"] == 6 and notifs[0]["routed"] is True

    stop.set()
    sub.join(timeout=3.0)

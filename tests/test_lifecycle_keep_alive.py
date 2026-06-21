"""R40 §9 — daemon (menu bar) keep-alive lifecycle.

Covers: the persisted flag, the pure decision helpers, the daemon's shutdown
broadcast, and the menubar client routing a shutdown event to its callback.
All event-driven — no polling anywhere in the path.
"""
import os
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))

from divoom_lib import lifecycle_config as lc
from divoom_daemon.daemon import DivoomDaemon
from divoom_daemon.daemon_protocol import DaemonClient, EVENT_SHUTDOWN


# ── flag persistence ──────────────────────────────────────────────────────

def test_flag_defaults_false_and_roundtrips(tmp_path):
    p = tmp_path / "config.ini"
    assert lc.get_keep_daemon_alive(p) is False          # default
    assert lc.set_keep_daemon_alive(True, p) is True
    assert lc.get_keep_daemon_alive(p) is True
    assert lc.set_keep_daemon_alive(False, p) is True
    assert lc.get_keep_daemon_alive(p) is False


def test_flag_read_tolerates_missing_and_garbage(tmp_path):
    assert lc.get_keep_daemon_alive(tmp_path / "nope.ini") is False
    bad = tmp_path / "bad.ini"
    bad.write_text("[gui]\nkeep_daemon_alive = not-a-bool\n")
    assert lc.get_keep_daemon_alive(bad) is False
    # preserves an existing unrelated section
    other = tmp_path / "o.ini"
    other.write_text("[gui]\ntimeout = 9\n")
    lc.set_keep_daemon_alive(True, other)
    import configparser
    c = configparser.ConfigParser(); c.read(other)
    assert c.get("gui", "timeout") == "9"
    assert c.getboolean("gui", "keep_daemon_alive") is True


# ── pure decision helpers (shared lifecycle ↔ NOT keep-alive) ──────────────

@pytest.mark.parametrize("keep,expect", [(False, True), (True, False)])
def test_decision_helpers(keep, expect):
    assert lc.should_follow_daemon_shutdown(keep) is expect
    assert lc.should_stop_daemon_on_dashboard_quit(keep) is expect
    assert lc.should_stop_daemon_on_menubar_quit(keep) is expect


# ── daemon broadcasts a shutdown event before stopping ─────────────────────

class _Monitor:
    is_running = False
    db_path = "/tmp/fake.db"
    def start(self, sink): self.is_running = True
    def stop(self): self.is_running = False


def _wait_daemon_ready(sock, timeout=5.0):
    """Wait until the daemon ACCEPTS a real connection, not just until the
    socket file exists — the file can appear before the accept loop is ready,
    which races on a loaded CI runner."""
    from divoom_gui.daemon_bridge import daemon_alive
    end = time.time() + timeout
    while time.time() < end:
        if os.path.exists(sock) and daemon_alive(sock, timeout=0.5):
            return True
        time.sleep(0.02)
    return False


def test_daemon_shutdown_broadcasts_event():
    # Short /tmp path — AF_UNIX rejects pytest's long tmp_path on macOS.
    sock = f"/tmp/divoom_lc_{os.getpid()}.sock"
    if os.path.exists(sock):
        os.remove(sock)
    daemon = DivoomDaemon(socket_path=sock, monitor=_Monitor(), device=object())
    t = threading.Thread(target=daemon.serve_forever, daemon=True)
    t.start()
    assert _wait_daemon_ready(sock), "daemon did not become ready"

    events = []
    stop = threading.Event()
    st = threading.Thread(
        target=lambda: DaemonClient(sock, timeout=3.0).subscribe(events.append, should_stop=stop.is_set),
        daemon=True)
    st.start()
    # Wait until the subscription is REGISTERED — proven by the initial status
    # event the daemon broadcasts on subscribe — before triggering shutdown, so
    # the shutdown broadcast can't race ahead of registration.
    end = time.time() + 5.0
    while time.time() < end and not events:
        time.sleep(0.02)
    assert events, "subscriber never received the initial status event"

    reply = DaemonClient(sock, timeout=2.0).shutdown()
    assert reply.get("success") is True
    end = time.time() + 3.0
    while time.time() < end and not any(e.get("type") == EVENT_SHUTDOWN for e in events):
        time.sleep(0.02)
    assert any(e.get("type") == EVENT_SHUTDOWN for e in events), "no shutdown event received"
    stop.set()
    t.join(timeout=2.0)
    if os.path.exists(sock):
        os.remove(sock)


# ── menubar client routes the shutdown event to its callback ───────────────

def test_menubar_client_dispatches_shutdown():
    from divoom_menubar.menubar_client import MenubarClient
    mc = MenubarClient(socket_path="/tmp/divoom_absent_lifecycle.sock")
    fired = []
    mc.set_shutdown_callback(lambda: fired.append(True))
    # Drive the private dispatcher directly (no live daemon needed).
    on_event = _capture_on_event(mc)
    on_event({"type": EVENT_SHUTDOWN})
    assert fired == [True]
    on_event({"type": "status", "state": "idle"})  # non-shutdown → no extra fire
    assert fired == [True]


def test_menubar_follows_on_dropped_subscription_when_daemon_gone():
    """R44 §4: if subscribe() returns (connection lost) without us stopping AND
    a reconnect probe finds the daemon gone, fire the shutdown callback."""
    from divoom_menubar.menubar_client import MenubarClient
    mc = MenubarClient(socket_path="/tmp/divoom_absent_lifecycle.sock")
    fired = []
    mc.set_shutdown_callback(lambda: fired.append(True))

    calls = {"n": 0}

    def _stub_subscribe(on_event, should_stop=None):
        calls["n"] += 1
        return True  # returns immediately = "connection lost", _running stays True

    mc._client.subscribe = _stub_subscribe
    # probe reports the daemon is unreachable → follow it down
    mc._client.send_command = lambda *a, **k: {"success": False, "error": "down"}
    mc._running = True
    mc._subscribe_loop()
    assert fired == [True], "menubar must follow the daemon down when it's gone"


def test_menubar_resubscribes_on_transient_drop():
    """A transient drop (daemon still reachable) must re-subscribe, not quit."""
    from divoom_menubar.menubar_client import MenubarClient
    mc = MenubarClient(socket_path="/tmp/divoom_absent_lifecycle.sock")
    fired = []
    mc.set_shutdown_callback(lambda: fired.append(True))

    seen = {"n": 0}

    def _stub_subscribe(on_event, should_stop=None):
        seen["n"] += 1
        if seen["n"] >= 2:
            mc._running = False  # second pass: stop so the test ends
        return True

    mc._client.subscribe = _stub_subscribe
    mc._client.send_command = lambda *a, **k: {"success": True}  # daemon alive
    mc._running = True
    mc._subscribe_loop()
    assert seen["n"] == 2, "must re-subscribe after a transient drop"
    assert fired == [], "must NOT follow down while the daemon is alive"


def _capture_on_event(mc):
    """Extract the inner on_event closure from _subscribe_loop by stubbing the
    client's subscribe to capture it. R44 §4: _subscribe_loop now retries in a
    `while self._running` loop, so the stub clears _running on capture to make
    the loop exit immediately (and we don't reach the daemon-gone probe)."""
    captured = {}

    def _stub_subscribe(on_event, should_stop=None):
        captured["fn"] = on_event
        mc._running = False   # exit the retry loop after one pass
        return True

    mc._client.subscribe = _stub_subscribe
    mc._running = True
    mc._subscribe_loop()
    return captured["fn"]

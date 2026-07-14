"""R40 §9 — the daemon broadcasts a shutdown event before stopping.

Split out of tests/test_lifecycle_keep_alive.py: this test spins up a real
archived divoom_daemon.daemon.DivoomDaemon over a temp Unix socket. The
lifecycle-flag persistence, pure decision-helper, and menubar-client tests
have no daemon-server dependency and stayed in
tests/test_lifecycle_keep_alive.py.
"""
import os
import sys
import threading
import time
from pathlib import Path

from archive.divoom_daemon.daemon import DivoomDaemon
from divoom_daemon.daemon_protocol import DaemonClient, EVENT_SHUTDOWN

sys.path.append(str(Path(__file__).parent.parent.parent))


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

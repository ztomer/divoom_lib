"""R53.33: a subscriber's initial status snapshot must be sent while holding
_sub_lock. broadcast() runs from the notification-monitor thread and does
sendall() on every registered subscriber under _sub_lock; if the initial send
happens OUTSIDE the lock (after the socket is already registered), the two
sendall()s race on the same fd and interleave their bytes — corrupting the
NDJSON stream so the subscriber drops both the snapshot and the event.

Teeth: move the initial send back out of _add_subscriber (i.e. send it in
_serve_subscriber after registration, as before) and `under_lock` becomes False.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from divoom_daemon.socket_server import SocketServer


def _make_server():
    return SocketServer(
        socket_path="/tmp/divoom-test-initial-frame.sock",
        command_handler=lambda c, a: {"success": True},
        status_event_factory=lambda: {"type": "status", "ok": True},
    )


def test_initial_status_frame_is_sent_holding_sub_lock():
    srv = _make_server()
    observed = {}

    class _FakeConn:
        def settimeout(self, _t):
            pass

        def sendall(self, _data):
            # _sub_lock is a non-reentrant threading.Lock. If THIS thread already
            # holds it, acquire(blocking=False) returns False → the send is under
            # the lock (serialized against broadcast). If it returns True, the
            # send is unlocked → it can race broadcast()'s sendall on this fd.
            got = srv._sub_lock.acquire(blocking=False)
            observed["under_lock"] = got is False
            if got:
                srv._sub_lock.release()

        def recv(self, _n):
            return b""  # peer closed → break the serve loop immediately

        def close(self):
            pass

    srv._running = True
    srv._serve_subscriber(_FakeConn())

    assert observed.get("under_lock") is True, (
        "initial status frame was sent WITHOUT holding _sub_lock — it can "
        "interleave with broadcast()'s sendall on the same socket"
    )


def test_dead_socket_on_initial_send_is_not_registered():
    """If the client dies before the initial send lands, it must not be left in
    the subscriber set (a phantom that broadcast keeps trying to write)."""
    srv = _make_server()

    class _DeadConn:
        def settimeout(self, _t):
            pass

        def sendall(self, _data):
            raise OSError("broken pipe")

        def recv(self, _n):
            return b""

        def close(self):
            pass

    srv._running = True
    srv._serve_subscriber(_DeadConn())
    assert srv._subscribers == [], "dead subscriber must not be registered"

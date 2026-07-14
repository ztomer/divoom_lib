"""Daemon-socket hardening — server side: the server's startup must not race
its own stop() into a half-published socket.

Split out of tests/test_daemon_socket_hardening.py: these two tests spin up a
real archived divoom_daemon.socket_server.SocketServer. The client-side
retry/backoff tests (no server involved) stayed in
tests/test_daemon_socket_hardening.py.
"""
import sys
import threading
import time
from pathlib import Path

from divoom_daemon.daemon_protocol import DaemonClient


sys.path.append(str(Path(__file__).parent.parent.parent))


def test_server_startup_is_robust_under_immediate_client():
    """End-to-end: spin the real SocketServer up and hammer it with a client
    immediately — the local-socket-before-publish fix means the client connects
    cleanly instead of racing a half-bound socket."""
    import os
    import tempfile
    from archive.divoom_daemon.socket_server import SocketServer

    # AF_UNIX paths are length-capped (~104 on macOS); keep it short under /tmp.
    sp = os.path.join(tempfile.gettempdir(), f"divoom_h_{os.getpid()}.sock")

    def _handler(command, args):
        return {"success": True, "command": command}

    srv = SocketServer(socket_path=sp, command_handler=_handler,
                       status_event_factory=lambda: {"success": True, "status": 1})
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        # Poll for readiness the way ensure_daemon does, then call.
        client = DaemonClient(sp, timeout=2.0)
        deadline = time.monotonic() + 3.0
        reply = {}
        while time.monotonic() < deadline:
            reply = client.send_command("device_status")
            if reply.get("success"):
                break
        assert reply.get("success") is True
    finally:
        srv.stop()
        t.join(timeout=3.0)
        if os.path.exists(sp):
            os.remove(sp)


def test_stop_before_serve_forever_does_not_crash(tmp_path):
    """Calling stop() before/around serve_forever must be safe (idempotent),
    never raising the 'NoneType has no attribute listen' the old code could."""
    from archive.divoom_daemon.socket_server import SocketServer

    sp = str(tmp_path / "s.sock")
    srv = SocketServer(socket_path=sp, command_handler=lambda c, a: {"success": True},
                       status_event_factory=lambda: {"success": True})
    srv.stop()                      # before it ever started — must be a no-op
    srv.stop()                      # idempotent
    assert srv._server is None

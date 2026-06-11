"""Daemon-socket hardening — transient connect refusals shouldn't surface as a
hard error to the user (the daemon is just mid-(re)start), and the server's
startup must not race its own stop() into a half-published socket.
"""
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))

from divoom_daemon import daemon_protocol
from divoom_daemon.daemon_protocol import DaemonClient, encode_message


# ── client: bounded connect-retry on a transient refusal ───────────────────

def test_send_command_retries_transient_connection_refused(monkeypatch):
    """A connect that's refused a couple times then succeeds must transparently
    recover — the user never sees 'Connection refused'."""
    calls = {"n": 0}

    class _FakeSock:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def settimeout(self, _t): pass
        def sendall(self, _d): pass
        def recv(self, _n): return encode_message({"success": True, "ok": 1})

    def _flaky_connect(self):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionRefusedError(61, "Connection refused")
        return _FakeSock()

    monkeypatch.setattr(DaemonClient, "_connect", _flaky_connect)
    monkeypatch.setattr(daemon_protocol.time, "sleep", lambda _s: None)

    c = DaemonClient("/tmp/whatever.sock")
    reply = c.send_command("device_status")
    assert reply.get("success") is True
    assert calls["n"] == 3          # refused twice, succeeded on the third


def test_send_command_gives_up_after_retries(monkeypatch):
    """A daemon that's genuinely down still fails (after the bounded budget),
    returning an error dict rather than raising."""
    calls = {"n": 0}

    def _always_refused(self):
        calls["n"] += 1
        raise ConnectionRefusedError(61, "Connection refused")

    monkeypatch.setattr(DaemonClient, "_connect", _always_refused)
    monkeypatch.setattr(daemon_protocol.time, "sleep", lambda _s: None)

    c = DaemonClient("/tmp/whatever.sock")
    reply = c.send_command("device_status")
    assert reply.get("success") is False
    assert "refused" in reply.get("error", "").lower()
    assert calls["n"] == daemon_protocol.DEFAULT_CONNECT_RETRIES + 1


def test_liveness_probe_fast_fails_without_retry(monkeypatch):
    """connect_retries=0 (used by _client_alive/daemon_alive) must NOT sit
    through the retry budget — exactly one connect attempt."""
    calls = {"n": 0}

    def _refused(self):
        calls["n"] += 1
        raise ConnectionRefusedError(61, "Connection refused")

    monkeypatch.setattr(DaemonClient, "_connect", _refused)
    slept = {"n": 0}
    monkeypatch.setattr(daemon_protocol.time, "sleep",
                        lambda _s: slept.__setitem__("n", slept["n"] + 1))

    c = DaemonClient("/tmp/whatever.sock")
    reply = c.send_command("device_status", connect_retries=0)
    assert reply.get("success") is False
    assert calls["n"] == 1 and slept["n"] == 0


def test_read_error_after_connect_is_not_retried(monkeypatch):
    """Once connected, a read failure is returned as-is (it may be a legit slow
    op, not a connection problem) — we must NOT reconnect-storm on it."""
    connects = {"n": 0}

    class _BadReadSock:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def settimeout(self, _t): pass
        def sendall(self, _d): pass
        def recv(self, _n): raise socket.timeout("read timed out")

    def _ok_connect(self):
        connects["n"] += 1
        return _BadReadSock()

    monkeypatch.setattr(DaemonClient, "_connect", _ok_connect)
    c = DaemonClient("/tmp/whatever.sock")
    reply = c.send_command("device_status")
    assert reply.get("success") is False
    assert connects["n"] == 1        # connected once, did NOT retry on read error


# ── server: real round-trip through the hardened serve_forever ─────────────

def test_server_startup_is_robust_under_immediate_client():
    """End-to-end: spin the real SocketServer up and hammer it with a client
    immediately — the local-socket-before-publish fix means the client connects
    cleanly instead of racing a half-bound socket."""
    import os
    import tempfile
    from divoom_daemon.socket_server import SocketServer

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
    from divoom_daemon.socket_server import SocketServer

    sp = str(tmp_path / "s.sock")
    srv = SocketServer(socket_path=sp, command_handler=lambda c, a: {"success": True},
                       status_event_factory=lambda: {"success": True})
    srv.stop()                      # before it ever started — must be a no-op
    srv.stop()                      # idempotent
    assert srv._server is None

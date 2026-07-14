"""Socket interface hardening — untrusted/buggy clients + resource exhaustion.

Every test drives a REAL in-process SocketServer over a REAL Unix socket (no
transport mocks), with tiny limits so the rails fire quickly.

Split out of tests/test_socket_hardening.py: this file kept the original name
(it carries the bulk of the original suite). The one client-only test that
doesn't touch the archived divoom_daemon.socket_server module
(test_client_caps_oversized_reply) stayed in tests/test_socket_hardening.py.
"""
import json
import os
import socket
import stat
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent.parent))

from archive.divoom_daemon.socket_server import SocketServer
from divoom_daemon.daemon_protocol import DaemonClient, MAX_REPLY_BYTES, encode_message


def _short_sock():
    return os.path.join(tempfile.gettempdir(), f"divoom_hard_{os.getpid()}_{time.time_ns()}.sock")


class _Server:
    """Start a real SocketServer in a thread; tear it down cleanly."""
    def __init__(self, handler=None, **kw):
        self.path = _short_sock()
        self.calls = []

        def _default(cmd, args):
            self.calls.append((cmd, args))
            return {"success": True, "echo": cmd}

        self.srv = SocketServer(
            socket_path=self.path,
            command_handler=handler or _default,
            status_event_factory=lambda: {"type": "status", "ok": True},
            **kw,
        )
        self.t = threading.Thread(target=self.srv.serve_forever, daemon=True)

    def __enter__(self):
        self.t.start()
        # Wait for real ACCEPT-readiness, not just the socket FILE: the file
        # appears at bind() but a connect between bind() and listen() gets
        # ECONNREFUSED (seen flaky in CI under load). Probe with an actual
        # connect until it succeeds.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if os.path.exists(self.path):
                try:
                    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    probe.settimeout(1.0)
                    probe.connect(self.path)
                    probe.close()
                    # let the probe's handler thread finish + release its
                    # connection-semaphore slot before the cap tests run.
                    time.sleep(0.05)
                    break
                except OSError:
                    pass
            time.sleep(0.02)
        return self

    def __exit__(self, *a):
        self.srv.stop()
        self.t.join(timeout=3.0)
        if os.path.exists(self.path):
            try:
                os.remove(self.path)
            except OSError:
                pass

    def raw(self):
        # Short connect-retry so a transient refusal under CI load (listen
        # backlog momentarily full) doesn't flake the raw-socket tests.
        deadline = time.monotonic() + 3.0
        last = None
        while time.monotonic() < deadline:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(3.0)
            try:
                s.connect(self.path)
                return s
            except OSError as e:
                last = e
                s.close()
                time.sleep(0.02)
        raise last


def _recv_reply(s):
    buf = b""
    while b"\n" not in buf:
        chunk = s.recv(4096)
        if not chunk:
            break
        buf += chunk
    return json.loads(buf.decode().splitlines()[0]) if buf.strip() else None


# ── H1: socket file permissions ────────────────────────────────────────────

def test_unix_socket_is_owner_only():
    with _Server() as srv:
        mode = stat.S_IMODE(os.stat(srv.path).st_mode)
        assert mode == 0o600, f"socket perms {oct(mode)} — must be owner-only 0600"


# ── H2: oversized frame is rejected, not buffered ──────────────────────────

def test_oversized_request_is_rejected():
    with _Server(max_message_bytes=64) as srv:
        s = srv.raw()
        # >64 bytes with no newline → server rejects without buffering it all.
        s.sendall(b"x" * 5000)
        reply = _recv_reply(s)
        assert reply and reply["success"] is False
        assert "max message size" in reply["error"]
        s.close()


# ── H3: slow-loris hits the total read deadline ────────────────────────────

def test_slow_request_hits_read_deadline():
    with _Server(read_deadline=0.3) as srv:
        s = srv.raw()
        s.settimeout(3.0)
        s.sendall(b'{"command":"devi')      # partial, never a newline
        reply = _recv_reply(s)               # server should time out + reply
        assert reply and reply["success"] is False
        assert "timed out" in reply["error"]
        s.close()


# ── H4: a handler exception never crashes the thread / strands the client ──

def test_handler_exception_returns_internal_error_and_server_survives():
    def _boom(cmd, args):
        if cmd == "explode":
            raise RuntimeError("kaboom secret detail")
        return {"success": True, "echo": cmd}

    with _Server(handler=_boom) as srv:
        c = DaemonClient(srv.path, timeout=2.0)
        r1 = c.send_command("explode")
        assert r1["success"] is False
        assert r1["error"] == "internal error"      # detail NOT leaked
        # the server is still alive and serves the next request
        r2 = c.send_command("ping")
        assert r2["success"] is True and r2["echo"] == "ping"


# ── H7: request validation ─────────────────────────────────────────────────

def test_non_string_command_is_rejected():
    with _Server() as srv:
        s = srv.raw()
        s.sendall(encode_message({"command": 123, "args": {}}))
        reply = _recv_reply(s)
        assert reply and reply["success"] is False and "command" in reply["error"]
        s.close()


def test_non_dict_args_is_coerced_not_crashed():
    with _Server() as srv:
        s = srv.raw()
        s.sendall(encode_message({"command": "ping", "args": [1, 2, 3]}))
        reply = _recv_reply(s)
        assert reply and reply["success"] is True   # args coerced to {}, handler ran
        s.close()


def test_empty_command_rejected():
    with _Server() as srv:
        s = srv.raw()
        s.sendall(encode_message({"command": "", "args": {}}))
        reply = _recv_reply(s)
        assert reply and reply["success"] is False
        s.close()


# ── H6: subscriber cap ─────────────────────────────────────────────────────

def test_subscriber_cap_rejects_excess():
    with _Server(max_subscribers=1, max_connections=8) as srv:
        held = srv.raw()
        held.sendall(encode_message({"command": "subscribe"}))
        _recv_reply(held)                            # first subscriber: status event
        time.sleep(0.1)
        # second subscribe → over the cap → rejected
        s2 = srv.raw()
        s2.sendall(encode_message({"command": "subscribe"}))
        reply = _recv_reply(s2)
        assert reply and reply["success"] is False
        assert "subscriber limit" in reply["error"]
        held.close(); s2.close()


# ── H5: connection cap ─────────────────────────────────────────────────────

def test_connection_cap_rejects_when_full():
    # 1 handler slot, held by a subscriber → the next connection is "server busy".
    # The server proactively sends the error reply and closes the connection,
    # so we read the buffered reply without sending first.
    with _Server(max_connections=1, max_subscribers=8) as srv:
        held = srv.raw()
        held.sendall(encode_message({"command": "subscribe"}))
        _recv_reply(held)
        time.sleep(0.1)
        s2 = srv.raw()
        reply = _recv_reply(s2)
        assert reply and reply["success"] is False and reply["error"] == "server busy"
        held.close(); s2.close()


# ── regression: a normal request still works end-to-end ────────────────────

def test_normal_request_roundtrip():
    with _Server() as srv:
        c = DaemonClient(srv.path, timeout=2.0)
        r = c.send_command("device_status")
        assert r["success"] is True and r["echo"] == "device_status"


# ── broadcast() must not freeze on a passive/wedged subscriber (R53.22) ──────

def test_broadcast_drops_blocking_subscriber_keeps_healthy():
    """A subscriber whose recv window is full makes sendall raise socket.timeout
    (because the subscriber socket now has a bounded timeout, not None) — broadcast
    must drop it and keep delivering to healthy subscribers, never blocking."""
    from archive.divoom_daemon.socket_server import SocketServer, SUBSCRIBER_IO_TIMEOUT
    assert 0 < SUBSCRIBER_IO_TIMEOUT < 60   # bounded, not None

    srv = SocketServer(
        socket_path=_short_sock(),
        command_handler=lambda c, a: {"success": True},
        status_event_factory=lambda: {"type": "status"},
    )

    sent = {"good": 0}

    class _Good:
        def sendall(self, data):
            sent["good"] += 1
        def close(self):
            pass

    class _Wedged:
        closed = False
        def sendall(self, data):
            raise socket.timeout("send buffer full")   # OSError subclass
        def close(self):
            self.closed = True

    good, bad = _Good(), _Wedged()
    srv._subscribers = [good, bad]
    srv.broadcast({"type": "event"})                    # must return promptly

    assert good in srv._subscribers                     # healthy kept
    assert bad not in srv._subscribers                  # wedged dropped
    assert sent["good"] == 1 and bad.closed is True

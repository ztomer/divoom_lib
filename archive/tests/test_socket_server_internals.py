"""R61 coverage push — internal branch coverage for `divoom_daemon/socket_server.py`.

Complements tests/test_socket_hardening.py (which drives a REAL socket end
to end for the documented hardening rails, H1-H7). These tests call the
private helper methods directly with fake conn/listener objects to reach
defensive branches that are hard to trigger reliably over a real socket
(a peer closing mid-write, a listener raising on accept(), a stale-socket
removal race, etc.) — all transport is faked; no real network/BLE.
"""
from __future__ import annotations

import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))

import archive.divoom_daemon.socket_server as socket_server
from archive.divoom_daemon.socket_server import SocketServer


def _short_sock():
    return os.path.join(tempfile.gettempdir(), f"divoom_int_{os.getpid()}_{time.time_ns()}.sock")


def _server(**kw):
    return SocketServer(
        socket_path=_short_sock(),
        command_handler=kw.pop("command_handler", lambda c, a: {"success": True}),
        status_event_factory=kw.pop("status_event_factory", lambda: {"type": "status"}),
        **kw,
    )


class _FakeConn:
    """A conn stand-in whose recv/sendall/close can be scripted."""

    def __init__(self, recv_side_effect=None, sendall_raises=None, close_raises=None):
        self._recv_side_effect = list(recv_side_effect or [])
        self.sent = []
        self.closed = False
        self._sendall_raises = sendall_raises
        self._close_raises = close_raises

    def settimeout(self, t):
        pass

    def recv(self, n):
        item = self._recv_side_effect.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def sendall(self, data):
        if self._sendall_raises:
            raise self._sendall_raises
        self.sent.append(data)

    def close(self):
        self.closed = True
        if self._close_raises:
            raise self._close_raises


# ── broadcast(): dead-subscriber close() raising is swallowed ──────────────


def test_broadcast_swallows_close_oserror_on_dead_subscriber():
    srv = _server()
    dead = _FakeConn(sendall_raises=OSError("gone"), close_raises=OSError("already closed"))
    srv._subscribers = [dead]
    srv.broadcast({"type": "event"})  # must not raise
    assert dead not in srv._subscribers
    assert dead.closed is True


# ── _add_subscriber / _remove_subscriber ────────────────────────────────────


def test_add_subscriber_without_initial_skips_send_and_registers():
    srv = _server()
    conn = _FakeConn()
    assert srv._add_subscriber(conn, initial=None) is True
    assert conn in srv._subscribers
    assert conn.sent == []  # no initial frame sent


def test_add_subscriber_dead_before_registration_when_initial_send_fails():
    """L106-107: if the initial-snapshot sendall fails (peer already gone),
    the subscriber must NOT be registered — broadcast() would otherwise
    try to fan out to a socket that never worked."""
    srv = _server()
    conn = _FakeConn(sendall_raises=OSError("dead on arrival"))
    assert srv._add_subscriber(conn, initial=b'{"type":"status"}\n') is False
    assert conn not in srv._subscribers


def test_remove_subscriber_noop_when_not_registered():
    srv = _server()
    conn = _FakeConn()
    srv._remove_subscriber(conn)  # never added — must not raise or KeyError
    assert conn not in srv._subscribers


# ── _authorized() ────────────────────────────────────────────────────────


def test_authorized_false_when_no_token_configured():
    srv = _server(token=None)
    assert srv._authorized({"token": "anything"}) is False


# ── _read_request_line(): deadline already elapsed before the first read ───


def test_read_request_line_raises_immediately_if_deadline_already_passed(monkeypatch):
    srv = _server(read_deadline=1.0)
    calls = iter([1000.0, 5000.0])  # second call already exceeds the 1s deadline
    monkeypatch.setattr(socket_server.time, "monotonic", lambda: next(calls))
    with pytest.raises(socket_server._RequestError, match="timed out"):
        srv._read_request_line(_FakeConn(recv_side_effect=[b"never reached"]))


# ── _handle_conn(): iter_messages() yielding no messages ────────────────────


def test_handle_conn_returns_quietly_when_no_messages_parsed():
    srv = _server()
    conn = _FakeConn(recv_side_effect=[b"\n"])  # blank line → iter_messages -> []
    srv._handle_conn(conn)  # must return without replying or raising
    assert conn.sent == []


# ── _handle_conn(): outer OSError guard + close() swallow ───────────────────


def test_handle_conn_outer_oserror_from_recv_is_swallowed():
    srv = _server()
    conn = _FakeConn(recv_side_effect=[ConnectionResetError("peer reset")])
    srv._handle_conn(conn)  # ConnectionResetError is an OSError, not socket.timeout
    assert conn.closed is True


def test_handle_conn_close_oserror_is_swallowed():
    srv = _server()
    conn = _FakeConn(recv_side_effect=[b"\n"], close_raises=OSError("already gone"))
    srv._handle_conn(conn)  # must not propagate the close() failure
    assert conn.closed is True


# ── _reply_safe(): a failed reply write is swallowed, not raised ───────────


def test_reply_safe_swallows_sendall_oserror():
    conn = _FakeConn(sendall_raises=OSError("peer gone"))
    SocketServer._reply_safe(conn, {"success": True})  # must not raise


# ── _serve_subscriber(): not-running short-circuit + loop branches ──────────


def test_serve_subscriber_exits_immediately_when_server_not_running():
    srv = _server()
    assert srv._running is False  # never called serve_forever()
    conn = _FakeConn()
    srv._serve_subscriber(conn)  # while self._running: False → straight to finally
    assert conn not in srv._subscribers  # removed (was added then immediately dropped)


def test_serve_subscriber_loop_handles_data_then_timeout_then_oserror():
    """One subscriber lifecycle exercising all three inner branches:
    truthy recv() (loop continues), socket.timeout (idle, continues), then
    a plain OSError (exits the loop and is swallowed)."""
    srv = _server()
    srv._running = True
    conn = _FakeConn(recv_side_effect=[b"client noise", socket.timeout("idle"), OSError("dead")])
    srv._serve_subscriber(conn)
    assert conn not in srv._subscribers  # removed via the finally


def test_serve_subscriber_peer_close_breaks_loop():
    srv = _server()
    srv._running = True
    conn = _FakeConn(recv_side_effect=[b""])  # b"" → peer closed cleanly
    srv._serve_subscriber(conn)
    assert conn not in srv._subscribers


# ── _accept_loop(): accept() raising a non-timeout OSError breaks the loop ──


class _FakeListener:
    def __init__(self, accept_side_effect):
        self._accept_side_effect = list(accept_side_effect)
        self.timeouts = []

    def settimeout(self, t):
        self.timeouts.append(t)

    def accept(self):
        item = self._accept_side_effect.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def test_accept_loop_breaks_on_oserror():
    srv = _server()
    srv._running = True
    listener = _FakeListener(accept_side_effect=[OSError("listener closed")])
    srv._accept_loop(listener, require_auth=False)  # must return, not hang/raise
    assert True  # reaching here proves the break fired


def test_accept_loop_busy_reject_swallows_close_oserror():
    srv = _server(max_connections=1)
    srv._running = True
    srv._conn_sem.acquire()  # fill the only slot so the next connection is "busy"
    busy_conn = _FakeConn(close_raises=OSError("already gone"))
    listener = _FakeListener(accept_side_effect=[(busy_conn, ("unix", 0)), OSError("stop loop")])
    srv._accept_loop(listener, require_auth=False)
    assert busy_conn.sent and b"server busy" in busy_conn.sent[0]
    assert busy_conn.closed is True


# ── serve_forever(): stale-socket removal / chmod / TCP-without-token ───────


def test_serve_forever_swallows_stale_socket_remove_oserror(monkeypatch):
    srv = _server()
    monkeypatch.setattr(socket_server.os.path, "exists", lambda p: True)
    monkeypatch.setattr(socket_server.os, "remove",
                         lambda p: (_ for _ in ()).throw(OSError("cannot remove")))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and not srv._running:
            time.sleep(0.02)
        assert srv._running is True  # survived the failed stale-file removal
    finally:
        srv.stop()
        t.join(timeout=2.0)


def test_serve_forever_swallows_chmod_oserror(monkeypatch):
    srv = _server()
    monkeypatch.setattr(socket_server.os, "chmod",
                         lambda p, mode: (_ for _ in ()).throw(OSError("cannot chmod")))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and not srv._running:
            time.sleep(0.02)
        assert srv._running is True  # survived the failed chmod
    finally:
        srv.stop()
        t.join(timeout=2.0)


def _free_tcp_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_serve_forever_tcp_requested_without_token_logs_and_skips_tcp():
    port = _free_tcp_port()
    srv = SocketServer(
        socket_path=_short_sock(),
        host="127.0.0.1", port=port, token=None,
        command_handler=lambda c, a: {"success": True},
        status_event_factory=lambda: {"type": "status"},
    )
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and not srv._running:
            time.sleep(0.02)
        assert srv._running is True
        assert len(srv._listeners) == 1, "no TCP listener should have been added without a token"
    finally:
        srv.stop()
        t.join(timeout=2.0)


# ── stop(): listener/server close() OSError is swallowed ────────────────────


def test_stop_swallows_listener_close_oserror():
    srv = _server()
    bad_listener = _FakeConn(close_raises=OSError("already closed"))
    srv._listeners = [bad_listener]
    srv.stop()  # must not raise
    assert srv._listeners == []


def test_stop_swallows_server_close_oserror():
    srv = _server()
    srv._server = _FakeConn(close_raises=OSError("already closed"))
    srv.stop()  # must not raise
    assert srv._server is None

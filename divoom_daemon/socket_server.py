"""Socket server for the Divoom daemon — Unix + TCP listeners, subscriber fan-out."""
from __future__ import annotations

import hmac
import logging
import os
import socket
import threading
import time
from typing import Callable, Optional

from divoom_daemon.daemon_protocol import (
    DEFAULT_SOCKET_PATH,
    SUBSCRIBE_COMMAND,
    encode_message,
    iter_messages,
)

logger = logging.getLogger("divoom_daemon.socket_server")

# Socket-hardening safety rails (untrusted/buggy clients + resource exhaustion).
# Sized for the largest legitimate frame — a base64 image blob shipped in a
# device_call — with headroom; oversized frames are rejected, not buffered.
DEFAULT_MAX_MESSAGE_BYTES = 16 * 1024 * 1024   # 16 MiB
DEFAULT_READ_DEADLINE = 30.0                   # total seconds to read ONE request
DEFAULT_MAX_CONNECTIONS = 32                   # concurrent handler threads
DEFAULT_MAX_SUBSCRIBERS = 16                   # concurrent event subscribers
SUBSCRIBER_IO_TIMEOUT = 5.0                    # bounded send/recv on a subscriber
                                               # socket — a passive (non-draining)
                                               # subscriber must not block broadcast()


class _RequestError(Exception):
    """A request was too large / too slow / malformed — reply + close, don't crash."""


class SocketServer:
    """Manages Unix + optional TCP listeners, accepts connections, dispatches commands,
    and broadcasts events to subscribers."""

    def __init__(
        self,
        socket_path: str = DEFAULT_SOCKET_PATH,
        *,
        host: Optional[str] = None,
        port: Optional[int] = None,
        token: Optional[str] = None,
        command_handler: Callable[[str, dict], dict],
        status_event_factory: Callable[[], dict],
        max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES,
        read_deadline: float = DEFAULT_READ_DEADLINE,
        max_connections: int = DEFAULT_MAX_CONNECTIONS,
        max_subscribers: int = DEFAULT_MAX_SUBSCRIBERS,
    ):
        self.socket_path = socket_path
        self.host = host
        self.port = port
        self.token = token
        self._command_handler = command_handler
        self._status_event_factory = status_event_factory
        self._listeners: list[socket.socket] = []
        self._subscribers: list[socket.socket] = []
        self._sub_lock = threading.Lock()
        self._server: Optional[socket.socket] = None
        self._running = False
        # Hardening rails.
        self._max_message_bytes = int(max_message_bytes)
        self._read_deadline = float(read_deadline)
        self._max_subscribers = int(max_subscribers)
        self._conn_sem = threading.BoundedSemaphore(max(1, int(max_connections)))

    # ── subscriber fan-out ───────────────────────────────────────────────
    def broadcast(self, event: dict) -> None:
        data = encode_message(event)
        with self._sub_lock:
            dead = []
            for conn in self._subscribers:
                try:
                    conn.sendall(data)
                except OSError:
                    dead.append(conn)
            for conn in dead:
                self._subscribers.remove(conn)
                try:
                    conn.close()
                except OSError:
                    pass

    def _add_subscriber(self, conn: socket.socket) -> bool:
        """Register a subscriber, or return False if the cap is reached (so a
        subscribe flood can't hold unbounded threads/sockets)."""
        with self._sub_lock:
            if len(self._subscribers) >= self._max_subscribers:
                return False
            self._subscribers.append(conn)
            return True

    def _remove_subscriber(self, conn: socket.socket) -> None:
        with self._sub_lock:
            if conn in self._subscribers:
                self._subscribers.remove(conn)

    # ── auth ─────────────────────────────────────────────────────────────
    def _authorized(self, req: dict) -> bool:
        if not self.token:
            return False
        supplied = req.get("token")
        return isinstance(supplied, str) and hmac.compare_digest(supplied, self.token)

    # ── connection handling ──────────────────────────────────────────────
    def _read_request_line(self, conn: socket.socket) -> bytes | None:
        """Read ONE NDJSON request line under a TOTAL deadline + a hard size cap.
        Returns the bytes, ``None`` on clean close, or raises ``_RequestError``
        when the client is too slow (slow-loris) or sends an oversized frame."""
        deadline = time.monotonic() + self._read_deadline
        buf = b""
        while b"\n" not in buf:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _RequestError("request read timed out")
            conn.settimeout(remaining)
            try:
                chunk = conn.recv(4096)
            except socket.timeout:
                # The per-recv timeout == remaining budget, so this IS the
                # total-deadline expiry (slow-loris) — reject, don't crash.
                raise _RequestError("request read timed out")
            if not chunk:
                return None
            buf += chunk
            if len(buf) > self._max_message_bytes:
                raise _RequestError("request exceeds max message size")
        return buf

    def _handle_conn(self, conn: socket.socket, *, require_auth: bool = False) -> None:
        try:
            try:
                buf = self._read_request_line(conn)
            except _RequestError as e:
                logger.warning("rejecting connection: %s", e)
                self._reply_safe(conn, {"success": False, "error": str(e)})
                return
            if buf is None:
                return
            msgs, _ = iter_messages(buf)
            if not msgs:
                return
            req = msgs[0]

            # H7: validate the request shape before it reaches a handler.
            command = req.get("command") if isinstance(req, dict) else None
            if not isinstance(command, str) or not command:
                self._reply_safe(conn, {"success": False, "error": "bad request: 'command' must be a non-empty string"})
                return
            args = req.get("args")
            if not isinstance(args, dict):
                args = {}

            if require_auth and not self._authorized(req):
                self._reply_safe(conn, {"success": False, "error": "unauthorized"})
                return

            if command == SUBSCRIBE_COMMAND:
                self._serve_subscriber(conn)
                return

            # H4: a handler bug must not crash the thread or strand the client.
            try:
                reply = self._command_handler(command, args)
            except Exception:
                logger.exception("command handler %r raised", command)
                reply = {"success": False, "error": "internal error"}
            self._reply_safe(conn, reply)
        except OSError as e:
            logger.debug(f"conn error: {e}")
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _serve_subscriber(self, conn: socket.socket) -> None:
        if not self._add_subscriber(conn):
            logger.warning("subscriber limit reached; rejecting subscribe")
            self._reply_safe(conn, {"success": False, "error": "subscriber limit reached"})
            return
        # Bounded (not None): broadcast() does sendall() on this socket while
        # holding _sub_lock. A passive subscriber whose recv window fills would
        # otherwise block that sendall FOREVER — freezing the whole event fan-out
        # and notification routing. With a timeout, a wedged sendall raises
        # socket.timeout (OSError) → broadcast drops it as dead. Here, recv
        # timeouts just mean "idle", so we loop rather than disconnect.
        conn.settimeout(SUBSCRIBER_IO_TIMEOUT)
        try:
            conn.sendall(encode_message(self._status_event_factory()))
            while self._running:
                try:
                    if not conn.recv(4096):
                        break                  # b"" → peer closed
                except socket.timeout:
                    continue                   # idle but alive
        except OSError:
            pass
        finally:
            self._remove_subscriber(conn)

    @staticmethod
    def _reply_safe(conn: socket.socket, reply: dict) -> None:
        try:
            conn.sendall(encode_message(reply))
        except OSError:
            pass

    def _accept_loop(self, listener: socket.socket, *, require_auth: bool) -> None:
        while self._running:
            listener.settimeout(1.0)
            try:
                conn, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            # H5: bound concurrent handlers; reject (don't block the accept loop)
            # when full so a connection flood can't exhaust threads/memory.
            if not self._conn_sem.acquire(blocking=False):
                logger.warning("connection limit reached; rejecting new connection")
                self._reply_safe(conn, {"success": False, "error": "server busy"})
                try:
                    conn.close()
                except OSError:
                    pass
                continue
            threading.Thread(
                target=self._handle_conn_guarded, args=(conn,),
                kwargs={"require_auth": require_auth}, daemon=True,
            ).start()

    def _handle_conn_guarded(self, conn: socket.socket, *, require_auth: bool) -> None:
        try:
            self._handle_conn(conn, require_auth=require_auth)
        finally:
            self._conn_sem.release()

    # ── lifecycle ────────────────────────────────────────────────────────
    def serve_forever(self) -> None:
        if os.path.exists(self.socket_path):
            try:
                os.remove(self.socket_path)
            except OSError:
                pass
        # Bind + listen on a LOCAL socket first, then publish it. A concurrent
        # stop() (e.g. a test that calls d.stop() while this setup is still in
        # flight on the daemon thread) could otherwise null self._server between
        # bind and listen → "NoneType has no attribute 'listen'", the socket
        # never comes up, and clients get "Connection refused" (flaky CI).
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(self.socket_path)
        # H1: restrict the socket to the owning user — it drives the BLE device
        # and exposes notification content, so any local user connecting is a
        # privilege boundary. bind() honours only the umask, so chmod explicitly.
        try:
            os.chmod(self.socket_path, 0o600)
        except OSError as e:
            logger.warning("could not restrict socket perms on %s: %s", self.socket_path, e)
        server.listen(8)
        self._server = server
        self._listeners = [server]
        self._running = True
        logger.info(f"Divoom daemon listening on {self.socket_path}")

        tcp = None
        if self.host and self.port:
            if not self.token:
                logger.error("TCP listener requested without a token; refusing to "
                             "expose the daemon unauthenticated. Set DIVOOM_DAEMON_TOKEN "
                             "or pass --token.")
            else:
                tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                tcp.bind((self.host, int(self.port)))
                tcp.listen(8)
                self._listeners.append(tcp)
                logger.info(f"Divoom daemon listening on tcp://{self.host}:{self.port} (token required)")

        try:
            if tcp is not None:
                threading.Thread(target=self._accept_loop, args=(tcp,),
                                 kwargs={"require_auth": True}, daemon=True,
                                 name="daemon-tcp-accept").start()
            self._accept_loop(self._server, require_auth=False)
        finally:
            self.stop()

    def stop(self) -> None:
        self._running = False
        for lst in self._listeners:
            try:
                lst.close()
            except OSError:
                pass
        self._listeners = []
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass
            self._server = None

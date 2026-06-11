"""Socket server for the Divoom daemon — Unix + TCP listeners, subscriber fan-out."""
from __future__ import annotations

import hmac
import logging
import os
import socket
import threading
from typing import Callable, Optional

from divoom_daemon.daemon_protocol import (
    DEFAULT_SOCKET_PATH,
    SUBSCRIBE_COMMAND,
    encode_message,
    iter_messages,
)

logger = logging.getLogger("divoom_daemon.socket_server")


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

    def _add_subscriber(self, conn: socket.socket) -> None:
        with self._sub_lock:
            self._subscribers.append(conn)

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
    def _handle_conn(self, conn: socket.socket, *, require_auth: bool = False) -> None:
        try:
            conn.settimeout(5.0)
            buf = b""
            while b"\n" not in buf:
                chunk = conn.recv(4096)
                if not chunk:
                    conn.close()
                    return
                buf += chunk
            msgs, _ = iter_messages(buf)
            if not msgs:
                conn.close()
                return
            req = msgs[0]
            command = req.get("command")
            args = req.get("args", {}) or {}

            if require_auth and not self._authorized(req):
                try:
                    conn.sendall(encode_message({"success": False, "error": "unauthorized"}))
                except OSError:
                    pass
                conn.close()
                return

            if command == SUBSCRIBE_COMMAND:
                conn.settimeout(None)
                self._add_subscriber(conn)
                try:
                    conn.sendall(encode_message(self._status_event_factory()))
                    while self._running:
                        if not conn.recv(4096):
                            break
                finally:
                    self._remove_subscriber(conn)
                    conn.close()
                return

            reply = self._command_handler(command, args)
            conn.sendall(encode_message(reply))
            conn.close()
        except OSError as e:
            logger.debug(f"conn error: {e}")
            try:
                conn.close()
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
            threading.Thread(
                target=self._handle_conn, args=(conn,),
                kwargs={"require_auth": require_auth}, daemon=True,
            ).start()

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

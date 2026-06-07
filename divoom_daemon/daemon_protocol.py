"""Wire protocol for the headless daemon (R16) — pure + testable, no AppKit/BLE.

The daemon owns the device + the macOS notification monitor and exposes a Unix
socket. Two interaction modes share one connection grammar:

  * request/response  — client sends one ``{"command","args"}`` line, reads one
    ``{"success",...}`` line, closes.
  * subscribe/stream  — client sends ``{"command":"subscribe"}``; the daemon then
    streams newline-delimited JSON *events* on the held-open connection until the
    client disconnects.

All messages are newline-delimited JSON ("NDJSON"): one compact JSON object per
line. This module has the framing, the message/event shapes, and a thin client.
The server lives in ``divoom_daemon/daemon.py``; clients are the menubar + the GUI.
"""
from __future__ import annotations

import json
import socket
from typing import Any, Callable, Iterable

DEFAULT_SOCKET_PATH = "/tmp/divoom.sock"

# Event types streamed to subscribers.
EVENT_STATUS = "status"
EVENT_NOTIFICATION = "notification"

SUBSCRIBE_COMMAND = "subscribe"


# ── framing ─────────────────────────────────────────────────────────────
def encode_message(obj: dict) -> bytes:
    """One NDJSON line (compact JSON + '\\n')."""
    return (json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8")


def iter_messages(buffer: bytes) -> tuple[list[dict], bytes]:
    """Split a byte buffer into complete JSON messages + the trailing remainder.

    Returns ``(messages, remainder)``. Blank lines are skipped; a malformed line
    is skipped (not raised) so one bad frame can't wedge the stream.
    """
    messages: list[dict] = []
    *lines, remainder = buffer.split(b"\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            messages.append(json.loads(line.decode("utf-8")))
        except (ValueError, UnicodeDecodeError):
            continue
    return messages, remainder


# ── message/event constructors ──────────────────────────────────────────
def make_request(command: str, args: dict | None = None) -> dict:
    return {"command": command, "args": args or {}}


def make_status_event(state: str, counters: dict | None = None) -> dict:
    return {"type": EVENT_STATUS, "state": state, "counters": counters or {}}


def make_notification_event(app_type: int, title: str, body: str, routed: bool) -> dict:
    return {
        "type": EVENT_NOTIFICATION,
        "app_type": int(app_type),
        "title": title,
        "body": body,
        "routed": bool(routed),
    }


# ── client ──────────────────────────────────────────────────────────────
class DaemonClient:
    """Thin Unix-socket client. Used by the menubar + GUI to talk to the daemon.

    Never raises on a missing/closed daemon — `send_command` returns an error
    dict and `subscribe` returns cleanly. The daemon being absent is a normal
    state (it may not be launched yet).
    """

    def __init__(self, socket_path: str = DEFAULT_SOCKET_PATH, timeout: float = 2.0):
        self.socket_path = socket_path
        self.timeout = timeout

    def send_command(self, command: str, args: dict | None = None) -> dict:
        """One-shot request/response. Returns the daemon's reply dict, or
        ``{"success": False, "error": ...}`` if the daemon isn't reachable."""
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(self.timeout)
                s.connect(self.socket_path)
                s.sendall(encode_message(make_request(command, args)))
                buf = b""
                while b"\n" not in buf:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                msgs, _ = iter_messages(buf)
                return msgs[0] if msgs else {"success": False, "error": "no reply"}
        except (OSError, ValueError) as e:
            return {"success": False, "error": str(e)}

    def device_call(self, method: str, args: list | None = None,
                    kwargs: dict | None = None) -> dict:
        """Proxy a device method through the daemon (R17 P5): the daemon owns the
        BLE connection and runs ``divoom.<method>(*args, **kwargs)``. Returns the
        daemon reply ``{"success", "result"|"error"}``."""
        return self.send_command("device_call", {
            "method": method, "args": args or [], "kwargs": kwargs or {},
        })

    def subscribe(
        self,
        on_event: Callable[[dict], None],
        *,
        should_stop: Callable[[], bool] | None = None,
    ) -> bool:
        """Open a streaming subscription, calling ``on_event(event)`` for each
        event until the connection closes or ``should_stop()`` returns True.
        Returns True if it connected, False if the daemon was unreachable.
        Blocking — callers run it on their own thread.
        """
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(self.timeout)
                s.connect(self.socket_path)
                s.sendall(encode_message(make_request(SUBSCRIBE_COMMAND)))
                s.settimeout(1.0)  # short read timeout so should_stop() is responsive
                buf = b""
                while True:
                    if should_stop is not None and should_stop():
                        return True
                    try:
                        chunk = s.recv(4096)
                    except socket.timeout:
                        continue
                    if not chunk:
                        return True  # daemon closed the stream
                    buf += chunk
                    events, buf = iter_messages(buf)
                    for ev in events:
                        on_event(ev)
        except (OSError, ValueError):
            return False

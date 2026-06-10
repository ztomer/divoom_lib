"""Shared logic for the menubar's notification-status display (R15 §6).

This module has **no AppKit/PyObjC dependency** so the pure logic
(status derivation, title/colour formatting, the "Open Notifications" launch
command, and the daemon client) is testable on any platform and in CI.
"""
from __future__ import annotations

import json
import socket
from typing import Any, Callable

from divoom_daemon.daemon_protocol import (
    DaemonClient,
    DEFAULT_SOCKET_PATH,
    EVENT_STATUS,
    EVENT_SHUTDOWN,
    make_request,
    encode_message,
    iter_messages,
)


# Status-item title state suffixes.
STATE_ACTIVE = "active"
STATE_IDLE = "idle"
STATE_ERROR = "error"
_VALID_STATES = (STATE_ACTIVE, STATE_IDLE, STATE_ERROR)

_BASE_TITLE = "Divoom"

# Colour tints, reusing the R14 §3 status-pill palette.
#   active -> green, idle -> muted grey, error -> amber.
STATE_COLORS = {
    STATE_ACTIVE: "#5ede91",
    STATE_IDLE: "#8c8c8c",   # opaque equivalent of rgba(255,255,255,0.55) on a bar
    STATE_ERROR: "#ffc864",
}


def derive_state(status: dict | None) -> str:
    """Map a notification-listener status dict to one of the three states.

    Accepts the dict shape from daemon's `notification_status` event
    (``{state, counters}``) or a raw listener status
    (``{running, error, platform_supported, ...}``). Unknown/empty -> idle.
    """
    if not status:
        return STATE_IDLE
    if isinstance(status.get("state"), str) and status["state"] in _VALID_STATES:
        return status["state"]
    if status.get("error"):
        return STATE_ERROR
    if status.get("platform_supported") is False:
        return STATE_IDLE
    return STATE_ACTIVE if status.get("running") else STATE_IDLE


def format_status_title(state: str) -> str:
    """`active` -> 'Divoom (active)'. Unknown states fall back to idle."""
    s = state if state in _VALID_STATES else STATE_IDLE
    return f"{_BASE_TITLE} ({s})"


def status_color(state: str) -> str:
    """Hex tint for the status-item title; idle for unknown states."""
    return STATE_COLORS.get(state, STATE_COLORS[STATE_IDLE])


def hex_to_rgb01(hex_color: str) -> tuple[float, float, float]:
    """'#5ede91' -> (0.36.., 0.87.., 0.56..) floats in [0,1] for NSColor."""
    if not hex_color.startswith("#"):
        raise ValueError(f"expected #RRGGBB, got {hex_color!r}")
    h = hex_color[1:]
    if len(h) != 6:
        raise ValueError(f"expected #RRGGBB, got {hex_color!r}")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return (r / 255.0, g / 255.0, b / 255.0)


def open_notifications_command(python: str, gui_main_path: str) -> list[str]:
    """argv to launch the GUI focused on Live Widgets -> Notifications."""
    return [python, gui_main_path, "--tab", "data-sources", "--card", "notifications"]


class MenubarClient:
    """Thin daemon client specialized for the menubar.

    Connects to the daemon over Unix socket (or TCP via env), subscribes to
    status/notification events, and exposes a small surface for the Cocoa
    menu actions.
    """

    def __init__(
        self,
        socket_path: str = DEFAULT_SOCKET_PATH,
        timeout: float = 2.0,
        *,
        host: str | None = None,
        port: int | None = None,
        token: str | None = None,
    ):
        self._client = DaemonClient(socket_path, timeout, host=host, port=port, token=token)
        self._subscribe_thread = None
        self._running = False
        self._status = {"state": STATE_IDLE, "counters": {}}
        self._on_status_change: Callable[[dict], None] | None = None
        self._on_shutdown: Callable[[], None] | None = None  # R40 §9

    def start(self) -> bool:
        """Start the subscription thread. Returns True if daemon reachable."""
        if self._running:
            return True
        self._running = True
        self._subscribe_thread = self._run_subscribe()
        return self._subscribe_thread is not None

    def stop(self) -> None:
        self._running = False
        if self._subscribe_thread and self._subscribe_thread.is_alive():
            self._subscribe_thread.join(timeout=1.0)

    def _run_subscribe(self):
        import threading
        t = threading.Thread(target=self._subscribe_loop, daemon=True)
        t.start()
        return t

    def _subscribe_loop(self) -> None:
        def on_event(ev: dict) -> None:
            etype = ev.get("type")
            if etype == EVENT_STATUS:
                state = derive_state(ev)
                self._status = {"state": state, "counters": ev.get("counters", {})}
                if "error" in ev:
                    self._status["error"] = ev["error"]
                if self._on_status_change:
                    self._on_status_change(self._status)
            elif etype == EVENT_SHUTDOWN:
                # R40 §9: daemon is stopping — let the agent decide whether to follow.
                if self._on_shutdown:
                    self._on_shutdown()

        self._client.subscribe(on_event, should_stop=lambda: not self._running)

    def set_status_callback(self, cb: Callable[[dict], None]) -> None:
        self._on_status_change = cb

    def set_shutdown_callback(self, cb: Callable[[], None]) -> None:
        self._on_shutdown = cb

    # ── device commands (proxied through daemon) ────────────────────────

    def device_call(self, method: str, args: list | None = None,
                    kwargs: dict | None = None, *, target: str = "device") -> dict:
        return self._client.device_call(method, args, kwargs, target=target)

    def connect_device(self, *, mac: str | None = None, lan_ip: str | None = None,
                       device_name: str | None = None,
                       use_ios_le_protocol: bool = True) -> dict:
        return self._client.connect_device(
            mac=mac, lan_ip=lan_ip, device_name=device_name,
            use_ios_le_protocol=use_ios_le_protocol,
        )

    def disconnect_device(self) -> dict:
        return self._client.disconnect_device()

    def device_status(self) -> dict:
        return self._client.device_status()

    # ── notification listener (via daemon) ──────────────────────────────

    def start_notifications(self) -> dict:
        return self._client.send_command("start_notifications")

    def stop_notifications(self) -> dict:
        return self._client.send_command("stop_notifications")

    def notification_status(self) -> dict:
        return self._client.send_command("notification_status")

    @property
    def status(self) -> dict:
        return self._status.copy()

    @property
    def is_remote(self) -> bool:
        return self._client.is_remote

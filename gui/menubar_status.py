"""Import-safe helpers for the menubar's notification-status display (R15 §6).

This module deliberately has **no AppKit/PyObjC dependency** so the pure logic
(status derivation, title/colour formatting, the "Open Notifications" launch
command, and the GUI->menubar push client) is testable on any platform and in
CI. `gui/menubar.py` (which is macOS-only) imports from here.

Design: the menubar does NOT poll. The GUI process pushes a status message over
the existing Unix socket *only when* the notification listener starts, stops, or
errors (the user rejected background polling). See `push_notification_status`.
"""
from __future__ import annotations

import json
import socket
from typing import Any

SOCKET_PATH = "/tmp/divoom.sock"

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

    Accepts the dict shape from `gui_api.get_notification_listener_status`
    (``{running, error, platform_supported, ...}``) or a already-reduced
    ``{state: ...}`` form. Unknown/empty -> idle.
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
    h = hex_color.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"expected #RRGGBB, got {hex_color!r}")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return (r / 255.0, g / 255.0, b / 255.0)


def open_notifications_command(python: str, gui_main_path: str) -> list[str]:
    """argv to launch the GUI focused on Live Widgets -> Notifications."""
    return [python, gui_main_path, "--tab", "data-sources", "--card", "notifications"]


def push_notification_status(
    state: str,
    counters: dict | None = None,
    *,
    socket_path: str = SOCKET_PATH,
    timeout: float = 1.0,
) -> bool:
    """Best-effort push of the listener status to the menubar's Unix socket.

    Returns True if the message was sent (and ideally acked). Never raises —
    if the menubar agent isn't running, this is a silent no-op returning False.
    """
    payload = {
        "command": "notification_status",
        "args": {"state": state, "counters": counters or {}},
    }
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(socket_path)
            s.sendall(json.dumps(payload).encode("utf-8"))
            try:
                s.recv(4096)  # drain the ack; ignore contents
            except OSError:
                pass
        return True
    except (OSError, ValueError) as e:  # socket missing / refused / bad path
        return False


def build_status_payload(status: dict | None) -> dict[str, Any]:
    """Reduce a rich listener status dict to the menubar's stored shape."""
    return {
        "state": derive_state(status),
        "counters": (status or {}).get("counters", {}) or {},
    }

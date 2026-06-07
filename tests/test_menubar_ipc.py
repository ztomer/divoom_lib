"""R15 §6 — menubar notification status (event-driven, no polling).

Tests the AppKit-free helpers in gui/menubar_status.py plus the GUI->menubar
push over a real (temp) Unix socket. menubar.py itself imports AppKit and is
macOS-only, so it is NOT imported here — all the testable logic lives in
menubar_status.py by design.
"""
import json
import socket
import sys
import threading
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "gui"))

from divoom_daemon.menubar_status import (
    STATE_ACTIVE, STATE_IDLE, STATE_ERROR,
    derive_state, format_status_title, status_color, hex_to_rgb01,
    open_notifications_command, push_notification_status, build_status_payload,
)


# ── derive_state / build_status_payload (status shape) ──────────────────
@pytest.mark.parametrize("status,expected", [
    ({"running": True}, STATE_ACTIVE),
    ({"running": False}, STATE_IDLE),
    ({"running": False, "error": "boom"}, STATE_ERROR),
    ({"running": True, "error": "boom"}, STATE_ERROR),       # error wins
    ({"platform_supported": False, "running": False}, STATE_IDLE),
    ({"state": STATE_ACTIVE}, STATE_ACTIVE),                 # pre-reduced form
    (None, STATE_IDLE),
    ({}, STATE_IDLE),
])
def test_derive_state(status, expected):
    assert derive_state(status) == expected


def test_build_status_payload_shape():
    p = build_status_payload({"running": True, "counters": {"seen": 3, "routed": 1, "dropped": 0}})
    assert p == {"state": STATE_ACTIVE, "counters": {"seen": 3, "routed": 1, "dropped": 0}}
    assert build_status_payload(None) == {"state": STATE_IDLE, "counters": {}}


# ── title formatting + colour ───────────────────────────────────────────
def test_format_status_title():
    assert format_status_title(STATE_ACTIVE) == "Divoom (active)"
    assert format_status_title(STATE_IDLE) == "Divoom (idle)"
    assert format_status_title(STATE_ERROR) == "Divoom (error)"
    assert format_status_title("garbage") == "Divoom (idle)"  # fallback


def test_status_color_and_rgb():
    assert status_color(STATE_ACTIVE) == "#5ede91"
    assert status_color("garbage") == status_color(STATE_IDLE)
    r, g, b = hex_to_rgb01("#5ede91")
    assert (round(r, 3), round(g, 3), round(b, 3)) == (0.369, 0.871, 0.569)
    with pytest.raises(ValueError):
        hex_to_rgb01("nope")


# ── "Open Notifications..." launch command ──────────────────────────────
def test_open_notifications_command():
    cmd = open_notifications_command("/usr/bin/python3", "/x/gui_main.py")
    assert cmd == ["/usr/bin/python3", "/x/gui_main.py",
                   "--tab", "data-sources", "--card", "notifications"]


# ── GUI -> menubar push over a real Unix socket ─────────────────────────
def _fake_server(sock_path, received):
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock_path)
    srv.listen(1)
    srv.settimeout(5.0)
    conn, _ = srv.accept()
    data = conn.recv(4096)
    received.append(json.loads(data.decode("utf-8")))
    conn.sendall(json.dumps({"success": True}).encode("utf-8"))
    conn.close()
    srv.close()


def test_push_notification_status_roundtrip():
    # AF_UNIX paths are limited to ~104 chars, so use a short /tmp path
    # (pytest's tmp_path under /var/folders is too long on macOS).
    import os
    sock_path = f"/tmp/divoom_test_{os.getpid()}.sock"
    if os.path.exists(sock_path):
        os.remove(sock_path)
    received = []
    t = threading.Thread(target=_fake_server, args=(sock_path, received), daemon=True)
    t.start()
    import time
    time.sleep(0.1)
    try:
        ok = push_notification_status(STATE_ACTIVE, {"seen": 2}, socket_path=sock_path)
        t.join(timeout=5.0)
    finally:
        if os.path.exists(sock_path):
            os.remove(sock_path)
    assert ok is True
    assert received and received[0]["command"] == "notification_status"
    assert received[0]["args"]["state"] == STATE_ACTIVE
    assert received[0]["args"]["counters"] == {"seen": 2}


def test_push_notification_status_no_server_is_silent():
    # Nothing listening -> returns False, never raises.
    assert push_notification_status(STATE_IDLE, socket_path="/tmp/divoom_nope_xyz.sock") is False

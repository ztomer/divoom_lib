"""Tests for the menubar client logic (R15 §6)."""
from __future__ import annotations

from divoom_menubar.menubar_client import (
    derive_state,
    format_status_title,
    status_color,
    hex_to_rgb01,
    STATE_ACTIVE,
    STATE_IDLE,
    STATE_ERROR,
)


def test_derive_state_from_daemon_event():
    # Daemon status event shape: {state: "active", counters: {...}}
    assert derive_state({"state": "active", "counters": {}}) == STATE_ACTIVE
    assert derive_state({"state": "idle", "counters": {}}) == STATE_IDLE
    assert derive_state({"state": "error", "counters": {}}) == STATE_ERROR
    assert derive_state({"state": "unknown", "counters": {}}) == STATE_IDLE


def test_derive_state_from_raw_listener_status():
    # Raw listener status shape from get_notification_listener_status
    assert derive_state({"running": True, "error": None, "platform_supported": True}) == STATE_ACTIVE
    assert derive_state({"running": False, "error": None, "platform_supported": True}) == STATE_IDLE
    assert derive_state({"running": True, "error": "some error"}) == STATE_ERROR
    assert derive_state({"running": False, "platform_supported": False}) == STATE_IDLE
    assert derive_state({}) == STATE_IDLE
    assert derive_state(None) == STATE_IDLE


def test_format_status_title():
    assert format_status_title("active") == "Divoom (active)"
    assert format_status_title("idle") == "Divoom (idle)"
    assert format_status_title("error") == "Divoom (error)"
    assert format_status_title("unknown") == "Divoom (idle)"


def test_status_color():
    assert status_color("active") == "#5ede91"
    assert status_color("idle") == "#8c8c8c"
    assert status_color("error") == "#ffc864"
    assert status_color("unknown") == "#8c8c8c"


def test_hex_to_rgb01():
    r, g, b = hex_to_rgb01("#5ede91")
    assert 0 <= r <= 1 and 0 <= g <= 1 and 0 <= b <= 1
    assert abs(r - (94/255)) < 0.01
    assert abs(g - (222/255)) < 0.01
    assert abs(b - (145/255)) < 0.01


def test_hex_to_rgb01_invalid():
    try:
        hex_to_rgb01("#abc")
        assert False, "should raise"
    except ValueError:
        pass
    try:
        hex_to_rgb01("5ede91")
        assert False, "should raise"
    except ValueError:
        pass

def _png_data_url(size=8, color=(94, 222, 145)):
    """A real tiny PNG as a data URL (the shape the GUI sends)."""
    import base64
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (size, size), color).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def test_menu_thumbnail_decodes_png_data_url():
    """R50: a PNG data URL decodes to a sized NSImage for the menubar tile."""
    import pytest
    pytest.importorskip("AppKit")
    from divoom_menubar.menubar import _menu_thumbnail
    img = _menu_thumbnail(_png_data_url(), size=18)
    assert img is not None
    assert round(img.size().width) == 18 and round(img.size().height) == 18


def test_menu_thumbnail_rejects_non_png_and_garbage():
    """R50: SVG/empty/garbage previews return None so the caller falls back to
    the SF Symbol glyph (the thumbnail can only improve the tile, never regress)."""
    import pytest
    pytest.importorskip("AppKit")
    from divoom_menubar.menubar import _menu_thumbnail
    assert _menu_thumbnail(None) is None
    assert _menu_thumbnail("") is None
    assert _menu_thumbnail("data:image/svg+xml;utf8,<svg/>") is None        # no base64
    assert _menu_thumbnail("data:image/png;base64,not-real-bytes") is None  # invalid

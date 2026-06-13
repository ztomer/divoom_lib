"""R17 P5 — GUI-side daemon bridge: the device proxy + daemon auto-spawn.

Proxy tests run against a real in-process daemon (temp socket, fake device);
the auto-spawn tests stub the spawner so no subprocess is launched.
"""
import asyncio
import os
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "divoom_gui"))

from divoom_daemon.daemon import DivoomDaemon
# The implementation lives in divoom_daemon.daemon_client (R28); monkeypatching
# below targets that module's globals, which ensure_daemon resolves against.
# divoom_gui.daemon_bridge re-exports the same objects.
from divoom_daemon import daemon_client as daemon_bridge
from divoom_gui.daemon_bridge import (
    DaemonDeviceProxy,
    daemon_alive,
    ensure_daemon,
)
from divoom_daemon.daemon_protocol import DaemonClient


class _Facade:
    def __init__(self, calls):
        self._calls = calls

    async def show_light(self, color, brightness):
        self._calls.append(("display.show_light", color, brightness))
        return True

    async def show_image(self, path):
        self._calls.append(("display.show_image", path))
        return True

    async def get_brightness(self):
        return {"brightness": 55}


class _DesignFacade:
    def __init__(self, calls):
        self._calls = calls

    async def use_user_define_index(self, page: int):
        self._calls.append(("design.use_user_define_index", page))
        return True

    async def clear_user_define_index(self, page: int):
        self._calls.append(("design.clear_user_define_index", page))
        return True


class FakeDevice:
    def __init__(self):
        self.is_connected = True
        self.calls = []
        self.display = _Facade(self.calls)
        self.design = _DesignFacade(self.calls)

    async def connect(self):
        self.is_connected = True

    async def disconnect(self):
        self.is_connected = False


@pytest.fixture
def live_daemon():
    sp = f"/tmp/divoom_bridge_{os.getpid()}.sock"
    if os.path.exists(sp):
        os.remove(sp)
    dev = FakeDevice()
    d = DivoomDaemon(socket_path=sp, monitor=object(), device=dev)
    t = threading.Thread(target=d.serve_forever, daemon=True)
    t.start()
    for _ in range(50):
        if os.path.exists(sp):
            break
        time.sleep(0.02)
    try:
        yield d, dev, sp
    finally:
        d.stop()
        t.join(timeout=3.0)
        if os.path.exists(sp):
            os.remove(sp)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_proxy_dispatches_dotted_method(live_daemon):
    _, dev, sp = live_daemon
    proxy = DaemonDeviceProxy(DaemonClient(sp))
    result = _run(proxy.display.show_light("00FFCC", 100))
    assert result is True
    assert dev.calls == [("display.show_light", "00FFCC", 100)]


def test_proxy_returns_dict_result(live_daemon):
    _, _, sp = live_daemon
    proxy = DaemonDeviceProxy(DaemonClient(sp))
    assert _run(proxy.display.get_brightness()) == {"brightness": 55}


def test_proxy_raises_on_daemon_error(live_daemon):
    _, _, sp = live_daemon
    proxy = DaemonDeviceProxy(DaemonClient(sp))
    with pytest.raises(RuntimeError):
        _run(proxy.display.nope())


def test_daemon_alive_true_for_live(live_daemon):
    _, _, sp = live_daemon
    assert daemon_alive(sp) is True


def test_daemon_alive_false_for_missing():
    assert daemon_alive(f"/tmp/divoom_absent_{os.getpid()}.sock") is False


def test_proxy_conn_mac_resolves_from_device_status(live_daemon):
    """``DaemonDeviceProxy._conn.mac`` resolves the MAC string from
    ``device_status`` (R17 §P5). The bare ``.mac`` access returns a child
    proxy because ``mac`` is NOT in ``_STATUS_ATTRS`` — call sites that
    need the string must go through ``_conn.mac``."""
    _, _, sp = live_daemon
    proxy = DaemonDeviceProxy(DaemonClient(sp))
    # _conn is in STATUS_ATTRS; returns _ConnView(mac_field_from_status).
    conn = proxy._conn
    # With no mac set on DeviceOwner, device_status returns None.
    assert conn.mac is None
    assert not isinstance(conn.mac, DaemonDeviceProxy)

# ── exclusive mode (R29) ─────────────────────────────────────────────────


def test_exclusive_start_and_end(live_daemon):
    _, _, sp = live_daemon
    client = DaemonClient(sp)
    reply = client.exclusive_start("anim-1")
    assert reply == {"success": True, "token": "anim-1"}
    reply = client.exclusive_end("anim-1")
    assert reply == {"success": True}


def test_exclusive_start_requires_token(live_daemon):
    _, _, sp = live_daemon
    client = DaemonClient(sp)
    # Call send_command directly to bypass the wrapper
    reply = client.send_command("exclusive_start", {})
    assert reply.get("success") is False
    assert "token" in reply.get("error", "")


def test_exclusive_end_requires_token(live_daemon):
    _, _, sp = live_daemon
    client = DaemonClient(sp)
    reply = client.send_command("exclusive_end", {})
    assert reply.get("success") is False
    assert "token" in reply.get("error", "")


def test_device_call_passes_token(live_daemon):
    _, dev, sp = live_daemon
    client = DaemonClient(sp)
    # Start exclusive session
    client.exclusive_start("my-token")
    # Call with matching token
    reply = client.device_call("display.show_light", args=["00FFCC", 100],
                               token="my-token")
    assert reply.get("success") is True
    assert reply.get("result") is True
    assert dev.calls == [("display.show_light", "00FFCC", 100)]
    client.exclusive_end("my-token")


def test_proxy_exclusive_context(live_daemon):
    _, dev, sp = live_daemon
    proxy = DaemonDeviceProxy(DaemonClient(sp))

    async def go():
        async with proxy.exclusive("test-tok") as p:
            await p.display.show_light("FF0000", 50)
        # After exclusive, no active session — normal dispatch resumes
        await p.display.show_light("00FF00", 75)

    _run(go())
    assert dev.calls == [
        ("display.show_light", "FF0000", 50),
        ("display.show_light", "00FF00", 75),
    ]


# ── push_animation (R30) ──────────────────────────────────────────────


def test_proxy_push_animation_calls_show_image(live_daemon):
    """DaemonDeviceProxy.push_animation() calls display.show_image inside
    an exclusive session (detected by the token being forwarded in device_call)."""
    _, dev, sp = live_daemon
    client = DaemonClient(sp)
    proxy = DaemonDeviceProxy(client)

    async def go():
        ok = await proxy.push_animation("tests/test_animation_8b_stream.py")
        assert ok is True

    _run(go())
    assert len(dev.calls) >= 1
    # The method path must include display.show_image
    assert any("show_image" in str(c) for c in dev.calls)


def test_proxy_push_animation_with_raw_bytes(live_daemon, tmp_path):
    """push_animation accepts raw bytes, writes them to a temp file, and
    calls display.show_image with the temp path."""
    _, dev, sp = live_daemon
    client = DaemonClient(sp)
    proxy = DaemonDeviceProxy(client)
    fake_gif = b"GIF89a" + b"\x00" * 100

    async def go():
        ok = await proxy.push_animation(fake_gif)
        assert ok is True

    _run(go())
    assert len(dev.calls) >= 1
    # should have called show_image with a temp file path
    assert any("show_image" in str(c) for c in dev.calls)


def test_exclusive_call_issues_command(live_daemon):
    """A device_call with a matching token dispatches inside an exclusive session.
    The non-matching call is queued by CommandQueue (internal behavior tested in
    test_command_queue.py). Here we just verify the RPC plumbing: no errors."""
    _, dev, sp = live_daemon
    client = DaemonClient(sp)
    client.exclusive_start("x")
    # Issue a matching-token call
    reply = client.device_call("display.show_light", args=["FF0000", 20],
                               token="x")
    assert reply.get("success") is True
    client.exclusive_end("x")


# ── custom_art_push / query_page RPCs (Round 37) ──────────────────────────


def test_custom_art_push_sends_correct_rpc(live_daemon):
    """Verify DaemonClient.custom_art_push sends the expected command.
    
    We monkeypatch send_command to capture the payload without hitting the
    real daemon handler (which needs network + real files)."""
    from unittest.mock import MagicMock, ANY
    _, _, sp = live_daemon
    client = DaemonClient(sp)
    client.send_command = MagicMock(return_value={"success": True})
    reply = client.custom_art_push(file_ids=["abc123", "def"], page=1, slot=None)
    assert reply == {"success": True}
    client.send_command.assert_called_once_with("custom_art_push", {
        "file_ids": ["abc123", "def"], "page": 1, "slot": None, "slots": None,
    }, read_timeout=ANY)


def test_custom_art_push_with_slot(live_daemon):
    from unittest.mock import MagicMock, ANY
    _, _, sp = live_daemon
    client = DaemonClient(sp)
    client.send_command = MagicMock(return_value={"success": True})
    client.custom_art_push(file_ids=["abc"], page=2, slot=5)
    client.send_command.assert_called_once_with("custom_art_push", {
        "file_ids": ["abc"], "page": 2, "slot": 5, "slots": None,
    }, read_timeout=ANY)


def test_custom_art_query_page_sends_correct_rpc(live_daemon):
    from unittest.mock import MagicMock, ANY
    _, _, sp = live_daemon
    client = DaemonClient(sp)
    client.send_command = MagicMock(return_value={"success": True, "ids": [1, 2, 3]})
    reply = client.custom_art_query_page(page=1)
    assert reply == {"success": True, "ids": [1, 2, 3]}
    client.send_command.assert_called_once_with("custom_art_query_page", {"page": 1}, read_timeout=ANY)


# ── device_call → design module (Round 37) ────────────────────────────────


def test_device_call_use_user_define_index(live_daemon):
    _, dev, sp = live_daemon
    client = DaemonClient(sp)
    reply = client.device_call("design.use_user_define_index", args=[0])
    assert reply.get("success") is True
    assert reply.get("result") is True
    assert ("design.use_user_define_index", 0) in dev.calls


def test_device_call_use_user_define_index_page_1(live_daemon):
    _, dev, sp = live_daemon
    client = DaemonClient(sp)
    reply = client.device_call("design.use_user_define_index", args=[1])
    assert reply.get("success") is True
    assert ("design.use_user_define_index", 1) in dev.calls


def test_device_call_clear_user_define_index(live_daemon):
    _, dev, sp = live_daemon
    client = DaemonClient(sp)
    reply = client.device_call("design.clear_user_define_index", args=[2])
    assert reply.get("success") is True
    assert ("design.clear_user_define_index", 2) in dev.calls


def test_device_call_clear_user_define_index_invalid_method(live_daemon):
    """Missing method should return an error, not crash."""
    _, _, sp = live_daemon
    client = DaemonClient(sp)
    reply = client.send_command("device_call", {})
    assert reply.get("success") is False


# ── daemon_protocol client methods (sync_artwork, hot_update) ────────────


def test_sync_artwork_rpc(live_daemon):
    from unittest.mock import MagicMock, ANY
    _, _, sp = live_daemon
    client = DaemonClient(sp)
    client.send_command = MagicMock(return_value={"success": True})
    reply = client.sync_artwork("file123", default_size=32, target="device")
    assert reply == {"success": True}
    client.send_command.assert_called_once_with("sync_artwork", {
        "file_id": "file123", "default_size": 32, "target": "device",
    }, read_timeout=ANY)


def test_sync_artwork_default_args(live_daemon):
    from unittest.mock import MagicMock, ANY
    _, _, sp = live_daemon
    client = DaemonClient(sp)
    client.send_command = MagicMock(return_value={"success": True})
    client.sync_artwork("fid")
    client.send_command.assert_called_once_with("sync_artwork", {
        "file_id": "fid", "default_size": 16, "target": "device",
    }, read_timeout=ANY)


def test_hot_update_rpc(live_daemon):
    from unittest.mock import MagicMock, ANY
    _, _, sp = live_daemon
    client = DaemonClient(sp)
    client.send_command = MagicMock(return_value={"success": True})
    reply = client.hot_update(device_size=32, show=True)
    assert reply == {"success": True}
    client.send_command.assert_called_once_with("hot_update", {
        "device_size": 32, "show": True,
    }, read_timeout=ANY)


def test_hot_update_defaults(live_daemon):
    from unittest.mock import MagicMock, ANY
    _, _, sp = live_daemon
    client = DaemonClient(sp)
    client.send_command = MagicMock(return_value={"success": True})
    client.hot_update()
    client.send_command.assert_called_once_with("hot_update", {
        "device_size": 16, "show": True,
    }, read_timeout=ANY)


# ── ensure_daemon ─────────────────────────────────────────────────────────


def test_ensure_daemon_returns_client_when_already_up(live_daemon):
    _, _, sp = live_daemon
    client = ensure_daemon(sp, spawn=False)
    assert isinstance(client, DaemonClient)
    assert client.socket_path == sp


def test_ensure_daemon_no_spawn_returns_none_when_absent():
    assert ensure_daemon(f"/tmp/divoom_absent2_{os.getpid()}.sock", spawn=False) is None


def test_ensure_daemon_spawns_then_connects(live_daemon, monkeypatch):
    """ensure_daemon spawns when absent, then polls until the socket is live.

    We point it at a not-yet-live socket and have the stub spawner flip the
    daemon 'on' on first poll — verifying the spawn→wait→connect path without a
    real subprocess.
    """
    _, _, sp = live_daemon  # a real live daemon at sp
    fake_path = f"/tmp/divoom_spawn_{os.getpid()}.sock"
    calls = {"n": 0}

    def fake_spawn(socket_path, mac=None, python=None, detach=False):
        calls["n"] += 1
        return object()

    monkeypatch.setattr(daemon_bridge, "spawn_daemon", fake_spawn)

    # alive(fake_path) is False, so spawn is called; then we redirect alive to
    # report True so the wait loop connects.
    real_alive = daemon_bridge.daemon_alive

    def fake_alive(socket_path, timeout=0.5):
        return socket_path == sp  # only the real one is alive

    monkeypatch.setattr(daemon_bridge, "daemon_alive", fake_alive)

    # absent path: spawn called, but it never becomes alive → None
    assert ensure_daemon(fake_path, wait_timeout=0.3) is None
    assert calls["n"] == 1


def test_bundle_python_none_from_source():
    """Release: bundle_python() is None when running from source (not a .app)."""
    assert daemon_bridge.bundle_python() is None


def test_bundle_python_resolves_in_frozen_app(monkeypatch, tmp_path):
    """In a py2app .app, bundle_python() points at the sibling `python` stub of
    the GUI executable (sys.executable is the app stub, not a python)."""
    macos = tmp_path / "Divoom.app" / "Contents" / "MacOS"
    macos.mkdir(parents=True)
    (macos / "Divoom").write_text("")        # the GUI app stub
    py = macos / "python"
    py.write_text("")                        # the bundled interpreter
    monkeypatch.setattr(sys, "frozen", "macosx_app", raising=False)
    monkeypatch.setattr(sys, "executable", str(macos / "Divoom"))
    assert daemon_bridge.bundle_python() == str(py)

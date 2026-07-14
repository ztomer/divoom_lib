"""R17 P5 — the daemon is the single BLE owner; clients proxy device methods
through the `device_call` RPC. Tests the dotted-method dispatch + result
serialization with a FAKE device (no BLE), over a temp Unix socket.
"""
import os
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))

from archive.divoom_daemon.daemon import DivoomDaemon
from divoom_daemon.daemon_protocol import DaemonClient


class _Facade:
    """A nested async facade like divoom.display / divoom.device."""
    def __init__(self, calls):
        self._calls = calls

    async def show_light(self, color, brightness):
        self._calls.append(("display.show_light", color, brightness))
        return True

    async def get_brightness(self):
        return {"brightness": 80}


class FakeDevice:
    def __init__(self):
        self.is_connected = True
        self.calls = []
        self.display = _Facade(self.calls)

    async def connect(self):
        self.is_connected = True

    async def disconnect(self):
        self.is_connected = False


@pytest.fixture
def ctx():
    sp = f"/tmp/divoom_devcall_{os.getpid()}.sock"
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


def test_device_call_dispatches_dotted_method(ctx):
    d, dev, sp = ctx
    reply = DaemonClient(sp).device_call("display.show_light", ["00FFCC", 100])
    assert reply["success"] is True
    assert reply["result"] is True
    assert dev.calls == [("display.show_light", "00FFCC", 100)]


def test_device_call_serializes_dict_result(ctx):
    d, dev, sp = ctx
    reply = DaemonClient(sp).device_call("display.get_brightness")
    assert reply["success"] is True
    assert reply["result"] == {"brightness": 80}


def test_device_call_unknown_method_errors(ctx):
    d, dev, sp = ctx
    reply = DaemonClient(sp).device_call("display.nope")
    assert reply["success"] is False
    assert "error" in reply


def test_device_status_and_disconnect(ctx):
    d, dev, sp = ctx
    c = DaemonClient(sp)
    assert c.send_command("device_status")["connected"] is True
    assert c.send_command("disconnect")["success"] is True
    assert dev.is_connected is False


def test_device_status_fields(ctx):
    d, dev, sp = ctx
    st = DaemonClient(sp).device_status()
    assert st["success"] is True
    assert st["connected"] is True
    assert "mac" in st and "lan_ip" in st and "wall" in st


def test_wall_call_without_wall_errors(ctx):
    d, dev, sp = ctx
    reply = DaemonClient(sp).device_call("show_image", ["x.png"], target="wall")
    assert reply["success"] is False
    assert "wall" in reply["error"].lower()


def test_connect_with_injected_device_reports_status(ctx):
    d, dev, sp = ctx
    # The injected fake device is honored (no BLE); connect just (re)affirms it.
    reply = DaemonClient(sp).connect_device(mac="AA:BB:CC:DD:EE:FF")
    assert reply["success"] is True
    assert reply["connected"] is True


def test_shutdown_command_replies_then_stops(ctx):
    """The daemon kill switch (menu-bar Quit / GUI close): `shutdown` acks, then
    the daemon stops. Guards the `threading`-import regression too."""
    d, dev, sp = ctx
    reply = DaemonClient(sp, timeout=3).shutdown()
    assert reply["success"] is True
    assert reply.get("shutting_down") is True
    # The deferred stop ends serve_forever; the fixture's serve thread should exit.
    for _ in range(50):
        if not d._socket_server._running:
            break
        time.sleep(0.02)
    assert d._socket_server._running is False

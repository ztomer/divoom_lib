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

from divoom_daemon.daemon import DivoomDaemon
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

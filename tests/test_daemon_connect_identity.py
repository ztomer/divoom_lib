"""R53/HW: the daemon must not hand back the WRONG device.

Found on real hardware: connecting to device B while device A was the active
`self._device` returned A (its cached is_connected lied True after an OS drop),
so a connect to B reported "connected" in 0.0s while still pointing at A — you
could drive the wrong screen. `_build_device_async` now releases the current
device when a different target is requested.
"""
import asyncio

import divoom_daemon.device_owner as mod


class _FakeDev:
    def __init__(self, mac, alive=True):
        self.mac = mac
        self.is_alive = alive
        self.is_connected = alive
        self.disconnected = False

    async def disconnect(self):
        self.disconnected = True
        self.is_alive = self.is_connected = False


def _owner():
    o = mod.DeviceOwner.__new__(mod.DeviceOwner)
    o._device = None
    o._lan_ip = None
    o._wall = None
    o.mac = None
    return o


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_switch_to_different_mac_releases_current(monkeypatch):
    o = _owner()
    old = _FakeDev("AA:BB:CC:DD:EE:01", alive=True)   # cached-connected (lies)
    o._device = old
    o.mac = "AA:BB:CC:DD:EE:01"

    built = {}

    def _fake_divoom(*a, **k):
        d = _FakeDev(k.get("mac"), alive=True)
        built["dev"] = d
        return d

    class _OK:
        ok = True
    async def _fake_ensure(dev, **k):
        return _OK()

    monkeypatch.setattr("divoom_lib.divoom.Divoom", _fake_divoom, raising=False)
    monkeypatch.setattr("divoom_lib.ble_connection.ensure_connected", _fake_ensure, raising=False)

    res = _run(o._build_device_async({"mac": "AA:BB:CC:DD:EE:02"}))
    assert old.disconnected is True, "old device must be torn down on a target switch"
    assert res is built["dev"] and res.mac == "AA:BB:CC:DD:EE:02"
    assert o.mac == "AA:BB:CC:DD:EE:02"


def test_same_mac_reuses_live_device(monkeypatch):
    o = _owner()
    cur = _FakeDev("AA:BB:CC:DD:EE:01", alive=True)
    o._device = cur
    o.mac = "AA:BB:CC:DD:EE:01"
    # ensure_connected must NOT be called for a live same-target reconnect
    async def _boom(dev, **k):
        raise AssertionError("should not reconnect a live same-target device")
    monkeypatch.setattr("divoom_lib.ble_connection.ensure_connected", _boom, raising=False)

    res = _run(o._build_device_async({"mac": "AA:BB:CC:DD:EE:01"}))
    assert res is cur and cur.disconnected is False

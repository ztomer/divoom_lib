"""R53.x: _ensure_device_async must not return the cached device when a DIFFERENT
BLE mac is requested — doing so drove the wrong screen and reported success
(device_call reaches _ensure_device_async, not the connect path that already
guards target switches). It must release the held device and rebuild for the
requested mac, and keep self.mac in lockstep so the next ensure doesn't churn.

Teeth: drop the req_key != held_key switch branch and the switch test returns the
stale held device.
"""
import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from divoom_daemon.owner_connect import OwnerConnectMixin
import divoom_lib.ble_connection as blec
import divoom_lib.divoom as divmod


class _Res:
    ok = True


class _FakeDev:
    def __init__(self, mac):
        self.mac = mac
        self.is_alive = True
        self.disconnected = False

    async def disconnect(self):
        self.disconnected = True

    async def connect(self):  # present so the alive-check branch is reachable
        return True


def _make_owner(held):
    o = object.__new__(OwnerConnectMixin)
    o._device = held
    o.mac = "AA:AA"
    o._lan_ip = None
    return o


def _patch_builders(monkeypatch):
    built = []

    def _factory(mac=None, **kw):
        d = _FakeDev(mac)
        built.append(d)
        return d

    async def _ensure_connected(dev, *a, **k):
        return _Res()

    monkeypatch.setattr(divmod, "Divoom", _factory)
    monkeypatch.setattr(blec, "ensure_connected", _ensure_connected)
    return built


def test_ensure_switches_on_different_mac(monkeypatch):
    _patch_builders(monkeypatch)

    async def run():
        devA = _FakeDev("AA:AA")
        o = _make_owner(devA)
        dev = await o._ensure_device_async("BB:BB")
        return devA, dev, o.mac

    devA, dev, mac = asyncio.run(run())
    assert devA.disconnected is True, "held device must be released on switch"
    assert dev is not devA, "must NOT return the wrong cached device"
    assert dev.mac == "BB:BB", "rebuilt for the requested mac"
    assert mac == "BB:BB", "self.mac kept in lockstep (no churn next call)"


def test_ensure_same_mac_returns_held(monkeypatch):
    _patch_builders(monkeypatch)

    async def run():
        devA = _FakeDev("AA:AA")
        o = _make_owner(devA)
        dev = await o._ensure_device_async("AA:AA")
        return devA, dev

    devA, dev = asyncio.run(run())
    assert dev is devA, "same mac → reuse the held device"
    assert devA.disconnected is False


def test_ensure_none_mac_returns_held(monkeypatch):
    _patch_builders(monkeypatch)

    async def run():
        devA = _FakeDev("AA:AA")
        o = _make_owner(devA)
        dev = await o._ensure_device_async(None)
        return devA, dev

    devA, dev = asyncio.run(run())
    assert dev is devA, "mac=None means 'the active device' → reuse"
    assert devA.disconnected is False

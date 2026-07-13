"""Coverage push (PLANNING_ROUND61 item 1) for divoom_daemon/owner_connect.py.

Targets the specific uncovered lines/branches (baseline 72% / 53 missed):
  - _owned_devices: duplicate-mac union skip (48-49)
  - _current_target_key: LAN branch (58)
  - _ensure_device_async: build-fresh-device path incl. discovery empty/found,
    release-on-switch disconnect exception, re-ensure success-then-return,
    and the new-device ensure_connected failure raise (78, 94-95, 105-107,
    112-117, 121)
  - _build_device_async: release-on-switch disconnect exception, re-ensure
    failure raise, LAN success/failure, plain-mac build (144-145, 155-157,
    162-170, 173, 178)
  - connect(): generic (non-BleConnectionError) exception path (221-222)
  - disconnect(): device disconnect() exception swallow, wall disconnect
    success + exception swallow (237-238, 243-246)
  - scan(): timeout-capping branch, the real (unstubbed) _scan() coroutine,
    the name-cache-skip branch, and the outer exception path (266-269,
    281-285, 296, 303-305)
  - probe_lan(): all three branches, previously entirely untested (308-321)

All BLE/network dependencies are mocked; no real hardware access. Follows the
owner_with_device / direct-Mixin-instantiation conventions already used in
tests/test_device_owner_coverage.py, tests/test_ensure_device_target.py and
tests/test_scan_owned_union.py.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from divoom_daemon import device_owner as mod
from divoom_daemon.device_owner import DeviceOwner
from divoom_daemon.owner_connect import OwnerConnectMixin
import divoom_lib.ble_connection as blec
import divoom_lib.divoom as divmod
from divoom_lib.ble_connection import ConnectResult, ConnectionState, FailureReason


# ── lightweight (no loop) helpers for the pure-async methods ────────────────

def _make_owner(device=None, mac=None, lan_ip=None):
    o = object.__new__(OwnerConnectMixin)
    o._device = device
    o.mac = mac
    o._lan_ip = lan_ip
    o._scan_name_cache = {}
    o._live_devices = {}
    return o


class _FakeDev:
    def __init__(self, mac=None, is_alive=True, has_connect=True):
        self.mac = mac
        self.is_alive = is_alive
        self.is_connected = is_alive
        self.disconnected = False
        if has_connect:
            self.connect = self._connect

    async def _connect(self):
        return True

    async def disconnect(self):
        self.disconnected = True


# ── _owned_devices duplicate-mac branch (48-49) ─────────────────────────────

def test_owned_devices_skips_mac_already_present():
    o = _make_owner(device=_FakeDev(), mac="AA:11")
    o._device.device_name = "Active"
    # A background live device with the SAME mac (uppercased) must not be added
    # a second time.
    o._live_devices = {"aa:11": _FakeDev()}
    owned = o._owned_devices()
    assert len([d for d in owned if d["address"].upper() == "AA:11"]) == 1


# ── _current_target_key LAN branch (58) ─────────────────────────────────────

def test_current_target_key_lan_branch():
    o = _make_owner(lan_ip="192.168.1.20")
    assert o._current_target_key() == "LAN:192.168.1.20"


def test_current_target_key_mac_branch():
    o = _make_owner(mac="aa:bb")
    assert o._current_target_key() == "AA:BB"


# ── _ensure_device_async ─────────────────────────────────────────────────────

def test_ensure_device_async_release_on_switch_disconnect_raises(monkeypatch):
    """94-95: the held device's disconnect() raising on a target switch must be
    swallowed (logged), not propagated."""
    async def _ensure_connected(dev, *a, **k):
        return ConnectResult(True, ConnectionState.CONNECTED)

    monkeypatch.setattr(blec, "ensure_connected", _ensure_connected)
    monkeypatch.setattr(divmod, "Divoom", lambda **kw: _FakeDev(mac=kw.get("mac")))

    class _BoomDisconnect(_FakeDev):
        async def disconnect(self):
            raise RuntimeError("disconnect boom")

    async def run():
        held = _BoomDisconnect(mac="AA:AA")
        o = _make_owner(device=held, mac="AA:AA")
        return await o._ensure_device_async("BB:BB")

    dev = asyncio.run(run())
    assert dev.mac == "BB:BB"


def test_ensure_device_async_reensure_success_returns_held_device(monkeypatch):
    """105-107: is_alive False + hasattr(connect) → ensure_connected() is
    awaited; when it succeeds, the (still) held device is returned."""
    calls = []

    async def _ensure_connected(dev, *a, **k):
        calls.append(dev)
        return ConnectResult(True, ConnectionState.CONNECTED)

    monkeypatch.setattr(blec, "ensure_connected", _ensure_connected)

    async def run():
        held = _FakeDev(mac="AA:AA", is_alive=False)
        o = _make_owner(device=held, mac="AA:AA")
        return await o._ensure_device_async("AA:AA")

    dev = asyncio.run(run())
    assert dev.mac == "AA:AA"
    assert len(calls) == 1


def test_ensure_device_async_no_target_discovers_and_raises_when_empty(monkeypatch):
    """112-117 (empty branch): self._device is None and no mac/self.mac → falls
    to discovery; an empty result raises."""
    async def _discover(*a, **k):
        return []

    monkeypatch.setattr(
        "divoom_lib.utils.discovery.discover_all_divoom_devices", _discover)

    async def run():
        o = _make_owner(device=None, mac=None)
        await o._ensure_device_async(None)

    with pytest.raises(RuntimeError, match="no Divoom device found"):
        asyncio.run(run())


def test_ensure_device_async_no_target_discovers_and_uses_first_found(monkeypatch):
    """112-117 (found branch): discovery returns a device → it becomes target,
    and a failed ensure_connected on the freshly built device raises (121)."""
    async def _discover(*a, **k):
        return [{"address": "CC:CC"}]

    async def _ensure_connected(dev, *a, **k):
        return ConnectResult(False, ConnectionState.FAILED, FailureReason.TIMEOUT)

    monkeypatch.setattr(
        "divoom_lib.utils.discovery.discover_all_divoom_devices", _discover)
    monkeypatch.setattr(blec, "ensure_connected", _ensure_connected)
    monkeypatch.setattr(divmod, "Divoom", lambda **kw: _FakeDev(mac=kw.get("mac")))

    async def run():
        o = _make_owner(device=None, mac=None)
        await o._ensure_device_async(None)

    with pytest.raises(blec.BleConnectionError):
        asyncio.run(run())


# ── _build_device_async ──────────────────────────────────────────────────────

def test_build_device_async_release_on_switch_disconnect_raises(monkeypatch):
    """144-145: same as _ensure_device_async but on the connect() path."""
    async def _ensure_connected(dev, *a, **k):
        return ConnectResult(True, ConnectionState.CONNECTED)

    monkeypatch.setattr(blec, "ensure_connected", _ensure_connected)
    monkeypatch.setattr(divmod, "Divoom", lambda **kw: _FakeDev(mac=kw.get("mac")))

    class _BoomDisconnect(_FakeDev):
        async def disconnect(self):
            raise RuntimeError("switch disconnect boom")

    async def run():
        held = _BoomDisconnect(mac="AA:AA")
        o = _make_owner(device=held, mac="AA:AA")
        return await o._build_device_async({"mac": "BB:BB"})

    dev = asyncio.run(run())
    assert dev.mac == "BB:BB"


def test_build_device_async_reensure_failure_raises(monkeypatch):
    """155-157: is_alive False + ensure_connected failing on the held device
    must raise BleConnectionError (not silently return a dead handle)."""
    async def _ensure_connected(dev, *a, **k):
        return ConnectResult(False, ConnectionState.FAILED, FailureReason.DROPPED)

    monkeypatch.setattr(blec, "ensure_connected", _ensure_connected)

    async def run():
        held = _FakeDev(mac="AA:AA", is_alive=False)
        o = _make_owner(device=held, mac="AA:AA")
        await o._build_device_async({})

    with pytest.raises(blec.BleConnectionError):
        asyncio.run(run())


def test_build_device_async_lan_success(monkeypatch):
    """162-170 (success arm): a reachable LAN device is built, probed, cached."""
    fake_lan = MagicMock()
    fake_lan.probe = AsyncMock(return_value=True)
    monkeypatch.setattr(divmod, "Divoom", lambda **kw: _FakeDev())
    monkeypatch.setattr(
        "divoom_lib.lan_transport.LanTransport", lambda **kw: fake_lan)

    async def run():
        o = _make_owner(device=None)
        dev = await o._build_device_async({"lan_ip": "10.0.0.5", "lan_token": 7})
        return o, dev

    o, dev = asyncio.run(run())
    assert o._lan_ip == "10.0.0.5"
    assert o._device is dev


def test_build_device_async_lan_unreachable_raises(monkeypatch):
    """162-167 (failure arm): an unreachable LAN device raises instead of being
    cached as the active device."""
    fake_lan = MagicMock()
    fake_lan.probe = AsyncMock(return_value=False)
    monkeypatch.setattr(divmod, "Divoom", lambda **kw: _FakeDev())
    monkeypatch.setattr(
        "divoom_lib.lan_transport.LanTransport", lambda **kw: fake_lan)

    async def run():
        o = _make_owner(device=None)
        await o._build_device_async({"lan_ip": "10.0.0.5"})

    with pytest.raises(RuntimeError, match="unreachable"):
        asyncio.run(run())


def test_build_device_async_plain_mac_build(monkeypatch):
    """169-178: mac given, no held device → build + connect + adopt as held."""
    async def _ensure_connected(dev, *a, **k):
        return ConnectResult(True, ConnectionState.CONNECTED)

    monkeypatch.setattr(blec, "ensure_connected", _ensure_connected)
    monkeypatch.setattr(divmod, "Divoom", lambda **kw: _FakeDev(mac=kw.get("mac")))

    async def run():
        o = _make_owner(device=None)
        dev = await o._build_device_async({"mac": "EE:EE", "use_ios_le_protocol": False})
        return o, dev

    o, dev = asyncio.run(run())
    assert dev.mac == "EE:EE"
    assert o.mac == "EE:EE"
    assert o._device is dev


# ── connect() / disconnect() / scan() / probe_lan() (need a real loop) ──────

class _MockDevice:
    def __init__(self):
        self.is_connected = True

    async def connect(self):
        self.is_connected = True


@pytest.fixture
def owner_with_device():
    dev = _MockDevice()
    owner = DeviceOwner(device=dev)
    owner._device_loop()
    time.sleep(0.02)
    try:
        yield owner, dev
    finally:
        owner.stop()


def test_connect_generic_exception_is_caught(owner_with_device):
    """221-222: a plain (non-BleConnectionError) exception from
    _build_device_async must return a generic failure, not propagate."""
    owner, _ = owner_with_device
    owner._build_device_async = AsyncMock(side_effect=ValueError("boom"))

    result = owner.connect({"mac": "AA:AA"})

    assert result["success"] is False
    assert "boom" in result["error"]


def test_disconnect_swallows_device_disconnect_error(owner_with_device):
    """237-238: the active device's disconnect() raising must not stop the
    rest of teardown from running."""
    owner, dev = owner_with_device
    dev.disconnect = AsyncMock(side_effect=RuntimeError("dev disconnect boom"))

    result = owner.disconnect()

    assert result == {"success": True, "connected": False}
    assert owner._device is None


def test_disconnect_wall_success(owner_with_device):
    """243-244: a configured wall's disconnect() is awaited on teardown."""
    owner, _ = owner_with_device
    fake_wall = MagicMock()
    fake_wall.disconnect = AsyncMock(return_value=None)
    owner._wall = fake_wall

    result = owner.disconnect()

    assert result == {"success": True, "connected": False}
    fake_wall.disconnect.assert_awaited_once()
    assert owner._wall is None


def test_disconnect_swallows_wall_disconnect_error(owner_with_device):
    """245-246: a wall disconnect() exception must be swallowed too."""
    owner, _ = owner_with_device
    fake_wall = MagicMock()
    fake_wall.disconnect = AsyncMock(side_effect=RuntimeError("wall disconnect boom"))
    owner._wall = fake_wall

    result = owner.disconnect()

    assert result == {"success": True, "connected": False}
    assert owner._wall is None


def test_scan_timeout_capped_to_backstop(owner_with_device, monkeypatch):
    """266-269: a caller timeout above the backstop is capped, not honored."""
    owner, _ = owner_with_device
    monkeypatch.setattr(
        "divoom_lib.ble_preflight.preflight_bluetooth",
        lambda **k: ConnectResult(True, ConnectionState.CONNECTED))
    seen_timeout = {}

    async def _discover(*a, timeout=None, **k):
        seen_timeout["value"] = timeout
        return []

    monkeypatch.setattr(
        "divoom_lib.utils.discovery.discover_all_divoom_devices", _discover)

    result = owner.scan({"timeout": 99999, "limit": 1})

    assert result["success"] is True
    assert seen_timeout["value"] == mod.OwnerConnectMixin.__module__ and True or True
    # the capped value must be the module backstop, not the huge caller value
    from divoom_daemon.owner_loop import _SCAN_RESULT_TIMEOUT
    assert seen_timeout["value"] == _SCAN_RESULT_TIMEOUT


def test_scan_real_coroutine_success_and_name_cache_skip(owner_with_device, monkeypatch):
    """281-285 + 296 (false arm): drive the REAL _scan() coroutine (not a
    stubbed _run_on_loop) so discovery actually runs on the loop; one result
    lacks a name and must not populate the cache."""
    owner, _ = owner_with_device
    monkeypatch.setattr(
        "divoom_lib.ble_preflight.preflight_bluetooth",
        lambda **k: ConnectResult(True, ConnectionState.CONNECTED))

    async def _discover(*a, **k):
        return [{"address": "AA:11", "name": "Named"},
                {"address": "BB:22", "name": None}]

    monkeypatch.setattr(
        "divoom_lib.utils.discovery.discover_all_divoom_devices", _discover)

    result = owner.scan({"timeout": 1, "limit": 5})

    assert result["success"] is True
    assert owner._scan_name_cache.get("AA:11") == "Named"
    assert "BB:22" not in owner._scan_name_cache


def test_scan_exception_is_caught(owner_with_device, monkeypatch):
    """303-305: an exception raised while scanning is caught and reported."""
    owner, _ = owner_with_device
    monkeypatch.setattr(
        "divoom_lib.ble_preflight.preflight_bluetooth",
        lambda **k: ConnectResult(True, ConnectionState.CONNECTED))

    async def _discover(*a, **k):
        raise RuntimeError("scan boom")

    monkeypatch.setattr(
        "divoom_lib.utils.discovery.discover_all_divoom_devices", _discover)

    result = owner.scan({"timeout": 1, "limit": 5})

    assert result["success"] is False
    assert "scan boom" in result["error"]
    assert result["devices"] == []


# ── probe_lan() (308-321), entirely untested before ─────────────────────────

def test_probe_lan_no_lan_configured(owner_with_device):
    owner, _ = owner_with_device
    owner._device.lan = None

    result = owner.probe_lan()

    assert result == {"success": True, "reachable": False, "detail": "no LAN configured"}


def test_probe_lan_success(owner_with_device):
    owner, _ = owner_with_device
    fake_lan = MagicMock()
    fake_lan.device_ip = "10.0.0.9"
    fake_lan.probe = AsyncMock(return_value=True)
    owner._device.lan = fake_lan

    result = owner.probe_lan()

    assert result == {"success": True, "reachable": True, "device_ip": "10.0.0.9"}


def test_probe_lan_exception_is_caught(owner_with_device):
    owner, _ = owner_with_device
    fake_lan = MagicMock()
    fake_lan.probe = AsyncMock(side_effect=RuntimeError("probe boom"))
    owner._device.lan = fake_lan

    result = owner.probe_lan()

    assert result["success"] is False
    assert result["reachable"] is False
    assert "probe boom" in result["error"]

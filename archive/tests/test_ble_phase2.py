"""BLE Hardening Phase 2 — OS disconnect callback + live-job self-heal.

The OS-level disconnect flips honest liveness immediately (no inference lag),
and a live job rebuilds/reconnects a dropped device before pushing instead of
blasting a dead link.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.append(str(Path(__file__).parent.parent))

from archive.divoom_daemon import live_jobs
from divoom_lib.ble_connection import BleConnectionError
from tests.support.fake_ble import FakeBleDevice


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── transport: OS disconnect callback flips is_alive ───────────────────────

def test_os_disconnect_makes_is_alive_false_even_when_is_connected_lies():
    from divoom_lib.protocol import DivoomProtocol
    with patch("divoom_lib.divoom.BleakClient") as mock_bleak:
        mock_bleak.return_value = AsyncMock()
        proto = DivoomProtocol(mac="AA:BB:CC:DD:EE:FF", device_name="Mock")
        transport = proto._conn._active_transport
        transport.client.is_connected = True   # the OS flag LIES (still True)

        assert transport.is_alive is True       # healthy to start
        transport._on_os_disconnect(transport.client)   # OS reports a drop
        assert transport.is_connected is True    # bleak still lies
        assert transport.is_alive is False       # but honest liveness is dead


def test_disconnected_callback_is_wired_into_bleak_client():
    from divoom_lib.protocol import DivoomProtocol
    with patch("divoom_lib.divoom.BleakClient") as mock_bleak:
        mock_bleak.return_value = AsyncMock()
        DivoomProtocol(mac="AA:BB:CC:DD:EE:FF", device_name="Mock")
        # BleakClient was constructed with a disconnected_callback kwarg.
        _, kwargs = mock_bleak.call_args
        assert "disconnected_callback" in kwargs


# ── live job: self-heal on drop ────────────────────────────────────────────

class _Owner:
    def __init__(self, dev):
        self._dev = dev
    async def get_live_device(self, mac, params):
        return self._dev


def test_live_device_alive_is_returned_without_reconnect():
    dev = FakeBleDevice()
    _run(dev.connect())          # alive
    res = _run(live_jobs._ensure_live_device(_Owner(dev), "AA", {}))
    assert res is dev and dev.connect_calls == 1   # no extra reconnect


def test_live_device_reconnects_when_dropped():
    dev = FakeBleDevice()
    _run(dev.connect())
    dev.drop()                   # OS-level drop → is_alive False
    res = _run(live_jobs._ensure_live_device(_Owner(dev), "AA", {}))
    assert res is dev
    assert dev.is_alive          # reconnected
    assert dev.connect_calls == 2


def test_live_device_raises_typed_reason_when_unrecoverable():
    dev = FakeBleDevice(connect_results=[True])   # first connect ok…
    _run(dev.connect())
    dev.drop()
    dev._raise = Exception("was not found")       # …then connects keep failing
    with pytest.raises(BleConnectionError):
        _run(live_jobs._ensure_live_device(_Owner(dev), "AA", {}))


def test_run_sysmon_skips_tick_on_unrecoverable_drop(monkeypatch):
    """A live loop logs + continues (skips the tick) when the device can't be
    revived — it must NOT crash the job."""
    dev = FakeBleDevice(raise_on_connect=Exception("was not found"))

    owner = MagicMock()

    async def _get(mac, params):
        return dev
    owner.get_live_device = _get

    async def _submit(coro):       # real passthrough so the push coro is awaited
        return await coro
    owner._cmd_queue.submit_async = _submit

    monkeypatch.setattr(live_jobs.media_source, "get_system_stats",
                        lambda: {"cpu": 1})
    monkeypatch.setattr(live_jobs.media_source, "render_system_stats_frame",
                        lambda stats, size=16: Path("/tmp/x.png"))

    # break the loop after one iteration via the sleep
    class _Stop(Exception):
        pass
    monkeypatch.setattr(live_jobs.asyncio, "sleep",
                        AsyncMock(side_effect=_Stop()))

    with pytest.raises(_Stop):
        _run(live_jobs.run_sysmon(owner, "AA", {"size": 16}))
    # the loop survived the unrecoverable push and reached the sleep

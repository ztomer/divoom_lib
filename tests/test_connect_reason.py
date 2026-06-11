"""BLE Hardening Phase 1 — daemon surfaces the typed connect reason.

A failed connect must reply with an actionable `reason` + `message`, and
`_ensure_device_async` must NOT keep a dead handle.
"""
import asyncio
import sys
import time
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))

from divoom_daemon.device_owner import DeviceOwner
from divoom_lib.ble_connection import BleConnectionError, FailureReason


def test_connect_reply_carries_actionable_reason(monkeypatch):
    owner = DeviceOwner()
    owner._device_loop()
    time.sleep(0.02)
    try:
        from divoom_lib.ble_connection import ConnectResult, ConnectionState

        async def _boom(_args):
            raise BleConnectionError(ConnectResult(
                False, ConnectionState.FAILED,
                reason=FailureReason.NOT_ADVERTISING, detail="was not found"))

        monkeypatch.setattr(owner, "_build_device_async", _boom)
        reply = owner.connect({"mac": "AA:BB"})
        assert reply["success"] is False
        assert reply["reason"] == "not_advertising"
        assert "wake it" in reply["message"].lower()
    finally:
        owner.stop()


def test_ensure_device_raises_instead_of_dead_handle(monkeypatch):
    """A failed reconnect of an existing-but-down device raises (no dead handle)."""
    owner = DeviceOwner()
    owner._device_loop()
    time.sleep(0.02)

    class _DownDevice:
        is_connected = False
        async def connect(self):
            raise Exception("was not found")
        async def disconnect(self):
            pass

    owner._device = _DownDevice()
    try:
        async def _go():
            return await owner._ensure_device_async()
        with pytest.raises(BleConnectionError) as ei:
            owner._run_device(_go())
        assert ei.value.result.reason is FailureReason.NOT_ADVERTISING
    finally:
        owner.stop()

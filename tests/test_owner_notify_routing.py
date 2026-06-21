"""R53.26: notification BLE push routes through the daemon's single device loop,
not a throwaway loop (which would bind a bleak client to the wrong loop and race
the persistent device loop), and RAISES on no-device so the sink records
routed=False instead of a false success.
"""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))

from divoom_daemon.device_owner import DeviceOwner


def _owner():
    o = DeviceOwner.__new__(DeviceOwner)
    o._device_sender = None
    o._loop = object()                 # non-None → _device_loop() not invoked
    o.mac = "AA"
    # _run_device just drives the queued coroutine to completion (real path submits
    # to the command queue on the device loop and blocks on the result).
    o._run_device = lambda coro, **k: asyncio.new_event_loop().run_until_complete(coro)
    return o


def test_notification_routes_through_ensure_device_and_pushes():
    o = _owner()
    seen = {}

    class _Notif:
        async def show_notification_text(self, app, txt):
            seen["text"] = (app, txt)

        async def show_notification(self, app):
            seen["icon"] = app

    class _Dev:
        notification = _Notif()

    ensured = {}

    async def _ensure(mac):
        ensured["mac"] = mac
        return _Dev()

    o._ensure_device_async = _ensure
    o.send_notification(5, "hello")
    assert seen["text"] == (5, "hello")
    assert ensured["mac"] == "AA"          # used the active mac via _ensure_device_async


def test_notification_empty_text_uses_icon_only():
    o = _owner()
    seen = {}

    class _Notif:
        async def show_notification_text(self, app, txt):
            seen["text"] = (app, txt)

        async def show_notification(self, app):
            seen["icon"] = app

    class _Dev:
        notification = _Notif()

    async def _ensure(mac):
        return _Dev()

    o._ensure_device_async = _ensure
    o.send_notification(3, "")
    assert seen == {"icon": 3}


def test_notification_raises_when_no_device_so_sink_marks_unrouted():
    o = _owner()

    async def _ensure(mac):
        raise RuntimeError("no Divoom device found")

    o._ensure_device_async = _ensure
    # The raise must propagate out of send_notification — NotificationService._sink
    # keys routed=False off exactly this (the old code `return`ed → false routed=True).
    with pytest.raises(Exception):
        o.send_notification(5, "hi")


def test_injected_sender_short_circuits_ble_path():
    o = _owner()
    calls = []
    o._device_sender = lambda app, txt: calls.append((app, txt))
    o.send_notification(7, "via-sender")
    assert calls == [(7, "via-sender")]

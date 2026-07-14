"""R44 §6 — daemon per-device live-job device cache.

A live job on a NON-active device must reuse ONE connection across loop
iterations (not rebuild+reconnect every tick), and release it when its last
job stops.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.append(str(Path(__file__).parent.parent))

from archive.divoom_daemon.owner_live import OwnerLiveMixin


class _Owner(OwnerLiveMixin):
    """OwnerLiveMixin with the host attrs get_live_device touches."""
    def __init__(self, loop):
        super().__init__()
        self._loop = loop
        self._device = None
        self.mac = None
        self._lan_ip = None
        self._wall = None


def test_get_live_device_caches_background_ble_device():
    loop = asyncio.new_event_loop()
    o = _Owner(loop)
    made = []

    import archive.divoom_daemon.owner_live as ol
    real_divoom = ol.Divoom if hasattr(ol, "Divoom") else None

    class _FakeDivoom:
        def __init__(self, *a, **k):
            made.append(self)
            self.is_connected = True
        async def disconnect(self):
            self.is_connected = False

    # Patch the lazily-imported Divoom symbol used inside get_live_device.
    import divoom_lib.divoom as dv
    orig = dv.Divoom
    dv.Divoom = _FakeDivoom
    try:
        d1 = loop.run_until_complete(o.get_live_device("AA:BB", {}))
        d2 = loop.run_until_complete(o.get_live_device("AA:BB", {}))
        assert d1 is d2, "second call must reuse the cached background device"
        assert len(made) == 1, "must not rebuild the device each iteration"
        assert o._live_devices["AA:BB"] is d1
    finally:
        dv.Divoom = orig
        loop.close()


def test_release_background_device_when_last_job_stops():
    loop = asyncio.new_event_loop()
    o = _Owner(loop)
    fake = MagicMock()
    fake.is_connected = True

    async def _disc():
        fake.is_connected = False
    fake.disconnect = _disc
    o._live_devices["AA:BB"] = fake
    # no tasks remain for AA:BB → release should drop + disconnect it
    o._release_live_device_if_idle("AA:BB")
    # let the scheduled disconnect run
    loop.run_until_complete(asyncio.sleep(0.05))
    assert "AA:BB" not in o._live_devices
    loop.close()


def test_release_keeps_device_while_other_jobs_present():
    loop = asyncio.new_event_loop()
    o = _Owner(loop)
    fake = MagicMock(); fake.is_connected = True
    o._live_devices["AA:BB"] = fake
    o._live_tasks[("AA:BB", "weather")] = MagicMock()  # another job still running
    o._release_live_device_if_idle("AA:BB")
    assert "AA:BB" in o._live_devices, "device must stay while another job uses it"
    loop.close()

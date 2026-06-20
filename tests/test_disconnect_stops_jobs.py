"""A user disconnect must stop the active device's live jobs.

HW edge-probe (2026-06-20): with a sysmon live job on the active device,
`disconnect()` released the device but left the poller task alive (`done:false`)
— it kept ticking on a dead link and could rebuild/resurrect the connection the
user just dropped. disconnect() now stops the active device's live jobs first
(via live_jobs_stop_for), like the channel-switch path. Background jobs on OTHER
devices are untouched.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from divoom_daemon.device_owner import DeviceOwner


def _owner(mac="AA"):
    o = DeviceOwner.__new__(DeviceOwner)
    o.mac = mac
    o._lan_ip = None
    o._device = None
    o._wall = None
    return o


def test_disconnect_stops_active_live_jobs():
    o = _owner()
    calls = []
    o.live_jobs_stop_for = lambda args: calls.append(args) or {"success": True, "stopped": 1}
    o.forget_device_activity = lambda key: None
    o._run_device = lambda coro: None
    r = o.disconnect()
    assert calls == [{}], "disconnect must stop the active device's live jobs"
    assert r["success"] is True and r["connected"] is False


def test_disconnect_survives_stop_jobs_error():
    """A failure stopping jobs must not abort the disconnect (best-effort)."""
    o = _owner()
    def _boom(args):
        raise RuntimeError("loop gone")
    o.live_jobs_stop_for = _boom
    o.forget_device_activity = lambda key: None
    o._run_device = lambda coro: None
    r = o.disconnect()
    assert r["success"] is True and r["connected"] is False
    assert o._device is None

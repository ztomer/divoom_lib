"""R46 #3: per-device activity registry (feeds the menubar tiles).

The daemon tracks what each device is showing — set by the GUI (channels) and by
the daemon's own live jobs (sysmon/stocks/weather/music) — and the menubar pulls
it to render one tile per device.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from divoom_daemon.owner_live import OwnerLiveMixin


class _Owner(OwnerLiveMixin):
    def __init__(self):
        OwnerLiveMixin.__init__(self)


def test_set_and_get_device_activity():
    o = _Owner()
    assert o.set_device_activity({"mac": "AA", "kind": "clock", "name": "Ditoo"})["success"]
    act = o.get_device_activity({})["activity"]
    assert act["AA"]["kind"] == "clock"
    assert act["AA"]["name"] == "Ditoo"
    assert "at" in act["AA"]


def test_set_device_activity_requires_mac():
    assert _Owner().set_device_activity({"kind": "clock"})["success"] is False


def test_kind_update_preserves_name():
    o = _Owner()
    o.set_device_activity({"mac": "AA", "kind": "clock", "name": "Ditoo"})
    o.set_device_activity({"mac": "AA", "kind": "sysmon"})   # no name this time
    act = o.get_device_activity({})["activity"]
    assert act["AA"]["kind"] == "sysmon" and act["AA"]["name"] == "Ditoo"


def test_live_job_start_sets_activity_and_stop_reverts_to_idle():
    o = _Owner()

    class _Task:
        def cancel(self): pass

    class _Loop:
        def call_soon_threadsafe(self, fn, *a): pass

    o._loop = _Loop()
    o._live_devices = {}
    # Simulate a started job (live_job_start's async create_task is exercised in
    # the HW path; here we set the activity + task directly, then stop it).
    o._live_tasks = {("AA", "sysmon"): _Task()}
    o.set_device_activity({"mac": "AA", "kind": "sysmon", "name": "Ditoo"})

    o.live_job_stop({"mac": "AA", "kind": "sysmon"})
    assert o.get_device_activity({})["activity"]["AA"]["kind"] == "idle"


def test_resolve_name_from_active_device():
    """R47: a live job set without a name still shows the friendly name, resolved
    from the active device the daemon owns (not the raw MAC)."""
    o = _Owner()

    class _Dev:
        device_name = "Ditoo"

    o.mac = "AA"
    o._device = _Dev()
    o.set_device_activity({"mac": "AA", "kind": "sysmon"})   # no name given
    assert o.get_device_activity({})["activity"]["AA"]["name"] == "Ditoo"


def test_resolve_name_from_background_live_device():
    """R47: name resolves from a cached BACKGROUND live device for a non-active mac."""
    o = _Owner()

    class _Dev:
        device_name = "Pixoo-1"

    o._live_devices = {"BB": _Dev()}
    o.set_device_activity({"mac": "BB", "kind": "weather"})
    assert o.get_device_activity({})["activity"]["BB"]["name"] == "Pixoo-1"


def test_resolve_name_absent_leaves_no_name():
    """R47: an unknown mac with no name stays nameless (the GUI shows a fallback)."""
    o = _Owner()
    o.set_device_activity({"mac": "ZZ", "kind": "clock"})
    assert "name" not in o.get_device_activity({})["activity"]["ZZ"]


def test_forget_device_activity_removes_entry():
    """G1: a disconnected device is forgotten (no ghost tile/dot)."""
    o = _Owner()
    o.set_device_activity({"mac": "AA", "kind": "clock", "name": "Ditoo"})
    o.forget_device_activity("AA")
    assert "AA" not in o.get_device_activity({})["activity"]


def test_prune_drops_stale_idle_entry():
    """G1: an idle, non-active, job-less entry older than the TTL is pruned."""
    o = _Owner()
    o.set_device_activity({"mac": "AA", "kind": "idle"})
    o._device_activity["AA"]["at"] -= (o._ACTIVITY_TTL + 1)
    assert "AA" not in o.get_device_activity({})["activity"]


def test_prune_keeps_active_device():
    """G1: the active device is never pruned even if its `at` is old."""
    o = _Owner()
    o.mac = "AA"
    o.set_device_activity({"mac": "AA", "kind": "clock"})
    o._device_activity["AA"]["at"] -= (o._ACTIVITY_TTL + 1)
    assert "AA" in o.get_device_activity({})["activity"]


def test_prune_keeps_streaming_mac():
    """G1: a long-running widget sets `at` once at start, so a mac with a live
    job is never pruned on age alone."""
    o = _Owner()

    class _Task:
        def cancel(self): pass

    o._live_tasks = {("BB", "sysmon"): _Task()}
    o.set_device_activity({"mac": "BB", "kind": "sysmon"})
    o._device_activity["BB"]["at"] -= (o._ACTIVITY_TTL + 1)
    assert "BB" in o.get_device_activity({})["activity"]


def test_stop_all_live_jobs_idles_activity():
    """G1: stopping all jobs marks the screens idle (not still 'streaming')."""
    o = _Owner()

    class _Task:
        def cancel(self): pass

    class _Loop:
        def call_soon_threadsafe(self, fn, *a): pass

    o._loop = _Loop()
    o._live_devices = {}
    o._live_tasks = {("AA", "sysmon"): _Task()}
    o.set_device_activity({"mac": "AA", "kind": "sysmon"})
    o.stop_all_live_jobs()
    assert o.get_device_activity({})["activity"]["AA"]["kind"] == "idle"


def test_stop_one_of_two_jobs_keeps_activity():
    o = _Owner()

    class _Task:
        def cancel(self): pass

    class _Loop:
        def call_soon_threadsafe(self, fn, *a): pass

    o._loop = _Loop()
    o._live_devices = {}
    o._live_tasks = {("AA", "sysmon"): _Task(), ("AA", "weather"): _Task()}
    o.set_device_activity({"mac": "AA", "kind": "sysmon"})

    o.live_job_stop({"mac": "AA", "kind": "sysmon"})   # weather still runs
    # another job remains → NOT reset to idle
    assert o.get_device_activity({})["activity"]["AA"]["kind"] == "sysmon"

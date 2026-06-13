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

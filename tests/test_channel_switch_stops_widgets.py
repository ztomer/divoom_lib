"""A channel/display switch must stop the device's live widgets first.

HW-found (only reproducible once live jobs actually push — they were
deadlocked before): switching to Clock while a sysmon widget streams left the
screen on the sysmon frame, because the widget's next 5s tick re-pushed it and
clobbered the switch. The fix stops the active device's live jobs first.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from divoom_daemon.device_owner import DeviceOwner
from divoom_gui.api.lighting import LightingApi


# ── daemon: live_jobs_stop_for ─────────────────────────────────────────────

class _Task:
    def __init__(self):
        self.cancelled = False
    def cancel(self):
        self.cancelled = True


class _Loop:
    def call_soon_threadsafe(self, fn, *a):
        fn(*a)


def _owner(tasks, mac="AA"):
    o = DeviceOwner.__new__(DeviceOwner)
    o.mac = mac
    o._loop = _Loop()
    o._live_tasks = dict(tasks)
    o._live_devices = {}
    return o


def test_stop_for_cancels_all_jobs_on_active_device():
    t1, t2, other = _Task(), _Task(), _Task()
    o = _owner({("AA", "sysmon"): t1, ("AA", "weather"): t2, ("BB", "stocks"): other})
    r = o.live_jobs_stop_for({})            # default mac = active (AA)
    assert r == {"success": True, "stopped": 2}
    assert t1.cancelled and t2.cancelled
    assert not other.cancelled              # a different device is untouched
    assert ("BB", "stocks") in o._live_tasks


def test_stop_for_explicit_mac():
    t = _Task()
    o = _owner({("BB", "stocks"): t}, mac="AA")
    r = o.live_jobs_stop_for({"mac": "BB"})
    assert r["stopped"] == 1 and t.cancelled


def test_stop_for_noop_when_no_jobs():
    o = _owner({}, mac="AA")
    assert o.live_jobs_stop_for({}) == {"success": True, "stopped": 0}


def test_stop_for_noop_when_no_active_mac():
    o = _owner({("AA", "sysmon"): _Task()}, mac=None)
    assert o.live_jobs_stop_for({}) == {"success": True, "stopped": 0}


# ── GUI: lighting actions stop widgets BEFORE the switch ───────────────────

class _RecorderClient:
    def __init__(self, calls):
        self._calls = calls
    def live_jobs_stop_for(self):
        self._calls.append("stop")
        return {"success": True}


def _lighting(calls):
    api = LightingApi(
        loop_thread=None,
        daemon_client_getter=lambda: _RecorderClient(calls),
        state_getter=lambda: {"current_target_mode": "single", "current_divoom": object()},
    )
    api._dispatch = lambda build: (calls.append("dispatch"), True)[1]
    return api


def test_switch_channel_stops_widgets_first():
    calls = []
    assert _lighting(calls).switch_channel("clock") is True
    assert calls == ["stop", "dispatch"]     # widget stopped BEFORE the switch


def test_set_clock_stops_widgets_first():
    calls = []
    _lighting(calls).set_clock(0)
    assert calls[0] == "stop"


def test_vj_and_visualizer_stop_widgets_first():
    for action in ("set_vj_effect", "set_visualization"):
        calls = []
        getattr(_lighting(calls), action)(0)
        assert calls[0] == "stop", action


def test_solid_light_stops_widgets_first():
    calls = []
    _lighting(calls).set_solid_light("#ffffff", 100)
    assert calls[0] == "stop"

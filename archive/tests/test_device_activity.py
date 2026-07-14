"""R46 #3: per-device activity registry (feeds the menubar tiles).

The daemon tracks what each device is showing — set by the GUI (channels) and by
the daemon's own live jobs (sysmon/stocks/weather/music) — and the menubar pulls
it to render one tile per device.
"""
import asyncio
import sys
import threading
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from archive.divoom_daemon.owner_live import OwnerLiveMixin


class _Owner(OwnerLiveMixin):
    def __init__(self):
        OwnerLiveMixin.__init__(self)


def _real_loop():
    """A real asyncio loop on a daemon thread — needed because R53's live_job_stop
    cancels AND AWAITS the task on the loop (a fake loop would hang the await)."""
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    return loop


def _live_task(loop):
    """A real, cancellable task on `loop` (a long sleep) standing in for a live
    poller, so live_job_stop's cancel+await behaves like production."""
    return asyncio.run_coroutine_threadsafe(
        _ensure_future_on_loop(), loop).result(timeout=2)


async def _ensure_future_on_loop():
    return asyncio.ensure_future(asyncio.sleep(3600))


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


def test_preview_thumbnail_stored_and_returned():
    """R50: a PNG data-URL preview is stored on the activity entry so the menubar
    can render the actual device face as a tile thumbnail."""
    o = _Owner()
    png = "data:image/png;base64,iVBORw0KGgo="
    o.set_device_activity({"mac": "AA", "kind": "clock", "name": "Ditoo", "preview": png})
    act = o.get_device_activity({})["activity"]
    assert act["AA"]["preview"] == png


def test_empty_kind_is_thumbnail_only_update():
    """R50: an empty kind means 'update the thumbnail, keep the kind' — a live
    frame must not clobber the semantic kind the daemon's live job set."""
    o = _Owner()
    o.set_device_activity({"mac": "AA", "kind": "music", "name": "Ditoo"})
    o.set_device_activity({"mac": "AA", "kind": "", "preview": "data:image/png;base64,Zm9v"})
    act = o.get_device_activity({})["activity"]
    assert act["AA"]["kind"] == "music"                       # not clobbered
    assert act["AA"]["preview"] == "data:image/png;base64,Zm9v"


def test_live_job_start_sets_activity_and_stop_reverts_to_idle():
    o = _Owner()
    o._loop = _real_loop()
    o._live_devices = {}
    # Simulate a started job (live_job_start's async create_task is exercised in
    # the HW path; here we set the activity + a real task directly, then stop it).
    o._live_tasks = {("AA", "sysmon"): _live_task(o._loop)}
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
    """G1: stopping all jobs marks the screens idle (not still 'streaming').
    R53.20: stop_all now cancel+AWAITs on the loop, so this needs a real loop+task."""
    o = _Owner()
    o._loop = _real_loop()
    o._live_devices = {}
    task = _live_task(o._loop)
    o._live_tasks = {("AA", "sysmon"): task}
    o.set_device_activity({"mac": "AA", "kind": "sysmon"})
    o.stop_all_live_jobs()
    assert task.done() is True                       # actually cancelled+awaited
    assert o.get_device_activity({})["activity"]["AA"]["kind"] == "idle"
    assert o._live_tasks == {}


def test_stop_all_live_jobs_disconnects_cached_devices():
    """R53.20: stop_all must AWAIT-disconnect cached background devices (not
    fire-and-forget), so device_owner.stop()'s loop teardown can't leak them."""
    o = _Owner()
    o._loop = _real_loop()

    class _Dev:
        def __init__(self):
            self.disconnected = False
        async def disconnect(self):
            self.disconnected = True

    dev = _Dev()
    o._live_devices = {"AA": dev}
    o._live_tasks = {("AA", "sysmon"): _live_task(o._loop)}
    o.set_device_activity({"mac": "AA", "kind": "sysmon"})
    o.stop_all_live_jobs()
    assert dev.disconnected is True                   # awaited, not fire-and-forget
    assert o._live_devices == {}


def test_live_jobs_persist_and_rehydrate(tmp_path, monkeypatch):
    """A2: a started live job is persisted; on a fresh owner, rehydrate restarts
    it. A user-stopped job is removed from the persisted set."""
    import json

    jobs_file = tmp_path / "live_jobs.json"

    o = _Owner()
    monkeypatch.setattr(o, "_live_jobs_path", lambda: jobs_file)
    o._loop = _real_loop()
    o._live_devices = {}
    # Simulate a started job (live_job_start's task creation is HW-path; here we
    # record params + persist directly via the same hooks).
    o._live_tasks = {("AA", "sysmon"): _live_task(o._loop)}
    o._live_params = {("AA", "sysmon"): {"size": 16}}
    o._save_live_jobs()
    assert json.loads(jobs_file.read_text()) == [
        {"mac": "AA", "kind": "sysmon", "params": {"size": 16}}]

    # Fresh owner rehydrates from the file.
    started = []
    o2 = _Owner()
    monkeypatch.setattr(o2, "_live_jobs_path", lambda: jobs_file)
    monkeypatch.setattr(o2, "live_job_start", lambda args: started.append(args) or {"success": True})
    o2.rehydrate_live_jobs()
    assert started == [{"mac": "AA", "kind": "sysmon", "params": {"size": 16}}]

    # A user stop removes it from the persisted set.
    o.live_job_stop({"mac": "AA", "kind": "sysmon"})
    assert json.loads(jobs_file.read_text()) == []


def test_live_health_stamped_onto_activity():
    """G5: a background live device's honest state is stamped onto its activity
    entry so the selector dot can show streaming vs degraded."""
    o = _Owner()

    class _Dev:
        def __init__(self, alive):
            self.is_connected = True
            self.is_alive = alive

    o._live_devices = {"AA": _Dev(True), "BB": _Dev(False)}
    o.set_device_activity({"mac": "AA", "kind": "sysmon"})
    o.set_device_activity({"mac": "BB", "kind": "weather"})
    act = o.get_device_activity({})["activity"]
    assert act["AA"]["state"] == "connected"
    assert act["BB"]["state"] == "degraded"   # reports connected but is_alive False


def test_live_job_stop_awaits_task_death():
    """R53: live_job_stop must AWAIT the task's cancellation (not fire-and-forget),
    so a stopped poller can't push one more frame or resurrect a released device."""
    o = _Owner()
    o._loop = _real_loop()
    o._live_devices = {}
    task = _live_task(o._loop)
    o._live_tasks = {("AA", "sysmon"): task}
    o.set_device_activity({"mac": "AA", "kind": "sysmon"})

    res = o.live_job_stop({"mac": "AA", "kind": "sysmon"})
    assert res["stopped"] is True
    assert task.done() is True                       # actually finished, not scheduled
    assert ("AA", "sysmon") not in o._live_tasks


def test_stop_one_of_two_jobs_keeps_activity():
    o = _Owner()
    o._loop = _real_loop()
    o._live_devices = {}
    o._live_tasks = {("AA", "sysmon"): _live_task(o._loop),
                     ("AA", "weather"): _live_task(o._loop)}
    o.set_device_activity({"mac": "AA", "kind": "sysmon"})

    o.live_job_stop({"mac": "AA", "kind": "sysmon"})   # weather still runs
    # another job remains → NOT reset to idle
    assert o.get_device_activity({})["activity"]["AA"]["kind"] == "sysmon"

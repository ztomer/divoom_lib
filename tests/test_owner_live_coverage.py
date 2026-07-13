"""Coverage push (PLANNING_ROUND61 item 1) for divoom_daemon/owner_live.py.

Targets the specific uncovered lines/branches (baseline 74% / 71 missed):
  - _save_live_jobs: persist-failure swallow (31-32)
  - rehydrate_live_jobs: no-file no-op (39), corrupt-json swallow (42-44),
    missing mac/kind skip (48), live_job_start-raises swallow (52-53)
  - set_device_activity: default-idle-kind branch for a brand-new entry (78)
  - _resolve_device_name: active device with no device_name falls through to
    the background/existing lookups instead of returning early (93->95)
  - _stamp_live_health: the ACTIVE device's own state stamp (135-137)
  - _idle_device_activity: falsy-mac no-op (152->exit)
  - live_job_start: missing args, unknown kind, and the full happy path incl.
    the device-loop bootstrap + task creation + A2 persistence (176-207)
  - live_job_stop: missing args (213), no-loop/unknown-key early return (217),
    the TOCTOU race where the task vanished before the loop-thread pop
    (228, 242), and the await-cancel exception path (237-240)
  - _drain_cmd_queue: exception swallow (270-271)
  - _release_live_device_if_idle: disconnect-exception swallow (283-284)
  - live_job_list (309-319), entirely untested before
  - stop_all_live_jobs: per-device disconnect exception swallow (345-346),
    the await-cancel exception path, and the no-loop else branch (352-356)
  - get_live_device: active-device reuse by mac/LAN-ip (366-368), cached-wall
    reuse (380), and the LAN device branch (412-418)

All BLE/network dependencies are mocked or replaced with fakes; no real
hardware access. Follows the owner_with_device / real-loop conventions already
used in tests/test_device_activity.py, tests/test_live_jobs.py and
tests/test_owner_connect_coverage.py.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from divoom_daemon.device_owner import DeviceOwner
from divoom_daemon.owner_live import OwnerLiveMixin


def _real_loop():
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    return loop


async def _ensure_future_on_loop():
    return asyncio.ensure_future(asyncio.sleep(3600))


def _live_task(loop):
    return asyncio.run_coroutine_threadsafe(
        _ensure_future_on_loop(), loop).result(timeout=2)


class _Owner(OwnerLiveMixin):
    """Bare OwnerLiveMixin host with the attrs the mixin's methods touch."""
    def __init__(self):
        OwnerLiveMixin.__init__(self)
        self._device = None
        self.mac = None
        self._lan_ip = None
        self._wall = None


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


# ── _save_live_jobs persist-failure swallow (31-32) ─────────────────────────

def test_save_live_jobs_swallows_write_failure(tmp_path):
    o = _Owner()
    o._live_params = {("AA", "sysmon"): {"x": 1}}
    o._live_jobs_path = lambda: tmp_path / "live_jobs.json"
    with patch("divoom_lib.utils.atomic_io.atomic_write_text",
               side_effect=OSError("disk full")):
        o._save_live_jobs()  # must not raise


# ── rehydrate_live_jobs (39, 42-44, 48, 52-53) ──────────────────────────────

def test_rehydrate_no_file_is_noop(tmp_path):
    o = _Owner()
    o._live_jobs_path = lambda: tmp_path / "missing.json"
    o.rehydrate_live_jobs()  # nothing to do, no exception


def test_rehydrate_corrupt_json_is_swallowed(tmp_path):
    path = tmp_path / "live_jobs.json"
    path.write_text("{not json", encoding="utf-8")
    o = _Owner()
    o._live_jobs_path = lambda: path
    o.rehydrate_live_jobs()  # must not raise


def test_rehydrate_skips_incomplete_entries(tmp_path):
    path = tmp_path / "live_jobs.json"
    path.write_text(json.dumps([
        {"mac": "AA"},              # missing kind -> skipped
        {"kind": "sysmon"},         # missing mac -> skipped
    ]), encoding="utf-8")
    o = _Owner()
    o._live_jobs_path = lambda: path
    started = []
    o.live_job_start = lambda args: started.append(args) or {"success": True}
    o.rehydrate_live_jobs()
    assert started == []


def test_rehydrate_swallows_live_job_start_failure(tmp_path):
    path = tmp_path / "live_jobs.json"
    path.write_text(json.dumps([{"mac": "AA", "kind": "sysmon", "params": {}}]),
                    encoding="utf-8")
    o = _Owner()
    o._live_jobs_path = lambda: path

    def _boom(args):
        raise RuntimeError("start boom")

    o.live_job_start = _boom
    o.rehydrate_live_jobs()  # must not raise


# ── set_device_activity default-idle-kind branch (78) ───────────────────────

def test_set_device_activity_defaults_kind_idle_for_new_entry():
    o = _Owner()
    o.set_device_activity({"mac": "ZZ", "kind": ""})
    assert o.get_device_activity({})["activity"]["ZZ"]["kind"] == "idle"


# ── _resolve_device_name active-device-no-name fallthrough (93->95) ─────────

def test_resolve_name_active_device_without_device_name_falls_through():
    o = _Owner()

    class _Dev:
        pass  # no device_name attribute

    o.mac = "AA"
    o._device = _Dev()
    o.set_device_activity({"mac": "AA", "kind": "clock"})
    assert "name" not in o.get_device_activity({})["activity"]["AA"]


# ── _stamp_live_health active-device branch (135-137) ───────────────────────

def test_stamp_live_health_stamps_active_device_state():
    o = _Owner()

    class _Dev:
        is_connected = True
        is_alive = True

    o.mac = "AA"
    o._device = _Dev()
    o._active_key = lambda: "AA"
    o.set_device_activity({"mac": "AA", "kind": "clock"})
    act = o.get_device_activity({})["activity"]
    assert act["AA"]["state"] == "connected"


# ── _idle_device_activity falsy-mac no-op (152->exit) ───────────────────────

def test_idle_device_activity_noop_for_falsy_mac():
    o = _Owner()
    o._idle_device_activity(None)
    o._idle_device_activity("")
    assert o.get_device_activity({})["activity"] == {}


# ── live_job_start (176-207) ─────────────────────────────────────────────────

def test_live_job_start_requires_mac_and_kind(owner_with_device):
    owner, _ = owner_with_device
    result = owner.live_job_start({"mac": "AA"})
    assert result["success"] is False
    assert "requires" in result["error"]


def test_live_job_start_unknown_kind_errors(owner_with_device):
    owner, _ = owner_with_device
    result = owner.live_job_start({"mac": "AA", "kind": "nonexistent_kind_xyz"})
    assert result["success"] is False
    assert "unknown live job kind" in result["error"]


def test_live_job_start_success_creates_task_and_persists(tmp_path, monkeypatch):
    """Full happy path incl. the loop bootstrap (self._loop is None branch),
    task creation, activity set, and A2 persistence."""
    from divoom_daemon import live_jobs

    ran = threading.Event()

    async def _fake_job(device_owner, mac, params):
        ran.set()
        await asyncio.sleep(3600)

    monkeypatch.setattr(live_jobs, "run_covtest", _fake_job, raising=False)

    dev = _MockDevice()
    owner = DeviceOwner(device=dev)
    jobs_file = tmp_path / "live_jobs.json"
    owner._live_jobs_path = lambda: jobs_file
    assert owner._loop is None   # exercises the bootstrap branch
    try:
        result = owner.live_job_start(
            {"mac": "AA:BB", "kind": "covtest", "params": {"device_name": "Ditoo"}})
        assert result == {"success": True}
        assert owner._loop is not None       # _device_loop() was triggered
        assert ("AA:BB", "covtest") in owner._live_tasks
        assert ran.wait(timeout=2)
        act = owner.get_device_activity({})["activity"]
        assert act["AA:BB"]["kind"] == "covtest"
        assert act["AA:BB"]["name"] == "Ditoo"
        assert owner._live_params[("AA:BB", "covtest")] == {"device_name": "Ditoo"}
        persisted = json.loads(jobs_file.read_text())
        assert persisted == [{"mac": "AA:BB", "kind": "covtest",
                              "params": {"device_name": "Ditoo"}}]
    finally:
        owner.stop()


# ── live_job_stop (213, 217, 228, 237-240, 242) ─────────────────────────────

def test_live_job_stop_requires_mac_and_kind(owner_with_device):
    owner, _ = owner_with_device
    result = owner.live_job_stop({"mac": "AA"})
    assert result["success"] is False
    assert "requires" in result["error"]


def test_live_job_stop_unknown_key_is_a_noop(owner_with_device):
    owner, _ = owner_with_device
    result = owner.live_job_stop({"mac": "AA", "kind": "sysmon"})
    assert result == {"success": True, "stopped": False}


def test_live_job_stop_race_task_already_popped():
    """228 + 242: another thread can pop the task between the outer 'key not
    in tasks' check and the loop-thread coroutine's own pop (a genuine TOCTOU
    the code defends against). Simulate deterministically with a dict whose
    __contains__ always reports present but whose pop always finds nothing."""
    class _RaceyTasks(dict):
        def __contains__(self, k):
            return True

        def pop(self, k, default=None):
            return default

    dev = _MockDevice()
    owner = DeviceOwner(device=dev)
    owner._device_loop()
    owner._live_tasks = _RaceyTasks()
    try:
        result = owner.live_job_stop({"mac": "AA", "kind": "sysmon"})
        assert result == {"success": True, "stopped": False}
    finally:
        owner.stop()


def test_live_job_stop_await_cancel_exception_is_caught(tmp_path):
    """237-240: run_coroutine_threadsafe raising (e.g. a closed loop) must be
    caught, the task popped best-effort, and the stop still reported."""
    o = _Owner()
    o._live_jobs_path = lambda: tmp_path / "live_jobs.json"
    loop = asyncio.new_event_loop()
    loop.close()
    o._loop = loop
    o._live_tasks = {("AA", "sysmon"): object()}
    result = o.live_job_stop({"mac": "AA", "kind": "sysmon"})
    assert result == {"success": True, "stopped": True}
    assert ("AA", "sysmon") not in o._live_tasks


# ── _drain_cmd_queue exception swallow (270-271) ────────────────────────────

def test_drain_cmd_queue_swallows_submit_exception():
    o = _Owner()

    class _BoomQueue:
        def submit_async(self, coro):
            coro.close()
            raise RuntimeError("submit boom")

    o._cmd_queue = _BoomQueue()
    asyncio.run(o._drain_cmd_queue())  # must not raise


# ── _release_live_device_if_idle disconnect exception (283-284) ─────────────

def test_release_live_device_swallows_disconnect_exception():
    o = _Owner()
    o._loop = _real_loop()

    class _BoomDev:
        async def disconnect(self):
            raise RuntimeError("disconnect boom")

    o._live_devices = {"AA": _BoomDev()}
    o._release_live_device_if_idle("AA")  # must not raise
    assert "AA" not in o._live_devices


# ── live_job_list (309-319), entirely untested before ───────────────────────

def test_live_job_list_all_and_filtered_by_mac():
    o = _Owner()

    class _Task:
        def __init__(self, done=False, cancelled=False):
            self._done, self._cancelled = done, cancelled

        def done(self):
            return self._done

        def cancelled(self):
            return self._cancelled

    o._live_tasks = {
        ("AA", "sysmon"): _Task(done=False, cancelled=False),
        ("BB", "weather"): _Task(done=True, cancelled=False),
    }

    all_jobs = o.live_job_list({})["jobs"]
    assert len(all_jobs) == 2

    filtered = o.live_job_list({"mac": "AA"})["jobs"]
    assert filtered == [{"mac": "AA", "kind": "sysmon",
                         "done": False, "cancelled": False}]


# ── stop_all_live_jobs (345-346, 352-356) ───────────────────────────────────

def test_stop_all_live_jobs_swallows_device_disconnect_exception():
    loop = _real_loop()
    o = _Owner()
    o._loop = loop

    class _BoomDev:
        async def disconnect(self):
            raise RuntimeError("disconnect boom")

    o._live_devices = {"AA": _BoomDev()}
    o._live_tasks = {("AA", "sysmon"): _live_task(loop)}
    o.stop_all_live_jobs()  # must not raise
    assert o._live_devices == {}
    assert o._live_tasks == {}


def test_stop_all_live_jobs_await_cancel_exception_is_caught():
    o = _Owner()
    loop = asyncio.new_event_loop()
    loop.close()
    o._loop = loop
    o._live_tasks = {("AA", "sysmon"): object()}
    o.stop_all_live_jobs()  # exception swallowed, tasks cleared best-effort
    assert o._live_tasks == {}


def test_stop_all_live_jobs_no_loop_clears_tasks_directly():
    o = _Owner()
    o._loop = None
    o._live_tasks = {("AA", "sysmon"): object()}
    o.stop_all_live_jobs()
    assert o._live_tasks == {}


# ── get_live_device (366-368, 380, 412-418) ─────────────────────────────────

def test_get_live_device_reuses_active_device_by_mac():
    o = _Owner()
    active_dev = object()
    o._device = active_dev
    o.mac = "AA:BB"

    async def run():
        return await o.get_live_device("AA:BB", {})

    assert asyncio.run(run()) is active_dev


def test_get_live_device_reuses_active_device_by_lan_ip():
    o = _Owner()
    active_dev = object()
    o._device = active_dev
    o.mac = None
    o._lan_ip = "10.0.0.5"

    async def run():
        return await o.get_live_device("LAN:10.0.0.5", {})

    assert asyncio.run(run()) is active_dev


def test_get_live_device_reuses_cached_wall():
    o = _Owner()
    fake_wall = object()
    o._wall = fake_wall
    o._device = None

    async def run():
        return await o.get_live_device("MatrixWall", {})

    assert asyncio.run(run()) is fake_wall


def test_get_live_device_lan_branch_builds_uncached_device(monkeypatch):
    import divoom_lib.divoom as divmod
    import divoom_lib.lan_transport as lan_mod

    built_lan = []

    class _FakeLan:
        def __init__(self, **kw):
            built_lan.append(kw)

    monkeypatch.setattr(lan_mod, "LanTransport", _FakeLan)
    monkeypatch.setattr(divmod, "Divoom", lambda **kw: MagicMock(mac=None))

    o = _Owner()

    async def run():
        return await o.get_live_device("LAN:10.0.0.9", {"lan_token": 42})

    result = asyncio.run(run())
    assert built_lan and built_lan[0]["device_ip"] == "10.0.0.9"
    assert "LAN:10.0.0.9" not in o._live_devices  # NOT cached (per source comment)
    assert result is not None

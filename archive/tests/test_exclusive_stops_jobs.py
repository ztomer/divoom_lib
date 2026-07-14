"""An exclusive session must stop the active device's live jobs first.

Deferred BLE finding (HW-confirmed 2026-06-20): an exclusive push (animation /
custom-art, `async with proxy.exclusive(token)`) takes over the screen, but a
sysmon live job keeps submitting TOKENLESS frames. During exclusive mode the
queue only dispatches matching-token items, so those frames pile up and then
BURST out FIFO the instant the session releases — clobbering what was just
pushed. exclusive_start() now stops the active device's live jobs first (like the
channel-switch path); background-device jobs are left running.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from archive.divoom_daemon.device_owner import DeviceOwner


class _Queue:
    # exclusive_start acquires OFF the dispatch queue via acquire_now (a lock-acquire
    # must not be gated by the lock it seeks — see CommandQueue.acquire_now). A foreign
    # owner would raise here; this fake always grants.
    def __init__(self):
        self.acquired = []

    def acquire_now(self, token):
        self.acquired.append(token)
        return None


def _owner():
    o = DeviceOwner.__new__(DeviceOwner)
    o._cmd_queue = _Queue()
    return o


def test_exclusive_start_stops_active_live_jobs():
    o = _owner()
    calls = []
    o.live_jobs_stop_for = lambda args: calls.append(args) or {"success": True, "stopped": 1}
    r = o.exclusive_start({"token": "art-token"})
    assert calls == [{}], "exclusive_start must stop the active device's live jobs"
    assert o._cmd_queue.acquired == ["art-token"], "must acquire off-queue via acquire_now"
    assert r["success"] is True and r["token"] == "art-token"


def test_exclusive_start_empty_token_does_not_stop_jobs():
    o = _owner()
    calls = []
    o.live_jobs_stop_for = lambda args: calls.append(args)
    r = o.exclusive_start({})
    assert r["success"] is False
    assert calls == [], "a rejected exclusive_start must not touch live jobs"


def test_exclusive_start_survives_stop_jobs_error():
    """A failure stopping jobs must not abort acquiring the exclusive session."""
    o = _owner()
    def _boom(args):
        raise RuntimeError("loop gone")
    o.live_jobs_stop_for = _boom
    r = o.exclusive_start({"token": "t"})
    assert r["success"] is True and r["token"] == "t"

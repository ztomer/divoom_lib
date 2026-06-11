"""Wall lifecycle — clearing/reconfiguring a wall must release its BLE links.

HW-found: wall_configure nulled self._wall without disconnecting, so every
screen's connection leaked; the next build then timed out reconnecting devices
the daemon still held.
"""
import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from divoom_daemon.device_owner import DeviceOwner


class _FakeWall:
    def __init__(self):
        self.disconnects = 0
        self.is_connected = True
    async def disconnect(self):
        self.disconnects += 1


def _owner(wall=None, slots=None):
    o = DeviceOwner.__new__(DeviceOwner)
    o._wall = wall
    o._wall_slots = slots or {}
    # _run_device just drives the coroutine to completion.
    o._run_device = lambda coro, **k: asyncio.new_event_loop().run_until_complete(coro)
    return o


def test_clear_disconnects_and_drops_the_wall():
    wall = _FakeWall()
    o = _owner(wall, {"AA": {}})
    r = o.wall_configure({"slots": {}})
    assert r == {"success": True, "wall": False}
    assert wall.disconnects == 1          # released, not leaked
    assert o._wall is None
    assert o._wall_slots == {}


def test_drop_current_wall_is_noop_without_a_wall():
    o = _owner(None)
    o._drop_current_wall()                # must not raise
    assert o._wall is None


def test_drop_current_wall_swallows_disconnect_errors():
    class _Bad:
        async def disconnect(self):
            raise RuntimeError("BLE gone")
    o = _owner(_Bad())
    o._drop_current_wall()                # error logged, not raised
    assert o._wall is None


def test_reconfigure_releases_old_wall_before_rebuild(monkeypatch):
    """A NEW layout (slots differ) must disconnect the old wall before building
    the new one — the path that leaked on hardware."""
    old = _FakeWall()
    o = _owner(old, {"AA": {"x": 0, "y": 0, "size": 16}})

    built = {"n": 0}

    class _NewWall:
        is_connected = True
        async def connect(self):
            built["n"] += 1

    monkeypatch.setattr("divoom_lib.wall.DivoomWall", lambda *a, **k: _NewWall())
    r = o.wall_configure({"slots": {"BB": {"x": 1, "y": 0, "size": 16}}})
    assert r["success"] is True
    assert old.disconnects == 1           # old wall released first
    assert built["n"] == 1                # new wall built + connected

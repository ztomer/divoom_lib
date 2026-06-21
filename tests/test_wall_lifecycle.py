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


# ── G4: a screen is owned by the active link OR the wall, not both ───────────


class _FakeDev:
    def __init__(self):
        self.disconnects = 0
    async def disconnect(self):
        self.disconnects += 1


def test_relinquish_active_when_its_mac_is_a_wall_slot():
    """HW-confirmed: a wall reusing the active device's MAC left a dead handle
    that timed out ~5s on every active call. The active device must be dropped."""
    o = _owner(None)
    o._device = _FakeDev()
    o.mac = "AA"
    o._lan_ip = None
    o._relinquish_active_if_in({"AA": {"x": 0, "y": 0, "size": 16}})
    assert o._device is None and o.mac is None
    assert o._lan_ip is None


def test_keep_active_when_its_mac_is_not_a_wall_slot():
    o = _owner(None)
    dev = _FakeDev()
    o._device = dev
    o.mac = "AA"
    o._lan_ip = None
    o._relinquish_active_if_in({"BB": {}})
    assert o._device is dev and o.mac == "AA"


def test_relinquish_is_case_insensitive():
    """R53.24/G4: a wall slot key in a DIFFERENT case than the active mac must STILL
    relinquish — else the mac is double-owned (active + wall)."""
    o = _owner(None)
    o._device = _FakeDev()
    o.mac = "aa:bb:cc:dd:ee:01"            # active stored lowercase
    o._lan_ip = None
    o._relinquish_active_if_in({"AA:BB:CC:DD:EE:01": {"x": 0, "y": 0, "size": 16}})
    assert o._device is None and o.mac is None, "case drift defeated G4"


def test_wall_configure_uppercases_slot_keys():
    """R53.24: slot MACs are canonicalized to upper at the boundary, so the delta
    key-arithmetic + device.mac lookups agree (else removed panels leak)."""
    o = _owner(None)
    captured = {}
    o._drop_current_wall = lambda: None
    o._relinquish_active_if_in = lambda slots: captured.update(relinquished=slots)
    o._run_device = lambda coro, **k: (coro.close(), object())[1]   # skip real build
    o.wall_configure({"slots": {"aa:bb": {"x": 0, "y": 0, "size": 16}}})
    assert set(o._wall_slots) == {"AA:BB"}                  # stored uppercase
    assert set(captured["relinquished"]) == {"AA:BB"}


def test_connect_to_a_wall_member_drops_the_wall(monkeypatch):
    """Taking a current wall slot as the active device relinquishes the wall so
    they don't both claim the same MAC."""
    wall = _FakeWall()
    o = _owner(wall, {"LAN:1.2.3.4": {"x": 0, "y": 0, "size": 16}})
    o._device = None
    o.mac = None
    o._lan_ip = None

    async def _fake_build(args):
        o._device = object()
        o._lan_ip = "1.2.3.4"
        return o._device

    o._build_device_async = _fake_build
    monkeypatch.setattr(o, "_status_fields", lambda: {"connected": True})
    r = o.connect({"lan_ip": "1.2.3.4"})
    assert r["success"] is True
    assert wall.disconnects == 1 and o._wall is None and o._wall_slots == {}


# ── G7: delta reconfigure — keep shared screens, swap only the delta ─────────


class _Slot:
    def __init__(self, dev):
        self.device = dev


class _WallDev:
    def __init__(self, mac):
        self.mac = mac
        self.is_connected = True
        self.disconnects = 0
    async def disconnect(self):
        self.disconnects += 1


def _slot(x):
    return {"x": x, "y": 0, "size": 16}


def test_wall_delta_reuses_shared_screens(monkeypatch):
    """Reconfiguring {A,B} -> {A,C} keeps A connected (transplanted, not rebuilt),
    drops B, and only the new wall connects (A fast-verifies)."""
    built = []

    class _NewWall:
        is_connected = True
        def __init__(self, configs, custom_logger=None):
            self.devices = [_Slot(_WallDev(c["mac"])) for c in configs]
            self.connected = 0
            built.append(self)
        async def connect(self):
            self.connected += 1

    devA, devB = _WallDev("A"), _WallDev("B")

    class _OldWall:
        devices = [_Slot(devA), _Slot(devB)]

    o = _owner(_OldWall(), {"A": _slot(0), "B": _slot(1)})
    o._device = None
    o.mac = None
    o._lan_ip = None
    monkeypatch.setattr("divoom_lib.wall.DivoomWall", _NewWall)

    r = o.wall_configure({"slots": {"A": _slot(0), "C": _slot(1)}})
    assert r == {"success": True, "wall": True}
    new = built[-1]
    by_mac = {s.device.mac: s.device for s in new.devices}
    assert by_mac["A"] is devA          # shared screen reused (no reconnect)
    assert by_mac["C"] is not devA      # added screen is fresh
    assert devB.disconnects == 1        # removed screen released
    assert new.connected == 1           # only the new wall connects
    assert o._wall is new
    assert "C" in o._wall_slots and "B" not in o._wall_slots


def test_wall_no_overlap_falls_back_to_full_rebuild(monkeypatch):
    """A disjoint layout {A,B} -> {C,D} has no shared screen, so it tears down the
    old wall fully and builds fresh."""
    built = []

    class _NewWall:
        is_connected = True
        def __init__(self, configs, custom_logger=None):
            self.devices = [_Slot(_WallDev(c["mac"])) for c in configs]
            built.append(self)
        async def connect(self):
            pass

    old = _FakeWall()
    o = _owner(old, {"A": _slot(0), "B": _slot(1)})
    o._device = None
    o.mac = None
    o._lan_ip = None
    monkeypatch.setattr("divoom_lib.wall.DivoomWall", _NewWall)

    r = o.wall_configure({"slots": {"C": _slot(0), "D": _slot(1)}})
    assert r == {"success": True, "wall": True}
    assert old.disconnects == 1         # old wall torn down fully (no overlap)
    assert {s.device.mac for s in built[-1].devices} == {"C", "D"}

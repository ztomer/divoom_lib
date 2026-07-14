"""R53.19: three bugs found by an adversarial multi-agent re-read of the BLE
subsystem (wall + live-job + transport-router), each fixed and locked here.

1. divoom_lib/connection.py: bare `BTSppTransport` (unbound name) crashed every
   SPP *reconnect* with NameError — hidden on first connect by short-circuit.
2. divoom_daemon/owner_live.py: a background-wall live job dropped every slot that
   lacked a "height" key (configs.append was wrongly nested under `if height`).
3. divoom_lib/wall.py: wall.disconnect() used a bare gather → the first failing
   slot abandoned the rest, leaking still-connected/registered devices.
"""
import asyncio
import logging
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.append(str(Path(__file__).parent.parent))


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── 3. wall.disconnect() disconnects ALL slots even if one raises ────────────

class _WDev:
    def __init__(self, mac, fail=False):
        self.mac = mac
        self.fail = fail
        self.disconnected = False

    async def disconnect(self):
        self.disconnected = True
        if self.fail:
            raise RuntimeError("boom")


class _WSlot:
    def __init__(self, dev):
        self.device = dev


def test_wall_disconnect_disconnects_all_slots_despite_one_failure():
    from divoom_lib.wall import DivoomWall
    w = DivoomWall.__new__(DivoomWall)
    w.logger = logging.getLogger("wall_test")
    a, b, c = _WDev("A"), _WDev("B", fail=True), _WDev("C")
    w.devices = [_WSlot(a), _WSlot(b), _WSlot(c)]
    _run(w.disconnect())                    # must NOT raise
    assert a.disconnected and b.disconnected and c.disconnected, "a slot was abandoned"


# ── 2. background-wall live job keeps every slot (even without "height") ─────

def test_wall_live_config_keeps_slots_without_height(monkeypatch):
    from archive.divoom_daemon.owner_live import OwnerLiveMixin

    captured = {}

    class _FakeWall:
        def __init__(self, configs, **k):
            captured["configs"] = configs

        async def connect(self):
            pass

    monkeypatch.setattr("divoom_lib.wall.DivoomWall", _FakeWall)

    o = OwnerLiveMixin.__new__(OwnerLiveMixin)
    o._device = None
    o._wall = None
    o._live_devices = {}
    o.mac = None

    params = {"wall_slots": {
        "AA": {"x": 0, "y": 0},                       # no width/height
        "BB": {"x": 1, "y": 0, "height": 16},         # has height
        "CC": {"x": 2, "y": 0, "width": 16},          # width only
    }}
    _run(o.get_live_device("MatrixWall", params))
    macs = {c["mac"] for c in captured["configs"]}
    assert macs == {"AA", "BB", "CC"}, f"slots dropped: only got {macs}"


def test_background_wall_live_device_is_cached(monkeypatch):
    """R53.23: a background MatrixWall live job must REUSE its built wall, not
    rebuild+reconnect (a full multi-device BLE connect storm) every tick."""
    from archive.divoom_daemon.owner_live import OwnerLiveMixin

    builds = {"n": 0}

    class _FakeWall:
        def __init__(self, configs, **k):
            builds["n"] += 1
            self.is_alive = True            # drives the reuse gate
        async def connect(self):
            pass

    monkeypatch.setattr("divoom_lib.wall.DivoomWall", _FakeWall)

    o = OwnerLiveMixin.__new__(OwnerLiveMixin)
    o._device = None
    o._wall = None
    o._live_devices = {}
    o.mac = None
    params = {"wall_slots": {"AA": {"x": 0, "y": 0, "height": 16}}}

    w1 = _run(o.get_live_device("MatrixWall", params))
    w2 = _run(o.get_live_device("MatrixWall", params))
    assert w1 is w2, "wall was rebuilt instead of reused"
    assert builds["n"] == 1, f"wall built {builds['n']}x (should cache after first)"
    assert o._live_devices["MatrixWall"] is w1


# ── 1. SPP reconnect no longer NameErrors on the isinstance check ───────────

def test_spp_reconnect_does_not_nameerror(monkeypatch):
    """Drive DivoomConnection.connect() through the use_spp branch with _use_spp
    already True (the reconnect case). Before the fix the bare `BTSppTransport`
    name raised NameError at the isinstance() check; now it swaps cleanly.

    NB: must NOT set DIVOOM_MOCK_BLE — is_mock=True would skip the use_spp logic
    entirely (line 75 requires `not is_mock`), so the bug only reproduces with a
    real (non-mock) connect path and a concrete already-SPP transport in place."""
    from divoom_lib.protocol import DivoomProtocol

    with patch("divoom_lib.divoom.BleakClient") as mk:
        mk.return_value = AsyncMock()
        proto = DivoomProtocol(mac="AA:BB:CC:DD:EE:FF", device_name="Ditoo-Test")
    conn = proto._conn

    class _FakeOldSPP:
        mac_address = "AA-BB-CC-DD-EE-FF"
        device_name = "Ditoo-Test"
        use_ios_le_protocol = False        # so use_spp resolves True
        client = None                      # so is_mock stays False
        is_connected = True
        async def disconnect(self):
            pass

    conn._active_transport = _FakeOldSPP()
    conn._use_spp = True                   # already on SPP → the reconnect branch

    # Must be a real CLASS (not a lambda) — the fixed code does isinstance() against it.
    class _FakeSppTransport:
        def __init__(self, **k):
            self.is_connected = True
        async def connect(self):
            pass
        async def disconnect(self):
            pass

    monkeypatch.setattr("divoom_lib.spp_connection.resolve_classic_mac",
                        lambda *a, **k: "11-22-33-44-55-66")
    monkeypatch.setattr("divoom_lib.bt_spp_transport.BTSppTransport", _FakeSppTransport)
    monkeypatch.setattr(conn, "_teardown_outgoing_transport", AsyncMock())

    _run(conn.connect())                   # before the fix: NameError at line 83
    assert isinstance(conn._active_transport, _FakeSppTransport), "SPP swap did not happen"

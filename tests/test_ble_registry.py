"""BLE connection registry — one live connection per address (R45 #6).

CoreBluetooth allows one connection per peripheral per central, so a MAC used
standalone and as a wall slot must not be double-connected. The registry evicts
the prior in-process owner before a new connect to the same address.
"""
import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from divoom_lib import ble_registry


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _T:
    """A minimal transport stand-in: an address + async disconnect()."""
    def __init__(self, mac="AA:BB:CC"):
        self.mac = mac
        self.disconnects = 0

    async def disconnect(self):
        self.disconnects += 1
        ble_registry.unregister(self.mac, self)   # mirror the real transport


def setup_function(_):
    ble_registry._reset()


def test_register_and_owner_case_insensitive():
    t = _T("aa:bb")
    ble_registry.register("aa:bb", t)
    assert ble_registry.owner("AA:BB") is t      # normalized to upper


def test_evict_disconnects_and_drops_prior_owner():
    old, new = _T("AA"), _T("AA")
    ble_registry.register("AA", old)
    _run(ble_registry.evict("AA", new))
    assert old.disconnects == 1
    assert ble_registry.owner("AA") is None       # evicted, registry cleared


def test_evict_noop_when_keep_is_current_owner():
    t = _T("AA")
    ble_registry.register("AA", t)
    _run(ble_registry.evict("AA", t))
    assert t.disconnects == 0 and ble_registry.owner("AA") is t


def test_evict_noop_when_nothing_registered():
    _run(ble_registry.evict("AA", _T("AA")))      # must not raise


def test_unregister_only_drops_the_current_owner():
    t1, t2 = _T("AA"), _T("AA")
    ble_registry.register("AA", t1)
    ble_registry.unregister("AA", t2)             # t2 isn't the owner — no-op
    assert ble_registry.owner("AA") is t1
    ble_registry.unregister("AA", t1)
    assert ble_registry.owner("AA") is None


def test_evict_swallows_disconnect_errors():
    class _Bad:
        mac = "AA"
        async def disconnect(self):
            raise RuntimeError("BLE gone")
    bad = _Bad()
    ble_registry.register("AA", bad)
    _run(ble_registry.evict("AA", _T("AA")))      # error logged, not raised
    assert ble_registry.owner("AA") is None        # still dropped


def test_blank_address_is_ignored():
    t = _T(None)
    ble_registry.register(None, t)
    assert ble_registry.owner(None) is None
    _run(ble_registry.evict(None, t))              # no-op, no raise

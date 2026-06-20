"""Scan must not drop a device the daemon already owns.

HW-found (2026-06-20 churn stress): a *connected* BLE peripheral stops
advertising, so a scan run while the daemon holds a device finds N-1 devices and
the held one vanishes from the selector ("should be 4, found 3"). The daemon
knows the device exists, so scan unions its owned devices back in — and resolves
their friendly names from a mac->name cache populated by prior scans.
"""
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))

from divoom_daemon import device_owner as mod
from divoom_lib.ble_connection import ConnectResult, ConnectionState
from divoom_lib.ble_preflight import preflight_bluetooth  # noqa: F401  (patched by path)


class _Dev:
    def __init__(self, name=None, is_connected=True):
        self.device_name = name
        self.is_connected = is_connected


def _owner(monkeypatch, advertised):
    """A DeviceOwner whose BLE scan returns `advertised` (list of {name,address})
    without touching real Bluetooth."""
    o = mod.DeviceOwner.__new__(mod.DeviceOwner)
    o.mac = None
    o._device = None
    o._lan_ip = None
    o._scan_name_cache = {}
    o._live_devices = {}
    monkeypatch.setattr("divoom_lib.ble_preflight.preflight_bluetooth",
                        lambda **k: ConnectResult(True, ConnectionState.CONNECTED))
    monkeypatch.setattr(mod, "_json_safe", lambda x: x, raising=False)
    # scan() runs the BLE coroutine via _run_on_loop; stub it to return a COPY of
    # advertised (scan mutates the list via the owned-union append).
    monkeypatch.setattr(o, "_run_on_loop", lambda coro: (coro.close(), list(advertised))[1],
                        raising=False)
    return o


ADVERTISED = [
    {"name": "Timoo-light-4", "address": "BB:22"},
    {"name": "Ditoo-light-2", "address": "CC:33"},
    {"name": "Tivoo-Max", "address": "DD:44"},
]


def test_held_active_device_unioned_back_in(monkeypatch):
    o = _owner(monkeypatch, ADVERTISED)
    # Pre-seed the name cache (as a prior scan would) and hold Pixoo active.
    o._scan_name_cache["AA:11"] = "Pixoo-1"
    o.mac = "AA:11"
    o._device = _Dev(name=None)             # transport doesn't know the name
    reply = o.scan({"timeout": 1, "limit": 4})
    by_addr = {d["address"].upper(): d for d in reply["devices"]}
    assert "AA:11" in by_addr                 # held device not dropped
    assert by_addr["AA:11"]["name"] == "Pixoo-1"   # name resolved from cache
    assert by_addr["AA:11"]["owned"] is True
    assert len(reply["devices"]) == 4         # all four present


def test_advertised_device_not_duplicated(monkeypatch):
    """If the owned device IS advertising this round, it appears once (not twice)."""
    o = _owner(monkeypatch, ADVERTISED + [{"name": "Pixoo-1", "address": "AA:11"}])
    o.mac = "AA:11"
    o._device = _Dev(name="Pixoo-1")
    reply = o.scan({"timeout": 1, "limit": 5})
    addrs = [d["address"].upper() for d in reply["devices"]]
    assert addrs.count("AA:11") == 1


def test_scan_populates_name_cache(monkeypatch):
    o = _owner(monkeypatch, ADVERTISED)
    o.scan({"timeout": 1, "limit": 4})
    assert o._scan_name_cache["BB:22"] == "Timoo-light-4"
    assert o._scan_name_cache["DD:44"] == "Tivoo-Max"


def test_background_live_device_unioned(monkeypatch):
    """A background live-job device (not the active one) is also kept visible."""
    o = _owner(monkeypatch, ADVERTISED)
    o._live_devices = {"EE:55": _Dev(name="Backpack-9")}
    reply = o.scan({"timeout": 1, "limit": 8})
    by_addr = {d["address"].upper(): d for d in reply["devices"]}
    assert by_addr["EE:55"]["name"] == "Backpack-9"
    assert by_addr["EE:55"]["owned"] is True


def test_lan_active_device_not_unioned(monkeypatch):
    """A LAN device isn't a BLE scan result — don't inject it."""
    o = _owner(monkeypatch, ADVERTISED)
    o.mac = "AA:11"
    o._device = _Dev(name="Pixoo-LAN")
    o._lan_ip = "192.168.1.50"
    reply = o.scan({"timeout": 1, "limit": 4})
    addrs = [d["address"].upper() for d in reply["devices"]]
    assert "AA:11" not in addrs

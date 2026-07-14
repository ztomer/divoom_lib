"""BLE Hardening Phase 6 — connection-state observability.

The daemon exposes ONE honest connection_state on device_status so the GUI dot
can show DEGRADED (connected-but-a-write/drop-just-failed), not just on/off, and
logs a one-line transition so the daemon log is a connection timeline.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from divoom_lib.ble_connection import derive_connection_state, ConnectionState
from archive.divoom_daemon.device_owner import DeviceOwner


class _Dev:
    def __init__(self, connected, alive):
        self.is_connected = connected
        self.is_alive = alive


# ── pure state derivation ──────────────────────────────────────────────────

def test_no_device_is_disconnected():
    assert derive_connection_state(None) is ConnectionState.DISCONNECTED


def test_not_connected_is_disconnected():
    assert derive_connection_state(_Dev(False, False)) is ConnectionState.DISCONNECTED


def test_connected_and_alive_is_connected():
    assert derive_connection_state(_Dev(True, True)) is ConnectionState.CONNECTED


def test_connected_but_not_alive_is_degraded():
    # The OS-drop callback / write-failure inference flipped is_alive — the dot
    # must show DEGRADED, not a misleading solid 'connected'.
    assert derive_connection_state(_Dev(True, False)) is ConnectionState.DEGRADED


def test_device_without_is_alive_defaults_connected():
    class _Old:
        is_connected = True
    assert derive_connection_state(_Old()) is ConnectionState.CONNECTED


# ── daemon device_status exposes it + logs transitions ─────────────────────

def _owner():
    o = DeviceOwner.__new__(DeviceOwner)
    o._device = None
    o._wall = None
    o._lan_ip = None
    o.mac = "AA:BB:CC:DD:EE:FF"
    o._last_conn_state = None
    return o


def test_status_fields_carry_connection_state():
    o = _owner()
    o._device = _Dev(True, True)
    fields = o._status_fields()
    assert fields["connection_state"] == ConnectionState.CONNECTED.value
    assert fields["connected"] is True


def test_degraded_surfaces_even_when_connected_true():
    o = _owner()
    o._device = _Dev(True, False)          # connected per OS, but link is dead
    fields = o._status_fields()
    assert fields["connected"] is True      # legacy field still reflects is_connected
    assert fields["connection_state"] == ConnectionState.DEGRADED.value


def test_transition_is_logged_once_per_change(caplog):
    import logging
    o = _owner()
    with caplog.at_level(logging.INFO, logger="divoom_daemon.device_owner"):
        o._connection_state()                       # none -> disconnected
        o._device = _Dev(True, True)
        o._connection_state()                       # disconnected -> connected
        o._connection_state()                       # connected -> connected (no log)
    transitions = [r for r in caplog.records if "connection state:" in r.message]
    assert len(transitions) == 2                    # only the two real changes


def test_wall_state_used_when_no_single_device():
    o = _owner()
    o._wall = _Dev(True, True)
    assert o._status_fields()["connection_state"] == ConnectionState.CONNECTED.value


def test_notification_mixin_still_present():
    # P6 housekeeping moved send_notification to OwnerNotifyMixin — verify it's
    # still on DeviceOwner so NotificationService keeps working.
    assert hasattr(DeviceOwner, "send_notification")
    assert hasattr(DeviceOwner, "_send_to_device_ble")

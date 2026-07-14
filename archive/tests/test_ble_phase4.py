"""BLE Hardening Phase 4 — adapter / permission preflight.

An empty scan / failed connect must carry a CAUSE: a denied Bluetooth grant or
a powered-off adapter maps to a typed, actionable reason instead of a silent
"no devices". The CoreBluetooth readers are injected so the mapping is tested
without a Mac/PyObjC.
"""
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))

from divoom_lib.ble_preflight import (
    preflight_bluetooth,
    AUTH_ALLOWED, AUTH_DENIED, AUTH_RESTRICTED, AUTH_NOT_DETERMINED,
    STATE_POWERED_ON, STATE_POWERED_OFF, STATE_UNSUPPORTED, STATE_UNAUTHORIZED,
)
from divoom_lib.ble_connection import FailureReason


def _pf(auth, power):
    return preflight_bluetooth(read_auth=lambda: auth, read_power=lambda **k: power)


# ── permission ─────────────────────────────────────────────────────────────

def test_denied_permission_is_actionable():
    r = _pf(AUTH_DENIED, STATE_POWERED_ON)
    assert r.ok is False
    assert r.reason is FailureReason.PERMISSION
    assert "permission" in r.message.lower()


def test_restricted_permission_blocks():
    r = _pf(AUTH_RESTRICTED, STATE_POWERED_ON)
    assert r.ok is False and r.reason is FailureReason.PERMISSION


# ── adapter power ──────────────────────────────────────────────────────────

def test_powered_off_adapter_is_actionable():
    r = _pf(AUTH_ALLOWED, STATE_POWERED_OFF)
    assert r.ok is False
    assert r.reason is FailureReason.ADAPTER_OFF
    assert "off" in r.message.lower()


def test_unsupported_adapter_blocks():
    r = _pf(AUTH_ALLOWED, STATE_UNSUPPORTED)
    assert r.ok is False and r.reason is FailureReason.ADAPTER_OFF


def test_unauthorized_state_maps_to_permission():
    r = _pf(AUTH_ALLOWED, STATE_UNAUTHORIZED)
    assert r.ok is False and r.reason is FailureReason.PERMISSION


# ── the happy / indeterminate paths must NOT block ─────────────────────────

def test_allowed_and_powered_on_passes():
    assert _pf(AUTH_ALLOWED, STATE_POWERED_ON).ok is True


def test_not_determined_auth_proceeds_to_let_scan_prompt():
    # A not-yet-granted process should proceed (the scan triggers the prompt),
    # so long as the adapter is on.
    assert _pf(AUTH_NOT_DETERMINED, STATE_POWERED_ON).ok is True


def test_indeterminate_power_does_not_block():
    # state never settled (None) → don't block a scan that might work.
    assert _pf(AUTH_ALLOWED, None).ok is True


def test_unreadable_corebluetooth_does_not_block():
    # non-macOS / PyObjC missing: read_auth raises → proceed.
    def _boom():
        raise RuntimeError("no CoreBluetooth")
    r = preflight_bluetooth(read_auth=_boom, read_power=lambda **k: None)
    assert r.ok is True


def test_power_reader_only_consulted_when_auth_ok():
    """If permission is denied we must short-circuit BEFORE touching the
    (run-loop-pumping) power reader."""
    calls = {"power": 0}

    def _power(**k):
        calls["power"] += 1
        return STATE_POWERED_ON

    preflight_bluetooth(read_auth=lambda: AUTH_DENIED, read_power=_power)
    assert calls["power"] == 0


# ── daemon wiring: scan + connect surface the typed reason ──────────────────

def test_daemon_scan_blocks_on_preflight(monkeypatch):
    from archive.divoom_daemon import device_owner as mod
    from divoom_lib.ble_connection import ConnectResult, ConnectionState

    blocked = ConnectResult(False, ConnectionState.FAILED,
                            reason=FailureReason.ADAPTER_OFF, detail="off")
    monkeypatch.setattr(mod, "_json_safe", lambda x: x, raising=False)

    owner = mod.DeviceOwner.__new__(mod.DeviceOwner)
    monkeypatch.setattr("divoom_lib.ble_preflight.preflight_bluetooth",
                        lambda **k: blocked)
    reply = mod.DeviceOwner.scan(owner, {"timeout": 1, "limit": 1})
    assert reply["success"] is False
    assert reply["reason"] == FailureReason.ADAPTER_OFF.value
    assert reply["devices"] == []
    assert "off" in reply["message"].lower()


def test_daemon_connect_blocks_on_preflight(monkeypatch):
    from archive.divoom_daemon import device_owner as mod
    from divoom_lib.ble_connection import ConnectResult, ConnectionState

    blocked = ConnectResult(False, ConnectionState.FAILED,
                            reason=FailureReason.PERMISSION, detail="denied")
    owner = mod.DeviceOwner.__new__(mod.DeviceOwner)
    monkeypatch.setattr("divoom_lib.ble_preflight.preflight_bluetooth",
                        lambda **k: blocked)
    reply = mod.DeviceOwner.connect(owner, {"mac": "AA:BB:CC:DD:EE:FF"})
    assert reply["success"] is False
    assert reply["reason"] == FailureReason.PERMISSION.value


def test_daemon_connect_lan_skips_preflight(monkeypatch):
    """A LAN connect (no mac) must NOT preflight Bluetooth."""
    from archive.divoom_daemon import device_owner as mod

    called = {"n": 0}
    monkeypatch.setattr("divoom_lib.ble_preflight.preflight_bluetooth",
                        lambda **k: called.__setitem__("n", called["n"] + 1))
    owner = mod.DeviceOwner.__new__(mod.DeviceOwner)
    # _build_device_async is reached; stub _run_device + status to avoid real BLE.
    monkeypatch.setattr(owner, "_run_device", lambda coro: coro.close() or None,
                        raising=False)
    monkeypatch.setattr(owner, "_status_fields", lambda: {"connected": True},
                        raising=False)
    mod.DeviceOwner.connect(owner, {"lan_ip": "192.168.1.50"})
    assert called["n"] == 0

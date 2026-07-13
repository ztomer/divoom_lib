"""Coverage push (PLANNING_ROUND61 #1) for divoom_lib/connection.py.

HAZARD (same class as ble_transport.py, see commit e26fc6d and
tests/test_ble_transport_coverage.py): ``BLETransport.__init__`` re-imports
``BleakClient`` via a call-time ``from .divoom import BleakClient`` whenever
``cfg.client`` is falsy and ``cfg.mac`` is set. Every ``DivoomConfig`` built
here supplies an explicit non-bleak ``client`` object (``_FakeClient`` / a
bare ``MockBleakClient`` stand-in), so the ``elif self.mac:`` branch that
imports the real ``BleakClient`` is NEVER taken — no patch of
``divoom_lib.divoom.BleakClient`` is required, and no real CoreBluetooth
call is reachable. ``BLETransport.connect``/``disconnect`` are additionally
patched at the class level to async no-ops so the router's OWN routing
decisions (device-name resolution, SPP-vs-BLE selection, transport-swap
teardown, and the large family of hasattr()-gated forwarding properties/
methods) are what's under test — not the delegate transports' internals
(already covered by test_ble_transport_coverage.py and the BTSppTransport
suite).

Targets the `--cov-report=term-missing` gaps on divoom_lib/connection.py:
connect()'s device-name resolution (IOBluetooth + discovered-devices cache,
both the "found" and "swallowed exception" arms), the SPP-vs-BLE routing
decision (keyword match, the "pixoo 64" exclusion, device_kind selection,
the resolve-failure fallback, and the same-type-reconnect no-op), transport
teardown on a type swap, and the long tail of forwarding properties/methods
that delegate to `self._active_transport` when it supports an attribute and
fall back (or no-op) when it doesn't.
"""
import asyncio
import json
import logging
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import divoom_lib.divoom  # noqa: F401  - import first to resolve the import cycle
from divoom_lib import models
from divoom_lib import bt_spp_transport
from divoom_lib import spp_connection
from divoom_lib.ble_transport import BLETransport
from divoom_lib.connection import DivoomConnection


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeClient:
    """Stand-in bleak client. Its class name does NOT contain
    'MockBleakClient', so `is_mock` stays False and connect()'s name
    -resolution / SPP-routing branches (the ones under test) actually run —
    without ever constructing (or needing to patch) a real BleakClient."""
    def __init__(self):
        self.is_connected = False


class _FakeDivoom:
    def __init__(self):
        self.logger = logging.getLogger("test_connection_router")


def _make_conn(monkeypatch, *, device_name=None, mac="AA:BB:CC:DD:EE:FF",
                use_ios_le_protocol=None, mock_ble_env=False):
    """A DivoomConnection wired to a real BLETransport whose `connect`/
    `disconnect` are patched to async no-ops at the class level (so any
    freshly-swapped-in BLETransport instance is safe too)."""
    if mock_ble_env:
        monkeypatch.setenv("DIVOOM_MOCK_BLE", "1")
    else:
        monkeypatch.delenv("DIVOOM_MOCK_BLE", raising=False)
    cfg = models.DivoomConfig(
        mac=mac, device_name=device_name, client=_FakeClient(),
        write_characteristic_uuid="w", notify_characteristic_uuid="n",
        read_characteristic_uuid="r", use_ios_le_protocol=use_ios_le_protocol,
    )
    divoom = _FakeDivoom()
    conn = DivoomConnection(divoom, cfg)
    monkeypatch.setattr(BLETransport, "connect", AsyncMock())
    monkeypatch.setattr(BLETransport, "disconnect", AsyncMock())
    return conn


class _FakeSpp:
    """Stand-in BTSppTransport — records constructor kwargs, never touches
    real macOS RFCOMM."""
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.mac_address = kwargs.get("mac_address")
        self.device_name = kwargs.get("device_name")

    async def connect(self):
        pass

    async def disconnect(self):
        pass


# ── connect(): device-name resolution (IOBluetooth + discovered-devices cache) ──

def test_connect_resolves_name_via_iobluetooth_then_routes_to_spp(monkeypatch):
    mock_iobluetooth = MagicMock()
    mock_dev = MagicMock()
    mock_dev.getName.return_value = "Ditoo-Pro"
    mock_iobluetooth.IOBluetoothDevice.deviceWithAddressString_.return_value = mock_dev
    monkeypatch.setitem(sys.modules, "IOBluetooth", mock_iobluetooth)
    monkeypatch.setattr(spp_connection, "resolve_classic_mac",
                         lambda *a, **k: "11-22-33-44-55-66")
    monkeypatch.setattr(bt_spp_transport, "BTSppTransport", _FakeSpp)

    conn = _make_conn(monkeypatch, device_name=None, use_ios_le_protocol=False)
    _run(conn.connect())

    assert conn.device_name == "Ditoo-Pro"
    assert conn._use_spp is True
    assert isinstance(conn._active_transport, _FakeSpp)
    assert conn._active_transport.kwargs["device_kind"] == "ditoo"


def test_connect_iobluetooth_returns_none_falls_back_to_cache_file(monkeypatch, tmp_path):
    mock_iobluetooth = MagicMock()
    mock_iobluetooth.IOBluetoothDevice.deviceWithAddressString_.return_value = None
    monkeypatch.setitem(sys.modules, "IOBluetooth", mock_iobluetooth)

    cache_dir = tmp_path / ".config" / "divoom-control"
    cache_dir.mkdir(parents=True)
    (cache_dir / "discovered_devices.json").write_text(json.dumps(
        [{"address": "AA:BB:CC:DD:EE:FF", "name": "Cached-NoneDev"}]))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    conn = _make_conn(monkeypatch, device_name=None, use_ios_le_protocol=False)
    _run(conn.connect())

    assert conn.device_name == "Cached-NoneDev"
    assert conn._use_spp is False


def test_connect_iobluetooth_exception_falls_back_to_cache_file(monkeypatch, tmp_path):
    mock_iobluetooth = MagicMock()
    mock_iobluetooth.IOBluetoothDevice.deviceWithAddressString_.side_effect = RuntimeError("no bt stack")
    monkeypatch.setitem(sys.modules, "IOBluetooth", mock_iobluetooth)

    cache_dir = tmp_path / ".config" / "divoom-control"
    cache_dir.mkdir(parents=True)
    (cache_dir / "discovered_devices.json").write_text(json.dumps(
        [{"address": "AA:BB:CC:DD:EE:FF", "name": "Cached-Other"}]))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    conn = _make_conn(monkeypatch, device_name=None, use_ios_le_protocol=False)
    _run(conn.connect())            # must not raise from the swallowed IOBluetooth error

    assert conn.device_name == "Cached-Other"
    assert conn._use_spp is False


def test_connect_cache_file_read_error_is_swallowed(monkeypatch, tmp_path, caplog):
    mock_iobluetooth = MagicMock()
    mock_iobluetooth.IOBluetoothDevice.deviceWithAddressString_.return_value = None
    monkeypatch.setitem(sys.modules, "IOBluetooth", mock_iobluetooth)

    cache_dir = tmp_path / ".config" / "divoom-control"
    cache_dir.mkdir(parents=True)
    (cache_dir / "discovered_devices.json").write_text("{ not valid json")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    conn = _make_conn(monkeypatch, device_name=None, use_ios_le_protocol=False)

    with caplog.at_level(logging.DEBUG):
        _run(conn.connect())        # malformed cache must not crash connect()

    assert conn.device_name is None
    assert conn._use_spp is False
    assert any("Failed to load device name from cache" in r.message for r in caplog.records)


def test_connect_cache_file_missing_leaves_name_none(monkeypatch, tmp_path):
    """cache_file.exists() is False — the whole read/parse block is skipped.

    NB: mac is a 17-char colon address, so connect() WILL attempt the
    IOBluetooth resolution branch first — stub sys.modules['IOBluetooth']
    (as every other name-resolution test here does) so this never reaches
    the real macOS IOBluetooth framework."""
    mock_iobluetooth = MagicMock()
    mock_iobluetooth.IOBluetoothDevice.deviceWithAddressString_.return_value = None
    monkeypatch.setitem(sys.modules, "IOBluetooth", mock_iobluetooth)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)   # tmp_path has no .config dir at all

    conn = _make_conn(monkeypatch, device_name=None, use_ios_le_protocol=False)
    _run(conn.connect())

    assert conn.device_name is None
    assert conn._use_spp is False


def test_connect_cache_file_skips_non_matching_entries_before_match(monkeypatch, tmp_path):
    """Two devices in the cache; the loop must iterate past the non-matching
    first entry before finding the match on the second."""
    mock_iobluetooth = MagicMock()
    mock_iobluetooth.IOBluetoothDevice.deviceWithAddressString_.return_value = None
    monkeypatch.setitem(sys.modules, "IOBluetooth", mock_iobluetooth)

    cache_dir = tmp_path / ".config" / "divoom-control"
    cache_dir.mkdir(parents=True)
    (cache_dir / "discovered_devices.json").write_text(json.dumps([
        {"address": "FF:FF:FF:FF:FF:FF", "name": "Someone-Else"},
        {"address": "AA:BB:CC:DD:EE:FF", "name": "Cached-Second-Match"},
    ]))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    conn = _make_conn(monkeypatch, device_name=None, use_ios_le_protocol=False)
    _run(conn.connect())

    assert conn.device_name == "Cached-Second-Match"


def test_connect_cache_file_empty_devices_list_leaves_name_none(monkeypatch, tmp_path):
    """An empty discovered-devices list: the for-loop body never executes."""
    mock_iobluetooth = MagicMock()
    mock_iobluetooth.IOBluetoothDevice.deviceWithAddressString_.return_value = None
    monkeypatch.setitem(sys.modules, "IOBluetooth", mock_iobluetooth)

    cache_dir = tmp_path / ".config" / "divoom-control"
    cache_dir.mkdir(parents=True)
    (cache_dir / "discovered_devices.json").write_text(json.dumps([]))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    conn = _make_conn(monkeypatch, device_name=None, use_ios_le_protocol=False)
    _run(conn.connect())

    assert conn.device_name is None


def test_connect_skips_iobluetooth_when_mac_not_standard_format(monkeypatch, tmp_path):
    """mac that isn't a 17-char, ':'/'-'-separated address must skip the
    IOBluetooth resolution branch entirely but still try the cache file."""
    cache_dir = tmp_path / ".config" / "divoom-control"
    cache_dir.mkdir(parents=True)
    (cache_dir / "discovered_devices.json").write_text(json.dumps(
        [{"address": "shortmac", "name": "Cached-NoFormat"}]))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    conn = _make_conn(monkeypatch, device_name=None, mac="shortmac", use_ios_le_protocol=False)
    _run(conn.connect())

    assert conn.device_name == "Cached-NoFormat"


def test_connect_is_mock_env_skips_name_resolution_and_spp(monkeypatch):
    conn = _make_conn(monkeypatch, device_name=None, use_ios_le_protocol=False, mock_ble_env=True)
    _run(conn.connect())

    assert conn.device_name is None      # never resolved — is_mock short-circuited it
    assert conn._use_spp is False
    assert isinstance(conn._active_transport, BLETransport)


def test_connect_is_mock_via_client_class_name(monkeypatch):
    class MockBleakClient:
        def __init__(self):
            self.is_connected = False

    cfg = models.DivoomConfig(mac="AA:BB:CC:DD:EE:FF", device_name=None,
                               client=MockBleakClient(),
                               write_characteristic_uuid="w", notify_characteristic_uuid="n",
                               read_characteristic_uuid="r", use_ios_le_protocol=False)
    conn = DivoomConnection(_FakeDivoom(), cfg)
    monkeypatch.setattr(BLETransport, "connect", AsyncMock())

    _run(conn.connect())

    assert conn.device_name is None
    assert conn._use_spp is False


# ── connect(): SPP-vs-BLE routing decision ──────────────────────────────────

def test_connect_pixoo64_device_name_is_excluded_from_spp(monkeypatch):
    conn = _make_conn(monkeypatch, device_name="Pixoo 64", use_ios_le_protocol=False)
    _run(conn.connect())

    assert conn._use_spp is False
    assert isinstance(conn._active_transport, BLETransport)


@pytest.mark.parametrize("name,expected_kind", [
    ("Pixoo-Max", "pixoo"),
    ("Timoo-One", "timoo"),
    ("Tivoo-Max", "tivoo"),
])
def test_connect_spp_device_kind_by_name(monkeypatch, name, expected_kind):
    monkeypatch.setattr(spp_connection, "resolve_classic_mac",
                         lambda *a, **k: "11-22-33-44-55-66")
    monkeypatch.setattr(bt_spp_transport, "BTSppTransport", _FakeSpp)

    conn = _make_conn(monkeypatch, device_name=name, use_ios_le_protocol=False)
    _run(conn.connect())

    assert conn._active_transport.kwargs["device_kind"] == expected_kind


def test_connect_spp_device_kind_defaults_for_unmatched_keyword(monkeypatch):
    """'timebox' triggers the SPP keyword match but isn't one of the
    pixoo/timoo/ditoo/tivoo device_kind buckets — device_kind stays 'default'."""
    monkeypatch.setattr(spp_connection, "resolve_classic_mac",
                         lambda *a, **k: "11-22-33-44-55-66")
    monkeypatch.setattr(bt_spp_transport, "BTSppTransport", _FakeSpp)

    conn = _make_conn(monkeypatch, device_name="Timebox-Evo", use_ios_le_protocol=False)
    _run(conn.connect())

    assert conn._active_transport.kwargs["device_kind"] == "default"


def test_connect_spp_resolve_fails_falls_back_to_ble_with_warning(monkeypatch, caplog):
    monkeypatch.setattr(spp_connection, "resolve_classic_mac", lambda *a, **k: None)

    conn = _make_conn(monkeypatch, device_name="Pixoo-Test", use_ios_le_protocol=False)
    with caplog.at_level(logging.WARNING):
        _run(conn.connect())

    assert conn._use_spp is False
    assert isinstance(conn._active_transport, BLETransport)
    assert any("Could not resolve Bluetooth Classic MAC" in r.message for r in caplog.records)


def test_connect_ble_to_spp_switch_tears_down_old_ble_transport(monkeypatch):
    monkeypatch.setattr(spp_connection, "resolve_classic_mac",
                         lambda *a, **k: "11-22-33-44-55-66")
    monkeypatch.setattr(bt_spp_transport, "BTSppTransport", _FakeSpp)

    conn = _make_conn(monkeypatch, device_name="Ditoo-Classic", use_ios_le_protocol=False)
    old_transport = conn._active_transport
    old_transport.disconnect = AsyncMock()

    _run(conn.connect())

    old_transport.disconnect.assert_awaited_once()
    assert isinstance(conn._active_transport, _FakeSpp)


def test_connect_spp_to_ble_switch_tears_down_old_spp_transport(monkeypatch, caplog):
    conn = _make_conn(monkeypatch, device_name="Generic Device", use_ios_le_protocol=False)

    class _OldSpp:
        def __init__(self):
            self.mac_address = "AA-BB-CC-DD-EE-FF"
            self.device_name = "Generic Device"
            self.disconnect = AsyncMock()

    old_spp = _OldSpp()
    conn._active_transport = old_spp
    conn._use_spp = True

    with caplog.at_level(logging.INFO):
        _run(conn.connect())

    old_spp.disconnect.assert_awaited_once()
    assert conn._use_spp is False
    assert isinstance(conn._active_transport, BLETransport)
    assert any("Switching transport to BLETransport" in r.message for r in caplog.records)


def test_connect_spp_reconnect_same_type_is_a_noop_swap(monkeypatch):
    """Already on SPP with the same concrete transport type: the router must
    reuse the existing transport rather than re-resolving/re-swapping."""
    resolve_called = {"n": 0}

    def _resolve(*a, **k):
        resolve_called["n"] += 1
        return "11-22-33-44-55-66"

    monkeypatch.setattr(spp_connection, "resolve_classic_mac", _resolve)
    monkeypatch.setattr(bt_spp_transport, "BTSppTransport", _FakeSpp)

    conn = _make_conn(monkeypatch, device_name="Ditoo-Reconnect", use_ios_le_protocol=False)
    existing = _FakeSpp(device_kind="ditoo", device_name="Ditoo-Reconnect")
    conn._active_transport = existing
    conn._use_spp = True

    _run(conn.connect())

    assert conn._active_transport is existing   # no swap happened
    assert resolve_called["n"] == 0              # resolve wasn't even attempted


# ── _teardown_outgoing_transport() ──────────────────────────────────────────

def test_teardown_outgoing_transport_none_is_noop(monkeypatch):
    conn = _make_conn(monkeypatch)
    conn._active_transport = None
    _run(conn._teardown_outgoing_transport())   # must not raise


def test_teardown_outgoing_transport_swallows_disconnect_exception(monkeypatch, caplog):
    conn = _make_conn(monkeypatch)

    class _Boom:
        async def disconnect(self):
            raise RuntimeError("disc fail")

    conn._active_transport = _Boom()
    with caplog.at_level(logging.DEBUG):
        _run(conn._teardown_outgoing_transport())   # must not raise

    assert any("outgoing transport teardown failed" in r.message for r in caplog.records)


# ── is_connected / is_alive / use_spp properties ────────────────────────────

def test_is_connected_delegates_to_active_transport(monkeypatch):
    conn = _make_conn(monkeypatch)
    conn._active_transport.client.is_connected = True
    assert conn.is_connected is True


def test_is_alive_uses_transport_is_alive_when_present(monkeypatch):
    conn = _make_conn(monkeypatch)
    conn._active_transport.client.is_connected = True
    conn._active_transport._connection_likely_broken = True
    assert conn.is_alive is False    # connected per OS, but a drop is pending


def test_is_alive_falls_back_to_is_connected_when_unsupported(monkeypatch):
    conn = _make_conn(monkeypatch)

    class _NoAlive:
        is_connected = True

    conn._active_transport = _NoAlive()
    assert conn.is_alive is True


def test_use_spp_property(monkeypatch):
    conn = _make_conn(monkeypatch)
    assert conn.use_spp is False
    conn._use_spp = True
    assert conn.use_spp is True


# ── notification_handler() ──────────────────────────────────────────────────

def test_notification_handler_forwards_when_supported(monkeypatch):
    conn = _make_conn(monkeypatch)
    seen = {}
    conn._active_transport.notification_handler = lambda sender, data: seen.update(sender=sender, data=data)

    conn.notification_handler(5, bytearray(b"abc"))

    assert seen == {"sender": 5, "data": bytearray(b"abc")}


def test_notification_handler_noop_when_unsupported(monkeypatch):
    conn = _make_conn(monkeypatch)

    class _NoHandler:
        pass

    conn._active_transport = _NoHandler()
    conn.notification_handler(1, bytearray(b"x"))   # must not raise


# ── send_command() (public router method — bypasses transport routing) ─────

def test_send_command_success_builds_payload_and_delegates(monkeypatch):
    conn = _make_conn(monkeypatch)
    captured = {}

    async def fake_send_payload(payload_bytes, write_with_response=False):
        captured["payload"] = payload_bytes
        captured["wwr"] = write_with_response
        return True

    conn._divoom._send_payload = fake_send_payload
    ok = _run(conn.send_command(0x45, [1, 2], write_with_response=True))

    assert ok is True
    assert captured["payload"] == [0x45, 1, 2]
    assert captured["wwr"] is True


def test_send_command_resolves_string_command_name(monkeypatch):
    conn = _make_conn(monkeypatch)
    name, cmd_id = next(iter(models.COMMANDS.items()))
    captured = {}

    async def fake_send_payload(payload_bytes, write_with_response=False):
        captured["payload"] = payload_bytes
        return True

    conn._divoom._send_payload = fake_send_payload
    _run(conn.send_command(name))

    assert captured["payload"][0] == cmd_id


def test_send_command_exception_is_caught(monkeypatch, caplog):
    conn = _make_conn(monkeypatch)

    async def boom(*_a, **_k):
        raise RuntimeError("boom")

    conn._divoom._send_payload = boom
    with caplog.at_level(logging.ERROR):
        ok = _run(conn.send_command(0x45))

    assert ok is False
    assert any("Error calling send_payload" in r.message for r in caplog.records)


# ── send_payload() / wait_for_response() (public delegation) ───────────────

def test_send_payload_public_delegates_to_active_transport(monkeypatch):
    conn = _make_conn(monkeypatch)
    called = {}

    async def fake(payload_bytes, max_retries, **kwargs):
        called["args"] = (payload_bytes, max_retries, kwargs)
        return "ok"

    conn._active_transport.send_payload = fake
    result = _run(conn.send_payload([0x01], max_retries=2, foo="bar"))

    assert result == "ok"
    assert called["args"] == ([0x01], 2, {"foo": "bar"})


def test_wait_for_response_public_delegates(monkeypatch):
    conn = _make_conn(monkeypatch)

    async def fake(cmd_id, timeout):
        return (cmd_id, timeout)

    conn._active_transport.wait_for_response = fake
    result = _run(conn.wait_for_response(0x5, timeout=3.0))

    assert result == (0x5, 3.0)


def test_disconnect_public_delegates(monkeypatch):
    conn = _make_conn(monkeypatch)
    conn._active_transport.disconnect = AsyncMock()

    _run(conn.disconnect())

    conn._active_transport.disconnect.assert_awaited_once()


# ── send_command_and_wait_for_response(): string command + contention log ──

def test_send_command_and_wait_for_response_resolves_string_command(monkeypatch):
    conn = _make_conn(monkeypatch)
    name, cmd_id = next(iter(models.COMMANDS.items()))

    class _FakeDivoomSend:
        async def send_command(self, command, args, write_with_response=False):
            pass

        async def _wait_for_response(self, command_id, timeout):
            assert command_id == cmd_id
            return b"resp"

    conn._divoom = _FakeDivoomSend()
    result = _run(conn.send_command_and_wait_for_response(name, timeout=1.0))

    assert result == b"resp"
    assert conn._expected_response_command == cmd_id


def test_send_command_and_wait_for_response_drains_stale_notification_queue(monkeypatch):
    """Stale frames left in the notification_queue from a prior exchange must
    be drained before the new wait is set up."""
    conn = _make_conn(monkeypatch)

    class _FakeDivoomSend:
        async def send_command(self, command, args, write_with_response=False):
            pass

        async def _wait_for_response(self, command_id, timeout):
            return b"resp"

    conn._divoom = _FakeDivoomSend()
    conn.notification_queue.put_nowait(b"stale-1")
    conn.notification_queue.put_nowait(b"stale-2")

    result = _run(conn.send_command_and_wait_for_response(0x01, timeout=1.0))

    assert result == b"resp"
    assert conn.notification_queue.empty()


def test_send_command_and_wait_for_response_logs_when_lock_contended(monkeypatch, caplog):
    conn = _make_conn(monkeypatch)

    class _SlowDivoom:
        async def send_command(self, command, args, write_with_response=False):
            await asyncio.sleep(0.05)

        async def _wait_for_response(self, command_id, timeout):
            return command_id

    conn._divoom = _SlowDivoom()

    async def run():
        return await asyncio.gather(
            conn.send_command_and_wait_for_response(0xAA, timeout=5.0),
            conn.send_command_and_wait_for_response(0xBB, timeout=5.0),
        )

    with caplog.at_level(logging.WARNING):
        results = _run(run())

    assert sorted(results) == [0xAA, 0xBB]
    assert any("contended" in r.message for r in caplog.records)


# ── wait_for_any_response() / _listen_commands ──────────────────────────────

def test_wait_for_any_response_returns_none_when_unsupported(monkeypatch):
    conn = _make_conn(monkeypatch)

    class _NoWaitAny:
        pass

    conn._active_transport = _NoWaitAny()
    result = _run(conn.wait_for_any_response([1, 2], timeout=0.01))

    assert result is None


def test_wait_for_any_response_forwards_to_transport(monkeypatch):
    conn = _make_conn(monkeypatch)

    async def fake_wait_any(command_ids, timeout):
        return (command_ids, timeout)

    conn._active_transport.wait_for_any_response = fake_wait_any
    result = _run(conn.wait_for_any_response([1, 2], timeout=5.0))

    assert result == ([1, 2], 5.0)


def test_listen_commands_property_forwards(monkeypatch):
    conn = _make_conn(monkeypatch)
    conn._active_transport._listen_commands = {1, 2}
    assert conn._listen_commands == {1, 2}


def test_listen_commands_property_defaults_none_when_unsupported(monkeypatch):
    conn = _make_conn(monkeypatch)

    class _NoListen:
        pass

    conn._active_transport = _NoListen()
    assert conn._listen_commands is None


# ── _spp_client property/setter ─────────────────────────────────────────────

def test_spp_client_getter_returns_active_transport_when_use_spp(monkeypatch):
    conn = _make_conn(monkeypatch)
    conn._use_spp = True
    assert conn._spp_client is conn._active_transport


def test_spp_client_getter_returns_none_when_not_spp(monkeypatch):
    conn = _make_conn(monkeypatch)
    conn._use_spp = False
    assert conn._spp_client is None


def test_spp_client_setter_switches_active_transport(monkeypatch):
    conn = _make_conn(monkeypatch)
    fake = object()
    conn._spp_client = fake

    assert conn._active_transport is fake
    assert conn._use_spp is True


def test_spp_client_setter_ignores_none(monkeypatch):
    conn = _make_conn(monkeypatch)
    original = conn._active_transport
    conn._spp_client = None

    assert conn._active_transport is original


# ── mac / device_name properties (both SPP and BLE branches) ───────────────

def test_mac_property_ble_branch(monkeypatch):
    conn = _make_conn(monkeypatch)
    assert conn.mac == conn._active_transport.mac

    conn.mac = "22-33-44-55-66-77"
    assert conn._active_transport.mac == "22-33-44-55-66-77"
    assert conn.cfg.mac == "22-33-44-55-66-77"


def test_mac_property_spp_branch(monkeypatch):
    conn = _make_conn(monkeypatch)
    conn._use_spp = True
    conn._active_transport.mac_address = "11-22-33"
    assert conn.mac == "11-22-33"

    conn.mac = "44-55-66"
    assert conn._active_transport.mac_address == "44-55-66"
    assert conn.cfg.mac == "44-55-66"


def test_device_name_property_roundtrip(monkeypatch):
    conn = _make_conn(monkeypatch)
    conn.device_name = "New-Name"

    assert conn.device_name == "New-Name"
    assert conn.cfg.device_name == "New-Name"


# ── characteristic UUID / escapePayload / use_ios_le_protocol / client /
#    notification_queue / message_buf setters — both hasattr branches ───────

def test_characteristic_and_misc_setters_forward_when_supported(monkeypatch):
    conn = _make_conn(monkeypatch)

    conn.WRITE_CHARACTERISTIC_UUID = "www"
    conn.NOTIFY_CHARACTERISTIC_UUID = "nnn"
    conn.READ_CHARACTERISTIC_UUID = "rrr"
    conn.SPP_CHARACTERISTIC_UUID = "sss"
    conn.escapePayload = True
    conn.use_ios_le_protocol = True
    conn.client = "new-client"
    conn.message_buf = bytearray(b"hi")

    t = conn._active_transport
    assert t.WRITE_CHARACTERISTIC_UUID == "www" and conn.WRITE_CHARACTERISTIC_UUID == "www"
    assert t.NOTIFY_CHARACTERISTIC_UUID == "nnn" and conn.NOTIFY_CHARACTERISTIC_UUID == "nnn"
    assert t.READ_CHARACTERISTIC_UUID == "rrr" and conn.READ_CHARACTERISTIC_UUID == "rrr"
    assert t.SPP_CHARACTERISTIC_UUID == "sss" and conn.SPP_CHARACTERISTIC_UUID == "sss"
    assert t.escapePayload is True and conn.escapePayload is True
    assert t.use_ios_le_protocol is True and conn.use_ios_le_protocol is True
    assert t.client == "new-client" and conn.client == "new-client"
    assert t.message_buf == bytearray(b"hi") and conn.message_buf == bytearray(b"hi")


def test_characteristic_and_misc_setters_noop_when_unsupported(monkeypatch):
    conn = _make_conn(monkeypatch)

    class _Bare:
        pass

    conn._active_transport = _Bare()

    conn.WRITE_CHARACTERISTIC_UUID = "x"
    conn.NOTIFY_CHARACTERISTIC_UUID = "y"
    conn.READ_CHARACTERISTIC_UUID = "z"
    conn.SPP_CHARACTERISTIC_UUID = "s"
    conn.escapePayload = False
    conn.use_ios_le_protocol = True
    conn.client = "fake-client"
    conn.message_buf = bytearray(b"x")

    # cfg is captured regardless of transport support...
    assert conn.cfg.write_characteristic_uuid == "x"
    assert conn.cfg.notify_characteristic_uuid == "y"
    assert conn.cfg.read_characteristic_uuid == "z"
    assert conn.cfg.spp_characteristic_uuid == "s"
    assert conn.cfg.escapePayload is False
    assert conn.cfg.use_ios_le_protocol is True
    assert conn.cfg.client == "fake-client"
    # ...but the bare transport has none of these attrs, so getters fall back
    # to their defaults instead of reflecting what was "set".
    assert conn.WRITE_CHARACTERISTIC_UUID == ""
    assert conn.NOTIFY_CHARACTERISTIC_UUID == ""
    assert conn.READ_CHARACTERISTIC_UUID == ""
    assert conn.SPP_CHARACTERISTIC_UUID == ""
    assert conn.escapePayload is True   # default per getattr(..., True)
    assert conn.use_ios_le_protocol is False   # default per getattr(..., False)
    assert conn.client is None
    assert conn.message_buf == bytearray()


def test_notification_queue_roundtrip(monkeypatch):
    conn = _make_conn(monkeypatch)
    q = asyncio.Queue()
    conn.notification_queue = q
    assert conn.notification_queue is q


def test_expected_response_command_roundtrip(monkeypatch):
    conn = _make_conn(monkeypatch)
    conn._expected_response_command = 0x99
    assert conn._expected_response_command == 0x99


def test_expected_response_command_noop_when_unsupported(monkeypatch):
    conn = _make_conn(monkeypatch)

    class _Bare:
        pass

    conn._active_transport = _Bare()
    conn._expected_response_command = 0x11    # setter no-ops (no such attr)
    assert conn._expected_response_command is None   # getter default


# ── Diagnostic / probing forwards: hasattr(transport) True vs fall back ────

def test_probe_write_characteristics_forwards_to_transport_when_supported(monkeypatch):
    conn = _make_conn(monkeypatch)

    async def fake(*_a, **_k):
        return "transport-result"

    conn._active_transport.probe_write_characteristics_and_try_channel_switch = fake
    result = _run(conn.probe_write_characteristics_and_try_channel_switch(
        ["w1"], ["n1"], ["r1"], {}, "/tmp/cache", "dev1"))

    assert result == "transport-result"


def test_probe_write_characteristics_falls_back_to_probing_module(monkeypatch):
    conn = _make_conn(monkeypatch)

    class _Bare:
        pass

    conn._active_transport = _Bare()
    from divoom_lib import probing

    async def fake_probe(*_a, **_k):
        return "probing-module-result"

    monkeypatch.setattr(probing, "probe_write_characteristics_and_try_channel_switch", fake_probe)
    result = _run(conn.probe_write_characteristics_and_try_channel_switch(
        ["w1"], ["n1"], ["r1"], {}, "/tmp/cache", "dev1"))

    assert result == "probing-module-result"


def test_set_canonical_light_forwards_to_transport_when_supported(monkeypatch):
    conn = _make_conn(monkeypatch)

    async def fake(*_a, **_k):
        return "transport-light"

    conn._active_transport.set_canonical_light = fake
    result = _run(conn.set_canonical_light("/tmp/cache", "dev1"))

    assert result == "transport-light"


def test_set_canonical_light_falls_back_to_probing_module(monkeypatch):
    conn = _make_conn(monkeypatch)

    class _Bare:
        pass

    conn._active_transport = _Bare()
    from divoom_lib import probing

    async def fake_probe(*_a, **_k):
        return "probing-light"

    monkeypatch.setattr(probing, "set_canonical_light", fake_probe)
    result = _run(conn.set_canonical_light("/tmp/cache", "dev1"))

    assert result == "probing-light"


def test_try_send_command_with_framing_forwards_to_transport_when_supported(monkeypatch):
    conn = _make_conn(monkeypatch)

    async def fake(*_a, **_k):
        return "transport-framing"

    conn._active_transport._try_send_command_with_framing = fake
    result = _run(conn._try_send_command_with_framing(0x01, [1, 2]))

    assert result == "transport-framing"


def test_try_send_command_with_framing_falls_back_to_probing_module(monkeypatch):
    conn = _make_conn(monkeypatch)

    class _Bare:
        pass

    conn._active_transport = _Bare()
    from divoom_lib import probing

    async def fake_probe(*_a, **_k):
        return "probing-framing"

    monkeypatch.setattr(probing, "_try_send_command_with_framing", fake_probe)
    result = _run(conn._try_send_command_with_framing(0x01, [1, 2]))

    assert result == "probing-framing"


def test_send_diagnostic_payload_forwards_to_transport_when_supported(monkeypatch):
    conn = _make_conn(monkeypatch)

    async def fake(*_a, **_k):
        return "transport-diag"

    conn._active_transport._send_diagnostic_payload = fake
    result = _run(conn._send_diagnostic_payload("w", [1], {}, "/tmp/cache", "dev1"))

    assert result == "transport-diag"


def test_send_diagnostic_payload_falls_back_to_probing_module(monkeypatch):
    conn = _make_conn(monkeypatch)

    class _Bare:
        pass

    conn._active_transport = _Bare()
    from divoom_lib import probing

    async def fake_probe(*_a, **_k):
        return "probing-diag"

    monkeypatch.setattr(probing, "_send_diagnostic_payload", fake_probe)
    result = _run(conn._send_diagnostic_payload("w", [1], {}, "/tmp/cache", "dev1"))

    assert result == "probing-diag"


def test_handle_cached_payload_forwards_to_transport_when_supported(monkeypatch):
    conn = _make_conn(monkeypatch)

    async def fake(*_a, **_k):
        return "transport-cached"

    conn._active_transport._handle_cached_payload = fake
    result = _run(conn._handle_cached_payload("w", {}, "/tmp/cache", "dev1"))

    assert result == "transport-cached"


def test_handle_cached_payload_falls_back_to_probing_module(monkeypatch):
    conn = _make_conn(monkeypatch)

    class _Bare:
        pass

    conn._active_transport = _Bare()
    from divoom_lib import probing

    async def fake_probe(*_a, **_k):
        return "probing-cached"

    monkeypatch.setattr(probing, "_handle_cached_payload", fake_probe)
    result = _run(conn._handle_cached_payload("w", {}, "/tmp/cache", "dev1"))

    assert result == "probing-cached"


# ── Lower-level compatibility hooks ─────────────────────────────────────────

def test_handle_ios_le_notification_forwards_and_falls_back(monkeypatch):
    conn = _make_conn(monkeypatch)
    conn._active_transport._handle_ios_le_notification = lambda data: True
    assert conn._handle_ios_le_notification(b"x") is True

    class _Bare:
        pass

    conn._active_transport = _Bare()
    assert conn._handle_ios_le_notification(b"x") is False


def test_handle_basic_protocol_notification_forwards_and_falls_back(monkeypatch):
    conn = _make_conn(monkeypatch)
    conn._active_transport._handle_basic_protocol_notification = lambda data: True
    assert conn._handle_basic_protocol_notification(bytearray(b"x")) is True

    class _Bare:
        pass

    conn._active_transport = _Bare()
    assert conn._handle_basic_protocol_notification(bytearray(b"x")) is False


# ── _send_basic_protocol_payload(): SPP path, forward path, fallback path ───

def test_send_basic_protocol_payload_spp_path_success(monkeypatch):
    conn = _make_conn(monkeypatch)
    sent = {}

    class _SppSend:
        FRAMING_BASIC = "basic"

        async def send(self, payload, framing):
            sent["payload"] = payload
            sent["framing"] = framing

    conn._active_transport = _SppSend()
    conn._use_spp = True
    ok = _run(conn._send_basic_protocol_payload([0x01, 0x02], write_with_response=False))

    assert ok is True
    assert sent == {"payload": [0x01, 0x02], "framing": "basic"}


def test_send_basic_protocol_payload_spp_path_exception_logged(monkeypatch, caplog):
    conn = _make_conn(monkeypatch)

    class _SppBoom:
        FRAMING_BASIC = "basic"

        async def send(self, payload, framing):
            raise RuntimeError("spp send boom")

    conn._active_transport = _SppBoom()
    conn._use_spp = True
    with caplog.at_level(logging.ERROR):
        ok = _run(conn._send_basic_protocol_payload([0x01], write_with_response=False))

    assert ok is False
    assert any("Error sending Basic SPP payload" in r.message for r in caplog.records)


def test_send_basic_protocol_payload_forwards_to_transport_when_supported(monkeypatch):
    conn = _make_conn(monkeypatch)
    called = {}

    async def fake(payload_bytes, write_with_response):
        called["args"] = (payload_bytes, write_with_response)
        return True

    conn._active_transport._send_basic_protocol_payload = fake
    ok = _run(conn._send_basic_protocol_payload([0x03], write_with_response=True))

    assert ok is True
    assert called["args"] == ([0x03], True)


def test_send_basic_protocol_payload_falls_back_to_send_payload(monkeypatch):
    conn = _make_conn(monkeypatch)

    class _Bare:
        pass

    conn._active_transport = _Bare()

    async def fake_send_payload(payload_bytes, write_with_response=False):
        return "fallback-ok"

    monkeypatch.setattr(conn, "send_payload", fake_send_payload)
    result = _run(conn._send_basic_protocol_payload([0x04], write_with_response=True))

    assert result == "fallback-ok"


# ── _send_ios_le_payload(): SPP path, forward path, fallback path ───────────

def test_send_ios_le_payload_spp_path_success(monkeypatch):
    conn = _make_conn(monkeypatch)
    sent = {}

    class _SppSend:
        FRAMING_IOS_LE = "ios_le"

        async def send(self, payload, framing):
            sent["payload"] = payload
            sent["framing"] = framing

    conn._active_transport = _SppSend()
    conn._use_spp = True
    ok = _run(conn._send_ios_le_payload([0x09], write_with_response=True))

    assert ok is True
    assert sent == {"payload": [0x09], "framing": "ios_le"}


def test_send_ios_le_payload_spp_path_exception_logged(monkeypatch, caplog):
    conn = _make_conn(monkeypatch)

    class _SppBoom:
        FRAMING_IOS_LE = "ios_le"

        async def send(self, payload, framing):
            raise RuntimeError("ios boom")

    conn._active_transport = _SppBoom()
    conn._use_spp = True
    with caplog.at_level(logging.ERROR):
        ok = _run(conn._send_ios_le_payload([0x09], write_with_response=False))

    assert ok is False
    assert any("Error sending iOS LE SPP payload" in r.message for r in caplog.records)


def test_send_ios_le_payload_forwards_to_transport_when_supported(monkeypatch):
    conn = _make_conn(monkeypatch)
    called = {}

    async def fake(payload_bytes, write_with_response):
        called["args"] = (payload_bytes, write_with_response)
        return True

    conn._active_transport._send_ios_le_payload = fake
    ok = _run(conn._send_ios_le_payload([0x0A], write_with_response=False))

    assert ok is True
    assert called["args"] == ([0x0A], False)


def test_send_ios_le_payload_falls_back_to_send_payload(monkeypatch):
    conn = _make_conn(monkeypatch)

    class _Bare:
        pass

    conn._active_transport = _Bare()

    async def fake_send_payload(payload_bytes, write_with_response=False):
        return "fallback-ios-ok"

    monkeypatch.setattr(conn, "send_payload", fake_send_payload)
    result = _run(conn._send_ios_le_payload([0x0B], write_with_response=True))

    assert result == "fallback-ios-ok"


# ── _send_payload() (internal router dispatch): SPP vs non-SPP ─────────────

def test_send_payload_dunder_delegates_to_basic_protocol_when_spp(monkeypatch):
    conn = _make_conn(monkeypatch)
    conn._use_spp = True
    called = {}

    async def fake_basic(payload_bytes, write_with_response=False):
        called["args"] = (payload_bytes, write_with_response)
        return True

    monkeypatch.setattr(conn, "_send_basic_protocol_payload", fake_basic)
    ok = _run(conn._send_payload([0x01], write_with_response=True))

    assert ok is True
    assert called["args"] == ([0x01], True)


def test_send_payload_dunder_delegates_to_transport_when_not_spp(monkeypatch):
    conn = _make_conn(monkeypatch)
    conn._use_spp = False
    called = {}

    async def fake_send_payload(payload_bytes, max_retries, **kwargs):
        called["args"] = (payload_bytes, max_retries, kwargs)
        return True

    conn._active_transport.send_payload = fake_send_payload
    ok = _run(conn._send_payload([0x02], max_retries=5, write_with_response=True))

    assert ok is True
    assert called["args"] == ([0x02], 5, {"write_with_response": True})


# ── _wait_for_response() (internal router dispatch) ─────────────────────────

def test_wait_for_response_dunder_forwards_when_supported(monkeypatch):
    conn = _make_conn(monkeypatch)

    async def fake(_cmd_id, _timeout):
        return b"resp"

    conn._active_transport._wait_for_response = fake
    result = _run(conn._wait_for_response(0x01, timeout=1.0))

    assert result == b"resp"


def test_wait_for_response_dunder_falls_back_to_public_wait(monkeypatch):
    conn = _make_conn(monkeypatch)

    class _Bare:
        pass

    conn._active_transport = _Bare()

    async def fake_wait(_cmd_id, _timeout):
        return b"fallback"

    monkeypatch.setattr(conn, "wait_for_response", fake_wait)
    result = _run(conn._wait_for_response(0x02, timeout=2.0))

    assert result == b"fallback"

"""Coverage-focused tests for divoom_lib/tools/hot_update.py (R61 coverage push).

Complements tests/test_hot_update.py (which drives full sessions against a fake
transport) by exercising the boundary functions directly (fetch_hot_manifest /
download_hot_file against a mocked urllib.request.urlopen, matching the
_FakeResp convention in tests/test_hot_preview_consistency.py) and the branch
edges the existing session tests don't reach: cache-expiry re-fetch, download
failure accounting, mid-stream write failures, device-jumps-ahead handling,
malformed/short device payloads, a missing wait_for_any_response transport, and
show_hot_channel().
"""
import json
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.append(str(Path(__file__).parent.parent))

from divoom_lib.models import COMMANDS
from divoom_lib.tools import hot_update as hu_mod
from divoom_lib.tools.hot_update import (
    HotFile,
    HotUpdate,
    clear_hot_manifest_cache,
    download_hot_file,
    fetch_hot_manifest,
)

CMD_LIST = COMMANDS["send hot file list"]
CMD_INFO = COMMANDS["hot update file info"]
CMD_DATA = COMMANDS["hot send file data"]
CMD_REQUEST = COMMANDS["request new file info"]
CMD_PAUSE = COMMANDS["hot pause file send"]


@pytest.fixture(autouse=True)
def _clear_hot_cache():
    clear_hot_manifest_cache()
    yield
    clear_hot_manifest_cache()


def _file(vendor=40005454, version=1099, body=b"\x07" * 522):
    f = HotFile(vendor, f"group1/v{version}.bin", version, "")
    f.body = body
    return f


class _FakeResp:
    """Minimal context-manager stand-in for urllib's HTTPResponse (matches the
    convention in tests/test_hot_preview_consistency.py)."""

    def __init__(self, data: bytes):
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._data


# ── fetch_hot_manifest / download_hot_file: the HTTP boundary ──────────────

def test_fetch_hot_manifest_parses_vendor_and_file_list(monkeypatch):
    payload = {
        "VendorList": [
            {"VendorId": 40005454, "FileList": [
                {"FileId": "group1/v1.bin", "Version": 1, "Sha1": "abc"},
                {"FileId": "group1/v2.bin", "Version": 2, "Sha1": ""},
            ]},
        ]
    }

    def fake_urlopen(req, timeout=None):
        assert req.full_url == hu_mod.HOT_API_URL
        return _FakeResp(json.dumps(payload).encode())

    monkeypatch.setattr(hu_mod.urllib.request, "urlopen", fake_urlopen)

    files = fetch_hot_manifest(0)
    assert len(files) == 2
    assert files[0].vendor_id == 40005454
    assert files[0].file_id == "group1/v1.bin"
    assert files[0].version == 1
    assert files[0].sha1 == "abc"
    assert files[1].sha1 == ""


def test_fetch_hot_manifest_handles_empty_response(monkeypatch):
    monkeypatch.setattr(hu_mod.urllib.request, "urlopen",
                        lambda req, timeout=None: _FakeResp(b"{}"))
    assert fetch_hot_manifest(1) == []


def test_download_hot_file_success_sets_body(monkeypatch):
    body = b"\x01\x02\x03"
    monkeypatch.setattr(hu_mod.urllib.request, "urlopen",
                        lambda req, timeout=None: _FakeResp(body))
    f = _file(body=None)
    assert download_hot_file(f) is True
    assert f.body == body


def test_download_hot_file_sha1_mismatch_fails(monkeypatch):
    import hashlib
    body = b"\xAA\xBB"
    monkeypatch.setattr(hu_mod.urllib.request, "urlopen",
                        lambda req, timeout=None: _FakeResp(body))
    f = HotFile(1, "bad.bin", 1, hashlib.sha1(b"other bytes").hexdigest())
    assert download_hot_file(f) is False
    assert f.body is None


def test_download_hot_file_sha1_match_succeeds(monkeypatch):
    import hashlib
    body = b"\xAA\xBB\xCC"
    monkeypatch.setattr(hu_mod.urllib.request, "urlopen",
                        lambda req, timeout=None: _FakeResp(body))
    f = HotFile(1, "good.bin", 1, hashlib.sha1(body).hexdigest().upper())
    assert download_hot_file(f) is True
    assert f.body == body


# ── _load_hot_files: cache-expiry / empty-manifest / download-failure edges ─

@pytest.mark.asyncio
async def test_load_hot_files_empty_manifest_returns_early(monkeypatch):
    monkeypatch.setattr(hu_mod, "fetch_hot_manifest", lambda dt: [])
    files, dl, from_cache = await hu_mod._load_hot_files(3)
    assert (files, dl, from_cache) == ([], 0, False)


@pytest.mark.asyncio
async def test_load_hot_files_reports_progress(monkeypatch):
    f1, f2 = _file(version=1, body=None), _file(version=2, body=None)
    monkeypatch.setattr(hu_mod, "fetch_hot_manifest", lambda dt: [f1, f2])
    monkeypatch.setattr(hu_mod, "download_hot_file",
                        lambda f: (setattr(f, "body", b"\x01"), True)[1])
    events = []
    files, dl, from_cache = await hu_mod._load_hot_files(4, progress_cb=events.append)
    assert dl == 2 and from_cache is False
    phases = [e["phase"] for e in events]
    assert phases[0] == "downloading" and phases[-1] == "downloading"
    assert events[0]["total"] == 2


@pytest.mark.asyncio
async def test_load_hot_files_download_exception_is_swallowed(monkeypatch):
    f = _file(body=None)
    monkeypatch.setattr(hu_mod, "fetch_hot_manifest", lambda dt: [f])

    def boom(_f):
        raise RuntimeError("network exploded")

    monkeypatch.setattr(hu_mod, "download_hot_file", boom)
    files, dl, from_cache = await hu_mod._load_hot_files(5)
    assert files == [f]
    assert dl == 0
    assert from_cache is False
    # A fully-failed download set is not cached (nothing usable to reuse).
    assert 5 not in hu_mod._manifest_cache


@pytest.mark.asyncio
async def test_load_hot_files_cache_hit_with_no_bodies_refetches(monkeypatch):
    """A cache entry whose files carry no downloaded bodies (all downloads
    failed last time) must not be treated as a usable cache hit — re-fetch."""
    stale = _file(version=1, body=None)
    hu_mod._manifest_cache[6] = (time.monotonic(), [stale])

    fresh = _file(version=2, body=b"\x09" * 10)
    calls = []

    def fake_fetch(dt):
        calls.append(dt)
        return [fresh]

    monkeypatch.setattr(hu_mod, "fetch_hot_manifest", fake_fetch)
    monkeypatch.setattr(hu_mod, "download_hot_file", lambda f: True)

    files, dl, from_cache = await hu_mod._load_hot_files(6)
    assert calls == [6]
    assert from_cache is False
    assert files == [fresh]


# ── _manifest_payload: files without a downloaded body are excluded ────────

def test_manifest_payload_skips_files_without_body():
    with_body = _file(vendor=1, version=5, body=b"\x01")
    no_body = _file(vendor=2, version=9, body=None)
    out = HotUpdate._manifest_payload([no_body, with_body])
    assert out[0] == 1  # only one vendor counted
    assert int.from_bytes(bytes(out[1:5]), "little") == 1  # vendor 1, not 2


# ── _stream_file: mid-stream failure, device-jumps-ahead, junk payload ─────

@pytest.mark.asyncio
async def test_stream_file_write_failure_returns_false():
    f = _file(body=b"\x01" * 300)
    divoom = MagicMock()
    divoom.logger = MagicMock()
    divoom.send_command = AsyncMock(return_value=False)
    hu = HotUpdate(divoom)
    wait_any = AsyncMock()
    ok, confirmed = await hu._stream_file(f, 0, wait_any)
    assert (ok, confirmed) == (False, False)
    wait_any.assert_not_awaited()


@pytest.mark.asyncio
async def test_stream_file_device_jumps_to_next_request():
    """The device may skip the done-ack for THIS file and go straight to
    requesting the next one; that still counts as accepted (True, True) and
    stashes the request for the caller."""
    f = _file(body=b"\x01" * 256)  # 1 packet
    divoom = MagicMock()
    divoom.logger = MagicMock()
    divoom.send_command = AsyncMock(return_value=True)
    hu = HotUpdate(divoom)
    next_req = bytes((1).to_bytes(4, "little")) + bytes((2).to_bytes(4, "little"))
    wait_any = AsyncMock(return_value=(CMD_REQUEST, next_req))
    ok, confirmed = await hu._stream_file(f, 0, wait_any)
    assert (ok, confirmed) == (True, True)
    assert hu._pending_request == next_req


@pytest.mark.asyncio
async def test_stream_file_ignores_junk_payload_then_confirms():
    """A payload that matches neither the 'done' (payload[0] in (1,2)) nor the
    'resend' (len>=3 and payload[0]==0) shape is ignored; the loop keeps
    waiting instead of misinterpreting it."""
    f = _file(body=b"\x01" * 256)
    divoom = MagicMock()
    divoom.logger = MagicMock()
    divoom.send_command = AsyncMock(return_value=True)
    hu = HotUpdate(divoom)
    wait_any = AsyncMock(side_effect=[
        (CMD_DATA, bytes([5])),   # junk: not a done code, too short to be resend
        (CMD_DATA, bytes([1])),   # done
    ])
    ok, confirmed = await hu._stream_file(f, 0, wait_any)
    assert (ok, confirmed) == (True, True)
    assert wait_any.await_count == 2


# ── update(): transport / manifest / download error paths ──────────────────

@pytest.mark.asyncio
async def test_update_returns_error_when_transport_lacks_wait_any():
    divoom = MagicMock(spec=["send_command", "logger"])
    divoom.logger = MagicMock()
    result = await HotUpdate(divoom).update()
    assert result == {"success": False, "error": "transport lacks wait_for_any_response"}


@pytest.mark.asyncio
async def test_update_empty_manifest_error(monkeypatch):
    monkeypatch.setattr(hu_mod, "fetch_hot_manifest", lambda dt: [])
    divoom = MagicMock()
    divoom.logger = MagicMock()
    conn = MagicMock()
    conn.wait_for_any_response = AsyncMock()
    divoom._conn = conn
    result = await HotUpdate(divoom).update(device_size=16)
    assert result == {"success": False, "error": "empty hot manifest"}


@pytest.mark.asyncio
async def test_update_no_downloadable_files_error(monkeypatch):
    f = _file(body=None)
    monkeypatch.setattr(hu_mod, "fetch_hot_manifest", lambda dt: [f])
    monkeypatch.setattr(hu_mod, "download_hot_file", lambda f: False)
    divoom = MagicMock()
    divoom.logger = MagicMock()
    conn = MagicMock()
    conn.wait_for_any_response = AsyncMock()
    divoom._conn = conn
    result = await HotUpdate(divoom).update(device_size=16)
    assert result == {"success": False, "error": "no hot files downloadable"}


@pytest.mark.asyncio
async def test_update_manifest_write_failure(monkeypatch):
    f = _file()
    monkeypatch.setattr(hu_mod, "fetch_hot_manifest", lambda dt: [f])
    monkeypatch.setattr(hu_mod, "download_hot_file", lambda f: True)
    divoom = MagicMock()
    divoom.logger = MagicMock()
    divoom.send_command = AsyncMock(return_value=False)  # CMD_LIST fails
    conn = MagicMock()
    conn._listen_commands = set()
    conn.wait_for_any_response = AsyncMock()
    divoom._conn = conn
    result = await HotUpdate(divoom).update(device_size=16)
    assert result == {"success": False, "error": "manifest (0x9B) write failed"}
    assert conn._listen_commands == set()  # finally still ran


@pytest.mark.asyncio
async def test_update_cache_hit_jumps_progress_bar(monkeypatch):
    """A device_type already cached (bodies present) should be reported as
    100% downloaded immediately instead of re-fetching."""
    cached = _file(body=b"\x01" * 10)
    hu_mod._manifest_cache[16] = (time.monotonic(), [cached])
    fetch_calls = []
    monkeypatch.setattr(hu_mod, "fetch_hot_manifest",
                        lambda dt: fetch_calls.append(dt) or [cached])

    divoom = MagicMock()
    divoom.logger = MagicMock()
    divoom.send_command = AsyncMock(return_value=True)
    conn = MagicMock()
    conn._listen_commands = set()
    conn.wait_for_any_response = AsyncMock(return_value=None)  # quiet -> up to date
    divoom._conn = conn

    # device_size=32 -> DEVICE_TYPE_BY_SIZE[32] == 0, use a matching cache key.
    hu_mod._manifest_cache[0] = (time.monotonic(), [cached])
    events = []
    result = await HotUpdate(divoom).update(device_size=32, progress_cb=events.append)
    assert result["success"] is True
    assert fetch_calls == []  # served from cache, no fetch
    dl_events = [e for e in events if e["phase"] == "downloading"]
    assert dl_events[0]["current"] == dl_events[0]["total"] == 1


@pytest.mark.asyncio
async def test_update_device_pauses_ends_session(monkeypatch):
    f = _file()
    monkeypatch.setattr(hu_mod, "fetch_hot_manifest", lambda dt: [f])
    monkeypatch.setattr(hu_mod, "download_hot_file", lambda f: True)
    divoom = MagicMock()
    divoom.logger = MagicMock()
    divoom.send_command = AsyncMock(return_value=True)
    conn = MagicMock()
    conn._listen_commands = set()
    conn.wait_for_any_response = AsyncMock(return_value=(CMD_PAUSE, b""))
    divoom._conn = conn
    result = await HotUpdate(divoom).update(device_size=16)
    assert result["success"] is True
    assert result["served"] == []


@pytest.mark.asyncio
async def test_update_ignores_short_request_payload_then_ends(monkeypatch):
    f = _file()
    monkeypatch.setattr(hu_mod, "fetch_hot_manifest", lambda dt: [f])
    monkeypatch.setattr(hu_mod, "download_hot_file", lambda f: True)
    divoom = MagicMock()
    divoom.logger = MagicMock()
    divoom.send_command = AsyncMock(return_value=True)
    conn = MagicMock()
    conn._listen_commands = set()
    conn.wait_for_any_response = AsyncMock(side_effect=[
        (CMD_REQUEST, bytes([1, 2, 3])),  # too short (< 8 bytes) -> ignored
        None,                             # then quiet -> session ends
    ])
    divoom._conn = conn
    result = await HotUpdate(divoom).update(device_size=16)
    assert result["success"] is True
    assert result["served"] == []


@pytest.mark.asyncio
async def test_update_file_info_write_failure(monkeypatch):
    f = _file()
    monkeypatch.setattr(hu_mod, "fetch_hot_manifest", lambda dt: [f])
    monkeypatch.setattr(hu_mod, "download_hot_file", lambda f: True)
    divoom = MagicMock()
    divoom.logger = MagicMock()
    # CMD_LIST succeeds, CMD_INFO fails.
    divoom.send_command = AsyncMock(side_effect=[True, False])
    conn = MagicMock()
    conn._listen_commands = set()
    req = bytes((40005454).to_bytes(4, "little")) + bytes((1099).to_bytes(4, "little"))
    conn.wait_for_any_response = AsyncMock(return_value=(CMD_REQUEST, req))
    divoom._conn = conn
    result = await HotUpdate(divoom).update(device_size=16)
    assert result == {"success": False, "error": "file info (0x9D) write failed", "served": []}


@pytest.mark.asyncio
async def test_update_no_ack_for_file_info_ends_session(monkeypatch):
    f = _file()
    monkeypatch.setattr(hu_mod, "fetch_hot_manifest", lambda dt: [f])
    monkeypatch.setattr(hu_mod, "download_hot_file", lambda f: True)
    divoom = MagicMock()
    divoom.logger = MagicMock()
    divoom.send_command = AsyncMock(return_value=True)
    conn = MagicMock()
    conn._listen_commands = set()
    req = bytes((40005454).to_bytes(4, "little")) + bytes((1099).to_bytes(4, "little"))
    conn.wait_for_any_response = AsyncMock(side_effect=[
        (CMD_REQUEST, req),
        None,  # no 0x9D ack -> ends the session
    ])
    divoom._conn = conn
    result = await HotUpdate(divoom).update(device_size=16)
    assert result["success"] is True
    assert result["served"] == []


@pytest.mark.asyncio
async def test_update_device_jumps_ahead_of_file_info_ack(monkeypatch):
    """Device requests the NEXT file instead of ack'ing this one's 0x9D; the
    pending request must be honored on the following loop iteration."""
    f1 = _file(vendor=1, version=1)
    f2 = _file(vendor=1, version=2)
    monkeypatch.setattr(hu_mod, "fetch_hot_manifest", lambda dt: [f1, f2])
    monkeypatch.setattr(hu_mod, "download_hot_file", lambda f: True)
    divoom = MagicMock()
    divoom.logger = MagicMock()
    divoom.send_command = AsyncMock(return_value=True)
    conn = MagicMock()
    conn._listen_commands = set()
    req1 = bytes((1).to_bytes(4, "little")) + bytes((1).to_bytes(4, "little"))
    req2 = bytes((1).to_bytes(4, "little")) + bytes((2).to_bytes(4, "little"))
    conn.wait_for_any_response = AsyncMock(side_effect=[
        (CMD_REQUEST, req1),
        (CMD_REQUEST, req2),  # jumps ahead instead of acking f1's 0x9D
        None,                 # then quiet
    ])
    divoom._conn = conn
    result = await HotUpdate(divoom).update(device_size=16)
    assert result["success"] is True
    assert result["served"] == []  # neither file ever got a streaming ack


@pytest.mark.asyncio
async def test_update_device_declines_file(monkeypatch):
    f = _file()
    monkeypatch.setattr(hu_mod, "fetch_hot_manifest", lambda dt: [f])
    monkeypatch.setattr(hu_mod, "download_hot_file", lambda f: True)
    divoom = MagicMock()
    divoom.logger = MagicMock()
    divoom.send_command = AsyncMock(return_value=True)
    conn = MagicMock()
    conn._listen_commands = set()
    req = bytes((40005454).to_bytes(4, "little")) + bytes((1099).to_bytes(4, "little"))
    conn.wait_for_any_response = AsyncMock(side_effect=[
        (CMD_REQUEST, req),
        (CMD_INFO, bytes([1])),  # non-zero status -> declined
        None,
    ])
    divoom._conn = conn
    result = await HotUpdate(divoom).update(device_size=16)
    assert result["success"] is True
    assert result["served"] == []


@pytest.mark.asyncio
async def test_update_mid_stream_write_failure_not_served(monkeypatch):
    """When packet writes fail mid-stream, the file must not be appended to
    served, and the session continues (rather than crashing)."""
    f = _file(body=b"\x01" * 300)  # 2 packets
    monkeypatch.setattr(hu_mod, "fetch_hot_manifest", lambda dt: [f])
    monkeypatch.setattr(hu_mod, "download_hot_file", lambda f: True)
    monkeypatch.setattr(hu_mod, "INTER_PACKET_DELAY", 0)
    divoom = MagicMock()
    divoom.logger = MagicMock()
    # CMD_LIST ok, CMD_INFO ok, then CMD_DATA (packet write) fails.
    divoom.send_command = AsyncMock(side_effect=[True, True, False])
    conn = MagicMock()
    conn._listen_commands = set()
    req = bytes((40005454).to_bytes(4, "little")) + bytes((1099).to_bytes(4, "little"))
    conn.wait_for_any_response = AsyncMock(side_effect=[
        (CMD_REQUEST, req),
        (CMD_INFO, bytes([0, 0, 0])),
        None,  # end session after the failed stream
    ])
    divoom._conn = conn
    result = await HotUpdate(divoom).update(device_size=16)
    assert result["success"] is True
    assert result["served"] == []


@pytest.mark.asyncio
async def test_update_progress_cb_full_success_reports_all_phases(monkeypatch):
    f = _file(body=b"\xAB" * 10)  # 1 packet
    monkeypatch.setattr(hu_mod, "fetch_hot_manifest", lambda dt: [f])
    monkeypatch.setattr(hu_mod, "download_hot_file", lambda f: True)
    monkeypatch.setattr(hu_mod, "INTER_PACKET_DELAY", 0)
    divoom = MagicMock()
    divoom.logger = MagicMock()
    divoom.send_command = AsyncMock(return_value=True)
    conn = MagicMock()
    conn._listen_commands = set()
    req = bytes((40005454).to_bytes(4, "little")) + bytes((1099).to_bytes(4, "little"))
    conn.wait_for_any_response = AsyncMock(side_effect=[
        (CMD_REQUEST, req),
        (CMD_INFO, bytes([0, 0, 0])),
        (CMD_DATA, bytes([1])),  # done
        None,
    ])
    divoom._conn = conn
    events = []
    result = await HotUpdate(divoom).update(device_size=16, progress_cb=events.append)
    assert result["success"] is True
    phases = [e["phase"] for e in events]
    assert phases[0] == "fetching_manifest"
    assert "uploading" in phases
    assert phases[-1] == "done"


@pytest.mark.asyncio
async def test_update_without_listen_commands_set_skips_listen_bookkeeping(monkeypatch):
    """comm._listen_commands may not exist / not be a set on some transports;
    update() must tolerate that (skip both the setup and teardown of the
    listen-set bookkeeping) instead of raising."""
    f = _file()
    monkeypatch.setattr(hu_mod, "fetch_hot_manifest", lambda dt: [f])
    monkeypatch.setattr(hu_mod, "download_hot_file", lambda f: True)
    divoom = MagicMock(spec=["send_command", "logger", "_conn"])
    divoom.logger = MagicMock()
    divoom.send_command = AsyncMock(return_value=True)
    conn = MagicMock(spec=["wait_for_any_response"])  # no _listen_commands attr
    conn.wait_for_any_response = AsyncMock(return_value=None)
    divoom._conn = conn
    result = await HotUpdate(divoom).update(device_size=16)
    assert result["success"] is True


# ── show_hot_channel() ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_show_hot_channel_without_page():
    divoom = MagicMock()
    divoom.send_command = AsyncMock(return_value=True)
    ok = await HotUpdate(divoom).show_hot_channel()
    assert ok is True
    divoom.send_command.assert_awaited_once_with(COMMANDS["set light mode"], [0x02])


@pytest.mark.asyncio
async def test_show_hot_channel_with_page_sends_hotctrl():
    divoom = MagicMock()
    divoom.send_command = AsyncMock(return_value=True)
    ok = await HotUpdate(divoom).show_hot_channel(page=3)
    assert ok is True
    assert divoom.send_command.await_args_list[0].args == (COMMANDS["set light mode"], [0x02])
    assert divoom.send_command.await_args_list[1].args == (COMMANDS["send hotctrl"], [1, 3])


@pytest.mark.asyncio
async def test_show_hot_channel_mode_failure_skips_page_select():
    divoom = MagicMock()
    divoom.send_command = AsyncMock(return_value=False)
    ok = await HotUpdate(divoom).show_hot_channel(page=3)
    assert ok is False
    divoom.send_command.assert_awaited_once()  # hotctrl never sent

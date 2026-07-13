"""Coverage push (PLANNING_ROUND61 item 1) for divoom_daemon/device_owner.py.

Targets the specific uncovered lines/branches (57% -> baseline 82 missed):
  - device_call: bad-blob cleanup incl. os.unlink OSError swallow (85-92, 122-123)
  - device_call: wall-target branch where a wall IS configured (97->101)
  - device_call: sync (non-awaitable) result branch (105->107)
  - exclusive_start: acquire_now rejection path (150-154)
  - exclusive_end: no-queue and _run_device-raises paths (161, 167-169)
  - sync_artwork: full method body, all branches (178-255)
  - stop(): every swallowed-exception teardown branch (263-264, 268-269,
    274-275, 283-284)

All BLE/network/PIL/media-decoder dependencies are mocked; no real hardware
or network access. Follows the owner_with_device / FakeSession conventions
already used in tests/test_device_owner_custom_art.py.
"""
from __future__ import annotations

import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from divoom_daemon.device_owner import DeviceOwner


class _MockDevice:
    def __init__(self):
        self.is_connected = True
        self.display = MagicMock()
        self.display.show_image = AsyncMock(return_value=True)

    async def connect(self):
        self.is_connected = True


@pytest.fixture
def owner_with_device():
    dev = _MockDevice()
    owner = DeviceOwner(device=dev)
    owner._device_loop()  # starts the asyncio loop + CommandQueue
    time.sleep(0.02)
    try:
        yield owner, dev
    finally:
        owner.stop()


class _FakeResponse:
    """Mimics an aiohttp response context manager returning fixed bytes."""
    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def read(self):
        return self._body


class _FakeSession:
    def __init__(self, body: bytes):
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    def get(self, url, **kw):
        return _FakeResponse(self._body)


# ── device_call: blob cleanup (85-92, 122-123) ──────────────────────────────

class TestDeviceCallBlobCleanup:
    def test_bad_blob_cleans_up_already_written_blobs(self, owner_with_device):
        """A second, malformed blob must trigger the except-cleanup loop that
        unlinks blobs already materialized earlier in the same call — and
        survive an os.unlink failure on that cleanup (85-92)."""
        owner, dev = owner_with_device
        import base64
        good_blob = base64.b64encode(b"\x89PNG good data").decode()

        written_paths = []
        real_mkstemp = __import__("tempfile").mkstemp

        def _tracking_mkstemp(*a, **kw):
            fd, path = real_mkstemp(*a, **kw)
            written_paths.append(path)
            return fd, path

        # First blob (idx "0") writes fine; second blob (idx "not-an-int")
        # fails at int(idx_str) -> ValueError, entering the except branch.
        # Patch os.unlink to raise OSError so the inner cleanup's except
        # branch (89-90 in source) also gets exercised, not just the happy
        # unlink.
        with patch("tempfile.mkstemp", side_effect=_tracking_mkstemp), \
             patch("os.unlink", side_effect=OSError("cleanup denied")):
            result = owner.device_call({
                "method": "connect",
                "blobs": {"0": good_blob, "not-an-int": good_blob},
            })

        assert result["success"] is False
        assert "bad blob not-an-int" in result["error"]
        assert len(written_paths) == 1, "only the first (valid) blob should have been written"
        # cleanup afterwards so we don't actually leak the temp file the
        # patched os.unlink pretended to fail on.
        for p in written_paths:
            if os.path.exists(p):
                os.unlink(p)

    def test_finally_cleanup_swallows_unlink_error(self, owner_with_device):
        """The outer finally's blob cleanup must swallow an OSError raised by
        os.unlink (122-123), e.g. because the device call already consumed
        and removed the file."""
        owner, dev = owner_with_device
        dev.receive_blob = AsyncMock(return_value=True)
        import base64
        blob = base64.b64encode(b"\x89PNG some bytes").decode()

        with patch("os.unlink", side_effect=OSError("already gone")):
            result = owner.device_call({
                "method": "receive_blob",
                "blobs": {"0": blob},
            })

        # receive_blob() succeeds; the finally-block unlink failure must not
        # surface as an error.
        assert result["success"] is True
        dev.receive_blob.assert_awaited_once()


# ── device_call: wall-configured branch + sync-result branch (97->101, 105->107) ──

class TestDeviceCallBranches:
    def test_wall_target_with_wall_configured(self, owner_with_device):
        """which='wall' with self._wall set must take the base-is-not-None
        branch (skip the 'no wall configured' raise) and reach the target
        resolution line (97->101)."""
        owner, dev = owner_with_device
        fake_wall = MagicMock()
        fake_wall.some_method = MagicMock(return_value="wall-value")
        owner._wall = fake_wall

        result = owner.device_call({"target": "wall", "method": "some_method"})

        assert result["success"] is True
        assert result["result"] == "wall-value"

    def test_wall_target_without_wall_configured_raises(self, owner_with_device):
        owner, dev = owner_with_device
        owner._wall = None

        result = owner.device_call({"target": "wall", "method": "connect"})

        assert result["success"] is False
        assert "no wall configured" in result["error"]

    def test_sync_result_is_returned_without_awaiting(self, owner_with_device):
        """When the resolved method returns a plain (non-awaitable) value,
        the hasattr(__await__) check must short-circuit straight to return
        (105->107)."""
        owner, dev = owner_with_device
        owner._ensure_device_async = AsyncMock(return_value=dev)
        dev.plain_method = lambda: 42  # not a coroutine function

        result = owner.device_call({"method": "plain_method"})

        assert result["success"] is True
        assert result["result"] == 42


# ── exclusive_start / exclusive_end error paths (150-154, 161, 167-169) ─────

class TestExclusiveErrorPaths:
    def test_exclusive_start_rejected_by_foreign_owner(self, owner_with_device):
        owner, _ = owner_with_device

        class _RejectingQueue:
            def acquire_now(self, token):
                raise RuntimeError("held by another session")

        owner._cmd_queue = _RejectingQueue()
        owner.live_jobs_stop_for = lambda args: {"success": True}

        result = owner.exclusive_start({"token": "tok"})

        assert result["success"] is False
        assert "held by another session" in result["error"]

    def test_exclusive_end_no_queue(self, owner_with_device):
        owner, _ = owner_with_device
        owner._cmd_queue = None

        result = owner.exclusive_end({"token": "tok"})

        assert result == {"success": False, "error": "no queue"}

    def test_exclusive_end_run_device_raises(self, owner_with_device):
        owner, _ = owner_with_device

        class _Queue:
            def release(self, token):
                return "coro-placeholder"

        owner._cmd_queue = _Queue()

        def _boom(coro, **kw):
            raise RuntimeError("release failed")

        with patch.object(owner, "_run_device", _boom):
            result = owner.exclusive_end({"token": "tok"})

        assert result["success"] is False
        assert "release failed" in result["error"]


# ── sync_artwork (178-255) ───────────────────────────────────────────────────

class TestSyncArtwork:
    def test_missing_file_id(self, owner_with_device):
        owner, _ = owner_with_device
        result = owner.sync_artwork({})
        assert result == {"success": False, "error": "sync_artwork requires 'file_id'"}

    def test_download_too_small_returns_false(self, owner_with_device):
        owner, dev = owner_with_device
        owner._ensure_device_async = AsyncMock(return_value=dev)

        with patch("aiohttp.ClientSession", return_value=_FakeSession(b"\x01")):
            result = owner.sync_artwork({"file_id": "abc"})

        assert result == {"success": False}

    def test_wall_target_without_wall_configured(self, owner_with_device):
        owner, _ = owner_with_device
        owner._wall = None
        fake_bytes = b"\x89PNG" + b"\x00" * 40

        with patch("aiohttp.ClientSession", return_value=_FakeSession(fake_bytes)):
            result = owner.sync_artwork({"file_id": "abc", "target": "wall"})

        assert result["success"] is False
        assert "no wall configured" in result["error"]

    def test_wall_target_success_non_gif(self, owner_with_device):
        """Wall target with a configured wall, and the resolver deciding the
        payload isn't image data (is_gif False) -> raw-stream fallback path."""
        owner, dev = owner_with_device
        slot = MagicMock()
        slot.device = dev
        slot.size = 16
        fake_wall = MagicMock()
        fake_wall.devices = [slot]
        owner._wall = fake_wall

        fake_bytes = b"\x8b" + b"\x00" * 40  # unknown/legacy magic

        with patch("aiohttp.ClientSession", return_value=_FakeSession(fake_bytes)), \
             patch("divoom_lib.media_decoder.resolve_to_gif", return_value=None), \
             patch("divoom_lib.monthly_best_daemon.stream_raw_bin_payload",
                   new=AsyncMock(return_value=True)) as raw_mock:
            result = owner.sync_artwork({"file_id": "abc", "target": "wall"})

        assert result == {"success": True}
        raw_mock.assert_called_once()

    def test_device_target_success_gif_path_resizes_and_shows(self, owner_with_device):
        """Device target where the resolver decodes to a GIF -> the resize +
        show_image path executes and returns success."""
        owner, dev = owner_with_device
        owner._ensure_device_async = AsyncMock(return_value=dev)

        fake_bytes = b"GIF89a" + b"\x00" * 40

        fake_frame = MagicMock()
        fake_frame.info = {"duration": 100}
        fake_frame.resize.return_value = fake_frame
        fake_frame.convert.return_value = fake_frame
        fake_frame.save = MagicMock()

        fake_img = MagicMock()
        fake_img.n_frames = 1
        fake_img.seek = MagicMock()
        fake_img.info = {"duration": 100}
        fake_img.resize.return_value = fake_frame
        fake_img.__enter__.return_value = fake_img
        fake_img.__exit__.return_value = False

        with patch("aiohttp.ClientSession", return_value=_FakeSession(fake_bytes)), \
             patch("divoom_lib.media_decoder.resolve_to_gif", return_value=b"\x00" * 10), \
             patch("PIL.Image.open", return_value=fake_img):
            result = owner.sync_artwork({"file_id": "abc", "default_size": 32})

        assert result == {"success": True}
        dev.display.show_image.assert_awaited_once()

    def test_device_target_show_image_failure_is_not_success(self, owner_with_device):
        owner, dev = owner_with_device
        owner._ensure_device_async = AsyncMock(return_value=dev)
        dev.display.show_image = AsyncMock(return_value=False)

        fake_bytes = b"\x8b" + b"\x00" * 40

        with patch("aiohttp.ClientSession", return_value=_FakeSession(fake_bytes)), \
             patch("divoom_lib.media_decoder.resolve_to_gif", return_value=None), \
             patch("divoom_lib.monthly_best_daemon.stream_raw_bin_payload",
                   new=AsyncMock(return_value=False)):
            result = owner.sync_artwork({"file_id": "abc"})

        assert result == {"success": False}

    def test_exception_during_fetch_is_caught(self, owner_with_device):
        owner, dev = owner_with_device
        owner._ensure_device_async = AsyncMock(return_value=dev)

        class _BoomSession:
            async def __aenter__(self):
                raise RuntimeError("network down")

            async def __aexit__(self, *a):
                pass

        with patch("aiohttp.ClientSession", return_value=_BoomSession()):
            result = owner.sync_artwork({"file_id": "abc"})

        assert result["success"] is False
        assert "network down" in result["error"]


# ── stop() swallowed-exception branches (263-264, 268-269, 274-275, 283-284) ─

class TestStopTeardownSwallowsErrors:
    def test_stop_survives_every_teardown_failure(self):
        owner = DeviceOwner.__new__(DeviceOwner)
        owner.stop_all_live_jobs = MagicMock(side_effect=RuntimeError("jobs boom"))

        class _BoomQueue:
            def stop(self):
                raise RuntimeError("queue boom")

        owner._cmd_queue = _BoomQueue()

        class _BoomLoop:
            def call_soon_threadsafe(self, fn):
                raise RuntimeError("loop boom")

        owner._loop = _BoomLoop()
        owner._loop_thread = None

        with patch("divoom_lib.ble_connection.forget_loop",
                   side_effect=RuntimeError("ble teardown boom")):
            owner.stop()  # must not raise despite every step failing

        assert owner._loop is None
        assert owner._cmd_queue is None
        assert owner._loop_thread is None

    def test_stop_happy_path_resets_state(self):
        """Sanity check for the non-exception arm: all teardown steps run
        and refs are nulled so a restart rebuilds fresh state."""
        owner = DeviceOwner.__new__(DeviceOwner)
        owner.stop_all_live_jobs = MagicMock()

        queue = MagicMock()
        owner._cmd_queue = queue

        loop = MagicMock()
        owner._loop = loop
        owner._loop_thread = MagicMock()

        with patch("divoom_lib.ble_connection.forget_loop") as forget_mock, \
             patch("divoom_lib.ble_registry.reset") as reset_mock:
            owner.stop()

        owner.stop_all_live_jobs.assert_called_once()
        queue.stop.assert_called_once()
        loop.call_soon_threadsafe.assert_called_once_with(loop.stop)
        forget_mock.assert_called_once_with(loop)
        reset_mock.assert_called_once()
        assert owner._loop is None
        assert owner._cmd_queue is None
        assert owner._loop_thread is None

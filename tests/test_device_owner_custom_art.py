"""Mock tests for DeviceOwner.custom_art_push and custom_art_query_page handlers.

These tests inject a mock device and patch network / image dependencies so
no BLE or real cloud access is needed.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from divoom_daemon.device_owner import DeviceOwner


class _MockDevice:
    """Minimal device that records send_command calls."""
    def __init__(self):
        self.is_connected = True
        self.calls = []
        self.send_command = AsyncMock(return_value=True)

    async def connect(self):
        self.is_connected = True


@pytest.fixture
def owner_with_device():
    """DeviceOwner with an injected mock device and a running command queue.

    Cleans up loop + thread on teardown.
    """
    dev = _MockDevice()
    owner = DeviceOwner(device=dev)
    owner._device_loop()  # starts the asyncio loop + CommandQueue
    # Give the loop thread a moment to init
    time.sleep(0.02)
    try:
        yield owner, dev
    finally:
        owner.stop()


# ── custom_art_push error paths ──────────────────────────────────────────────

class TestCustomArtPushErrors:
    def test_missing_file_ids(self, owner_with_device):
        owner, _ = owner_with_device
        result = owner.custom_art_push({})
        assert result == {"success": False,
                          "error": "custom_art_push requires 'slots' or 'file_ids'"}

    def test_empty_file_ids(self, owner_with_device):
        owner, _ = owner_with_device
        result = owner.custom_art_push({"file_ids": []})
        assert result == {"success": False,
                          "error": "custom_art_push requires 'slots' or 'file_ids'"}

    def test_exception_during_push(self, owner_with_device):
        """If push_slot raises, the handler catches and returns error."""
        owner, dev = owner_with_device

        def mock_run(coro, **kw):
            raise RuntimeError("mock BLE failure")

        with patch.object(owner, "_run_device", mock_run):
            result = owner.custom_art_push({"file_ids": ["abc"]})
        assert result["success"] is False
        assert "mock BLE failure" in result.get("error", "")


# ── custom_art_push success path ─────────────────────────────────────────────

class TestCustomArtPushSuccess:
    def test_push_single_file(self, owner_with_device):
        """Full success path with all dependencies mocked."""
        owner, dev = owner_with_device

        # Mock _ensure_device_async → return our mock device
        owner._ensure_device_async = AsyncMock(return_value=dev)

        # Mock aiohttp session to return fake image bytes
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        class FakeResponse:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                pass
            async def read(self):
                return fake_png

        class FakeSession:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                pass
            def get(self, url, **kw):
                return FakeResponse()

        # These imports happen inside device_owner._do(), so we patch at
        # the global module level where they resolve.
        patches = [
            patch("aiohttp.ClientSession", return_value=FakeSession()),
            patch("divoom_lib.media_decoder.extract_gif_from_magic_43",
                  return_value=None),
            patch("divoom_lib.media_decoder.decode_cloud_to_gif",
                  new=MagicMock(return_value=True)),
            patch("divoom_lib.media_decoder.CLOUD_CONTAINER_MAGICS",
                  new={0x0B}),
            patch("PIL.Image.open",
                  return_value=MagicMock(
                      convert=MagicMock(return_value=MagicMock(
                          resize=MagicMock(return_value=MagicMock(
                              tobytes=MagicMock(return_value=b"\x00" * 768)
                          ))
                      ))
                  )),
            patch("divoom_lib.utils.divoom_image_encode.encode_animation_frame",
                  return_value=b"\x01\x02\x03"),
            patch("divoom_lib.tools.custom_art_push.push_page",
                  new=AsyncMock(return_value=True)),
        ]

        for p in patches:
            p.start()
        try:
            result = owner.custom_art_push({"file_ids": ["test123"], "page": 0, "slot": None})
        finally:
            for p in patches:
                p.stop()

        assert result.get("success") is True
        assert result.get("files_pushed") == 1

    def test_push_with_specific_slot(self, owner_with_device):
        """When slot is specified, all files go to that slot."""
        owner, dev = owner_with_device
        owner._ensure_device_async = AsyncMock(return_value=dev)

        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        class FakeResponse:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                pass
            async def read(self):
                return fake_png

        class FakeSession:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                pass
            def get(self, url, **kw):
                return FakeResponse()

        push_page_mock = AsyncMock(return_value=True)

        patches = [
            patch("aiohttp.ClientSession", return_value=FakeSession()),
            patch("divoom_lib.media_decoder.extract_gif_from_magic_43",
                  return_value=None),
            patch("divoom_lib.media_decoder.CLOUD_CONTAINER_MAGICS",
                  new=set()),
            patch("PIL.Image.open",
                  return_value=MagicMock(
                      convert=MagicMock(return_value=MagicMock(
                          resize=MagicMock(return_value=MagicMock(
                              tobytes=MagicMock(return_value=b"\x00" * 768)
                          ))
                      ))
                  )),
            patch("divoom_lib.utils.divoom_image_encode.encode_animation_frame",
                  return_value=b"\x01\x02\x03"),
            patch("divoom_lib.tools.custom_art_push.push_page", push_page_mock),
        ]

        for p in patches:
            p.start()
        try:
            result = owner.custom_art_push({"file_ids": ["f1", "f2"], "page": 1, "slot": 5})
        finally:
            for p in patches:
                p.stop()

        assert result.get("success") is True
        assert result.get("files_pushed") == 2
        # The whole page is sent exactly once: f1 at slot 5, f2 at slot 6.
        assert push_page_mock.call_count == 1
        _args, _kwargs = push_page_mock.call_args
        assert _args[1] == 1  # page
        frames = _args[2]
        assert len(frames) == 12
        assert frames[5] == b"\x01\x02\x03" and frames[6] == b"\x01\x02\x03"
        assert all(f == b"" for i, f in enumerate(frames) if i not in (5, 6))
        assert _kwargs.get("use_new_mode") is False

    def test_push_slot_failure(self, owner_with_device):
        """When push_page returns False, the handler returns error."""
        owner, dev = owner_with_device
        owner._ensure_device_async = AsyncMock(return_value=dev)

        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        class FakeResponse:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                pass
            async def read(self):
                return fake_png

        class FakeSession:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                pass
            def get(self, url, **kw):
                return FakeResponse()

        patches = [
            patch("aiohttp.ClientSession", return_value=FakeSession()),
            patch("divoom_lib.media_decoder.extract_gif_from_magic_43",
                  return_value=None),
            patch("divoom_lib.media_decoder.CLOUD_CONTAINER_MAGICS",
                  new=set()),
            patch("PIL.Image.open",
                  return_value=MagicMock(
                      convert=MagicMock(return_value=MagicMock(
                          resize=MagicMock(return_value=MagicMock(
                              tobytes=MagicMock(return_value=b"\x00" * 768)
                          ))
                      ))
                  )),
            patch("divoom_lib.utils.divoom_image_encode.encode_animation_frame",
                  return_value=b"\x01\x02\x03"),
            patch("divoom_lib.tools.custom_art_push.push_page",
                  new=AsyncMock(return_value=False)),
        ]

        for p in patches:
            p.start()
        try:
            result = owner.custom_art_push({"file_ids": ["abc"], "page": 0})
        finally:
            for p in patches:
                p.stop()

        assert result["success"] is False
        assert "page push failed" in result.get("error", "")

    def test_push_fails_on_empty_download(self, owner_with_device):
        """A download under 4 bytes can't fill its slot — the push errors
        instead of silently sending a partial page."""
        owner, dev = owner_with_device
        owner._ensure_device_async = AsyncMock(return_value=dev)

        class FakeEmptyResponse:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                pass
            async def read(self):
                return b""  # less than 4 bytes

        class FakeSession:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                pass
            def get(self, url, **kw):
                return FakeEmptyResponse()

        patches = [
            patch("aiohttp.ClientSession", return_value=FakeSession()),
        ]

        for p in patches:
            p.start()
        try:
            result = owner.custom_art_push({"file_ids": ["abc"], "page": 0})
        finally:
            for p in patches:
                p.stop()

        assert result.get("success") is False
        assert "could not fetch" in result.get("error", "")


# ── custom_art_query_page ────────────────────────────────────────────────────

class TestCustomArtQueryPage:
    def test_query_page_success(self, owner_with_device):
        owner, dev = owner_with_device
        owner._ensure_device_async = AsyncMock(return_value=dev)

        with patch("divoom_lib.tools.custom_art_push.query_page",
                   new=AsyncMock(return_value=[1, 2, 3])):
            result = owner.custom_art_query_page({"page": 0})

        assert result.get("success") is True
        assert result.get("ids") == [1, 2, 3]

    def test_query_page_empty(self, owner_with_device):
        owner, dev = owner_with_device
        owner._ensure_device_async = AsyncMock(return_value=dev)

        with patch("divoom_lib.tools.custom_art_push.query_page",
                   new=AsyncMock(return_value=None)):
            result = owner.custom_art_query_page({"page": 1})

        assert result.get("success") is True
        assert result.get("ids") == []

    def test_query_page_exception(self, owner_with_device):
        owner, _ = owner_with_device
        owner._ensure_device_async = AsyncMock(side_effect=RuntimeError("BLE fail"))

        result = owner.custom_art_query_page({"page": 0})

        assert result.get("success") is False
        assert "BLE fail" in result.get("error", "")

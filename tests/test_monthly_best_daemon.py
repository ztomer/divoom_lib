#!/usr/bin/env python3
import sys
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path

# Add paths to sys.path
sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "api_scraper"))

from divoom_lib import monthly_best_daemon

class TestMonthlyBestDaemon(unittest.IsolatedAsyncioTestCase):

    def test_extract_gif_from_magic_43_invalid(self):
        """Test extract_gif_from_magic_43 returns None for non-Magic 43 data."""
        # Non-magic-43 bytes
        data = b"\x1a\x00\x00\x00\x00\x00"
        result = monthly_best_daemon.extract_gif_from_magic_43(data)
        self.assertIsNone(result)

    def test_extract_gif_from_magic_43_valid(self):
        """Test extract_gif_from_magic_43 correctly parses valid Magic 43 payload."""
        # Magic 43 payload structure:
        # Magic byte 43 (0x2b) - 1 byte
        # Offset 1-5: arbitrary padding
        # Offset 6-9: text_len (4 bytes little-endian)
        # Offset 10: text content (text_len bytes)
        # Next 4 bytes: gif_len (4 bytes little-endian)
        # Next gif_len bytes: GIF data starting with GIF89a
        text = b"Hello, World!"
        gif = b"GIF89aXXXXXX"
        
        payload = bytearray([43, 0, 0, 0, 0, 0])
        payload.extend(len(text).to_bytes(4, byteorder='little'))
        payload.extend(text)
        payload.extend(len(gif).to_bytes(4, byteorder='little'))
        payload.extend(gif)
        
        result = monthly_best_daemon.extract_gif_from_magic_43(bytes(payload))
        self.assertEqual(result, gif)

    async def test_stream_raw_bin_payload_delegates_to_shared_streamer(self):
        """R34 §1b: stream_raw_bin_payload is a thin delegator to the single
        APK-aligned 0x8b streamer (Animation.stream_animation_8b) — the 3-phase
        wire format itself is covered by tests/test_animation_8b_stream.py."""
        mock_divoom = MagicMock()
        mock_divoom.animation.stream_animation_8b = AsyncMock(return_value=True)
        file_data = b"X" * 600

        success = await monthly_best_daemon.stream_raw_bin_payload(mock_divoom, file_data)
        self.assertTrue(success)
        mock_divoom.animation.stream_animation_8b.assert_awaited_once_with(file_data)

        mock_divoom.animation.stream_animation_8b = AsyncMock(return_value=False)
        self.assertFalse(
            await monthly_best_daemon.stream_raw_bin_payload(mock_divoom, file_data))

if __name__ == '__main__':
    unittest.main()

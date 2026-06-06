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

    @patch('divoom_lib.monthly_best_daemon.asyncio.sleep', new_callable=AsyncMock)
    async def test_stream_raw_bin_payload(self, mock_sleep):
        """Test stream_raw_bin_payload correctly calls app_new_send_gif_cmd for CW 0, 1, 2."""
        mock_divoom = MagicMock()
        mock_divoom.animation.app_new_send_gif_cmd = AsyncMock(return_value=True)
        
        # 600 bytes payload → 3 chunks at the 256-byte size (256, 256, 88).
        # (Chunk size MUST be 256 to match futpib; offset_id is a chunk index
        # and the device positions chunk N at byte N*256 — R11 fix.)
        file_data = b"X" * 600

        success = await monthly_best_daemon.stream_raw_bin_payload(mock_divoom, file_data)
        self.assertTrue(success)

        # CW 0 (start) + CW 1 (data) x 3 + CW 2 (terminate) = 5 calls
        self.assertEqual(mock_divoom.animation.app_new_send_gif_cmd.call_count, 5)

        mock_divoom.animation.app_new_send_gif_cmd.assert_any_call(
            control_word=0, file_size=600
        )
        mock_divoom.animation.app_new_send_gif_cmd.assert_any_call(
            control_word=2
        )
        # Data phases must carry sequential chunk-INDEX offset ids (0,1,2).
        data_offsets = [
            c.kwargs.get("file_offset_id")
            for c in mock_divoom.animation.app_new_send_gif_cmd.call_args_list
            if c.kwargs.get("control_word") == 1
        ]
        self.assertEqual(data_offsets, [0, 1, 2])

if __name__ == '__main__':
    unittest.main()

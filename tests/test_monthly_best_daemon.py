#!/usr/bin/env python3
import sys
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path

# Add paths to sys.path
sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "api_scraper"))

import monthly_best_daemon

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

    @patch('monthly_best_daemon.asyncio.sleep', new_callable=AsyncMock)
    async def test_stream_raw_bin_payload(self, mock_sleep):
        """Test stream_raw_bin_payload correctly calls app_new_send_gif_cmd for CW 0, 1, 2."""
        mock_divoom = MagicMock()
        mock_divoom.animation.app_new_send_gif_cmd = AsyncMock(return_value=True)
        
        # 410 bytes payload (will trigger 3 chunks: 200, 200, 10 bytes)
        file_data = b"X" * 410
        
        success = await monthly_best_daemon.stream_raw_bin_payload(mock_divoom, file_data)
        self.assertTrue(success)
        
        # Verify app_new_send_gif_cmd is called with CW 0 (start), CW 1 (data) x 3 times, CW 2 (terminate)
        self.assertEqual(mock_divoom.animation.app_new_send_gif_cmd.call_count, 5)
        
        # Verify CW 0 call
        mock_divoom.animation.app_new_send_gif_cmd.assert_any_call(
            control_word=0, file_size=410
        )
        # Verify CW 2 call
        mock_divoom.animation.app_new_send_gif_cmd.assert_any_call(
            control_word=2
        )

if __name__ == '__main__':
    unittest.main()

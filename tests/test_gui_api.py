import sys
import json
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import pytest

# Add paths to imports
sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "gui"))

from gui_main import DivoomGuiAPI

class TestDivoomGuiAPI(unittest.TestCase):
    def setUp(self):
        # Prevent actually touching credentials files or presetting configs on disk during unit testing
        self.presets_patcher = patch("pathlib.Path.exists", return_value=False)
        self.presets_patcher.start()

        self.api = DivoomGuiAPI()
        self.api.window = MagicMock()

    def tearDown(self):
        self.presets_patcher.stop()

    def test_window_controls(self):
        """Test native window minimize, maximize, and thread-delayed close controls."""
        self.api.minimize_window()
        self.api.window.minimize.assert_called_once()

        self.api.maximize_window()
        self.api.window.toggle_fullscreen.assert_called_once()

        with patch("threading.Thread") as mock_thread:
            self.api.close_window()
            mock_thread.assert_called_once()

    @patch("gui_main.BleakScanner")
    def test_scan_devices_with_config(self, mock_scanner_cls):
        """Test BLE scanning executes cleanly under thread-safe asyncio loops."""
        mock_scanner = MagicMock()
        mock_scanner.start = AsyncMock()
        mock_scanner.stop = AsyncMock()
        mock_scanner_cls.return_value = mock_scanner

        # Mock discovery.discover_all_divoom_devices fallback
        with patch("divoom_lib.utils.discovery.discover_all_divoom_devices", new_callable=AsyncMock) as mock_discovery:
            mock_discovery.return_value = [{"name": "Pixoo-mock", "address": "AA:BB:CC:DD:EE:FF"}]
            
            # 1. Run limit=0 fallback path
            res = self.api.scan_devices_with_config(timeout=2, limit=0)
            res_list = json.loads(res)
            self.assertEqual(len(res_list), 1)
            self.assertEqual(res_list[0]["name"], "Pixoo-mock")

            # 2. Run callback detection path (limit > 0)
            def side_effect(*args, **kwargs):
                # Simulate detection callback directly inside the run loop
                cb = mock_scanner_cls.call_args[1].get("detection_callback")
                dev = MagicMock(name="Pixoo-Test", address="11:22:33:44:55:66")
                dev.name = "Pixoo-Test"
                cb(dev, None)
                return mock_scanner

            mock_scanner_cls.side_effect = side_effect
            res_cb = self.api.scan_devices_with_config(timeout=2, limit=1)
            res_cb_list = json.loads(res_cb)
            self.assertEqual(len(res_cb_list), 1)
            self.assertEqual(res_cb_list[0]["name"], "Pixoo-Test")

    @patch("gui_main.Divoom")
    def test_connect_single_device(self, mock_divoom_cls):
        """Test single device BLE connection and state transition."""
        mock_divoom = MagicMock()
        mock_divoom.connect = AsyncMock()
        mock_divoom.disconnect = AsyncMock()
        mock_divoom.is_connected = True
        mock_divoom_cls.return_value = mock_divoom

        success = self.api.connect_single_device("00:11:22:33:44:55")
        self.assertTrue(success)
        self.assertEqual(self.api.current_divoom, mock_divoom)
        mock_divoom.connect.assert_called_once()

    def test_preset_persistence(self):
        """Test preset name loading when no files exist."""
        preset_names = self.api.load_preset_names()
        self.assertEqual(json.loads(preset_names), [])

        preset_data = self.api.load_preset_by_name("NonExistent")
        self.assertEqual(json.loads(preset_data), {})

    @patch("gui_main.DivoomWall")
    def test_wall_operations(self, mock_wall_cls):
        """Test layout coordinate updates, wall building, solid colors, and clocks."""
        mock_wall = MagicMock()
        mock_wall.connect = AsyncMock()
        mock_wall.is_connected = True
        mock_wall.set_light = AsyncMock(return_value=True)
        mock_wall.show_clock = AsyncMock(return_value=True)
        mock_wall_cls.return_value = mock_wall

        # Sync coordinate positions
        slots = {"AA:BB:CC:DD:EE:FF": {"x": 0, "y": 0, "size": 16, "width": 120, "height": 120}}
        self.api.update_wall_slots(json.dumps(slots))
        self.assertEqual(self.api.wall_slots, slots)

        # Apply solid color setting
        light_success = self.api.set_solid_light("00FFCC", 100)
        self.assertTrue(light_success)
        mock_wall.set_light.assert_called_with("00FFCC", 100)

        # Apply clock style setting
        clock_success = self.api.set_clock(3)
        self.assertTrue(clock_success)
        mock_wall.show_clock.assert_called_with(clock=3)

    @patch("urllib.request.urlopen")
    def test_fetch_gallery_and_batch_sync(self, mock_urlopen):
        """Test cloud gallery catalog scraping and concurrent monthly best async streams."""
        # Mock fetch_gallery HTTP JSON response
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "FileList": [
                {"FileName": "NeonSkull", "FileId": "9999", "LikeCnt": 1500, "FileType": 5, "PixelAmbId": "amb123"}
            ]
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        # Mock authentication credentials
        self.api.cached_creds = MagicMock()
        self.api.cached_creds.token = "token123"
        self.api.cached_creds.user_id = 99
        self.api.cached_creds.is_valid.return_value = True

        gallery_json = self.api.fetch_gallery(classify=1)
        gallery = json.loads(gallery_json)
        self.assertEqual(len(gallery), 1)
        self.assertEqual(gallery[0]["name"], "NeonSkull")
        self.assertEqual(gallery[0]["file_id"], "9999")

        # Mock the stream_raw_bin_payload monthly best sync routine
        mock_stream = MagicMock()
        async def dummy_stream(*args, **kwargs):
            return True
        mock_stream.side_effect = dummy_stream
        
        with patch("monthly_best_daemon.stream_raw_bin_payload", mock_stream):
            # Setup wall coordinates and mock targets
            mock_device = MagicMock()
            self.api.wall_slots = {"AA:BB:CC:DD:EE:FF": {"x": 0, "y": 0, "size": 16}}
            self.api.wall_instance = MagicMock()
            self.api.wall_instance.is_connected = True
            self.api.wall_instance.devices = [(mock_device, 0, 0, 16, 120, 120)]

            artwork_json = json.dumps({"file_id": "9999"})
            sync_success = self.api.batch_sync_artwork(artwork_json)
            self.assertTrue(sync_success)
            mock_stream.assert_called_once()

    def test_stock_ticker_apply(self):
        """Test Yahoo Stock ticker downsampling and display coordination pipeline."""
        mock_data = {"price": 105.5, "change": 1.2, "pct_change": 1.15}
        with patch("divoom_lib.utils.media_source.fetch_stock_ticker", return_value=mock_data) as mock_fetch, \
             patch("divoom_lib.utils.media_source.render_stock_ticker_frame", return_value=Path("/tmp/ticker.png")) as mock_render:
            
            # Single connected device path
            self.api.current_divoom = MagicMock()
            self.api.current_divoom.is_connected = True
            self.api.current_divoom.display.show_image = AsyncMock(return_value=True)

            res = self.api.apply_stock_ticker("AAPL")
            res_dict = json.loads(res)
            self.assertTrue(res_dict["success"])
            self.assertEqual(res_dict["price"], 105.5)
            mock_fetch.assert_called_with("AAPL")
            mock_render.assert_called_with("AAPL", mock_data, size=16)

if __name__ == "__main__":
    unittest.main()

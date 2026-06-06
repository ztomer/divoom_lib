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

    def test_push_text(self):
        """R7 Text Channel: push_text runs the LPWA sequence ending with content."""
        from divoom_lib.models import LPWA_CONTROL_CONTENT, LPWA_CONTROL_COLOR, LPWA_CONTROL_SPEED
        dev = MagicMock()
        dev.is_connected = True
        dev.text.set_light_phone_word_attr = AsyncMock(return_value=True)
        self.api.current_divoom = dev
        self.api.current_target_mode = "single"
        with patch.object(type(self.api), "_active_device_size", return_value=16):
            ok = self.api.push_text("HELLO", color="#FF0000", speed=40, effect_style=1)
        self.assertTrue(ok)
        calls = dev.text.set_light_phone_word_attr.call_args_list
        controls = [c.args[0] for c in calls]
        self.assertIn(LPWA_CONTROL_COLOR, controls)
        self.assertIn(LPWA_CONTROL_SPEED, controls)
        self.assertIn(LPWA_CONTROL_CONTENT, controls)
        content_call = next(c for c in calls if c.args[0] == LPWA_CONTROL_CONTENT)
        self.assertEqual(content_call.kwargs.get("text_content"), "HELLO")

    def test_push_text_empty_noop(self):
        """Empty text is a no-op (returns False, sends nothing)."""
        dev = MagicMock()
        dev.text.set_light_phone_word_attr = AsyncMock(return_value=True)
        self.api.current_divoom = dev
        self.api.current_target_mode = "single"
        self.assertFalse(self.api.push_text("   "))
        dev.text.set_light_phone_word_attr.assert_not_called()

    @patch("gui_main.BleakScanner")
    def test_scan_devices(self, mock_scanner_cls):
        """Test BLE scanning executes cleanly under thread-safe asyncio loops."""
        mock_scanner = MagicMock()
        mock_scanner.start = AsyncMock()
        mock_scanner.stop = AsyncMock()
        mock_scanner_cls.return_value = mock_scanner

        # Mock discovery.discover_all_divoom_devices fallback
        with patch("divoom_lib.utils.discovery.discover_all_divoom_devices", new_callable=AsyncMock) as mock_discovery:
            mock_discovery.return_value = [{"name": "Pixoo-mock", "address": "AA:BB:CC:DD:EE:FF"}]
            
            # 1. Run limit=0 fallback path
            res = self.api.scan_devices(timeout=2, limit=0)
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
            res_cb = self.api.scan_devices(timeout=2, limit=1)
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
        self.api.current_target_mode = "wall"

        # Apply solid color setting
        light_success = self.api.set_solid_light("00FFCC", 100)
        self.assertTrue(light_success)
        mock_wall.set_light.assert_called_with("00FFCC", 100)

        # Apply clock style setting
        clock_success = self.api.set_clock(3)
        self.assertTrue(clock_success)
        mock_wall.show_clock.assert_called_with(clock=3)

    @patch("gui_main.DivoomWall")
    def test_vj_and_visualization_selectors(self, mock_wall_cls):
        """2.c/2.d: VJ effect and EQ/visualizer selectors dispatch to the device."""
        mock_wall = MagicMock()
        mock_wall.connect = AsyncMock()
        mock_wall.is_connected = True
        mock_wall.show_effects = AsyncMock(return_value=True)
        mock_wall.show_visualization = AsyncMock(return_value=True)
        mock_wall_cls.return_value = mock_wall

        # Put the API in wall-target mode.
        self.api.update_wall_slots(json.dumps(
            {"AA:BB:CC:DD:EE:FF": {"x": 0, "y": 0, "size": 16, "width": 120, "height": 120}}
        ))
        self.api.current_target_mode = "wall"

        self.assertTrue(self.api.set_vj_effect(5))
        mock_wall.show_effects.assert_called_with(number=5)

        self.assertTrue(self.api.set_visualization(3))
        mock_wall.show_visualization.assert_called_with(number=3)

    def test_vj_visualization_no_target(self):
        """With no connected device and no wall, selectors fail gracefully (no raise)."""
        self.api.current_divoom = None
        self.api.wall_slots = {}
        self.assertFalse(self.api.set_vj_effect(0))
        self.assertFalse(self.api.set_visualization(0))

    def test_hot_channel_bridges_delegate(self):
        """4.c/4.d: target + schedule bridges delegate to hotchannel_config."""
        cfg = {"enabled": False, "interval": 3600, "classify": 18, "targets": ["AA"]}
        with patch("divoom_lib.hotchannel_config.set_targets", return_value=True) as mset, \
             patch("divoom_lib.hotchannel_config.load_config", return_value=cfg), \
             patch("divoom_lib.hotchannel_config.get_targets", return_value=["AA"]), \
             patch("divoom_lib.hotchannel_config.save_config", return_value=True) as msave:

            self.assertTrue(self.api.set_sync_targets(json.dumps(["AA", "BB"])))
            mset.assert_called_once_with(["AA", "BB"])

            self.assertEqual(json.loads(self.api.get_hot_channel_config())["targets"], ["AA"])

            self.assertTrue(self.api.save_hot_channel_config(json.dumps({"enabled": True})))
            msave.assert_called_once()

            cands = json.loads(self.api.get_sync_candidates())
            sel = {c["address"]: c["selected"] for c in cands}
            self.assertTrue(sel.get("AA"))  # persisted target shows as selected

    def test_ticker_preview_returns_data_url(self):
        """5.d: get_ticker_preview renders a frame and returns a PNG data URL."""
        from pathlib import Path as _P
        with patch("divoom_lib.utils.media_source.fetch_stock_ticker",
                   return_value={"price": 100.0, "change": 1.0, "pct_change": 1.0}), \
             patch("divoom_lib.utils.media_source.render_stock_ticker_frame",
                   return_value=_P("/tmp/ticker_preview_test.png")), \
             patch.object(type(self.api), "_frame_to_data_url",
                          staticmethod(lambda p: "data:image/png;base64,AAA")):
            res = json.loads(self.api.get_ticker_preview("AAPL", 32))
            self.assertTrue(res["ok"])
            self.assertEqual(res["size"], 32)
            self.assertTrue(res["preview"].startswith("data:image/png;base64,"))

    def test_apply_stock_ticker_no_target(self):
        """5.a: clear failure when there is no connected device."""
        self.api.current_divoom = None
        self.api.wall_slots = {}
        with patch("divoom_lib.utils.media_source.fetch_stock_ticker",
                   return_value={"price": 1.0, "change": 0.0, "pct_change": 0.0}):
            res = json.loads(self.api.apply_stock_ticker("AAPL"))
            self.assertFalse(res["success"])
            self.assertEqual(res["error"], "No device connected")

    def test_ticker_persistence(self):
        """5.e: tickers save/load, de-duped and upper-cased."""
        import tempfile, os
        from pathlib import Path as _P
        tmp = _P(tempfile.mkdtemp()) / "tickers.json"
        # Override the setUp-wide Path.exists=False so the read path works.
        with patch.object(type(self.api), "_tickers_path", lambda self: tmp), \
             patch("pathlib.Path.exists", return_value=True):
            self.assertTrue(self.api.set_tickers(json.dumps(["aapl", "AAPL", "btc-usd", ""])))
            self.assertEqual(json.loads(self.api.get_tickers()), ["AAPL", "BTC-USD"])

    def test_system_stats_preview_and_apply(self):
        """Area 7: system-monitor widget renders a frame and reports stats."""
        from pathlib import Path as _P
        with patch("divoom_lib.utils.media_source.get_system_stats",
                   return_value={"cpu": 12, "mem": 43, "battery": 80}), \
             patch("divoom_lib.utils.media_source.render_system_stats_frame",
                   return_value=_P("/tmp/sysmon_test.png")), \
             patch.object(type(self.api), "_frame_to_data_url",
                          staticmethod(lambda p: "data:image/png;base64,BBB")):
            prev = json.loads(self.api.get_system_stats_preview(32))
            self.assertTrue(prev["ok"])
            self.assertEqual(prev["stats"]["cpu"], 12)
            self.assertTrue(prev["preview"].startswith("data:image/png;base64,"))

            # apply with no device → clear failure
            self.api.current_divoom = None
            self.api.wall_slots = {}
            res = json.loads(self.api.apply_system_stats())
            self.assertFalse(res["success"])
            self.assertEqual(res["error"], "No device connected")

    def test_sync_hot_channel_multi(self):
        """4.b: sync_hot_channel pushes every artwork and reports a summary."""
        with patch.object(self.api, "batch_sync_artwork", return_value=True) as m:
            res = json.loads(self.api.sync_hot_channel(json.dumps(["id1", "id2", "id3"])))
            self.assertTrue(res["ok"])
            self.assertEqual(res["synced"], ["id1", "id2", "id3"])
            self.assertEqual(m.call_count, 3)

        with patch.object(self.api, "batch_sync_artwork", side_effect=[True, False]):
            res2 = json.loads(self.api.sync_hot_channel(json.dumps(["a", "b"])))
            self.assertFalse(res2["ok"])
            self.assertEqual(res2["failed"], ["b"])

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

        # Pre-seed cached data for the offline cache loader check.
        # Use a real-looking file_id (not "9999") so the rebuild-on-stale path
        # doesn't trigger (see gui/gallery_sync.py load_cached_gallery).
        cached_items = [
            {"name": "NeonSkull", "file_id": "group1/M00/01/AAA_neon", "likes": 1500, "magic": 5, "preview_url": "data:image/png;base64,..."}
        ]

        import threading
        import time

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.read_text", return_value=json.dumps(cached_items)):
            gallery_json = self.api.fetch_gallery(classify=1)
            gallery = json.loads(gallery_json)
            self.assertEqual(len(gallery), 1)
            self.assertEqual(gallery[0]["name"], "NeonSkull")
            self.assertEqual(gallery[0]["file_id"], "group1/M00/01/AAA_neon")

            # Wait for background fetch worker to finish executing under mocked Path
            for t in threading.enumerate():
                if t.name == "DivoomGalleryFetch":
                    t.join(timeout=5.0)

        # Mock the stream_raw_bin_payload monthly best sync routine
        mock_stream = MagicMock()
        async def dummy_stream(*args, **kwargs):
            return True
        mock_stream.side_effect = dummy_stream
        
        with patch("divoom_lib.monthly_best_daemon.stream_raw_bin_payload", mock_stream):
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

    def test_lan_device_operations(self):
        """Test adding, loading, and deleting LAN devices with mock preset file storage."""
        mock_presets_data = {}
        def mock_read_text(*args, **kwargs):
            return json.dumps(mock_presets_data)
        def mock_write_text(content, *args, **kwargs):
            nonlocal mock_presets_data
            mock_presets_data = json.loads(content)
            return len(content)
            
        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.read_text", side_effect=mock_read_text), \
             patch("pathlib.Path.write_text", side_effect=mock_write_text):
                 
            # Add device
            success = self.api.add_lan_device("192.168.1.100", 123)
            self.assertTrue(success)
            
            # Load devices
            devices_json = self.api.load_lan_devices()
            devices = json.loads(devices_json)
            self.assertEqual(len(devices), 1)
            self.assertEqual(devices[0]["ip"], "192.168.1.100")
            self.assertEqual(devices[0]["token"], 123)
            
            # Delete device
            del_success = self.api.delete_lan_device("192.168.1.100")
            self.assertTrue(del_success)
            
            # Load again to check empty
            devices_json2 = self.api.load_lan_devices()
            self.assertEqual(json.loads(devices_json2), [])

if __name__ == "__main__":
    unittest.main()

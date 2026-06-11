#!/usr/bin/env python3
import sys
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path
from PIL import Image

sys.path.append(str(Path(__file__).parent.parent))

from divoom_lib.wall import DivoomWall, wall_resolution

class TestDivoomWall(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.device_configs = [
            {"mac": "AA:BB:CC:DD:EE:01", "x": 0, "y": 0, "size": 16}, # Top-left
            {"mac": "AA:BB:CC:DD:EE:02", "x": 1, "y": 0, "size": 16}, # Top-right
            {"mac": "AA:BB:CC:DD:EE:03", "x": 0, "y": 1, "size": 16}, # Bottom-left
            {"mac": "AA:BB:CC:DD:EE:04", "x": 1, "y": 1, "size": 16}  # Bottom-right
        ]

    @patch('divoom_lib.wall.Divoom', new_callable=MagicMock)
    def test_wall_init(self, mock_divoom_class):
        """Test DivoomWall initialization and dimensions."""
        wall = DivoomWall(self.device_configs)
        
        self.assertEqual(len(wall.devices), 4)
        self.assertEqual(wall.total_width, 32)
        self.assertEqual(wall.total_height, 32)
        self.assertEqual(wall.grid_unit_size, 16)

    @patch('divoom_lib.wall.Divoom', new_callable=MagicMock)
    async def test_wall_connect_disconnect(self, mock_divoom_class):
        """Test DivoomWall connect and disconnect async methods."""
        # Setup mocks — start DISCONNECTED and flip to connected on connect(),
        # mirroring reality. The P3 honest connect (ensure_connected) skips a
        # device that already reports is_connected, so a mock pinned True would
        # never call connect().
        mock_clients = []
        for _ in range(4):
            mc = MagicMock()

            async def _connect(_m=mc):
                _m.is_connected = True
            mc.connect = AsyncMock(side_effect=_connect)
            mc.disconnect = AsyncMock(return_value=None)
            mc.is_connected = False
            mock_clients.append(mc)

        mock_divoom_class.side_effect = mock_clients
        
        wall = DivoomWall(self.device_configs)
        await wall.connect()
        
        for mc in mock_clients:
            mc.connect.assert_called_once()
            
        self.assertTrue(wall.is_connected)
        
        await wall.disconnect()
        for mc in mock_clients:
            mc.disconnect.assert_called_once()

    @patch('divoom_lib.wall.Divoom', new_callable=MagicMock)
    @patch('divoom_lib.wall.Image.open')
    async def test_wall_show_image(self, mock_image_open, mock_divoom_class):
        """Test DivoomWall splitting and cropping logic for show_image."""
        # Mock main image
        mock_img = MagicMock(spec=Image.Image)
        mock_img.is_animated = False
        mock_img.crop = MagicMock(return_value=mock_img)
        mock_img.resize = MagicMock(return_value=mock_img)
        mock_image_open.return_value = mock_img
        
        # Setup mock Divoom clients
        mock_clients = []
        for _ in range(4):
            mc = MagicMock()
            mc.display.show_image = AsyncMock(return_value=True)
            mock_clients.append(mc)
        mock_divoom_class.side_effect = mock_clients
        
        orig_exists = Path.exists
        def mock_exists(self_path):
            return "mock_path.png" in str(self_path)

        Path.exists = mock_exists
        try:
            wall = DivoomWall(self.device_configs)
            success = await wall.show_image("mock_path.png")
            self.assertTrue(success)
        finally:
            Path.exists = orig_exists
            
            # Verify cropping bounds for each grid coordinate
            # Top-left slot (0, 0)
            mock_img.resize.assert_called_with((32, 32), Image.NEAREST)
            mock_img.crop.assert_any_call((0, 0, 16, 16))
            # Top-right slot (1, 0)
            mock_img.crop.assert_any_call((16, 0, 32, 16))
            # Bottom-left slot (0, 1)
            mock_img.crop.assert_any_call((0, 16, 16, 32))
            # Bottom-right slot (1, 1)
            mock_img.crop.assert_any_call((16, 16, 32, 32))
            
            # Verify all Divoom show_image methods were called
            for mc in mock_clients:
                mc.display.show_image.assert_called_once()

    @patch('divoom_lib.wall.Divoom', new_callable=MagicMock)
    async def test_wall_set_light_and_clock(self, mock_divoom_class):
        """Test DivoomWall batch operations: set_light and show_clock."""
        mock_clients = []
        for _ in range(4):
            mc = MagicMock()
            mc.display.show_light = AsyncMock(return_value=True)
            mc.display.show_clock = AsyncMock(return_value=True)
            mock_clients.append(mc)
        mock_divoom_class.side_effect = mock_clients
        
        wall = DivoomWall(self.device_configs)
        
        res_light = await wall.set_light("FF0000", brightness=80)
        self.assertTrue(res_light)
        for mc in mock_clients:
            mc.display.show_light.assert_called_once_with(color="FF0000", brightness=80)
            
        res_clock = await wall.show_clock(clock=2)
        self.assertTrue(res_clock)
        for mc in mock_clients:
            mc.display.show_clock.assert_called_once_with(clock=2)

    @patch('divoom_lib.wall.Divoom', new_callable=MagicMock)
    async def test_wall_switch_channel_volume_brightness(self, mock_divoom_class):
        """R17 P5: wall-level fan-out methods added so the daemon-owned wall is
        callable via a single device_call (no GUI-side per-device iteration)."""
        mock_clients = []
        for _ in range(4):
            mc = MagicMock()
            mc.lan = None
            mc.display.switch_channel = AsyncMock(return_value=True)
            mc.music.set_volume = AsyncMock(return_value=True)
            mc.device.set_brightness = AsyncMock(return_value=True)
            mock_clients.append(mc)
        mock_divoom_class.side_effect = mock_clients

        wall = DivoomWall(self.device_configs)

        self.assertTrue(await wall.switch_channel("cloud"))
        for mc in mock_clients:
            mc.display.switch_channel.assert_called_once_with("cloud")

        self.assertTrue(await wall.set_volume(7))
        for mc in mock_clients:
            mc.music.set_volume.assert_called_once_with(7)

        # No LAN transport on any panel -> BLE device.set_brightness path.
        self.assertTrue(await wall.set_brightness(55))
        for mc in mock_clients:
            mc.device.set_brightness.assert_called_once_with(55)

    @patch('divoom_lib.wall.Divoom', new_callable=MagicMock)
    async def test_wall_push_text(self, mock_divoom_class):
        """Wall push_text runs the LPWA sequence on every screen with its size."""
        from divoom_lib.models import LPWA_CONTROL_CONTENT
        mock_clients = []
        for _ in range(4):
            mc = MagicMock()
            mc.text.set_light_phone_word_attr = AsyncMock(return_value=True)
            mock_clients.append(mc)
        mock_divoom_class.side_effect = mock_clients

        wall = DivoomWall(self.device_configs)
        self.assertTrue(await wall.push_text("HI", color="#00FF00", speed=30))
        for mc in mock_clients:
            controls = [c.args[0] for c in mc.text.set_light_phone_word_attr.call_args_list]
            self.assertIn(LPWA_CONTROL_CONTENT, controls)


class TestWallResolution(unittest.TestCase):
    """R13 §1 — the wall_resolution() helper. It must be derived from
    panel_resolution (per-panel pixels), not the wall canvas size."""

    def test_2x2_wall_of_16px_panels(self):
        """Four Pixoos (16×16) in a 2×2 grid = 32×32 composite."""
        self.assertEqual(wall_resolution(16, 2, 2), (32, 32))

    def test_2x1_wall_of_32px_panels(self):
        """Two Tivoo Maxes (32×32) side-by-side = 64×32 composite."""
        self.assertEqual(wall_resolution(32, 2, 1), (64, 32))

    def test_4x2_wall_of_32px_panels(self):
        """Eight Timoos (32×32) in a 4×2 grid = 128×64 composite."""
        self.assertEqual(wall_resolution(32, 4, 2), (128, 64))

    def test_single_panel_returns_panel_resolution(self):
        """A 1×1 wall is just one panel — the canvas is panel_resolution square."""
        self.assertEqual(wall_resolution(16, 1, 1), (16, 16))
        self.assertEqual(wall_resolution(32, 1, 1), (32, 32))

    def test_64px_panels(self):
        """A Pixoo 64 (64×64) in a 1×1 wall = 64×64; in 2×1 = 128×64."""
        self.assertEqual(wall_resolution(64, 1, 1), (64, 64))
        self.assertEqual(wall_resolution(64, 2, 1), (128, 64))

    def test_invalid_panel_resolution_rejected(self):
        """panel_resolution must be 16, 32, or 64. Other values raise."""
        with self.assertRaises(ValueError):
            wall_resolution(8, 1, 1)
        with self.assertRaises(ValueError):
            wall_resolution(128, 1, 1)
        with self.assertRaises(ValueError):
            wall_resolution(0, 1, 1)

    def test_invalid_grid_rejected(self):
        """Grid must be at least 1×1."""
        with self.assertRaises(ValueError):
            wall_resolution(32, 0, 1)
        with self.assertRaises(ValueError):
            wall_resolution(32, 1, 0)


if __name__ == '__main__':
    unittest.main()

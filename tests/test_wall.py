#!/usr/bin/env python3
import sys
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path
from PIL import Image

sys.path.append(str(Path(__file__).parent.parent))

from divoom_lib.wall import DivoomWall

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
        # Setup mocks
        mock_clients = []
        for _ in range(4):
            mc = MagicMock()
            mc.connect = AsyncMock(return_value=None)
            mc.disconnect = AsyncMock(return_value=None)
            mc.is_connected = True
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
        
        # Patch Path.exists to pass validation
        with patch('divoom_lib.wall.Path.exists', return_value=True):
            wall = DivoomWall(self.device_configs)
            success = await wall.show_image("mock_path.png")
            
            self.assertTrue(success)
            
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

if __name__ == '__main__':
    unittest.main()

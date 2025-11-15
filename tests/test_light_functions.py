
import asyncio
import logging
import unittest
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from divoom_lib import Divoom
from divoom_lib.utils.discovery import discover_device

# --- Configuration ---
DEVICE_NAME_SUBSTRING = "Timoo"
LOG_LEVEL = logging.DEBUG

# Setup basic logging
logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("light_functions_test")

class TestLightFunctions(unittest.IsolatedAsyncioTestCase):

    divoom: Divoom = None
    
    async def asyncSetUp(self):
        """Discover and connect to the device before each test."""
        ble_device, _ = await discover_device(name_substring=DEVICE_NAME_SUBSTRING)
        if not ble_device:
            self.fail(f"No device found with name containing '{DEVICE_NAME_SUBSTRING}'.")
        
        # Based on previous investigations, we know the correct protocol settings
        self.divoom = Divoom(
            mac=ble_device.address, 
            logger=logger, 
            use_ios_le_protocol=False # Use Basic Protocol for notifications
        )
        await self.divoom.connect()
        
        self.divoom.WRITE_CHARACTERISTIC_UUID = "49535343-8841-43f4-a8d4-ecbe34729bb3"
        self.divoom.NOTIFY_CHARACTERISTIC_UUID = "49535343-1e4d-4bd9-ba61-23c647249616"
        self.divoom.escapePayload = False

    async def asyncTearDown(self):
        """Disconnect after each test."""
        if self.divoom and self.divoom.is_connected:
            await self.divoom.disconnect()

    async def test_get_light_mode(self):
        """Test getting the current light mode, which contains many settings."""
        logger.info("--- Running test_get_light_mode ---")
        
        light_settings = await self.divoom.light.get_light_mode()
        
        logger.info(f"Got light settings: {light_settings}")
        self.assertIsNotNone(light_settings)
        self.assertIsInstance(light_settings, dict)
        
        # Check for the presence of all expected keys
        expected_keys = [
            "current_light_effect_mode", "temperature_display_mode", "vj_selection_option",
            "rgb_color_values", "brightness_level", "lighting_mode_selection_option",
            "on_off_switch", "music_mode_selection_option", "system_brightness",
            "time_display_format_selection_option", "time_display_rgb_color_values",
            "time_display_mode", "time_checkbox_modes"
        ]
        for key in expected_keys:
            self.assertIn(key, light_settings)
            
        # Validate that brightness exists and is a valid value
        self.assertIn("brightness_level", light_settings)
        self.assertIsInstance(light_settings["brightness_level"], int)
        self.assertTrue(0 <= light_settings["brightness_level"] <= 100)
        logger.info(f"Brightness level is {light_settings['brightness_level']}, which is a valid value.")

    async def test_set_gif_speed(self):
        """Test setting the GIF animation speed."""
        logger.info("--- Running test_set_gif_speed ---")
        test_speed = 100  # 100ms
        
        # This is an action command, we just check for success
        result = await self.divoom.light.set_gif_speed(test_speed)
        self.assertTrue(result)
        logger.info(f"Successfully sent set_gif_speed command with speed {test_speed}ms.")


if __name__ == '__main__':
    unittest.main()

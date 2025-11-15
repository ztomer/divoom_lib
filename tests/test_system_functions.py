
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
LOG_LEVEL = logging.INFO

# Setup basic logging
logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("system_functions_test")

class TestSystemFunctions(unittest.IsolatedAsyncioTestCase):

    divoom: Divoom = None
    
    async def asyncSetUp(self):
        """Discover and connect to the device before each test."""
        ble_device, _ = await discover_device(name_substring=DEVICE_NAME_SUBSTRING)
        if not ble_device:
            self.fail(f"No device found with name containing '{DEVICE_NAME_SUBSTRING}'.")
        
        self.divoom = Divoom(mac=ble_device.address, logger=logger, use_ios_le_protocol=False)
        await self.divoom.connect()
        
        # We know from previous tests which characteristics and protocol work
        self.divoom.WRITE_CHARACTERISTIC_UUID = "49535343-8841-43f4-a8d4-ecbe34729bb3"
        self.divoom.NOTIFY_CHARACTERISTIC_UUID = "49535343-1e4d-4bd9-ba61-23c647249616"
        self.divoom.escapePayload = False

    async def asyncTearDown(self):
        """Disconnect after each test."""
        if self.divoom and self.divoom.is_connected:
            await self.divoom.disconnect()

    async def test_get_brightness(self):
        """Test getting the current brightness."""
        logger.info("--- Running test_get_brightness ---")
        brightness = await self.divoom.system.get_brightness()
        logger.info(f"Got brightness: {brightness}")
        self.assertIsNotNone(brightness)
        self.assertIsInstance(brightness, int)
        self.assertTrue(0 <= brightness <= 100)

    async def test_set_and_get_brightness(self):
        """Test setting the brightness and then getting it to verify."""
        logger.info("--- Running test_set_and_get_brightness ---")
        
        # Set brightness to a known value
        test_brightness = 50
        logger.info(f"Setting brightness to {test_brightness}...")
        await self.divoom.system.set_brightness(test_brightness)
        
        # Give the device a moment to process
        await asyncio.sleep(2.0)
        
        # Get brightness and verify
        logger.info("Getting brightness to verify...")
        current_brightness = await self.divoom.system.get_brightness()
        logger.info(f"Got brightness: {current_brightness}")
        
        # The getter might be flaky, so we add a retry
        retries = 3
        while current_brightness != test_brightness and retries > 0:
            logger.warning(f"Brightness mismatch. Expected {test_brightness}, got {current_brightness}. Retrying...")
            await asyncio.sleep(2.0)
            current_brightness = await self.divoom.system.get_brightness()
            retries -= 1

        self.assertEqual(current_brightness, test_brightness)

        # Set it back to 100
        logger.info("Setting brightness back to 100...")
        await self.divoom.system.set_brightness(100)

if __name__ == '__main__':
    unittest.main()

import os
import sys
import asyncio
import unittest
import logging

# Add the project root to sys.path to allow importing divoom_api
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from divoom_api.divoom_protocol import Divoom
from divoom_api.utils.discovery import discover_divoom_devices, discover_characteristics, discover_device_and_characteristics

# Configure logging for the test
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestChannelRotation(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        logger.info("Starting real device setup...")
        mac_address, write_uuid, notify_uuid, read_uuid = await discover_device_and_characteristics(
            device_name="Tivoo-Max",
            logger=logger
        )

        self.assertIsNotNone(mac_address, "Could not discover Tivoom device.")
        self.assertIsNotNone(write_uuid, "Could not discover write characteristic.")
        self.assertIsNotNone(notify_uuid, "Could not discover notify characteristic.")

        self.divoom = Divoom(
            mac=mac_address,
            logger=logger,
            write_characteristic_uuid=write_uuid,
            notify_characteristic_uuid=notify_uuid,
            read_characteristic_uuid=read_uuid
        )
        await self.divoom.connect()
        logger.info(f"Connected to real Tivoom device at {mac_address}")

    async def asyncTearDown(self):
        if self.divoom.client and self.divoom.client.is_connected:
            await self.divoom.disconnect()
            logger.info("Disconnected from real Tivoom device.")

    async def test_discovery_and_channel_rotation(self):
        logger.info("Starting test_discovery_and_channel_rotation...")

        logger.info("Simulating setting to light mode and keeping it there...")

        # Show Light (e.g., red light)
        await self.divoom.display.show_light(color="FF0000", brightness=50, power=True)
        logger.info("Called show_light and keeping it there.")

        logger.info("Finished test_discovery_and_channel_rotation.")

if __name__ == '__main__':
    unittest.main()

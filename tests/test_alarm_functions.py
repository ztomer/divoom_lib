import unittest
import asyncio
import logging
import os
import sys

# Add the project root to sys.path to allow importing divoom_lib
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from divoom_lib import Divoom
from divoom_lib.utils.discovery import discover_device

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("test_alarm_functions")

class TestAlarmFunctions(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.divoom = None
        self.device_id = None
        
        try:
            ble_device, device_id = await discover_device(name_substring="Timoo")
            if ble_device:
                self.device_id = device_id
                self.divoom = Divoom(mac=self.device_id, logger=logger)
                await self.divoom.connect()
                logger.info(f"Connected to Divoom device at {self.divoom.mac}")
            else:
                logger.error("No Divoom device found for testing.")
        except Exception as e:
            logger.error(f"Error during device setup: {e}")
            self.divoom = None # Ensure divoom is None if connection fails

        if not self.divoom or not self.divoom.is_connected:
            raise unittest.SkipTest("Could not connect to Divoom device, skipping this test.")

    async def asyncTearDown(self):
        if self.divoom and self.divoom.is_connected:
            await self.divoom.disconnect()
            logger.info("Disconnected from Divoom device.")

    async def test_set_alarm(self):
        logger.info("--- Running test_set_alarm ---")
        # Set an alarm for 10:30 AM, Monday, enabled
        await self.divoom.alarm.set_alarm(
            alarm_index=0,
            status=1, # On
            hour=10,
            minute=30,
            week=1, # Monday
            mode=0, # ALARM_MUSIC
            trigger_mode=1, # ALARM_TRIGGER_MUSIC
            fm_freq=0,
            volume=50
        )
        logger.info("Set alarm for 10:30 AM Monday, enabled.")
        # In a real scenario, you'd want to verify this by getting the alarm back
        # For now, we just check if the command was sent without error.

    async def test_get_alarm(self):
        logger.info("--- Running test_get_alarm ---")
        alarm_settings = await self.divoom.alarm.get_alarm_time()
        self.assertIsNotNone(alarm_settings, "Failed to retrieve alarm settings.")
        logger.info(f"Retrieved alarm settings: {alarm_settings}")
        # Add more specific assertions based on expected structure of alarm_settings

    async def test_enable_disable_alarm(self):
        logger.info("--- Running test_enable_disable_alarm ---")
        # First, set an alarm to ensure it exists
        await self.divoom.alarm.set_alarm(
            alarm_index=0,
            status=1, # On
            hour=11,
            minute=0,
            week=2, # Tuesday
            mode=0,
            trigger_mode=1,
            fm_freq=0,
            volume=50
        )
        logger.info("Set alarm for 11:00 AM Tuesday, enabled.")

        # Disable the alarm
        await self.divoom.alarm.set_alarm(
            alarm_index=0,
            status=0, # Off
            hour=11,
            minute=0,
            week=2, # Tuesday
            mode=0,
            trigger_mode=1,
            fm_freq=0,
            volume=50
        )
        logger.info("Disabled alarm for 11:00 AM Tuesday.")

        # In a real scenario, you'd get the alarm settings back and assert enabled=False

if __name__ == '__main__':
    unittest.main()

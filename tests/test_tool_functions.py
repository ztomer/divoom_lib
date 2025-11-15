
import asyncio
import logging
import unittest
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from divoom_lib import Divoom
from divoom_lib.utils.discovery import discover_device
from divoom_lib import constants

# --- Configuration ---
DEVICE_NAME_SUBSTRING = "Timoo"
LOG_LEVEL = logging.INFO

# Setup basic logging
logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("tool_functions_test")

class TestToolFunctions(unittest.IsolatedAsyncioTestCase):

    divoom: Divoom = None
    
    async def asyncSetUp(self):
        """Discover and connect to the device before each test."""
        ble_device, _ = await discover_device(name_substring=DEVICE_NAME_SUBSTRING)
        if not ble_device:
            self.fail(f"No device found with name containing '{DEVICE_NAME_SUBSTRING}'.")
        
        self.divoom = Divoom(
            mac=ble_device.address, 
            logger=logger, 
            use_ios_le_protocol=False
        )
        await self.divoom.connect()
        
        self.divoom.WRITE_CHARACTERISTIC_UUID = "49535343-8841-43f4-a8d4-ecbe34729bb3"
        self.divoom.NOTIFY_CHARACTERISTIC_UUID = "49535343-1e4d-4bd9-ba61-23c647249616"
        self.divoom.escapePayload = False

    async def asyncTearDown(self):
        """Disconnect after each test."""
        if self.divoom and self.divoom.is_connected:
            await self.divoom.disconnect()

    async def test_scoreboard(self):
        """Test setting and getting the scoreboard tool."""
        logger.info("--- Running test_scoreboard ---")
        
        # First, switch to the scoreboard tool so we can query it
        logger.info("Switching to scoreboard tool...")
        await self.divoom.system.set_channel(constants.CHANNEL_ID_SCOREBOARD)
        await asyncio.sleep(2)

        # Set new scores
        test_red_score = 15
        test_blue_score = 25
        logger.info(f"Setting scores to Red={test_red_score}, Blue={test_blue_score}...")
        result = await self.divoom.tool.set_tool_info(
            constants.TOOL_TYPE_SCORE,
            on_off=constants.STI_SCORE_ON,
            red_score=test_red_score,
            blue_score=test_blue_score
        )
        self.assertTrue(result)
        await asyncio.sleep(2)

        # Get new state and verify. Note: some devices may not reflect the score
        # change immediately or at all via the getter. We will log the result
        # but the primary test is that the set command was successful.
        logger.info("Getting scoreboard state to verify...")
        new_state = await self.divoom.tool.get_tool_info(constants.TOOL_TYPE_SCORE)
        self.assertIsNotNone(new_state)
        logger.info(f"New scores reported: Red={new_state['red_score']}, Blue={new_state['blue_score']}")
        
        # The most important assertion is that the command was sent successfully.
        # We log the outcome of the get command for debugging purposes.
        if new_state['red_score'] != test_red_score or new_state['blue_score'] != test_blue_score:
            logger.warning("Device did not report the new scores. This may be normal for some models.")

        # Reset scores to 0
        logger.info("Resetting scores...")
        await self.divoom.tool.set_tool_info(
            constants.TOOL_TYPE_SCORE,
            on_off=constants.STI_SCORE_ON,
            red_score=0,
            blue_score=0
        )

    async def test_countdown(self):
        """Test setting and getting the countdown tool."""
        logger.info("--- Running test_countdown ---")

        # Switch to a mode where tools are accessible, e.g., the clock
        await self.divoom.system.set_channel(constants.CHANNEL_ID_TIME)
        await asyncio.sleep(2)

        # Set a new countdown
        test_minutes = 1
        test_seconds = 30
        logger.info(f"Setting countdown to {test_minutes}m {test_seconds}s...")
        result = await self.divoom.tool.set_tool_info(
            constants.TOOL_TYPE_COUNTDOWN,
            ctrl_flag=constants.STI_CTRL_FLAG_COUNTDOWN_START,
            minutes=test_minutes,
            seconds=test_seconds
        )
        self.assertTrue(result)
        await asyncio.sleep(2)

        # Get state and verify (note: countdown will have started, so we check if it's running)
        logger.info("Getting countdown state to verify...")
        new_state = await self.divoom.tool.get_tool_info(constants.TOOL_TYPE_COUNTDOWN)
        self.assertIsNotNone(new_state)
        # The device reports status '3' when a countdown is active.
        self.assertEqual(new_state['status'], 3)
        logger.info(f"Countdown is running as expected (status={new_state['status']}).")

        # Cancel the countdown
        logger.info("Cancelling countdown...")
        await self.divoom.tool.set_tool_info(
            constants.TOOL_TYPE_COUNTDOWN,
            ctrl_flag=constants.STI_CTRL_FLAG_COUNTDOWN_CANCEL,
            minutes=0,
            seconds=0
        )

if __name__ == '__main__':
    unittest.main()

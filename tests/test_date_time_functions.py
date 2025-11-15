
import asyncio
import logging
import unittest
import os
import sys
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from divoom_lib.commands.date_time import DateTimeCommand
from divoom_lib.base import DivoomBase # Import DivoomBase for type hinting and mocking
from divoom_lib import constants

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("test_date_time_functions")

class TestDateTimeFunctions(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        """Set up a mock Divoom instance for testing."""
        self.mock_divoom_instance = AsyncMock(spec=DivoomBase)
        self.mock_divoom_instance.logger = logger
        # Mock necessary methods/attributes from DivoomBase that DateTimeCommand uses
        self.mock_divoom_instance.number2HexString = MagicMock(side_effect=lambda x: f"{x:02x}")
        self.mock_divoom_instance.send_command = AsyncMock(return_value=True) # Mock send_command

        # Instantiate DateTimeCommand without triggering _update_message in __init__
        self.date_time_command = DateTimeCommand(self.mock_divoom_instance)

    async def test_update_message_sends_correct_command(self):
        """Test that _update_message constructs and sends the correct date/time command."""
        logger.info("--- Running test_update_message_sends_correct_command ---")
        
        # Set a specific date and time for predictable testing
        test_datetime = datetime.datetime(2025, 11, 15, 10, 30, 45)
        self.date_time_command.date = test_datetime
        
        # Explicitly trigger the update
        await self.date_time_command.update_date_time()
        
        self.mock_divoom_instance.send_command.assert_called_once()
        
        # Expected command ID is 0x18
        expected_command_id = 0x18
        self.assertEqual(self.mock_divoom_instance.send_command.call_args[0][0], expected_command_id)

        # Expected args: year_lsb, year_msb, month, day, hour, minute, second, 0x00
        # 2025 -> 25 (0x19), 20 (0x14)
        # 11 -> 0x0B
        # 15 -> 0x0F
        # 10 -> 0x0A
        # 30 -> 0x1E
        # 45 -> 0x2D
        expected_args = [0x19, 0x14, 0x0B, 0x0F, 0x0A, 0x1E, 0x2D, 0x00]
        self.assertEqual(self.mock_divoom_instance.send_command.call_args[0][1], expected_args)

    async def test_date_setter_updates_internal_state(self):
        """Test that setting the date property updates the internal state."""
        logger.info("--- Running test_date_setter_updates_internal_state ---")
        
        new_datetime = datetime.datetime(2026, 1, 1, 0, 0, 0)
        self.date_time_command.date = new_datetime
        
        self.assertEqual(self.date_time_command.date, new_datetime)
        
        # Ensure send_command was NOT called automatically by the setter
        self.mock_divoom_instance.send_command.assert_not_called()

    async def test_update_date_time_with_default_date(self):
        """Test update_date_time when initialized with default date (current time)."""
        logger.info("--- Running test_update_date_time_with_default_date ---")
        
        # Reset mock for this test
        self.mock_divoom_instance.send_command.reset_mock()
        
        # Instantiate with default date (current time)
        date_time_command_default = DateTimeCommand(self.mock_divoom_instance)
        
        # Explicitly trigger the update
        await date_time_command_default.update_date_time()
        
        self.mock_divoom_instance.send_command.assert_called_once()
        
        # Verify command ID
        self.assertEqual(self.mock_divoom_instance.send_command.call_args[0][0], 0x18)
        
        # Verify args structure (values will be current time, so just check length and type)
        args = self.mock_divoom_instance.send_command.call_args[0][1]
        self.assertIsInstance(args, list)
        self.assertEqual(len(args), 8) # 7 date/time bytes + 1 padding byte

if __name__ == '__main__':
    unittest.main()

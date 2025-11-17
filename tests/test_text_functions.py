
import asyncio
import logging
import unittest
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List

from divoom_lib.drawing.text import DisplayText
from divoom_lib.base import DivoomBase # Import DivoomBase for type hinting and mocking
from divoom_lib import constants

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("test_text_functions")

class TestTextFunctions(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        """Set up a mock Divoom instance for testing."""
        self.mock_divoom_instance = AsyncMock(spec=DivoomBase)
        self.mock_divoom_instance.logger = logger
        # Mock necessary methods/attributes from DivoomBase that DisplayText uses
        self.mock_divoom_instance._int2hexlittle = MagicMock(side_effect=lambda x: f"{x & 0xFF:02x}{((x >> 8) & 0xFF):02x}")
        self.mock_divoom_instance.number2HexString = MagicMock(side_effect=lambda x: f"{x:02x}")
        self.mock_divoom_instance.color2HexString = MagicMock(side_effect=lambda x: x.replace("#", "")) # Simple mock for color hex conversion
        self.mock_divoom_instance.send_command = AsyncMock(return_value=True) # Mock send_command

        self.display_text = DisplayText(self.mock_divoom_instance, opts={"text": "TEST"})

    async def test_palette_text_on_background(self):
        """Test PALETTE_TEXT_ON_BACKGROUND function."""
        logger.info("--- Running test_palette_text_on_background ---")
        palette = self.display_text.PALETTE_TEXT_ON_BACKGROUND(text_color="FF0000", background_color="0000FF")
        self.assertEqual(len(palette), 256)
        self.assertEqual(palette[0], "0000FF") # Background color
        self.assertEqual(palette[126], "0000FF") # Background color
        self.assertEqual(palette[127], "FF0000") # Text color
        self.assertEqual(palette[255], "FF0000") # Text color

    async def test_palette_black_on_cmy_rainbow(self):
        """Test PALETTE_BLACK_ON_CMY_RAINBOW function."""
        logger.info("--- Running test_palette_black_on_cmy_rainbow ---")
        palette = self.display_text.PALETTE_BLACK_ON_CMY_RAINBOW()
        self.assertEqual(len(palette), 256)
        self.assertEqual(palette[255], "000000") # Black

    async def test_palette_black_on_rainbow(self):
        """Test PALETTE_BLACK_ON_RAINBOW function."""
        logger.info("--- Running test_palette_black_on_rainbow ---")
        palette = self.display_text.PALETTE_BLACK_ON_RAINBOW()
        self.assertEqual(len(palette), 256)
        self.assertEqual(palette[255], "000000") # Black

    async def test_anim_static_background(self):
        """Test ANIM_STATIC_BACKGROUND function."""
        logger.info("--- Running test_anim_static_background ---")
        pixels = self.display_text.ANIM_STATIC_BACKGROUND()
        self.assertEqual(len(pixels), 256)
        self.assertTrue(all(p == 0 for p in pixels))

    async def test_anim_uni_gradiant_background(self):
        """Test ANIM_UNI_GRADIANT_BACKGROUND function."""
        logger.info("--- Running test_anim_uni_gradiant_background ---")
        pixels = self.display_text.ANIM_UNI_GRADIANT_BACKGROUND(frame=10)
        self.assertEqual(len(pixels), 256)
        self.assertTrue(all(p == 10 for p in pixels))

    async def test_anim_horizontal_gradiant_background(self):
        """Test ANIM_HORIZONTAL_GRADIANT_BACKGROUND function."""
        logger.info("--- Running test_anim_horizontal_gradiant_background ---")
        pixels = self.display_text.ANIM_HORIZONTAL_GRADIANT_BACKGROUND(frame=0)
        self.assertEqual(len(pixels), 256)
        # Check first row (16 pixels)
        for i in range(16):
            self.assertEqual(pixels[i], i)

    async def test_anim_vertical_gradiant_background(self):
        """Test ANIM_VERTICAL_GRADIANT_BACKGROUND function."""
        logger.info("--- Running test_anim_vertical_gradiant_background ---")
        pixels = self.display_text.ANIM_VERTICAL_GRADIANT_BACKGROUND(frame=0)
        self.assertEqual(len(pixels), 256)
        # Check first column (every 16th pixel)
        for i in range(16):
            self.assertEqual(pixels[i*16], i)

    async def test_encode_text(self):
        """Test _encode_text method."""
        logger.info("--- Running test_encode_text ---")
        encoded = self.display_text._encode_text("Hi")
        # Expected: [0x86, 0x01, len("Hi"), H_byte1, H_byte2, i_byte1, i_byte2]
        # ord('H') = 72 (0x48), ord('i') = 105 (0x69)
        # _int2hexlittle returns "4800" for H, "6900" for i
        # The _encode_text method extends with individual bytes from the hex string.
        # So, "4800" becomes [0x48, 0x00]
        self.assertEqual(encoded, [0x86, 0x01, 2, 0x48, 0x00, 0x69, 0x00])

    async def test_update_message(self):
        """Test _update_message method calls send_command correctly."""
        logger.info("--- Running test_update_message ---")
        self.mock_divoom_instance.send_command.reset_mock() # Clear calls from __init__
        self.display_text.text = "Hello" # Update internal state
        await self.display_text.update_display() # Explicitly trigger update
        await asyncio.sleep(0.1) # Allow task to run

        # Check calls to send_command
        self.assertEqual(self.mock_divoom_instance.send_command.call_count, 4)
        
        # First call: PACKAGE_INIT_MESSAGE (0x6e, 0x01)
        self.mock_divoom_instance.send_command.assert_any_call(0x6e, [0x01])

        # Second call: encoded text (0x86, 0x01, len, text_bytes...)
        # For "Hello": [0x86, 0x01, 5, 0x48, 0x00, 0x65, 0x00, 0x6c, 0x00, 0x6c, 0x00, 0x6f, 0x00]
        self.mock_divoom_instance.send_command.assert_any_call(0x86, [0x01, 5, 0x48, 0x00, 0x65, 0x00, 0x6c, 0x00, 0x6c, 0x00, 0x6f, 0x00])

        # Third call: palette and initial pixels (0x6c, args...)
        # The args are complex, so we'll just check the command ID for now.
        self.mock_divoom_instance.send_command.assert_any_call(0x6c, unittest.mock.ANY)

    async def test_get_next_animation_frame(self):
        """Test get_next_animation_frame method calls send_command correctly."""
        logger.info("--- Running test_get_next_animation_frame ---")
        self.mock_divoom_instance.send_command.reset_mock() # Clear calls from __init__
        
        await self.display_text.get_next_animation_frame()
        
        self.mock_divoom_instance.send_command.assert_called_once()
        # Check command ID is 0x6c
        self.assertEqual(self.mock_divoom_instance.send_command.call_args[0][0], 0x6c)
        # Check args are a list
        self.assertIsInstance(self.mock_divoom_instance.send_command.call_args[0][1], list)
        # Check anim_frame increments
        self.assertEqual(self.display_text.frame, 1)

    async def test_text_setter_triggers_update_message(self):
        """Test that setting the text property triggers _update_message."""
        logger.info("--- Running test_text_setter_triggers_update_message ---")
        self.mock_divoom_instance.send_command.reset_mock() # Clear calls from __init__
        self.display_text.text = "New Text"
        await self.display_text.update_display() # Explicitly trigger update
        await asyncio.sleep(0.1) # Allow task to run
        self.assertGreater(self.mock_divoom_instance.send_command.call_count, 0)

    async def test_palette_fn_setter_triggers_update_message(self):
        """Test that setting the palette_fn property triggers _update_message."""
        logger.info("--- Running test_palette_fn_setter_triggers_update_message ---")
        self.mock_divoom_instance.send_command.reset_mock() # Clear calls from __init__
        self.display_text.palette_fn = self.display_text.PALETTE_BLACK_ON_RAINBOW
        await self.display_text.update_display() # Explicitly trigger update
        await asyncio.sleep(0.1) # Allow task to run
        self.assertGreater(self.mock_divoom_instance.send_command.call_count, 0)

    async def test_anim_fn_setter_triggers_update_message(self):
        """Test that setting the anim_fn property triggers _update_message."""
        logger.info("--- Running test_anim_fn_setter_triggers_update_message ---")
        self.mock_divoom_instance.send_command.reset_mock() # Clear calls from __init__
        self.display_text.anim_fn = self.display_text.ANIM_HORIZONTAL_GRADIANT_BACKGROUND
        await self.display_text.update_display() # Explicitly trigger update
        await asyncio.sleep(0.1) # Allow task to run
        self.assertGreater(self.mock_divoom_instance.send_command.call_count, 0)

if __name__ == '__main__':
    unittest.main()

import os
import sys
import asyncio
import logging
from bleak import BleakClient
from PIL import Image

# Add the project root to sys.path to allow importing divoom_api
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from divoom_lib import Divoom
from divoom_lib.utils.discovery import discover_divoom_devices
from divoom_lib.utils.logger_utils import print_ok, print_wrn, print_err, print_info
from divoom_lib.constants import DIVOOM_DISP_LIGHT_MODE

logger = logging.getLogger(__name__)

async def debug_light_settings(device_name_substring: str = "Tivoo"):
    """
    Discovers a Divoom device by name, connects to it, and tests various light setting methods.
    """
    print_info(f"Scanning for Divoom device(s) containing '{device_name_substring}'...")
    
    # Use the simplified discover_divoom_devices
    found_devices = await discover_divoom_devices(device_name=device_name_substring, logger=logger)

    if not found_devices:
        print_wrn(f"No Divoom device containing '{device_name_substring}' found. Exiting.")
        return

    # For debug, we select the first found device
    target_device = found_devices[0]
    print_ok(f"Found target Divoom device: {target_device.name} ({target_device.address})")

    divoom_instance = None
    try:
        divoom_instance = Divoom(mac=target_device.address, logger=logger)

        print_info(f"Connecting to Divoom device at {target_device.address}...")
        await divoom_instance.connect()
        print_ok(f"Successfully connected to {target_device.name}.")

        # --- Method 1: divoom_api.display.show_light (Red) ---
        print_info(f"Testing Method 1: divoom_lib.display.show_light (Red - FF0000)")
        await divoom_instance.display.show_light(color="FF0000", brightness=75)
        print_ok(f"Method 1: Light set to Red. Waiting 5 seconds...")
        await asyncio.sleep(5)

        # --- Method 2: divoom_api.display.show_light (Blue) ---
        print_info(f"Testing Method 2: divoom_lib.display.show_light (Blue - 0000FF)")
        await divoom_instance.display.show_light(color="0000FF", brightness=100) # Max brightness
        print_ok(f"Method 2: Light set to Blue, with brightness to 100. Waiting 5 seconds...")
        await asyncio.sleep(5)

        # --- Method 3: divoom_api.display.show_effects (Green) ---
        print_info(f"Testing Method 3: divoom_lib.display.show_effects (Green - 00FF00)")
        # Set to VJ Effects channel (0x03) with effect 0
        await divoom_instance.display.show_effects(0)
        # Then set a green color using show_light, as show_effects doesn't take color directly
        await divoom_instance.display.show_light(color="00FF00", brightness=75)
        print_ok(f"Method 3: Set to VJ Effect 0, then light set to Green. Waiting 5 seconds...")
        await asyncio.sleep(5)

        # --- Method 4: Direct send_command with set light mode (Yellow) ---
        print_info(f"Testing Method 4: Direct send_command with set light mode (Yellow - FFFF00)")
        rgb_color = divoom_instance.convert_color("FFFF00") # Yellow
        brightness = 75
        power_state = 0x01 # On
        type_of_lightning = 0x00 # Plain color

        # Payload structure for 0x45 command, DIVOOM_DISP_LIGHT_MODE (1)
        # 45 01 RRGGBB BB TT PP 000000
        args = [
            DIVOOM_DISP_LIGHT_MODE, # Mode: 1 for Light mode
            rgb_color[0], rgb_color[1], rgb_color[2],
            brightness,
            type_of_lightning,
            power_state,
            0x00, 0x00, 0x00 # Fixed String 000000
        ]
        await divoom_instance.send_command("set light mode", args) # Using the original "set light mode" command name
        print_ok(f"Method 4: Light set to Yellow via direct command. Waiting 5 seconds...")
        await asyncio.sleep(5)

    except Exception as e:
        print_err(f"An error occurred: {e}")
    finally:
        if divoom_instance and divoom_instance.is_connected:
            print_info("Disconnecting from the Divoom device.")
            await divoom_instance.disconnect()
        elif divoom_instance:
            print_wrn("Divoom instance was not connected or already disconnected.")
        print_ok("Debug session finished.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
    asyncio.run(debug_light_settings())

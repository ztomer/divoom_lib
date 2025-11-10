import os
import sys
import asyncio
import logging

# Add the project root to sys.path to allow importing divoom_api
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from divoom_lib import Divoom
from divoom_lib.utils.discovery import discover_divoom_devices
from divoom_lib.utils.logger_utils import print_ok, print_wrn, print_err, print_info

# Configure logging to DEBUG level
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)

async def debug_light_command(color: str = "FF0000", brightness: int = 75):
    """
    Discovers the first Divoom device, connects to it, and sends a light command.
    """
    divoom_instance = None
    try:
        print_info("Scanning for Divoom devices...")
        
        # Discover the device
        devices = await discover_divoom_devices(logger=logger)

        if not devices:
            print_err("No Divoom devices found. Exiting.")
            return
        
        # Pick the first found device
        device = devices[0]

        print_ok(f"Found device '{device.name}' at MAC address: {device.address}.")

        # Initialize Divoom instance
        divoom_instance = Divoom(mac=device.address, logger=logger)

        print_info(f"Connecting to Divoom device at {device.address}...")
        await divoom_instance.connect()
        print_ok("Successfully connected to the Divoom device.")

        print_info(f"Setting light to color {color} with brightness {brightness}...")
        await divoom_instance.display.show_light(color=color, brightness=brightness, power=True)
        print_ok(f"Light command sent to {device.name}.")

        # Keep connection open for a short period to observe any immediate effects or responses
        await asyncio.sleep(5)

    except Exception as e:
        print_err(f"An error occurred: {e}")
    finally:
        if divoom_instance and divoom_instance.is_connected:
            print_info("Disconnecting from the Divoom device.")
            await divoom_instance.disconnect()
        elif divoom_instance:
            print_wrn("Divoom instance was not connected or already disconnected.")

if __name__ == "__main__":
    asyncio.run(debug_light_command())

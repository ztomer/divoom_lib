import os
import sys
import asyncio
import logging
from bleak import BleakClient

# Add the project root to sys.path to allow importing divoom_api
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from divoom_lib import Divoom
from divoom_lib.utils.discovery import discover_divoom_devices
from divoom_lib.utils.logger_utils import print_ok, print_wrn, print_err, print_info
from divoom_lib.constants import CHANNEL_ID_CLOUD

logger = logging.getLogger(__name__)

async def rotate_to_cloud():
    """
    Discovers all Divoom devices and sets their channel to 'Cloud'.
    """
    print_info("Scanning for Divoom devices...")
    devices = await discover_divoom_devices(logger=logger)

    if not devices:
        print_wrn("No Divoom devices found.")
        return

    print_ok(f"Found {len(devices)} Divoom device(s).")

    for device in devices:
        print_info(f"Attempting to connect to {device.name} ({device.address})...")
        divoom_instance = None # Initialize to None
        try:
            # Instantiate Divoom with the discovered device's address
            divoom_instance = Divoom(mac=device.address, logger=logger)
            await divoom_instance.connect()
            print_ok(f"Successfully connected to {device.name}.")
            print_info(f"Setting {device.name} to Cloud channel...")
            await divoom_instance.system.set_channel(CHANNEL_ID_CLOUD)
            print_ok(f"Successfully set {device.name} to Cloud channel.")

        except Exception as e:
            print_err(f"Error processing device {device.name} ({device.address}): {e}")
        finally:
            if divoom_instance and divoom_instance.is_connected:
                await divoom_instance.disconnect()
                print_info(f"Disconnected from {device.name}.")
            elif divoom_instance:
                print_wrn(f"Divoom instance for {device.name} was not connected or already disconnected.")
        print("-" * 30) # Separator for readability

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:%(name)s:%(message)s')
    asyncio.run(rotate_to_cloud())

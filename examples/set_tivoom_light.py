import os
import sys
import asyncio
import logging

# Add the project root to sys.path to allow importing divoom_api
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from divoom_api.divoom_protocol import Divoom
from divoom_api.utils.discovery import discover_divoom_devices, discover_characteristics, discover_device_and_characteristics

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def set_tivoom_light(device_name: str = "Tivoom", color: str = "FF0000", brightness: int = 50, duration_seconds: int = 60):
    """
    Discovers a Divoom device by name, connects to it, sets a light mode,
    and keeps it there for a specified duration.
    """
    divoom_device = None
    try:
        logger.info(f"Attempting to discover Divoom device '{device_name}'...")
        
        # Discover the device and its characteristics
        mac_address, write_uuid, notify_uuid, read_uuid = \
            await discover_device_and_characteristics(device_name, logger)

        if not mac_address:
            logger.error(f"Failed to find Divoom device named '{device_name}'. Exiting.")
            return

        logger.info(f"Found device '{device_name}' at MAC address: {mac_address}.")

        # Initialize Divoom instance
        divoom_device = Divoom(
            mac=mac_address,
            logger=logger,
            write_characteristic_uuid=write_uuid,
            notify_characteristic_uuid=notify_uuid,
            read_characteristic_uuid=read_uuid
        )

        logger.info(f"Connecting to Divoom device at {mac_address}...")
        await divoom_device.connect()
        logger.info("Successfully connected to the Divoom device.")

        logger.info(f"Setting light to color {color} with brightness {brightness}...")
        await divoom_device.display.show_light(color=color, brightness=brightness, power=True)
        logger.info(f"Light set. Keeping it for {duration_seconds} seconds.")

        await asyncio.sleep(duration_seconds)

    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        if divoom_device and divoom_device.client and divoom_device.client.is_connected:
            logger.info("Disconnecting from the Divoom device.")
            await divoom_device.disconnect()
        elif divoom_device:
            logger.info("Divoom device was not connected or already disconnected.")

if __name__ == "__main__":
    # You can change the device name, color, brightness, and duration here
    asyncio.run(set_tivoom_light(device_name="Tivoom", color="0000FF", brightness=75, duration_seconds=30))

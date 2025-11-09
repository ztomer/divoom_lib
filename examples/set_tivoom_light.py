import os
import sys
import asyncio
import logging

# Add the project root to sys.path to allow importing divoom_api
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


from divoom_lib.divoom_protocol import Divoom
from divoom_lib.utils.discovery import discover_divoom_devices


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def set_tivoom_light(device_name: str = "Tivoo", color: str = "FF0000", brightness: int = 50, duration_seconds: int = 60):
    """
    Discovers a Divoom device by name, connects to it, sets a light mode,
    and keeps it there for a specified duration.
    """
    divoom_instance = None
    try:
        logger.info(f"Attempting to discover Divoom device '{device_name}'...")

        # Discover the device and its characteristics
        # discover_divoom_devices now returns a list of (BLEDevice, write_uuid, notify_uuid, read_uuid)
        found_devices = await discover_divoom_devices(device_name_substring=device_name, logger=logger)

        if not found_devices:
            logger.error(
                f"Failed to find Divoom device containing '{device_name}'. Exiting.")
            return

        # For set_tivoom_light, we expect to find only one device matching the name, or pick the first one
        device, write_uuid, notify_uuid, read_uuid = found_devices[0]

        logger.info(
            f"Found device '{device.name}' at MAC address: {device.address}.")

        # Initialize Divoom instance
        divoom_instance = Divoom(
            mac=device.address,
            logger=logger,
            write_characteristic_uuid=write_uuid,
            notify_characteristic_uuid=notify_uuid,
            read_characteristic_uuid=read_uuid
        )

        logger.info(f"Connecting to Divoom device at {device.address}...")
        await divoom_instance.connect()
        logger.info("Successfully connected to the Divoom device.")

        logger.info(
            f"Setting light to color {color} with brightness {brightness}...")
        await divoom_instance.display.show_light(color=color, brightness=brightness, power=True)
        logger.info(f"Light set. Keeping it for {duration_seconds} seconds.")

        await asyncio.sleep(duration_seconds)

    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        if divoom_instance and divoom_instance.is_connected:
            logger.info("Disconnecting from the Divoom device.")
            await divoom_instance.disconnect()
        elif divoom_instance:
            logger.info(
                "Divoom device was not connected or already disconnected.")

if __name__ == "__main__":
    # You can change the device name, color, brightness, and duration here
    asyncio.run(set_tivoom_light(device_name="Tivoo",
                color="0000FF", brightness=75, duration_seconds=30))

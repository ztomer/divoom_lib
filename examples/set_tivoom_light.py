import os
import sys
import asyncio
import logging
import argparse

# Add the project root to sys.path to allow importing divoom_api
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


from divoom_lib.divoom import Divoom
from divoom_lib.utils.discovery import discover_device


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def set_tivoom_light(device_name: str, color: str, brightness: int, duration_seconds: int):
    """
    Discovers a Divoom device by name, connects to it, sets a light mode,
    and keeps it there for a specified duration.
    """
    divoom_instance = None
    try:
        logger.info(f"Attempting to discover Divoom device '{device_name}'...")

        # Discover the device
        device, device_id = await discover_device(name_substring=device_name, logger=logger)

        if not device:
            logger.error(
                f"Failed to find Divoom device containing '{device_name}'. Exiting.")
            return

        logger.info(
            f"Found device '{device.name}' at MAC address: {device.address}.")

        # Create a DivoomConfig object with the device's MAC address
        from divoom_lib.models import DivoomConfig
        config = DivoomConfig(mac=device.address, logger=logger)
        divoom_instance = Divoom(config)

        logger.info(f"Connecting to Divoom device at {device.address}...")
        await divoom_instance.connect()
        logger.info("Successfully connected to the Divoom device.")

        logger.info(
            f"Setting light to color {color} with brightness {brightness}...")
        await divoom_instance.light.show_light(color=color, brightness=brightness, power=True)
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
    parser = argparse.ArgumentParser(description="Set the light on a Divoom device.")
    parser.add_argument("--device_name", default="Tivoo", help="Device name to connect to")
    parser.add_argument("--color", default="0000FF", help="Color in hex format (e.g., FF0000 for red)")
    parser.add_argument("--brightness", type=int, default=75, help="Brightness from 0 to 100")
    parser.add_argument("--duration", type=int, default=30, help="Duration in seconds to keep the light on")
    args = parser.parse_args()

    asyncio.run(set_tivoom_light(device_name=args.device_name, color=args.color, brightness=args.brightness, duration_seconds=args.duration))

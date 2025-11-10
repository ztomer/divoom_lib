import argparse
import asyncio
import logging
import os
import sys

# Add the project root to sys.path to allow importing divoom_api
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from divoom_lib import Divoom
from divoom_lib.utils.discovery import discover_device

# Configure logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("api_test")

async def main():
    """
    Connects to a Divoom device and sends a command to set the device's light to blue.
    """
    parser = argparse.ArgumentParser(description="Divoom API Test Script")
    parser.add_argument(
        "--address", help="BLE address / identifier of the target device")
    parser.add_argument("--name", default="Timoo",
                        help="Device name substring to search for (e.g., 'Timoo')")
    args = parser.parse_args()

    divoom = None
    try:
        if args.address:
            divoom = Divoom(mac=args.address, logger=logger)
        else:
            ble_device, device_id = await discover_device(name_substring=args.name, address=None)
            if not ble_device:
                logger.error(
                    f"No Bluetooth device found with name containing '{args.name}'. Exiting.")
                return
            divoom = Divoom(mac=device_id, logger=logger)

        await divoom.connect()
        logger.info(f"Successfully connected to {divoom.mac}!")

        # Get characteristics for probing
        write_chars = []
        notify_chars = []
        read_chars = []
        for service in divoom.client.services:
            for char in service.characteristics:
                if "write" in char.properties or "write_without_response" in char.properties:
                    write_chars.append(char)
                if "notify" in char.properties:
                    notify_chars.append(char)
                if "read" in char.properties:
                    read_chars.append(char)

        logger.info("Probing write characteristics to find a working one...")
        working_char_uuid = await divoom.probe_write_characteristics_and_try_channel_switch(
            write_chars, notify_chars, read_chars, {}, "", divoom.mac, []
        )

        if working_char_uuid:
            logger.info(f"Successfully identified working characteristic: {working_char_uuid}")
        else:
            logger.warning("Could not identify a working characteristic. Proceeding with default.")

        logger.info("Sending blue light command...")
        await divoom.display.show_light(color="0000FF", brightness=100)
        logger.info("Command sent successfully.")

    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        if divoom and divoom.is_connected:
            await divoom.disconnect()
            logger.info("Disconnected from Divoom device.")

if __name__ == "__main__":
    import traceback
    import sys

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        try:
            sys.exit(0)
        except SystemExit:
            pass
    except Exception as e:
        logger.error("Unhandled exception in api_test: printing traceback:")
        traceback.print_exc()
        logger.error(f"Exception: {e}")
        sys.exit(1)

import asyncio
import logging
import os
import sys

# Add the project root to sys.path to allow importing divoom_lib
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from divoom_lib import Divoom
from divoom_lib.utils.discovery import discover_device

# Configure logging
logging.basicConfig(level=logging.DEBUG, # Set to DEBUG to see all messages
                    format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("debug_channel_switch")

async def main():
    """
    Connects to a Divoom device and attempts to probe write characteristics and switch channels.
    """
    divoom = None
    try:
        # Discover device (using "Timoo" as default name substring)
        # For debugging, we'll use the known MAC address directly to bypass discovery issues.
        device_mac = "F90D2CC9-420E-65F9-9E06-F9554470FCED" # Replace with your Timoo's MAC address if different
        logger.info(f"Attempting to connect directly to MAC address: {device_mac}")
        
        divoom = Divoom(mac=device_mac, logger=logger)
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

        logger.info("Attempting to probe write characteristics and try channel switch...")
        # The probe_write_characteristics_and_try_channel_switch method is designed to find a working characteristic
        # and attempt channel switching as part of its fallback.
        # We pass empty cache and args for this debug script.
        working_char_uuid = await divoom.probe_write_characteristics_and_try_channel_switch(
            write_chars, notify_chars, read_chars, {}, "", device_mac, []
        )

        if working_char_uuid:
            logger.info(f"Successfully identified working characteristic: {working_char_uuid}")
        else:
            logger.warning("Could not identify a working characteristic or complete channel switch.")

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
    finally:
        if divoom and divoom.is_connected:
            await divoom.disconnect()
            logger.info("Disconnected from Divoom device.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Script interrupted by user")
    except Exception as e:
        logger.critical(f"Unhandled exception in debug_channel_switch: {e}", exc_info=True)
        sys.exit(1)

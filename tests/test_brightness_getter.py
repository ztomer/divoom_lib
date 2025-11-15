
import asyncio
import logging
import sys
import os
from bleak import BleakClient

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from divoom_lib.divoom_protocol import Divoom
from divoom_lib.utils.discovery import discover_device

# --- Configuration ---
DEVICE_NAME_SUBSTRING = "Timoo"
LOG_LEVEL = logging.INFO

# Setup basic logging
logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("brightness_getter_test")

# --- Notification Handling ---
notification_queue = asyncio.Queue()

def notification_handler(sender, data):
    """Handle incoming BLE notifications."""
    logger.info(f"Received notification from {sender}: {data.hex()}")
    notification_queue.put_nowait((sender, data))

async def get_brightness(divoom: Divoom):
    """Send the command to request the brightness level."""
    logger.info("Sending 'get brightness' command...")
    # This is based on community-documented commands. The command ID for getting settings is often 0x46.
    # The exact payload to get brightness might vary, but an empty payload often requests current state.
    await divoom.send_command(0x46, [])

async def main():
    """
    Main function to discover, connect, and test getting brightness from a Divoom device.
    """
    divoom = None
    try:
        # Discover the device
        ble_device, device_id = await discover_device(name_substring=DEVICE_NAME_SUBSTRING)
        if not ble_device:
            logger.error(f"No device found with name containing '{DEVICE_NAME_SUBSTRING}'.")
            return

        logger.info(f"Found device: {ble_device.name} ({ble_device.address})")

        async with BleakClient(ble_device) as client:
            divoom = Divoom(client=client, logger=logger)
            logger.info("Connected to Divoom device.")

            # Find all write and notify characteristics
            write_chars = [char for service in client.services for char in service.characteristics if "write" in char.properties]
            notify_chars = [char for service in client.services for char in service.characteristics if "notify" in char.properties]

            if not write_chars:
                logger.error("No writeable characteristics found.")
                return
            if not notify_chars:
                logger.error("No notification characteristics found.")
                return

            # Subscribe to all notify characteristics
            logger.info("Subscribing to all notification characteristics...")
            for char in notify_chars:
                try:
                    await client.start_notify(char.uuid, notification_handler)
                    logger.info(f"Subscribed to notifications on {char.uuid}")
                except Exception as e:
                    logger.error(f"Failed to subscribe to {char.uuid}: {e}")
            
            # Iterate through each write characteristic and framing protocol
            for write_char in write_chars:
                divoom.WRITE_CHARACTERISTIC_UUID = write_char.uuid
                logger.info(f"Testing with WRITE characteristic: {write_char.uuid}")

                # Test with SPP framing
                logger.info("Attempting with SPP framing (use_ios=False, escape=True)...")
                async with divoom._framing_context(use_ios=False, escape=True):
                    await get_brightness(divoom)
                    try:
                        sender, data = await asyncio.wait_for(notification_queue.get(), timeout=5.0)
                        logger.info(f"SUCCESS: Received response on {sender} for WRITE char {write_char.uuid} (SPP)")
                        logger.info(f"Data: {data.hex()}")
                        return  # Exit after first success
                    except asyncio.TimeoutError:
                        logger.warning("No notification received for SPP framing.")

                # Test with iOS-LE framing
                logger.info("Attempting with iOS-LE framing (use_ios=True, escape=False)...")
                async with divoom._framing_context(use_ios=True, escape=False):
                    await get_brightness(divoom)
                    try:
                        sender, data = await asyncio.wait_for(notification_queue.get(), timeout=5.0)
                        logger.info(f"SUCCESS: Received response on {sender} for WRITE char {write_char.uuid} (iOS-LE)")
                        logger.info(f"Data: {data.hex()}")
                        return  # Exit after first success
                    except asyncio.TimeoutError:
                        logger.warning("No notification received for iOS-LE framing.")

            logger.error("Failed to get a brightness notification from any characteristic combination.")

    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
    finally:
        if divoom and divoom.is_connected:
            await divoom.disconnect()
            logger.info("Disconnected from Divoom device.")

if __name__ == "__main__":
    asyncio.run(main())

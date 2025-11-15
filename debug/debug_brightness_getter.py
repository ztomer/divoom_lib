import asyncio
import logging
import os
import sys

# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bleak import BleakClient
from divoom_lib.utils.discovery import discover_device

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("debug_brightness_getter")

DEVICE_NAME = "Timoo"
WRITE_CHAR_UUID = "49535343-8841-43f4-a8d4-ecbe34729bb3"
NOTIFY_CHAR_UUID = "49535343-1e4d-4bd9-ba61-23c647249616"

# Command to get light mode (0x46)
# Payload format: 01 <len_L> <len_H> <cmd> <checksum_L> <checksum_H> 02
# Command: 0x46
# Payload: [0x46]
# Length of payload + checksum = 1 + 2 = 3
# Checksum of (length + payload) = sum([0x03, 0x00, 0x46]) = 0x49
# Message: 01 03 00 46 49 00 02
GET_LIGHT_MODE_COMMAND = bytes.fromhex("01030046490002")

def notification_handler(sender: int, data: bytearray):
    """Simple handler that prints the received data."""
    logger.info(f"NOTIFICATION RECEIVED from {sender}: {data.hex()}")

async def main():
    logger.info(f"Scanning for device named '{DEVICE_NAME}'...")
    ble_device, device_address = await discover_device(name_substring=DEVICE_NAME)

    if not ble_device:
        logger.error(f"Device '{DEVICE_NAME}' not found.")
        return

    logger.info(f"Found device: {device_address}")

    async with BleakClient(device_address) as client:
        if not client.is_connected:
            logger.error("Failed to connect.")
            return

        logger.info("Connected successfully.")

        try:
            # Subscribe to notifications
            logger.info(f"Subscribing to notifications on {NOTIFY_CHAR_UUID}...")
            await client.start_notify(NOTIFY_CHAR_UUID, notification_handler)
            logger.info("Subscribed successfully.")

            # Send the command
            logger.info(f"Writing command to {WRITE_CHAR_UUID}: {GET_LIGHT_MODE_COMMAND.hex()}")
            await client.write_gatt_char(WRITE_CHAR_UUID, GET_LIGHT_MODE_COMMAND, response=True)
            logger.info("Command sent.")

            # Wait to see if notifications arrive
            logger.info("Waiting for notifications for 10 seconds...")
            await asyncio.sleep(10)
            logger.info("Finished waiting.")

        except Exception as e:
            logger.error(f"An error occurred: {e}", exc_info=True)
        finally:
            logger.info("Stopping notifications.")
            await client.stop_notify(NOTIFY_CHAR_UUID)

if __name__ == "__main__":
    asyncio.run(main())

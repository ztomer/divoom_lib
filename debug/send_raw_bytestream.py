import asyncio
import logging
from bleak import BleakScanner, BleakClient
from bleak.exc import BleakError

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(levelname)s:%(asctime)s - %(name)s - %(message)s')
logger = logging.getLogger("send_raw_bytestream")

# --- Configuration ---
DEVICE_NAME_SUBSTRING = "Timoo"  # Substring to search for in device name
# Replace with your device's MAC address if you want to connect directly
DEVICE_MAC_ADDRESS = None
# Replace with the UUID of the characteristic you want to write to
WRITE_CHARACTERISTIC_UUID = "49535343-8841-43f4-a8d4-ecbe34729bb3"
# Replace with the raw bytestream you want to send (example: a simple command)
# This example sends a command to set the light to red (0x45 is set light mode, 0x01 is mode, FF0000 is red, 64 is brightness, 0001 are unknown bytes)
# This is just an example, you'll need to provide the correct bytestream for your purpose.
RAW_BYTESTREAM_TO_SEND = bytes([0x01, 0x0c, 0x00, 0x45, 0x01, 0xFF, 0x00, 0x00, 0x64, 0x00, 0x01, 0x53, 0x00, 0x02]) # Example: a full Divoom packet for red light

async def discover_device(name_substring: str) -> str | None:
    """Discovers a Bluetooth device by name substring and returns its address."""
    logger.info(f"Scanning for Bluetooth devices searching for name containing '{name_substring}'...")
    devices = await BleakScanner.discover()
    for device in devices:
        if device.name and name_substring.lower() in device.name.lower():
            logger.info(f"Found device: {device.name} ({device.address})")
            return device.address
    logger.warning(f"No device found with name containing '{name_substring}'.")
    return None

async def main():
    mac_address = DEVICE_MAC_ADDRESS
    if not mac_address:
        mac_address = await discover_device(DEVICE_NAME_SUBSTRING)
        if not mac_address:
            logger.error("Could not find a suitable device to connect to. Exiting.")
            return

    logger.info(f"Attempting to connect to {mac_address}")
    async with BleakClient(mac_address) as client:
        if client.is_connected:
            logger.info(f"Connected to {mac_address}")

            # Optional: Discover services and characteristics for debugging
            # logger.info("Discovering services and characteristics...")
            # for service in client.services:
            #     logger.info(f"  Service: {service.uuid}")
            #     for char in service.characteristics:
            #         logger.info(f"    Characteristic: {char.uuid} (Properties: {char.properties})")

            if not WRITE_CHARACTERISTIC_UUID:
                logger.error("WRITE_CHARACTERISTIC_UUID is not set. Cannot send data.")
                return

            try:
                logger.info(f"Sending raw bytestream to {WRITE_CHARACTERISTIC_UUID}: {RAW_BYTESTREAM_TO_SEND.hex()}")
                # Send the raw bytestream. response=True is often needed for Divoom devices.
                await client.write_gatt_char(WRITE_CHARACTERISTIC_UUID, RAW_BYTESTREAM_TO_SEND, response=True)
                logger.info("Bytestream sent successfully.")
            except BleakError as e:
                logger.error(f"Failed to send bytestream: {e}")
            except Exception as e:
                logger.error(f"An unexpected error occurred: {e}")
        else:
            logger.error(f"Failed to connect to {mac_address}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Script interrupted by user.")
    except Exception as e:
        logger.critical(f"Unhandled exception: {e}", exc_info=True)

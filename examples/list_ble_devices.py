import asyncio
import logging
from bleak import BleakScanner

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def list_ble_devices():
    """
    Scans for all discoverable Bluetooth Low Energy devices and prints their names and addresses.
    """
    logger.info("Scanning for all discoverable BLE devices (this may take a few seconds)...")
    devices = await BleakScanner.discover()

    if not devices:
        logger.info("No BLE devices found.")
        return

    logger.info("\n--- Discovered BLE Devices ---")
    for device in devices:
        logger.info(f"  Name: {device.name if device.name else 'N/A'}, Address: {device.address}")
    logger.info("------------------------------")
    logger.info("Please note the exact name of your Divoom device from the list above.")

if __name__ == "__main__":
    asyncio.run(list_ble_devices())

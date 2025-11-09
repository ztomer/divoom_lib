import os
import sys
import asyncio
import logging

# Add the project root to sys.path to allow importing divoom_api
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from divoom_lib.utils.discovery import discover_divoom_devices
from divoom_lib.utils.logger_utils import print_ok, print_wrn

logger = logging.getLogger(__name__)

async def main():
    """Main function to test the Divoom device discovery."""
    devices = await discover_divoom_devices(device_name_substring="light", logger=logger)
    if devices:
        print_ok("Found the following Divoom devices:")
        for ble_device, _, _, _ in devices:
            print(f"  - {ble_device.name} ({ble_device.address})")
    else:
        print_wrn("No Divoom devices found.")

if __name__ == "__main__":
    asyncio.run(main())

import os
import sys
import asyncio
import logging
import argparse

# Add the project root to sys.path to allow importing divoom_api
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from divoom_lib.utils.discovery import discover_device
from divoom_lib.utils.logger_utils import print_ok, print_wrn

logger = logging.getLogger(__name__)

async def main():
    """Main function to test the Divoom device discovery."""
    parser = argparse.ArgumentParser(description="Divoom Device Discovery Script")
    parser.add_argument("--name", default="Timoo",
                        help="Device name substring to search for (e.g., 'Timoo')")
    args = parser.parse_args()

    ble_device, device_id = await discover_device(name_substring=args.name, address=None)
    if ble_device:
        print_ok(f"Found Divoom device: {ble_device.name} ({device_id})")
    else:
        print_wrn(f"No Divoom device found with name containing '{args.name}'.")

if __name__ == "__main__":
    asyncio.run(main())

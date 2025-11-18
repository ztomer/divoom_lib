import asyncio
import logging
import argparse
from divoom_lib.divoom import Divoom
from divoom_lib.utils.discovery import discover_device
from divoom_lib.utils.logger_utils import print_info, print_wrn, print_err, print_ok

async def main():
    """Main function to test the Divoom device discovery and connection."""
    parser = argparse.ArgumentParser(description="Divoom Control Script")
    parser.add_argument("--device_name", default="Timoo-light-4", help="Device name to connect to")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    device, device_id = await discover_device(name_substring=args.device_name, logger=logger)
    if device:
        print_ok(f"Found Divoom device: {device.name} ({device.address})")

        # Create a DivoomConfig object with the device's MAC address
        from divoom_lib.models import DivoomConfig
        config = DivoomConfig(mac=device.address, logger=logger)
        divoom_device = Divoom(config)

        try:
            await divoom_device.connect()
            print_ok(f"Successfully connected to {device.name} ({device.address}).")

            print_info("Setting brightness to 100...")
            await divoom_device.device.set_brightness(100)
            print_ok("Brightness set to 100.")

        except Exception as e:
            print_err(f"Error communicating with {device.name} ({device.address}): {e}")
        finally:
            if divoom_device.is_connected:
                await divoom_device.disconnect()
                print_info(f"Disconnected from {device.name} ({device.address}).")
    else:
        print_wrn(f"No Divoom device found with name containing '{args.device_name}'.")

if __name__ == "__main__":
    asyncio.run(main())

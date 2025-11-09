import asyncio
import logging
from divoom_lib.divoom_protocol import Divoom
from divoom_lib.utils.discovery import discover_divoom_devices
from divoom_lib.utils.logger_utils import print_info, print_wrn, print_err, print_ok

async def main():
    """Main function to test the Divoom device discovery and connection."""
    devices = await discover_divoom_devices("Divoom", logging.getLogger(__name__)) # Pass a logger instance
    if devices:
        print_ok("Found the following Divoom devices:")
        for device in devices:
            print(f"  - {device.name} ({device.address})")

        timoo_device = None
        for d in devices:
            if "Timoo-light-4" in d.name:
                timoo_device = d
                break

        if timoo_device:
            print_info(
                f"Attempting to connect to {timoo_device.name} ({timoo_device.address})...")

            divoom_device = Divoom(mac=timoo_device.address)

            try:
                await divoom_device.connect()
                print_ok(
                    f"Successfully connected to {timoo_device.name} ({timoo_device.address}).")

                print_info("Setting hot pick channel...")
                await divoom_device.display.show_clock(hot=True) # Corrected call
                print_ok("Hot pick channel set.")

            except Exception as e:
                print_err(
                    f"Error communicating with {timoo_device.name} ({timoo_device.address}): {e}")
            finally:
                await divoom_device.disconnect()
                print_info(f"Disconnected from {timoo_device.name} ({timoo_device.address}).")
        else:
            print_wrn("Timoo-light-4 device not found.")


    else:
        print_wrn("No Divoom devices found.")

if __name__ == "__main__":
    asyncio.run(main())

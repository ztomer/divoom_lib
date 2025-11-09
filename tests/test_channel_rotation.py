import asyncio
import logging
from divoom_api.divoom_protocol import Divoom
from divoom_api.utils.discovery import discover_divoom_devices

def print_info(message):
    """Prints an informational message."""
    print(f"[ ==> ] {message}")

def print_wrn(message):
    """Prints a warning message."""
    print(f"[ Wrn ] {message}")

def print_err(message):
    """Prints an error message."""
    print(f"[ Err ] {message}")

def print_ok(message):
    """Prints a success message."""
    print(f"[ Ok  ] {message}")

async def test_channel_rotation():
    """
    Test script to discover a Divoom device and rotate through various display channels.
    """
    device_name_to_find = "Timoo-light-4" # Or "Divoom" if you want to find any Divoom device

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(levelname)s:%(name)s:%(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    print_info(f"Scanning for Divoom device '{device_name_to_find}'...")
    devices = await discover_divoom_devices(device_name_substring=device_name_to_find, logger=logger, single_device_name=device_name_to_find)

    if not devices:
        print_wrn(f"No Divoom device named '{device_name_to_find}' found. Exiting test.")
        return

    target_device = devices # discover_divoom_devices returns a single device if single_device_name is used
    print_ok(f"Found Divoom device: {target_device.name} ({target_device.address})")

    divoom_device = Divoom(mac=target_device.address, logger=logger)

    try:
        print_info(f"Connecting to {target_device.name} ({target_device.address})...")
        await divoom_device.connect()
        print_ok(f"Successfully connected to {target_device.name}.")

        print_info("Starting channel rotation test...")

        # Rotate through various display channels
        print_info("Showing Clock (Hot Pick)...")
        await divoom_device.display.show_clock(hot=True)
        await asyncio.sleep(5)

        print_info("Showing Design (e.g., design number 1)...")
        await divoom_device.display.show_design(number=1)
        await asyncio.sleep(5)

        print_info("Showing Effects (e.g., effect number 1)...")
        await divoom_device.display.show_effects(number=1)
        await asyncio.sleep(5)

        print_info("Showing Light (Red, Brightness 50%)...")
        await divoom_device.display.show_light(color="FF0000", brightness=50)
        await asyncio.sleep(5)

        print_info("Showing Visualization (e.g., visualization number 1)...")
        await divoom_device.display.show_visualization(number=1, color1="00FF00", color2="0000FF")
        await asyncio.sleep(5)

        print_ok("Channel rotation test completed.")

    except Exception as e:
        print_err(f"An error occurred during channel rotation test: {e}")
    finally:
        if divoom_device.client and divoom_device.client.is_connected:
            print_info("Disconnecting from device...")
            await divoom_device.disconnect()
            print_ok("Disconnected.")

if __name__ == "__main__":
    asyncio.run(test_channel_rotation())

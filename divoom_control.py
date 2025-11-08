import asyncio
import logging
from bleak import BleakScanner
from divoom_protocol import Divoom

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


async def discover_divoom_devices():
    """Scans for Bluetooth devices and returns a list of Divoom devices."""
    print_info("Scanning for Divoom devices...")
    devices = await BleakScanner.discover()
    divoom_devices = []
    divoom_keywords = ["Timoo", "Tivoo", "Pixoo", "Ditoo"]
    for device in devices:
        if device.name and any(keyword in device.name for keyword in divoom_keywords):
            divoom_devices.append(device)
    return divoom_devices


async def main():
    """Main function to test the Divoom device discovery and connection."""
    devices = await discover_divoom_devices()
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

            divoom_device = Divoom(mac=timoo_device.address, gatt_characteristic_uuid="00001101-0000-1000-8000-00805f9b34fb")

            try:
                await divoom_device.connect()
                print_ok(
                    f"Successfully connected to {timoo_device.name} ({timoo_device.address}).")

                print_info("Setting hot pick channel...")
                await divoom_device.show_clock(hot=True)
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

import asyncio
import logging
from bleak import BleakScanner
from divoom_protocol import DivoomBluetoothProtocol

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

        # Test connection to the first device found
        device = devices[0]
        print_info(
            f"Attempting to connect to {device.name} ({device.address})...")

        # Instantiate the new protocol class
        divoom_device = DivoomBluetoothProtocol(mac=device.address, gatt_characteristic_uuid="00001101-0000-1000-8000-00805f9b34fb")

        try:
            await divoom_device.connect()
            print_ok(
                f"Successfully connected to {device.name} ({device.address}).")

            # Example: Set brightness to 50
            print_info("Setting brightness to 50...")
            await divoom_device.send_brightness(50)
            print_ok("Brightness set to 50.")

            # Example: Turn off the device
            print_info("Turning off the device...")
            await divoom_device.send_off()
            print_ok("Device turned off.")

        except Exception as e:
            print_err(
                f"Error communicating with {device.name} ({device.address}): {e}")
        finally:
            await divoom_device.disconnect()
            print_info(f"Disconnected from {device.name} ({device.address}).")
    else:
        print_wrn("No Divoom devices found.")

if __name__ == "__main__":
    asyncio.run(main())

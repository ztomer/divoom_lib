import os
import sys
import asyncio
from bleak import BleakScanner, BleakClient

# Add the project root to sys.path to allow importing divoom_api
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def print_info(message):
    """Prints an informational message."""
    print(f"[ ==> ] {message}")

def print_ok(message):
    """Prints a success message."""
    print(f"[ Ok  ] {message}")

async def discover_divoom_characteristics():
    print_info("Scanning for Divoom devices...")
    devices = await BleakScanner.discover()
    
    divoom_devices = []
    divoom_keywords = ["Timoo", "Tivoo", "Pixoo", "Ditoo"]
    for device in devices:
        if device.name and any(keyword in device.name for keyword in divoom_keywords):
            divoom_devices.append(device)
            print_ok(f"Found Divoom device: {device.name} ({device.address})")

    if not divoom_devices:
        print_info("No Divoom devices found.")
        return

    # For simplicity, connect to the first Divoom device found
    selected_device = divoom_devices[0]
    print_info(f"\nConnecting to {selected_device.name} ({selected_device.address})...")

    async with BleakClient(selected_device.address) as client:
        if client.is_connected:
            print_ok(f"Connected to {selected_device.name}.")
            print_info("\nDiscovering services and characteristics:")
            for service in client.services:
                print_info(f"  Service: {service.uuid} ({service.description})")
                for char in service.characteristics:
                    print_info(f"    Characteristic: {char.uuid} (Properties: {char.properties})")
        else:
            print_info(f"Failed to connect to {selected_device.name}.")

if __name__ == "__main__":
    asyncio.run(discover_divoom_characteristics())

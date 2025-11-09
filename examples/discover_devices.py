import asyncio
from divoom_control import discover_divoom_devices, print_ok, print_wrn

async def main():
    """Main function to test the Divoom device discovery."""
    devices = await discover_divoom_devices()
    if devices:
        print_ok("Found the following Divoom devices:")
        for device in devices:
            print(f"  - {device.name} ({device.address})")
    else:
        print_wrn("No Divoom devices found.")

if __name__ == "__main__":
    asyncio.run(main())

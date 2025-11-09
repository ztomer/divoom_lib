import argparse
import asyncio
import json
import os
from pathlib import Path
import logging
import datetime
from bleak import BleakScanner
from bleak.exc import BleakError
from bleak import BleakClient

from divoom_api.divoom_protocol import Divoom
from divoom_api.utils.discovery import discover_characteristics

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("api_test")

DEFAULT_CACHE_DIR = os.path.join(
    os.path.expanduser("~"), ".divoom-control", "cache")

def ensure_cache_dir(cache_dir: str) -> None:
    Path(cache_dir).mkdir(parents=True, exist_ok=True)

def device_cache_path(cache_dir: str, device_id: str) -> str:
    safe_id = device_id.replace(':', '_')
    return os.path.join(cache_dir, f"{safe_id}.json")

def load_device_cache(cache_dir: str, device_id: str) -> dict | None:
    p = device_cache_path(cache_dir, device_id)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to load device cache from {p}: {e}")
        return None

def save_device_cache(cache_dir: str, device_id: str, data: dict) -> None:
    ensure_cache_dir(cache_dir)
    p = device_cache_path(cache_dir, device_id)
    try:
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        logger.info(f"Saved device cache to {p}")
    except OSError as e:
        logger.error(f"Failed to save device cache to {p}: {e}")

async def main():
    parser = argparse.ArgumentParser(description="Divoom API Test Script")
    parser.add_argument("--address", help="BLE address / identifier of the target device")
    parser.add_argument("--name", default="Timoo", help="Device name substring to search for (e.g., 'Timoo')")
    parser.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR, help="Directory to store per-device cache files")
    args = parser.parse_args()

    ensure_cache_dir(args.cache_dir)

    ble_device = None
    device_id = None

    if not args.address:
        logger.info(f"Scanning for Bluetooth devices searching for name containing '{args.name}'...")
        devices = await BleakScanner.discover()
        found = None
        for d in devices:
            if d.name and args.name.lower() in d.name.lower():
                found = d
                break
        if not found:
            logger.error(f"No Bluetooth device found with name containing '{args.name}'. Exiting.")
            return
        logger.info(f"Found device: {found.name} ({found.address}) — using this device.")
        ble_device = found
    else:
        logger.info(f"Resolving address {args.address} to BLEDevice (short scan)...")
        devices = await BleakScanner.discover(timeout=3.0)
        resolved = None
        for d in devices:
            if d.address == args.address or (d.name and args.address.lower() in d.name.lower()):
                resolved = d
                break
        if resolved:
            logger.info(f"Resolved address to BLEDevice: {resolved.name} ({resolved.address})")
            ble_device = resolved
        else:
            logger.warning("Could not resolve address to BLEDevice quickly; will attempt connect using raw address string.")
            ble_device = args.address

    if hasattr(ble_device, "address"):
        device_id = ble_device.address
    else:
        device_id = ble_device
    
    args.address = device_id # Ensure args.address is the stable device_id

    cache = load_device_cache(args.cache_dir, device_id)

    # Initialize Divoom instance. We'll set characteristics after connection.
    # Use DivoomBase for now, as it's lighter and we're manually managing client.
    div = Divoom(mac=args.address) # Use Divoom, as it has the full protocol logic

    # Establish a low-level BleakClient first
    client = BleakClient(ble_device)
    try:
        await client.connect()
        logger.info(f"Successfully connected to {args.address}!")
    except (OSError, RuntimeError, asyncio.TimeoutError) as e:
        logger.error(f"Failed to connect to {args.address}: {e}")
        return

    # Discover services/characteristics and set them on the Divoom instance
    write_chars, notify_chars, read_chars = await discover_characteristics(client)

    # Use the known working characteristic from previous successful run
    # This is the characteristic that responded to the blue color payload
    chosen_write_uuid = "49535343-8841-43f4-a8d4-ecbe34729bb3"
    # The notify characteristic was 49535343-1e4d-4bd9-ba61-23c647249616 based on logs
    chosen_notify_uuid = "49535343-1e4d-4bd9-ba61-23c647249616"

    # Set the client and characteristics on the Divoom instance
    div.client = client
    div.WRITE_CHARACTERISTIC_UUID = chosen_write_uuid
    div.NOTIFY_CHARACTERISTIC_UUID = chosen_notify_uuid
    div.READ_CHARACTERISTIC_UUID = chosen_notify_uuid # Fallback for read

    # Start notifications on the chosen notify characteristic
    try:
        await client.start_notify(div.NOTIFY_CHARACTERISTIC_UUID, div.notification_handler)
        logger.info(f"Started notify on {div.NOTIFY_CHARACTERISTIC_UUID}")
        await asyncio.sleep(1.0) # Give device a moment
    except (BleakError, OSError, RuntimeError) as e:
        logger.error(f"Failed to start notify on {div.NOTIFY_CHARACTERISTIC_UUID}: {e}")
        await client.disconnect()
        return

    # Set the protocol and escape preferences based on the successful run
    div.use_ios_le_protocol = True
    div.escapePayload = False # Based on iOS LE protocol not using escaping

    # Send the "night light with blue color" command
    # Command 0x45 (Light Mode), payload: [mode(1), R,G,B, brightness, effect_mode, on_off]
    # [0x01, 0x00, 0x00, 0xFF, 0x64, 0x00, 0x01] -> mode 1, blue, 100 brightness, effect 0, on
    mode = 0x01
    r, g, b = 0x00, 0x00, 0xFF # Blue
    brightness = 100
    effect_mode = 0x00
    power_state = 0x01
    args = [mode, r, g, b, brightness, effect_mode, power_state]

    logger.info(f"Sending blue light command (0x45) with args: {[hex(x) for x in args]}")
    try:
        response = await div.send_command_and_wait_for_response(0x45, args, timeout=5)
        if response:
            logger.info(f"Command sent successfully, response: {response}")
            # Save successful characteristic and protocol to cache
            save_device_cache(args.cache_dir, device_id, {
                "write_characteristic_uuid": chosen_write_uuid,
                "ack_characteristic_uuid": chosen_notify_uuid,
                "last_successful_use_ios_le": True,
                "escapePayload": False,
                "last_successful_payload": [f"{b:02x}" for b in args],
            })
        else:
            logger.warning("Command sent, but no response received within timeout.")
    except Exception as e:
        logger.error(f"Error sending command: {e}")

    await div.disconnect()
    logger.info("Disconnected from Divoom device.")


if __name__ == "__main__":
    import traceback
    import sys

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        try:
            sys.exit(0)
        except SystemExit:
            pass
    except Exception as e:
        logger.error("Unhandled exception in api_test: printing traceback:")
        traceback.print_exc()
        logger.error(f"Exception: {e}")
        sys.exit(1)
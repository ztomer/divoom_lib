import asyncio
import logging
from typing import List, Tuple, Optional, Union
from bleak import BleakScanner, BleakClient
from bleak.backends.device import BLEDevice

async def discover_divoom_devices(device_name_substring: str = "", logger: logging.Logger = logging.getLogger(__name__)) -> List[BLEDevice]:
    """
    Scans for Divoom devices whose name contains `device_name_substring` and returns a list of matching BLEDevice objects.
    """
    logger.info(f"Scanning for Divoom device(s) containing '{device_name_substring}'...")
    devices = await BleakScanner.discover()
    
    divoom_keywords = ["Ditoo", "Tivoo", "Pixoo", "Timoo", "Divoom"] # Add more keywords if needed
    
    found_divoom_devices = []
    for device in devices:
        # Check if device name contains any of the Divoom keywords
        is_divoom_device = False
        if device.name:
            for keyword in divoom_keywords:
                if keyword.lower() in device.name.lower():
                    is_divoom_device = True
                    break
        
        # If it's a Divoom device and matches the substring (if provided)
        if is_divoom_device and (not device_name_substring or device_name_substring.lower() in device.name.lower()):
            logger.info(f"Found Divoom device: {device.name} ({device.address})")
            found_divoom_devices.append(device)
    
    if not found_divoom_devices:
        logger.warning(f"No Divoom device containing '{device_name_substring}' found.")
        if not devices:
            logger.info("No Bluetooth devices were discovered at all.")
        else:
            logger.info("Discovered devices (no match found):")
            for device in devices:
                logger.info(f"  - {device.name} ({device.address})")
    return found_divoom_devices

async def discover_characteristics(mac_address: str, logger: logging.Logger) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Discovers and returns the characteristic UUIDs for write, notify, and read operations for a given MAC address.
    Prioritizes a specific write characteristic UUID if available.
    """
    logger.info(f"Discovering characteristics for device at {mac_address}...")
    write_uuid = None
    notify_uuid = None
    read_uuid = None

    temp_client = BleakClient(mac_address)
    try:
        await temp_client.connect()
        logger.info(f"Connected to {mac_address} for characteristic discovery.")
        await asyncio.sleep(0.1) # Add a small delay to allow services to be fully discovered
        for service in temp_client.services:
            for char in service.characteristics:
                if "write" in char.properties or "write-without-response" in char.properties:
                    # Prioritize the characteristic that also has 'notify' for writing
                    if char.uuid == "49535343-aca3-481c-91ec-d85e28a60318":
                        write_uuid = char.uuid
                    elif write_uuid is None: # Only assign if not already assigned to the preferred one
                        write_uuid = char.uuid
                if "notify" in char.properties:
                    notify_uuid = char.uuid
                if "read" in char.properties:
                    read_uuid = char.uuid
    except Exception as e:
        logger.error(f"Error during characteristic discovery for {mac_address}: {e}")
    finally:
        if temp_client.is_connected:
            await temp_client.disconnect()
            logger.info(f"Disconnected temporary client from {mac_address}.")
    
    if not all([write_uuid, notify_uuid, read_uuid]):
        logger.error("Could not discover all required characteristics.")
        return None, None, None
    
    return write_uuid, notify_uuid, read_uuid

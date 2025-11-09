import asyncio
import logging
from typing import List, Tuple, Optional, Union
from bleak import BleakScanner, BleakClient
from bleak.backends.device import BLEDevice

async def discover_divoom_devices(device_name_substring: str, logger: logging.Logger) -> List[BLEDevice]:
    """
    Scans for Divoom devices whose name contains `device_name_substring` and returns a list of matching devices.
    """
    logger.info(f"Scanning for Divoom device(s) containing '{device_name_substring}'...")
    devices = await BleakScanner.discover()
    
    matching_devices = []
    for device in devices:
        if device.name and device_name_substring.lower() in device.name.lower():
            logger.info(f"Found Divoom device: {device.name} ({device.address})")
            matching_devices.append(device)
    
    if not matching_devices:
        logger.warning(f"No Divoom device containing '{device_name_substring}' found.")
        if not devices:
            logger.info("No Bluetooth devices were discovered at all.")
        else:
            logger.info("Discovered devices (no match found):")
            for device in devices:
                logger.info(f"  - {device.name} ({device.address})")
    return matching_devices

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

async def discover_device_and_characteristics(device_name: str, logger: logging.Logger) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Discovers a single Divoom device by name and then its communication characteristics.
    Returns a tuple of (mac_address, write_uuid, notify_uuid, read_uuid).
    """
    logger.info(f"Attempting to discover Divoom device '{device_name}' and its characteristics...")
    
    device = await discover_divoom_devices(device_name_substring=device_name, logger=logger)
    
    if not device:
        logger.error(f"Failed to find Divoom device named '{device_name}'.")
        return None, None, None, None
    
    mac_address = device.address
    logger.info(f"Found device '{device.name}' at MAC address: {mac_address}. Discovering characteristics...")
    
    write_uuid, notify_uuid, read_uuid = await discover_characteristics(mac_address, logger)
    
    if not all([write_uuid, notify_uuid, read_uuid]):
        logger.error(f"Failed to discover all required characteristics for device '{device_name}'.")
        return mac_address, None, None, None
        
    logger.info(f"Successfully discovered characteristics for '{device_name}'.")
    return mac_address, write_uuid, notify_uuid, read_uuid

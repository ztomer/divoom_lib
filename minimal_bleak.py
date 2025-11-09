import asyncio
from bleak import BleakScanner, BleakClient
import logging

# Configure logging for bleak
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("bleak").setLevel(logging.DEBUG)
logging.getLogger("bleak.backends.corebluetooth").setLevel(
    logging.DEBUG)  # For macOS
logging.getLogger("bleak.backends.bluez").setLevel(logging.DEBUG)  # For Linux
logging.getLogger("bleak.backends.windows").setLevel(
    logging.DEBUG)  # For Windows

# Divoom protocol constants
START_BYTE = 0x01
END_BYTE = 0x02
# Identified working characteristic
WRITE_CHARACTERISTIC_UUID = "49535343-aca3-481c-91ec-d85e28a60318"

# Global flag for payload escaping
ENABLE_PAYLOAD_ESCAPING = True  # Set to True to enable escaping, False to disable

# Light Effect Types (from PROTOCOL.md - Set Light Effect 0x45, Mode 0x02)
LIGHT_EFFECT_TYPE_PLAIN_COLOR = 0x00
LIGHT_EFFECT_TYPE_FLASHING = 0x01
LIGHT_EFFECT_TYPE_RAINBOW = 0x02
LIGHT_EFFECT_TYPE_SCROLLING = 0x03
LIGHT_EFFECT_TYPE_CUSTOM = 0x04

def calculate_checksum(data_bytes: list) -> bytes:
    checksum_value = sum(data_bytes)
    return checksum_value.to_bytes(2, byteorder='little')

def escape_payload(payload: list) -> list:
    escaped_payload = []
    for byte in payload:
        if byte == 0x01:
            escaped_payload.extend([0x03, 0x04])
        elif byte == 0x02:
            escaped_payload.extend([0x03, 0x05])
        elif byte == 0x03:
            escaped_payload.extend([0x03, 0x06])
        else:
            escaped_payload.append(byte)
    return escaped_payload

def construct_packet(command_code: int, payload: list) -> bytes:
    full_payload = [command_code] + payload
    
    if ENABLE_PAYLOAD_ESCAPING:
        full_payload = escape_payload(full_payload)

    length_value = len(full_payload) + 2  # +2 for checksum bytes
    length_bytes = length_value.to_bytes(2, byteorder='little')

    checksum_data = list(length_bytes) + full_payload
    checksum = calculate_checksum(checksum_data)

    packet = bytes([START_BYTE]) + length_bytes + \
        bytes(full_payload) + checksum + bytes([END_BYTE])
    return packet

async def send_light_effect_command(client: BleakClient, effect_type: int, color: list, brightness: int, power_on: int):
    command_code = 0x45 # Command for Set Channel
    mode = 0x02 # Mode for Light Effect
    # Payload: [Mode, Type, R, G, B, Brightness, Power]
    payload = [mode, effect_type] + color + [brightness, power_on]
    packet_to_send = construct_packet(command_code, payload)
    
    print(f"Sending light effect packet (Type: {effect_type}, escaped: {ENABLE_PAYLOAD_ESCAPING}): {packet_to_send.hex()}")
    await client.write_gatt_char(WRITE_CHARACTERISTIC_UUID, packet_to_send, response=False)
    print(f"Light effect command (Type: {effect_type}) sent.")

async def send_brightness_command(client: BleakClient, brightness_level: int):
    command_code = 0x74 # Command for setting brightness
    payload = [brightness_level]
    packet_to_send = construct_packet(command_code, payload)

    print(f"Sending brightness packet (level {brightness_level}, escaped: {ENABLE_PAYLOAD_ESCAPING}): {packet_to_send.hex()}")
    await client.write_gatt_char(WRITE_CHARACTERISTIC_UUID, packet_to_send, response=False)
    print(f"Brightness command (level {brightness_level}) sent.")

async def find_and_connect_timoo():
    print("Scanning for Bluetooth devices...")
    devices = await BleakScanner.discover()
    
    timoo_device = None
    for device in devices:
        if device.name and "Timoo" in device.name:
            timoo_device = device
            print(f"Found Timoo device: {device.name} ({timoo_device.address})")
            break

    if timoo_device:
        print(f"Attempting to connect to {timoo_device.name} ({timoo_device.address})...")
        try:
            async with BleakClient(timoo_device.address) as client:
                if client.is_connected:
                    print(f"Successfully connected to {timoo_device.name}!")
                    
                    # Test different light effect types
                    # Plain Color (Red)
                    await send_light_effect_command(client, LIGHT_EFFECT_TYPE_PLAIN_COLOR, [0xFF, 0x00, 0x00], 0x32, 0x01)
                    await asyncio.sleep(2)

                    # Flashing (Green)
                    await send_light_effect_command(client, LIGHT_EFFECT_TYPE_FLASHING, [0x00, 0xFF, 0x00], 0x46, 0x01)
                    await asyncio.sleep(2)

                    # Rainbow (Blue - color might not be used for rainbow effect, but sending it anyway)
                    await send_light_effect_command(client, LIGHT_EFFECT_TYPE_RAINBOW, [0x00, 0x00, 0xFF], 0x64, 0x01)
                    await asyncio.sleep(2)

                    # Test brightness control
                    await send_brightness_command(client, 0x10) # Set brightness to a low level (e.g., 16)
                    await asyncio.sleep(2)
                    await send_brightness_command(client, 0x64) # Set brightness to max level (100)
                    await asyncio.sleep(5) 
                    print(f"Disconnected from {timoo_device.name}.")
                else:
                    print(f"Failed to connect to {timoo_device.name}.")
        except Exception as e:
            print(f"An error occurred during connection: {e}")
    else:
        print("No 'Timoo' device found.")

if __name__ == "__main__":
    asyncio.run(find_and_connect_timoo())
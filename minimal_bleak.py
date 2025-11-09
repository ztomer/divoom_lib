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

async def discover_write_characteristics(client: BleakClient) -> list:
    write_characteristics = []
    for service in client.services:
        for char in service.characteristics:
            if "write" in char.properties or "write_without_response" in char.properties:
                write_characteristics.append(char.uuid)
                print(f"Discovered writeable characteristic: {char.uuid} (Properties: {char.properties})")
    return write_characteristics

async def send_light_effect_command(client: BleakClient, write_characteristic_uuid: str, effect_type: int, color: list, brightness: int, power_on: int):
    command_code = 0x45 # Command for Set Channel
    mode = 0x02 # Mode for Light Effect
    # Payload: [Mode, Type, R, G, B, Brightness, Power]
    payload = [mode, effect_type] + color + [brightness, power_on]
    packet_to_send = construct_packet(command_code, payload)
    
    print(f"Sending light effect packet (Type: {effect_type}, escaped: {ENABLE_PAYLOAD_ESCAPING}) to {write_characteristic_uuid}: {packet_to_send.hex()}")
    await client.write_gatt_char(write_characteristic_uuid, packet_to_send, response=False)
    print(f"Light effect command (Type: {effect_type}) sent to {write_characteristic_uuid}.")

async def send_work_mode_command(client: BleakClient, write_characteristic_uuid: str, mode: int):
    command_code = 0x05 # Command for Set Play Mode (Work Mode)
    payload = [mode]
    packet_to_send = construct_packet(command_code, payload)

    print(f"Sending work mode packet (Mode: {mode}, escaped: {ENABLE_PAYLOAD_ESCAPING}) to {write_characteristic_uuid}: {packet_to_send.hex()}")
    await client.write_gatt_char(write_characteristic_uuid, packet_to_send, response=False)
    print(f"Work mode command (Mode: {mode}) sent to {write_characteristic_uuid}.")

async def send_poweron_channel_command(client: BleakClient, write_characteristic_uuid: str, channel: int):
    command_code = 0x8a # Command for Set Power On Channel
    payload = [channel]
    packet_to_send = construct_packet(command_code, payload)

    print(f"Sending poweron channel packet (Channel: {channel}, escaped: {ENABLE_PAYLOAD_ESCAPING}) to {write_characteristic_uuid}: {packet_to_send.hex()}")
    await client.write_gatt_char(write_characteristic_uuid, packet_to_send, response=False)
    print(f"Poweron channel command (Channel: {channel}) sent to {write_characteristic_uuid}.")

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

                    write_characteristics = await discover_write_characteristics(client)

                    if not write_characteristics:
                        print("No writeable characteristics found. Cannot send commands.")
                        return
                    
                    for char_uuid in write_characteristics:
                        print(f"\n--- Testing characteristic: {char_uuid} ---")
                        try:
                            # Try setting work mode to Divoom Show (0x09)
                            await send_work_mode_command(client, char_uuid, 0x09)
                            await asyncio.sleep(1)

                            # Try setting poweron channel to Light Effect (0x02)
                            await send_poweron_channel_command(client, char_uuid, 0x02)
                            await asyncio.sleep(1)

                            # Test different light effect types
                            # Plain Color (Red)
                            await send_light_effect_command(client, char_uuid, LIGHT_EFFECT_TYPE_PLAIN_COLOR, [0xFF, 0x00, 0x00], 0x32, 0x01)
                            await asyncio.sleep(1)

                            # Flashing (Green)
                            await send_light_effect_command(client, char_uuid, LIGHT_EFFECT_TYPE_FLASHING, [0x00, 0xFF, 0x00], 0x46, 0x01)
                            await asyncio.sleep(1)

                            # Rainbow (Blue - color might not be used for rainbow effect, but sending it anyway)
                            await send_light_effect_command(client, char_uuid, LIGHT_EFFECT_TYPE_RAINBOW, [0x00, 0x00, 0xFF], 0x64, 0x01)
                            await asyncio.sleep(2)
                        except Exception as write_e:
                            print(f"Error writing to {char_uuid}: {write_e}")
                    
                    print(f"Disconnected from {timoo_device.name}.")
                else:
                    print(f"Failed to connect to {timoo_device.name}.")
        except Exception as e:
            print(f"An error occurred during connection: {e}")
    else:
        print("No 'Timoo' device found.")

if __name__ == "__main__":
    asyncio.run(find_and_connect_timoo())

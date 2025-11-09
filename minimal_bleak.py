import asyncio
from bleak import BleakScanner, BleakClient
import logging

# Configure logging for bleak
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("bleak").setLevel(logging.DEBUG)
logging.getLogger("bleak.backends.corebluetooth").setLevel(logging.DEBUG) # For macOS
logging.getLogger("bleak.backends.bluez").setLevel(logging.DEBUG) # For Linux
logging.getLogger("bleak.backends.windows").setLevel(logging.DEBUG) # For Windows

# Divoom protocol constants
START_BYTE = 0x01
END_BYTE = 0x02
WRITE_CHARACTERISTIC_UUID = "49535343-1e4d-4bd9-ba61-23c647249616" # Trying another characteristic with write properties

def calculate_checksum(data_bytes: list) -> bytes:
    checksum_value = sum(data_bytes)
    return checksum_value.to_bytes(2, byteorder='little')

def construct_packet(command_code: int, payload: list) -> bytes:
    full_payload = [command_code] + payload
    length_value = len(full_payload) + 2  # +2 for checksum bytes
    length_bytes = length_value.to_bytes(2, byteorder='little')

    checksum_data = list(length_bytes) + full_payload
    checksum = calculate_checksum(checksum_data)

    packet = bytes([START_BYTE]) + length_bytes + bytes(full_payload) + checksum + bytes([END_BYTE])
    return packet

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
                    
                    # --- Bitbanging for Lightning Channel ---
                    # Command: 4501 RRGGBB BB TT PP 000000
                    # RRGGBB: FF0000 (Red)
                    # BB: 32 (50% brightness, 0-100 range, 0x32 hex)
                    # TT: 00 (PlainColor)
                    # PP: 01 (Power On)
                    
                    command_code = 0x45 # Command for setting light mode (0x45)
                    
                    # Payload for setting light mode:
                    # data[0]: Mode (0x01 for DIVOOM_DISP_LIGHT_MODE)
                    # data[1-3]: RGB color values (0xFF, 0x00, 0x00 for Red)
                    # data[4]: Brightness level (0x32 for 50%)
                    # data[5]: Light effect mode (0x00 for default/plain)
                    # data[6]: Light on/off switch (0x01 for On)
                    payload_for_45_command = [0x01, 0xFF, 0x00, 0x00, 0x32, 0x00, 0x01]
                    
                    # Construct the full Divoom packet
                    packet_to_send = construct_packet(command_code, payload_for_45_command)
                    
                    print(f"Sending packet: {packet_to_send.hex()}")
                    
                    # Assuming a common write characteristic UUID for Divoom devices
                    # This UUID might need to be discovered for specific devices if it's different
                    await client.write_gatt_char(WRITE_CHARACTERISTIC_UUID, packet_to_send)
                    print("Light mode command sent.")
                    
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
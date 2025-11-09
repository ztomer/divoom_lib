# divoom_api/base.py
import datetime
import itertools
import logging
import math
import os
import time
import asyncio
from bleak import BleakClient

from .constants import COMMANDS
from .utils.discovery import discover_characteristics, discover_device_and_characteristics


class DivoomBase:
    """Base class for Divoom Bluetooth communication."""

    # Identified as containing "SPP"
    SPP_CHARACTERISTIC_UUID = "49535343-6daa-4d02-abf6-19569aca69fe"
    WRITE_CHARACTERISTIC_UUID = None
    NOTIFY_CHARACTERISTIC_UUID = None
    READ_CHARACTERISTIC_UUID = None

    def __init__(self, mac=None, logger=None, write_characteristic_uuid=None, notify_characteristic_uuid=None, read_characteristic_uuid=None, spp_characteristic_uuid=None, escapePayload=False, use_ios_le_protocol=False, device_name=None):
        self.type = "Ditoo"  # Default to Ditoo
        self.screensize = 16
        self.chunksize = 200
        self.colorpalette = None
        self.mac = mac
        self.device_name = device_name # Store device name
        self.WRITE_CHARACTERISTIC_UUID = write_characteristic_uuid
        self.NOTIFY_CHARACTERISTIC_UUID = notify_characteristic_uuid
        self.READ_CHARACTERISTIC_UUID = read_characteristic_uuid
        self.SPP_CHARACTERISTIC_UUID = spp_characteristic_uuid if spp_characteristic_uuid else DivoomBase.SPP_CHARACTERISTIC_UUID
        self.escapePayload = escapePayload
        self.client = BleakClient(self.mac) if self.mac else None  # Initialize client internally only if mac is provided
        self.use_ios_le_protocol = use_ios_le_protocol if use_ios_le_protocol is not None else False
        self._response_event = asyncio.Event()
        self._response_data = None
        self._expected_response_command = None # New attribute to store the expected command ID
        self.message_buf = []

        if logger is None:
            logger = logging.getLogger(self.type)
            logger.setLevel(logging.DEBUG)
            # Add a StreamHandler if none exist to ensure output to console
            if not logger.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter('%(levelname)s:%(name)s:%(message)s')
                handler.setFormatter(formatter)
                logger.addHandler(handler)
        self.logger = logger

    async def connect(self):
        """Open a connection to the Divoom device using bleak."""
        if not self.mac and self.device_name:
            self.logger.info(f"MAC address not provided, attempting to discover device '{self.device_name}' and its characteristics.")
            mac_address, write_uuid, notify_uuid, read_uuid = \
                await discover_device_and_characteristics(self.device_name, self.logger)
            if not mac_address:
                self.logger.error(f"Failed to discover device '{self.device_name}' or its characteristics.")
                raise Exception(f"Failed to discover device '{self.device_name}' or its characteristics.")
            self.mac = mac_address
            self.WRITE_CHARACTERISTIC_UUID = write_uuid
            self.NOTIFY_CHARACTERISTIC_UUID = notify_uuid
            self.READ_CHARACTERISTIC_UUID = read_uuid
        
        if not self.mac:
            self.logger.error("No MAC address provided or discovered. Cannot connect.")
            raise Exception("No MAC address provided or discovered. Cannot connect.")

        if not self.client or self.client.address != self.mac:
            self.client = BleakClient(self.mac)

        if not self.client.is_connected:
            try:
                await self.client.connect()
                self.logger.info(f"Connected to Divoom device at {self.mac}")
            except Exception as e:
                self.logger.error(f"Failed to connect to {self.mac}: {e}")
                raise

        if not all([self.WRITE_CHARACTERISTIC_UUID, self.NOTIFY_CHARACTERISTIC_UUID, self.READ_CHARACTERISTIC_UUID]):
            self.logger.info("Characteristic UUIDs not fully set, attempting to discover them.")
            write_uuid, notify_uuid, read_uuid = \
                await discover_characteristics(self.mac, self.logger)
            
            if not all([write_uuid, notify_uuid, read_uuid]):
                self.logger.error("Could not discover all required characteristics.")
                raise Exception("Could not discover all required characteristics.")
            self.WRITE_CHARACTERISTIC_UUID = write_uuid
            self.NOTIFY_CHARACTERISTIC_UUID = notify_uuid
            self.READ_CHARACTERISTIC_UUID = read_uuid

        # Enable notifications for all characteristics that support it
        for service in self.client.services:
            for characteristic in service.characteristics:
                if "notify" in characteristic.properties:
                    await self.client.start_notify(characteristic.uuid, self.notification_handler)
                    self.logger.info(
                        f"Enabled notifications for {characteristic.uuid}")
        await asyncio.sleep(1.0)

    async def disconnect(self):
        """Closes the connection to the Divoom device."""
        if self.client and self.client.is_connected:
            try:
                # Disable notifications for all characteristics that support it
                for service in self.client.services:
                    for characteristic in service.characteristics:
                        if "notify" in characteristic.properties:
                            await self.client.stop_notify(characteristic.uuid)
                            self.logger.info(
                                f"Disabled notifications for {characteristic.uuid}")
                await self.client.disconnect()
                self.logger.info(
                    f"Disconnected from Divoom device at {self.mac}")
            except Exception as e:
                self.logger.error(f"Error disconnecting from {self.mac}: {e}")

    def notification_handler(self, sender, data):
        """Handler for GATT notifications, attempting to parse Basic Protocol responses."""
        self.logger.debug("THIS IS MY NOTIFICATION HANDLER")
        self.logger.debug(f"ALL INCOMING NOTIFICATION DATA: {data.hex()}")
        self.logger.debug(f"Notification received from {sender}: {data.hex()}")
        self.message_buf.append(data)  # Keep this for general debugging

        # For now, just log the raw data to see if anything is coming back
        self.logger.info(f"Raw notification data: {data.hex()}")

        if self.use_ios_le_protocol:
            # Attempt to parse iOS LE Protocol response: Header (4) + Data Length (2) + Command Identifier (1) + Packet Number (4) + Data + Checksum (2)
            if len(data) >= 13 and data[0:4] == bytes([0xFE, 0xEF, 0xAA, 0x55]):
                self.logger.info(f"iOS LE Protocol response found. Full data: {data.hex()}")

                data_length = int.from_bytes(data[4:6], byteorder='little')
                command_identifier = data[6]
                packet_number = int.from_bytes(data[7:11], byteorder='little')
                response_data = data[11:-2] # Data part is between Packet Number and Checksum
                checksum = int.from_bytes(data[-2:], byteorder='little')

                self.logger.info(
                    f"Parsed iOS LE response: Cmd ID: 0x{command_identifier:02x}, Packet Num: {packet_number}, Data: {response_data.hex()}, Checksum: 0x{checksum:04x}")
                
                self.logger.debug(f"Notification Handler: Expected command: 0x{self._expected_response_command:02x if self._expected_response_command else 'None'}, Received command: 0x{command_identifier:02x}")

                if self._expected_response_command is not None and command_identifier == self._expected_response_command:
                    self.logger.info(f"Matching response found for command 0x{command_identifier:02x}.")
                    self._response_data = response_data
                    self._response_event.set()
                    self._expected_response_command = None # Reset after matching
                    return
                else:
                    self.logger.warning(f"Response command 0x{command_identifier:02x} does not match expected command 0x{self._expected_response_command:02x if self._expected_response_command else 'None'}.")

            else:
                self.logger.warning(
                    f"Unrecognized notification data (not iOS LE Protocol format): {data.hex()}")
        else:
            # Attempt to parse Basic Protocol response: Head (0x01) + Len (2) + Cmd (1) + Data + Checksum (2) + Tail (0x02)
            if len(data) >= 6 and data[0] == 0x01 and data[-1] == 0x02:
                self.logger.info(
                    f"Basic Protocol response found. Full data: {data.hex()}")

                # Extract length (2 bytes, little-endian)
                response_len = int.from_bytes(data[1:3], byteorder='little')
                # Extract data (between command and checksum)
                response_data = data[4:-3]
                # Extract command (1 byte) - this is the command *within* the payload
                response_cmd_in_payload = response_data[1] if len(response_data) > 1 else None
                # Extract checksum (2 bytes, little-endian)
                response_checksum = int.from_bytes(data[-3:-1], byteorder='little')

                self.logger.info(
                    f"Parsed response: Len: {response_len}, Cmd: 0x{data[3]:02x} (Outer Cmd), Cmd in Payload: 0x{response_cmd_in_payload:02x if response_cmd_in_payload else 'None'}, Data: {response_data.hex()}, Checksum: 0x{response_checksum:04x}")

                # Always log the raw response data for debugging purposes
                self.logger.debug(f"Raw Basic Protocol response data: {response_data.hex()}")

                if self._expected_response_command is not None and response_cmd_in_payload == self._expected_response_command:
                    self.logger.info(f"Matching response found for command 0x{response_cmd_in_payload:02x}.")
                    
                    if response_cmd_in_payload == 0x46 and len(response_data) >= 5 and response_data[0] == 0x04 and response_data[2] == 0x55:
                        # For command 0x46, extract channel (CC) and brightness (BB)
                        # response_data is 04 CC 55 XX YY
                        self._response_data = response_data[3:5] # This will be [CC, BB]
                        self.logger.info(f"Extracted channel and brightness: {self._response_data.hex()}")
                    else:
                        self._response_data = response_data
                    
                    self._response_event.set()
                    self._expected_response_command = None # Reset after matching
                    return
                else:
                    self.logger.warning(f"Response command in payload 0x{response_cmd_in_payload:02x if response_cmd_in_payload else 'None'} does not match expected command 0x{self._expected_response_command:02x if self._expected_response_command else 'None'}.")
            else:
                self.logger.warning(
                    f"Unrecognized notification data (not Basic Protocol format): {data.hex()}")            
    
    async def send_command_and_wait_for_response(self, command, args=None, timeout=10):
        self.logger.debug(f"Entering _send_command_and_wait_for_response for command: {command}")
        if self.client is None or not self.client.is_connected:
            self.logger.error(f"Cannot send command '{command}': Not connected to a Divoom device.")
            return None
        self._response_data = None
        self._expected_response_command = command # Store the command ID
        self.logger.debug(f"Event state before clear: {self._response_event.is_set()}")
        self._response_event.clear()
        self.logger.debug(f"Event state after clear: {self._response_event.is_set()}")
            
        await self.send_command(command, args)
        
        self.logger.debug(f"Event state before wait: {self._response_event.is_set()}")
        try:
            await asyncio.wait_for(self._response_event.wait(), timeout=timeout)
            return self._response_data
        except asyncio.TimeoutError:
            self.logger.warning(
                f"Timeout waiting for notification response to command: {command}")
            # Original fallback: try to read all readable characteristics (for logging purposes)
            if self.client and self.client.is_connected:
                self.logger.info(
                    "Attempting to read from all readable characteristics as a fallback (for logging)...")
                for service in self.client.services:
                    for characteristic in service.characteristics:
                        if "read" in characteristic.properties:
                            try:
                                read_data = await self.client.read_gatt_char(characteristic.uuid)
                                self.logger.info(
                                    f"Fallback Read data from {characteristic.uuid}: {read_data.hex()} (ASCII: {read_data.decode('ascii', errors='ignore')})")
                            except Exception as e:
                                self.logger.error(
                                    f"Error reading from {characteristic.uuid} during fallback: {e}")
            return None
    async def send_command(self, command, args=None):
        """Send command with optional arguments"""
        if args is None:
            args = []
        if isinstance(command, str):
            command_name = command
            command = COMMANDS[command]
        else:
            command_name = f"0x{command:02x}"

        self.logger.debug(
            f"Sending command: {command_name} (0x{command:02x}) with args: {args}")

        # Construct payload as a list of bytes
        payload_bytes = [command] + args

        try:
            return await self.send_payload(payload_bytes)
        except Exception as e:
            self.logger.error(f"Error calling send_payload for command {command_name}: {e}")
            return False

    async def send_payload(self, payload_bytes):
        """Send raw payload to the Divoom device using the Timebox Evo protocol."""
        self.logger.debug(f"send_payload: self.client.is_connected = {self.client.is_connected}")
        if self.client is None or not self.client.is_connected:
            self.logger.error("Not connected to a Divoom device.")
            return

        if self.use_ios_le_protocol:
            full_message_hex = self._make_message_ios_le(payload_bytes)
            # For iOS LE protocol, we don't split messages this way
            message_bytes = bytes.fromhex(full_message_hex)
            try:
                self.logger.debug(f"{self.type} PAYLOAD OUT (iOS LE): {full_message_hex}")
                self.logger.debug(f"Raw message bytes being sent (iOS LE): {message_bytes.hex()}")
                await self.client.write_gatt_char(self.WRITE_CHARACTERISTIC_UUID, message_bytes)
                return True
            except Exception as e:
                self.logger.error(f"Error sending iOS LE payload: {e}")
                return False
        else:
            full_message_hex = self._make_message(payload_bytes)
            
            # Split message into chunks if it exceeds the chunksize
            # Each byte is 2 hex characters, so chunksize * 2
            chunk_length_hex = self.chunksize * 2
            
            if len(full_message_hex) > chunk_length_hex:
                self.logger.debug(f"Message too long ({len(full_message_hex)} hex chars), splitting into chunks of {chunk_length_hex} hex chars.")
                chunks = [full_message_hex[i:i + chunk_length_hex] for i in range(0, len(full_message_hex), chunk_length_hex)]
                
                for i, chunk_hex in enumerate(chunks):
                    try:
                        message_bytes = bytes.fromhex(chunk_hex)
                        self.logger.debug(f"{self.type} PAYLOAD OUT (Chunk {i+1}/{len(chunks)}): {chunk_hex}")
                        self.logger.debug(f"Raw message bytes being sent (Chunk {i+1}/{len(chunks)}): {message_bytes.hex()}")
                        await self.client.write_gatt_char(self.WRITE_CHARACTERISTIC_UUID, message_bytes)
                        await asyncio.sleep(0.05) # Small delay between chunks
                    except Exception as e:
                        self.logger.error(f"Error sending chunk {i+1}: {e}")
                        return False
                return True
            else:
                try:
                    # Convert hex string to bytes
                    message_bytes = bytes.fromhex(full_message_hex)
                    self.logger.debug(f"{self.type} PAYLOAD OUT: {full_message_hex}")
                    self.logger.debug(f"Raw message bytes being sent: {message_bytes.hex()}")
                    self.logger.debug(f"Attempting to write to characteristic: {self.WRITE_CHARACTERISTIC_UUID}")
                    await self.client.write_gatt_char(self.WRITE_CHARACTERISTIC_UUID, message_bytes)
                    return True
                except Exception as e:
                    self.logger.error(f"Error sending payload: {e}")
                    return False

    def _int2hexlittle(self, value):
        byte1 = (value & 0xFF)
        byte2 = ((value >> 8) & 0xFF)
        return f"{byte1:02x}{byte2:02x}"

    def _getCRC(self, hex_str):
        sum_val = 0
        for i in range(0, len(hex_str), 2):
            sum_val += int(hex_str[i:i+2], 16)
        return self._int2hexlittle(sum_val)

    def _make_message(self, payload_bytes):
        """Make a complete message from the payload data using the Timebox Evo protocol."""
        # Convert payload_bytes (list of integers) to hex string
        payload_hex = "".join(f"{b:02x}" for b in payload_bytes)

        # Calculate LLLL (length of payload_hex + CRC hex string length (4)) / 2
        length_value = (len(payload_hex) + 4) // 2
        length_hex = self._int2hexlittle(length_value)

        # Combine length_hex and payload_hex for CRC calculation
        crc_input_hex = length_hex + payload_hex
        checksum_hex = self._getCRC(crc_input_hex)

        # Construct the full message hex string
        final_message_hex = f"01{length_hex}{payload_hex}{checksum_hex}02"
        
        return final_message_hex

    def _make_message_ios_le(self, payload_bytes, packet_number=0x00000000):
        """Make a complete message from the payload data using the iOS LE protocol."""
        # iOS LE Header
        header = [0xFE, 0xEF, 0xAA, 0x55]

        # The actual command is the first byte of payload_bytes
        command_identifier = payload_bytes[0]

        # Data (command + args)
        data_bytes = payload_bytes

        # Packet Number (4 bytes, little-endian)
        packet_number_bytes = list(
            packet_number.to_bytes(4, byteorder='little'))

        # First, calculate the data_length_value assuming a 2-byte checksum
        data_length_value = 1 + 4 + len(data_bytes) + 2 # 1 (Cmd ID) + 4 (Packet Num) + len(Data) + 2 (Checksum)
        data_length_bytes = list(data_length_value.to_bytes(2, byteorder='little'))

        # Now, calculate the checksum over data_length_bytes, command_identifier, packet_number_bytes, and data_bytes
        checksum_input = data_length_bytes + [command_identifier] + packet_number_bytes + data_bytes
        checksum_value = sum(checksum_input)
        checksum_bytes = list(checksum_value.to_bytes(2, byteorder='little'))

        # Construct the full iOS LE message
        final_message_bytes = header + data_length_bytes + \
            [command_identifier] + packet_number_bytes + data_bytes + checksum_bytes

        return "".join(f"{b:02x}" for b in final_message_bytes)

    def convert_color(self, color_input) -> list:
        """
        Converts a color input (e.g., "RRGGBB", hex, or named color) to an
        RGB list [R, G, B].
        """
        if isinstance(color_input, str):
            if len(color_input) == 6 and all(c in '0123456789abcdefABCDEF' for c in color_input.lower()):
                return [int(color_input[i:i+2], 16) for i in (0, 2, 4)]
            # Add more robust color parsing here if necessary (e.g., named colors)
        elif isinstance(color_input, tuple) and len(color_input) == 3:  # (R, G, B) tuple
            return list(color_input)
        elif isinstance(color_input, list) and len(color_input) == 3:  # [R, G, B] list
            return color_input
        self.logger.warning(f"Unsupported color input format: {color_input}. Defaulting to [255, 255, 255].")
        return [255, 255, 255]

    def make_framepart(self, total_size, frame_id, data):
        """
        Constructs a frame part for image/animation transmission.
        total_size: Total size of the image/animation data.
        frame_id: Identifier for the current frame (-1 for static image, 0 for first animation frame, etc.).
        data: List of bytes for the current frame part.
        """
        frame = []
        frame += total_size.to_bytes(2, byteorder='little')
        frame += frame_id.to_bytes(1, byteorder='big', signed=True)
        frame += len(data).to_bytes(2, byteorder='little')
        frame.extend(data)
        return frame

    def number2HexString(self, byte_value: int) -> str:
        """
        Converts an integer (0-255) to its two-character hexadecimal string representation.
        """
        if not 0 <= byte_value <= 255:
            raise ValueError("number2HexString works only with numbers between 0 and 255")
        return f"{int(byte_value):02x}"

    def boolean2HexString(self, boolean_value: bool) -> str:
        """Convert a boolean to "01" (true) or "00" (false) hexadecimal string."""
        return "01" if boolean_value else "00"
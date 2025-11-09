# divoom_api/base.py
import datetime
import itertools
import logging
import math
import os
import time
import asyncio
from bleak import BleakClient
from bleak.exc import BleakError

from .constants import COMMANDS
from .utils.converters import color_to_rgb_list, number2HexString, boolean2HexString, color2HexString
from .utils.image_processing import make_framepart


class DivoomBase:
    """Base class for Divoom Bluetooth communication."""

    def __init__(self, mac=None, logger=None, write_characteristic_uuid=None, notify_characteristic_uuid=None, read_characteristic_uuid=None, spp_characteristic_uuid=None, escapePayload=False, use_ios_le_protocol=False, device_name=None):
        self.type = "Ditoo"  # Default to Ditoo
        self.screensize = 16
        self.chunksize = 200
        self.colorpalette = None
        self.mac = mac
        self.device_name = device_name  # Store device name
        self.WRITE_CHARACTERISTIC_UUID = write_characteristic_uuid
        self.NOTIFY_CHARACTERISTIC_UUID = notify_characteristic_uuid
        self.READ_CHARACTERISTIC_UUID = read_characteristic_uuid
        self.SPP_CHARACTERISTIC_UUID = spp_characteristic_uuid if spp_characteristic_uuid else "49535343-6daa-4d02-abf6-19569aca69fe"
        self.escapePayload = escapePayload
        # Initialize client internally only if mac is provided
        self.client = BleakClient(self.mac) if self.mac else None
        self.use_ios_le_protocol = use_ios_le_protocol if use_ios_le_protocol is not None else False
        self._response_event = asyncio.Event()
        self._response_data = None
        # New attribute to store the expected command ID
        self._expected_response_command = None
        self.message_buf = []
        self.max_reconnect_attempts = 5  # Increased from default
        self.reconnect_delay = 0.5  # Increased from default

        if logger is None:
            self.logger = logging.getLogger(self.type)
            self.logger.setLevel(logging.DEBUG)
            if not self.logger.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter(
                    '%(levelname)s:%(name)s:%(message)s')
                handler.setFormatter(formatter)
                self.logger.addHandler(handler)
        else:
            self.logger = logger

    @property
    def is_connected(self) -> bool:
        """Returns True if the BleakClient is connected, False otherwise."""
        return self.client and self.client.is_connected

    def color2HexString(self, color_input) -> str:
        """
        Converts a color input to an hexadecimal string representation (RRGGBB).
        Wraps divoom_api.utils.converters.color2HexString.
        """
        return color2HexString(color_input)

    def number2HexString(self, byte_value: int) -> str:
        """
        Converts an integer (0-255) to its two-character hexadecimal string representation.
        Wraps divoom_api.utils.converters.number2HexString.
        """
        return number2HexString(byte_value)

    def boolean2HexString(self, boolean_value: bool) -> str:
        """
        Convert a boolean to "01" (true) or "00" (false) hexadecimal string.
        Wraps divoom_api.utils.converters.boolean2HexString.
        """
        return boolean2HexString(boolean_value)

    def convert_color(self, color_input) -> list:
        """
        Converts a color input to a list of three integers [R, G, B].
        Wraps divoom_api.utils.converters.color_to_rgb_list.
        """
        return color_to_rgb_list(color_input)

    async def connect(self):
        """Open a connection to the Divoom device using bleak."""
        if not self.mac:
            self.logger.error(
                "No MAC address provided or discovered. Cannot connect.")
            raise Exception(
                "No MAC address provided or discovered. Cannot connect.")

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
            self.logger.error(
                "Characteristic UUIDs not fully set. Cannot connect.")
            raise Exception(
                "Characteristic UUIDs not fully set. Cannot connect.")

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
                # Rely on the Bleak backend to clean up notifications on
                # disconnect (this is what `minimal_bleak.py` does). Calling
                # stop_notify explicitly can raise backend-specific errors
                # like "Characteristic notification never started" on macOS
                # CoreBluetooth. To match the working reference behavior, skip
                # explicit stop_notify and simply disconnect.
                await self.client.disconnect()
                self.logger.info(
                    "Disconnected from Divoom device at %s", self.mac)
            except Exception as e:
                self.logger.error(
                    "Error disconnecting from %s: %s", self.mac, e)

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
                self.logger.info(
                    f"iOS LE Protocol response found. Full data: {data.hex()}")

                data_length = int.from_bytes(data[4:6], byteorder='little')
                command_identifier = data[6]
                packet_number = int.from_bytes(data[7:11], byteorder='little')
                # Data part is between Packet Number and Checksum
                response_data = data[11:-2]
                checksum = int.from_bytes(data[-2:], byteorder='little')

                self.logger.info(
                    f"Parsed iOS LE response: Cmd ID: 0x{command_identifier:02x}, Packet Num: {packet_number}, Data: {response_data.hex()}, Checksum: 0x{checksum:04x}")

                self.logger.debug(
                    f"Notification Handler: Expected command: 0x{self._expected_response_command:02x if self._expected_response_command else 'None'}, Received command: 0x{command_identifier:02x}")

                if self._expected_response_command is not None and command_identifier == self._expected_response_command:
                    self.logger.info(
                        f"Matching response found for command 0x{command_identifier:02x}.")
                    self._response_data = response_data
                    self._response_event.set()
                    self._expected_response_command = None  # Reset after matching
                    return
                else:
                    self.logger.warning(
                        f"Response command 0x{command_identifier:02x} does not match expected command 0x{self._expected_response_command:02x if self._expected_response_command else 'None'}.")

            else:
                self.logger.warning(
                    f"Unrecognized notification data (not iOS LE Protocol format): {data.hex()}")
        else:
            # First, try the lightweight scan for ACK-like patterns used by the
            # canonical harness: look for occurrences of [0x04, CMD, 0x55] anywhere
            # in the notification payload. This is robust to small framing
            # differences and matches what minimal_bleak.py does.
            try:
                b = bytes(data)
            except Exception:
                b = data

            # Find occurrences of [0x04, cmd, 0x55]
            for i in range(0, len(b) - 2):
                if b[i] == 0x04 and b[i + 2] == 0x55:
                    cmd = b[i + 1]
                    self.logger.info(
                        f"Parsed potential response: cmd=0x{cmd:02x} at offset {i}")
                    if self._expected_response_command is not None and cmd == self._expected_response_command:
                        self.logger.info(
                            f"Matched expected command 0x{cmd:02x} in notification.")
                        self._response_data = b
                        self._response_event.set()
                        self._expected_response_command = None
                        return

            # If the simple scan didn't find anything, fall back to the older
            # Basic Protocol parsing (head/tail + explicit offsets). Keep this
            # for completeness but prefer the pattern scan above.
            if len(data) >= 6 and data[0] == 0x01 and data[-1] == 0x02:
                self.logger.info(
                    f"Basic Protocol response found. Full data: {data.hex()}")

                # Extract length (2 bytes, little-endian)
                response_len = int.from_bytes(data[1:3], byteorder='little')
                # response payload lives between the outer header and checksum
                response_payload = data[3:-3]
                # The inner command may be at payload[0] or payload[1] depending on framing; try to be defensive
                response_cmd_in_payload = None
                if len(response_payload) >= 2:
                    # If payload starts with 0x04 pattern, inner cmd is at index 1
                    if response_payload[0] == 0x04 and len(response_payload) >= 3 and response_payload[2] == 0x55:
                        response_cmd_in_payload = response_payload[1]
                    else:
                        # Otherwise, assume the first byte is the inner command
                        response_cmd_in_payload = response_payload[0]

                response_checksum = int.from_bytes(
                    data[-3:-1], byteorder='little')

                self.logger.info(
                    f"Parsed response: Len: {response_len}, Cmd in Payload: {response_cmd_in_payload if response_cmd_in_payload is not None else 'None'}, Data: {response_payload.hex()}, Checksum: 0x{response_checksum:04x}")

                if self._expected_response_command is not None and response_cmd_in_payload == self._expected_response_command:
                    self._response_data = response_payload
                    self._response_event.set()
                    self._expected_response_command = None
                    return
                else:
                    self.logger.warning(
                        f"Response command in payload {response_cmd_in_payload} does not match expected {self._expected_response_command}.")
            else:
                self.logger.warning(
                    f"Unrecognized notification data (not Basic Protocol format): {data.hex()}")

    async def send_command_and_wait_for_response(self, command, args=None, timeout=10):
        self.logger.debug(
            f"Entering _send_command_and_wait_for_response for command: {command}")
        if self.client is None or not self.client.is_connected:
            self.logger.error(
                f"Cannot send command '{command}': Not connected to a Divoom device.")
            return None
        self._response_data = None
        self._expected_response_command = command  # Store the command ID
        self.logger.debug(
            f"Event state before clear: {self._response_event.is_set()}")
        self._response_event.clear()
        self.logger.debug(
            f"Event state after clear: {self._response_event.is_set()}")

        # When waiting for a notification response, perform the GATT write with
        # a request for a write-with-response (response=True) so the peripheral
        # processes the write more deterministically (matches minimal_bleak.py behavior).
        await self.send_command(command, args, write_with_response=True)

        self.logger.debug(
            f"Event state before wait: {self._response_event.is_set()}")
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

    async def send_command(self, command, args=None, write_with_response: bool = False):
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
            return await self.send_payload(payload_bytes, write_with_response=write_with_response)
        except Exception as e:
            self.logger.error(
                f"Error calling send_payload for command {command_name}: {e}")
            return False

    async def send_payload(self, payload_bytes, max_retries=3, retry_delay=0.1, write_with_response: bool = False):
        """Send raw payload to the Divoom device using the Timebox Evo protocol."""
        for attempt in range(max_retries):
            if self.client is None or not self.client.is_connected:
                self.logger.warning(
                    f"Attempt {attempt + 1}: Not connected to a Divoom device. Retrying in {retry_delay}s...")
                await asyncio.sleep(retry_delay)
                # Attempt to reconnect if not connected
                if not self.client or not self.client.is_connected:
                    try:
                        await self.connect()
                        self.logger.info(
                            f"Attempt {attempt + 1}: Reconnected to Divoom device at {self.mac}")
                    except Exception as e:
                        self.logger.error(
                            f"Attempt {attempt + 1}: Failed to reconnect: {e}")
                        if attempt == max_retries - 1:
                            self.logger.error(
                                "Max retries reached. Giving up.")
                            return False
                        continue

            self.logger.debug(
                f"send_payload: self.client.is_connected = {self.client.is_connected}")
            if self.use_ios_le_protocol:
                full_message_hex = self._make_message_ios_le(payload_bytes)
                # For iOS LE protocol, we don't split messages this way
                message_bytes = bytes.fromhex(full_message_hex)
                try:
                    self.logger.debug(
                        f"{self.type} PAYLOAD OUT (iOS LE): {full_message_hex}")
                    self.logger.debug(
                        f"Raw message bytes being sent (iOS LE): {message_bytes.hex()}")
                    # Use write_with_response when requested (important when awaiting ACKs)
                    await self.client.write_gatt_char(self.WRITE_CHARACTERISTIC_UUID, message_bytes, response=write_with_response)
                    return True
                except Exception as e:
                    self.logger.error(f"Error sending iOS LE payload: {e}")
                    if attempt == max_retries - 1:
                        return False
                    await asyncio.sleep(retry_delay)
            else:
                full_message_hex = self._make_message(payload_bytes)

                # Split message into chunks if it exceeds the chunksize
                # Each byte is 2 hex characters, so chunksize * 2
                chunk_length_hex = self.chunksize * 2

                if len(full_message_hex) > chunk_length_hex:
                    self.logger.debug(
                        f"Message too long ({len(full_message_hex)} hex chars), splitting into chunks of {chunk_length_hex} hex chars.")
                    chunks = [full_message_hex[i:i + chunk_length_hex]
                              for i in range(0, len(full_message_hex), chunk_length_hex)]

                    success = True
                    for i, chunk_hex in enumerate(chunks):
                        try:
                            message_bytes = bytes.fromhex(chunk_hex)
                            self.logger.debug(
                                f"{self.type} PAYLOAD OUT (Chunk {i+1}/{len(chunks)}): {chunk_hex}")
                            self.logger.debug(
                                f"Raw message bytes being sent (Chunk {i+1}/{len(chunks)}): {message_bytes.hex()}")
                            # If caller requested write-with-response, only request it on the final chunk
                            chunk_response = write_with_response and (
                                i == len(chunks) - 1)
                            await self.client.write_gatt_char(self.WRITE_CHARACTERISTIC_UUID, message_bytes, response=chunk_response)
                            # Small delay between chunks
                            await asyncio.sleep(0.05)
                        except Exception as e:
                            self.logger.error(
                                f"Error sending chunk {i+1}: {e}")
                            success = False
                            break
                    if success:
                        return True
                    elif attempt == max_retries - 1:
                        return False
                    await asyncio.sleep(retry_delay)
                else:
                    try:
                        # Convert hex string to bytes
                        message_bytes = bytes.fromhex(full_message_hex)
                        self.logger.debug(
                            f"{self.type} PAYLOAD OUT: {full_message_hex}")
                        self.logger.debug(
                            f"Raw message bytes being sent: {message_bytes.hex()}")
                        self.logger.debug(
                            f"Attempting to write to characteristic: {self.WRITE_CHARACTERISTIC_UUID}")
                        await self.client.write_gatt_char(self.WRITE_CHARACTERISTIC_UUID, message_bytes, response=write_with_response)
                        return True
                    except Exception as e:
                        self.logger.error(f"Error sending payload: {e}")
                        if attempt == max_retries - 1:
                            return False
                        await asyncio.sleep(retry_delay)
        return False  # Should not be reached if successful or max_retries reached

    def _int2hexlittle(self, value):
        byte1 = (value & 0xFF)
        byte2 = ((value >> 8) & 0xFF)
        return f"{byte1:02x}{byte2:02x}"

    def _escape_payload(self, payload_bytes: list) -> list:
        """
        Escape payload bytes for SPP/basic framing.
        Replaces:
          0x01 -> [0x03, 0x04]
          0x02 -> [0x03, 0x05]
          0x03 -> [0x03, 0x06]
        This mirrors the behavior used by the minimal BLE test harness so saved
        payloads and automatic replays behave the same across both code paths.
        """
        escaped = []
        for b in payload_bytes:
            if b == 0x01:
                escaped.extend([0x03, 0x04])
            elif b == 0x02:
                escaped.extend([0x03, 0x05])
            elif b == 0x03:
                escaped.extend([0x03, 0x06])
            else:
                escaped.append(b)
        return escaped

    def _getCRC(self, data_bytes: list):
        """
        Calculates the checksum for a list of byte values.
        The checksum is the sum of all byte values, converted to a 2-byte little-endian hex string.
        """
        sum_val = sum(data_bytes)
        return self._int2hexlittle(sum_val)

    def _make_message(self, payload_bytes):
        """Make a complete message from the payload data using the Timebox Evo protocol."""
        # Optionally escape payload bytes for SPP/basic framing
        working_payload = payload_bytes
        if getattr(self, "escapePayload", False):
            working_payload = self._escape_payload(payload_bytes)

        # Calculate LLLL (length of command_code + payload + checksum)
        # payload_bytes already contains the command_code as its first element
        # Checksum is 2 bytes
        # Length of (command + args) + 2 bytes for checksum
        length_value = len(working_payload) + 2

        # Convert length_value to its 2-byte little-endian representation
        length_bytes = list(length_value.to_bytes(2, byteorder='little'))
        length_hex = "".join(f"{b:02x}" for b in length_bytes)

        # Calculate checksum over length_bytes and (escaped) payload
        checksum_input_bytes = length_bytes + working_payload
        checksum_hex = self._getCRC(checksum_input_bytes)

        # Convert payload_bytes (list of integers) to hex string (use escaped payload)
        payload_hex = "".join(f"{b:02x}" for b in working_payload)

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
        # 1 (Cmd ID) + 4 (Packet Num) + len(Data) + 2 (Checksum)
        data_length_value = 1 + 4 + len(data_bytes) + 2
        data_length_bytes = list(
            data_length_value.to_bytes(2, byteorder='little'))

        # Now, calculate the checksum over data_length_bytes, command_identifier, packet_number_bytes, and data_bytes
        checksum_input = data_length_bytes + \
            [command_identifier] + packet_number_bytes + data_bytes
        checksum_value = sum(checksum_input)
        checksum_bytes = list(checksum_value.to_bytes(2, byteorder='little'))

        # Construct the full iOS LE message
        final_message_bytes = header + data_length_bytes + \
            [command_identifier] + packet_number_bytes + \
            data_bytes + checksum_bytes

        return "".join(f"{b:02x}" for b in final_message_bytes)

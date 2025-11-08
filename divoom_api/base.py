# divoom_api/base.py
import datetime
import itertools
import logging
import math
import os
import time
import asyncio
from PIL import Image, ImageDraw, ImageFont
from bleak import BleakClient

from .constants import COMMANDS


class DivoomBase:
    """Base class for Divoom Bluetooth communication."""

    # Identified as containing "SPP"
    SPP_CHARACTERISTIC_UUID = "49535343-6daa-4d02-abf6-19569aca69fe"
    WRITE_CHARACTERISTIC_UUID = None
    NOTIFY_CHARACTERISTIC_UUID = None
    READ_CHARACTERISTIC_UUID = None

    def __init__(self, mac=None, logger=None, write_characteristic_uuid=None, notify_characteristic_uuid=None, read_characteristic_uuid=None, spp_characteristic_uuid=None, escapePayload=False, use_ios_le_protocol=False):
        self.type = "Ditoo"  # Default to Ditoo
        self.screensize = 16
        self.chunksize = 200
        self.colorpalette = None
        self.mac = mac
        self.WRITE_CHARACTERISTIC_UUID = write_characteristic_uuid
        self.NOTIFY_CHARACTERISTIC_UUID = notify_characteristic_uuid
        self.READ_CHARACTERISTIC_UUID = read_characteristic_uuid
        self.SPP_CHARACTERISTIC_UUID = spp_characteristic_uuid if spp_characteristic_uuid else DivoomBase.SPP_CHARACTERISTIC_UUID
        self.escapePayload = escapePayload
        self.client = BleakClient(self.mac) if self.mac else None  # Initialize client internally
        self.use_ios_le_protocol = False
        self._response_event = asyncio.Event()
        self._response_data = None
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
        if self.client is None:  # Only create a new client if one wasn't provided
            self.client = BleakClient(self.mac)

        if not self.client.is_connected:
            try:
                await self.client.connect()
                self.logger.info(f"Connected to Divoom device at {self.mac}")
            except Exception as e:
                self.logger.error(f"Failed to connect to {self.mac}: {e}")
                raise

        if not all([self.WRITE_CHARACTERISTIC_UUID, self.NOTIFY_CHARACTERISTIC_UUID, self.READ_CHARACTERISTIC_UUID]):
            await self.discover_characteristics()

        # Enable notifications for all characteristics that support it
        for service in self.client.services:
            for characteristic in service.characteristics:
                if "notify" in characteristic.properties:
                    await self.client.start_notify(characteristic.uuid, self.notification_handler)
                    self.logger.info(
                        f"Enabled notifications for {characteristic.uuid}")
        await asyncio.sleep(1.0)

    async def discover_characteristics(self):
        """Discover and set the characteristic UUIDs for the device."""
        self.logger.info("Discovering characteristics...")
        for service in self.client.services:
            for char in service.characteristics:
                if "write" in char.properties and not "write-without-response" in char.properties:
                    self.WRITE_CHARACTERISTIC_UUID = char.uuid
                    self.logger.info(f"Found WRITE characteristic: {char.uuid}")
                if "notify" in char.properties:
                    self.NOTIFY_CHARACTERISTIC_UUID = char.uuid
                    self.logger.info(f"Found NOTIFY characteristic: {char.uuid}")
                if "read" in char.properties:
                    self.READ_CHARACTERISTIC_UUID = char.uuid
                    self.logger.info(f"Found READ characteristic: {char.uuid}")
        
        if not all([self.WRITE_CHARACTERISTIC_UUID, self.NOTIFY_CHARACTERISTIC_UUID, self.READ_CHARACTERISTIC_UUID]):
            self.logger.error("Could not discover all required characteristics.")
            raise Exception("Could not discover all required characteristics.")

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

                self._response_data = response_data
                self._response_event.set()
                return
            else:
                self.logger.warning(
                    f"Unrecognized notification data (not iOS LE Protocol format): {data.hex()}")
        else:
            # Attempt to parse Basic Protocol response: Head (0x01) + Len (2) + MainCmd (0x04) + Cmd (1) + AckCode (1) + Data + Checksum (2) + Tail (0x02)
            if len(data) >= 9 and data[0] == 0x01 and data[3] == 0x04 and data[-1] == 0x02:
                self.logger.info(
                    f"Basic Protocol MainCmd response found. Full data: {data.hex()}")

                # This is the original command that was sent
                response_cmd = data[4]
                ack_code = data[5]
                # Data part is between AckCode and Checksum
                response_data = data[6:-3]

                self.logger.info(
                    f"Parsed response command: 0x{response_cmd:02x}, AckCode: 0x{ack_code:02x}, Data: {response_data.hex()}")

                self._response_data = response_data
                self._response_event.set()
                return
            else:
                self.logger.warning(
                    f"Unrecognized notification data (not Basic Protocol MainCmd format): {data.hex()}")

    async def read_spp_characteristic_value(self):
        """Read the current value from the Divoom device's SPP characteristic."""
        if self.client is None or not self.client.is_connected:
            self.logger.error("Not connected to a Divoom device.")
            return None

        self.logger.info("Attempting to read SPP mode directly...")
        try:
            spp_data = await self.client.read_gatt_char(self.SPP_CHARACTERISTIC_UUID)
            spp_mode = spp_data.decode('ascii', errors='ignore')
            self.logger.info(f"Successfully read SPP mode: {spp_mode}")
            return spp_mode
        except Exception as e:
            self.logger.error(
                f"Error reading SPP characteristic {self.SPP_CHARACTERISTIC_UUID}: {e}")
            return None

    async def _send_command_and_wait_for_response(self, command, args=None, timeout=10):
        self.logger.debug(f"Entering _send_command_and_wait_for_response for command: {command}")
        if self.client is None or not self.client.is_connected:
            self.logger.error(f"Cannot send command '{command}': Not connected to a Divoom device.")
            return None
        self._response_data = None
        self._response_event.clear()

        await self.send_command(command, args)

        try:
            await asyncio.wait_for(self._response_event.wait(), timeout=timeout)
            return self._response_data
        except asyncio.TimeoutError:
            self.logger.warning(
                f"Timeout waiting for notification response to command: {command}")
            # Fallback: try to read from the READ_CHARACTERISTIC_UUID
            if self.client and self.client.is_connected and self.READ_CHARACTERISTIC_UUID:
                self.logger.info(
                    f"Attempting to read from READ_CHARACTERISTIC_UUID ({self.READ_CHARACTERISTIC_UUID}) as a fallback...")
                try:
                    read_data = await self.client.read_gatt_char(self.READ_CHARACTERISTIC_UUID)
                    self.logger.info(
                        f"Fallback Read data from {self.READ_CHARACTERISTIC_UUID}: {read_data.hex()} (ASCII: {read_data.decode('ascii', errors='ignore')})")
                    # Pass the read data to the notification handler for parsing
                    self.notification_handler(self.READ_CHARACTERISTIC_UUID, read_data)
                    # If the notification handler successfully parsed and set the event, return the data
                    if self._response_event.is_set():
                        return self._response_data
                except Exception as e:
                    self.logger.error(
                        f"Error reading from {self.READ_CHARACTERISTIC_UUID} during fallback: {e}")
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
        """Send raw payload to the Divoom device using the new protocol."""
        self.logger.debug(f"send_payload: self.client.is_connected = {self.client.is_connected}")
        if self.client is None or not self.client.is_connected:
            self.logger.error("Not connected to a Divoom device.")
            return

        if self.use_ios_le_protocol:
            full_message_hex = self._make_message_ios_le(payload_bytes)
        else:
            full_message_hex = self._make_message(payload_bytes)

        try:
            # Convert hex string to bytes
            message_bytes = bytes.fromhex(full_message_hex)
            self.logger.debug(f"{self.type} PAYLOAD OUT: {full_message_hex}")
            # Add this line for debugging
            self.logger.debug(
                f"Raw message bytes being sent: {message_bytes.hex()}")
            self.logger.debug(
                f"Attempting to write to characteristic: {self.WRITE_CHARACTERISTIC_UUID}")
            await self.client.write_gatt_char(self.WRITE_CHARACTERISTIC_UUID, message_bytes)
            return True
        except Exception as e:
            self.logger.error(f"Error sending payload: {e}")
            return False

    def _make_message(self, payload_bytes):
        """Make a complete message from the payload data using the new protocol."""
        # payload_bytes is expected to be a list of integers (bytes) where the first byte is the command
        command = payload_bytes[0]
        data = payload_bytes[1:]

        # Calculate checksum over command and data
        checksum_value = sum([command] + data)
        checksum_bytes = checksum_value.to_bytes(2, byteorder='little')

        # Combine command, data, and checksum
        command_data_checksum = [command] + data + list(checksum_bytes)

        # Calculate length (length of command, data, and checksum)
        length = len(command_data_checksum)
        length_bytes = length.to_bytes(2, byteorder='little')

        # Construct the full message
        final_message_bytes = [0x01] + \
            list(length_bytes) + command_data_checksum + [0x02]

        # Convert the list of integers to a hex string for sending
        return "".join(f"{b:02x}" for b in final_message_bytes)

    def _make_message_ios_le(self, payload_bytes, command_identifier=0x01, packet_number=0x00000000):
        """Make a complete message from the payload data using the iOS LE protocol."""
        # iOS LE Header
        header = [0xFE, 0xEF, 0xAA, 0x55]

        # Data (command + args)
        # The Divoom API doc says "Data: The data format remains unchanged from before."
        # So, payload_bytes (command + args) is our 'Data' here.
        data_bytes = payload_bytes

        # Packet Number (4 bytes, little-endian)
        packet_number_bytes = list(
            packet_number.to_bytes(4, byteorder='little'))

        # Checksum calculation for iOS LE: sum of data length, command identifier, packet number, and data.
        # First, calculate the 'data length' which includes packet number, data, and checksum.
        # Let's assume the checksum itself is 2 bytes for now, as in the original protocol.
        # This is a bit circular, so we'll calculate the checksum over the known parts first.

        # The 'Data' part of the iOS LE message is `command + args`.
        # The 'Data Length' field in iOS LE includes: packet number (4 bytes), Data (command + args), and Checksum (2 bytes).
        # So, the length of the 'Data' part of the iOS LE message is:
        # len(packet_number_bytes) + len(data_bytes) + len(checksum_bytes)
        # We need to calculate the checksum over this entire 'Data' section.

        # Let's construct the "Data" part of the iOS LE message first, which includes
        # Command Identifier (1 byte) + Packet Number (4 bytes) + Data (command + args)
        ios_le_data_section_for_checksum = [
            command_identifier] + packet_number_bytes + data_bytes

        # Calculate checksum over this section
        checksum_value = sum(ios_le_data_section_for_checksum)
        checksum_bytes = list(checksum_value.to_bytes(
            2, byteorder='little'))  # Assuming 2-byte checksum

        # Now, calculate the Data Length field for the iOS LE header.
        # Data Length = len(Command Identifier) + len(Packet Number) + len(Data) + len(Checksum)
        # Data Length = 1 + 4 + len(payload_bytes) + 2
        data_length_value = len(
            ios_le_data_section_for_checksum) + len(checksum_bytes)
        data_length_bytes = list(
            data_length_value.to_bytes(2, byteorder='little'))

        # Construct the full iOS LE message
        final_message_bytes = header + data_length_bytes + \
            ios_le_data_section_for_checksum + checksum_bytes

        return "".join(f"{b:02x}" for b in final_message_bytes)

    def _parse_frequency(self, frequency):
        if frequency is not None:
            if isinstance(frequency, str):
                frequency = float(frequency)

            frequency = frequency * 10
            if frequency > 1000:
                return [int(frequency - 1000), int(frequency / 100)]
            else:
                return [int(frequency % 100), int(frequency / 100)]

        return [0x00, 0x00]

    def chunks(self, lst, n):
        """Yield successive n-sized chunks from lst."""
        for i in range(0, len(lst), n):
            yield lst[i:i + n]

    def convert_color(self, color):
        result = []
        result += color[0].to_bytes(1, byteorder='big')
        result += color[1].to_bytes(1, byteorder='big')
        return result

    def checksum(self, payload):
        """Compute the payload checksum. Returned as list with LSM, MSB"""
        length = sum(payload)
        csum = []
        csum += length.to_bytes(4 if length >=
                                65535 else 2, byteorder='little')
        return csum

    def escape_payload(self, payload):
        """Escaping is not needed anymore as some smarter guys found out"""
        if self.escapePayload == None or self.escapePayload == False:
            return payload

        """Escape the payload. It is not allowed to have occurrences of the codes
        0x01, 0x02 and 0x03. They must be escaped by a leading 0x03 followed by 0x04,
        0x05 or 0x06 respectively"""
        escpayload = []
        for payload_data in payload:
            escpayload += \
                [0x03, payload_data +
                    0x03] if payload_data in range(0x01, 0x04) else [payload_data]
        return escpayload

    def make_frame(self, frame):
        length = len(frame) + 3
        header = [0xAA]
        header += length.to_bytes(2, byteorder='little')
        return [header + frame, length]

    def make_framepart(self, lsum, index, framePart):
        header = []
        if index >= 0:
            # Pixoo-Max expects more
            header += lsum.to_bytes(4 if self.screensize ==
                                    32 else 2, byteorder='little')
            # Pixoo-Max expects more
            header += index.to_bytes(2 if self.screensize ==
                                     32 else 1, byteorder='little')
        else:
            header += [0x00, 0x0A, 0x0A, 0x04]  # Fixed header on single frames
        return header + framePart

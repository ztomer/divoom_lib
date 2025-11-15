import asyncio
import datetime
import itertools
import logging
import math
import os
import time
from bleak import BleakClient
from bleak.exc import BleakError

from . import constants
from .utils.converters import color_to_rgb_list, number2HexString, boolean2HexString, color2HexString
from .utils.image_processing import make_framepart


class DivoomBase:
    """Base class for Divoom Bluetooth communication."""

    def __init__(self, mac: str | None = None, logger: logging.Logger | None = None, write_characteristic_uuid: str | None = None, notify_characteristic_uuid: str | None = None, read_characteristic_uuid: str | None = None, spp_characteristic_uuid: str | None = None, escapePayload: bool = False, use_ios_le_protocol: bool = False, device_name: str | None = None, client: BleakClient | None = None) -> None:
        self.type = constants.DEFAULT_DEVICE_TYPE  # Default to Ditoo
        self.screensize = constants.DEFAULT_SCREEN_SIZE
        self.chunksize = constants.DEFAULT_CHUNK_SIZE
        self.colorpalette = None
        self.mac = mac
        self.device_name = device_name  # Store device name
        self.WRITE_CHARACTERISTIC_UUID = write_characteristic_uuid
        self.NOTIFY_CHARACTERISTIC_UUID = notify_characteristic_uuid
        self.READ_CHARACTERISTIC_UUID = read_characteristic_uuid
        self.SPP_CHARACTERISTIC_UUID = spp_characteristic_uuid if spp_characteristic_uuid else constants.DEFAULT_SPP_CHARACTERISTIC_UUID
        self.escapePayload = escapePayload
        # Initialize client internally only if mac is provided, or use provided client
        self.client = client if client else (BleakClient(self.mac) if self.mac else None)
        self.use_ios_le_protocol = bool(use_ios_le_protocol)
        self.notification_queue = asyncio.Queue()
        # New attribute to store the expected command ID
        self._expected_response_command = None
        self.message_buf = []
        self.max_reconnect_attempts = constants.DEFAULT_MAX_RECONNECT_ATTEMPTS  # Increased from default
        self.reconnect_delay = constants.DEFAULT_RECONNECT_DELAY  # Increased from default

        if logger is None:
            logger = logging.getLogger(self.type)
            logger.setLevel(logging.DEBUG)
            if not logger.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter(
                    '%(levelname)s:%(name)s:%(message)s')
                handler.setFormatter(formatter)
                logger.addHandler(handler)
        self.logger = logger

    @property
    def is_connected(self) -> bool:
        """Returns True if the BleakClient is connected, False otherwise."""
        return self.client and self.client.is_connected

    def convert_color(self, color_input: str | tuple | list) -> list:
        """
        Converts a color input to a list of three integers [R, G, B].
        Wraps divoom_api.utils.converters.color_to_rgb_list.
        """
        return color_to_rgb_list(color_input)

    async def connect(self) -> None:
        """Open a connection to the Divoom device using bleak."""
        if not self.mac:
            self.logger.error("No MAC address provided or discovered. Cannot connect.")
            raise ValueError("No MAC address provided or discovered. Cannot connect.")

        if not all([self.WRITE_CHARACTERISTIC_UUID, self.NOTIFY_CHARACTERISTIC_UUID, self.READ_CHARACTERISTIC_UUID]):
            self.logger.error("Characteristic UUIDs not fully set. Cannot connect.")
            raise ValueError("Characteristic UUIDs not fully set. Cannot connect.")

        # If a client was provided and is already connected, skip connection
        if self.client and self.client.is_connected:
            self.logger.info(f"Client already connected to {self.mac}. Skipping connection.")
            return

        if not self.client or self.client.address != self.mac:
            self.client = BleakClient(self.mac)

        if not self.client.is_connected:
            try:
                await self.client.connect()
                self.logger.info(f"Connected to Divoom device at {self.mac}")
            except Exception as e:
                self.logger.error(f"Failed to connect to {self.mac}: {e}")
                raise ConnectionError(f"Failed to connect to {self.mac}: {e}")

        # Enable notifications only for the designated notify characteristic
        if self.NOTIFY_CHARACTERISTIC_UUID:
            def bleak_callback_handler(sender, data):
                # This closure ensures `self` is captured correctly.
                self.notification_handler(sender, data)

            await self.client.start_notify(self.NOTIFY_CHARACTERISTIC_UUID, bleak_callback_handler)
            self.logger.info(f"Enabled notifications for {self.NOTIFY_CHARACTERISTIC_UUID}")
        else:
            self.logger.warning("No notify characteristic UUID set. Cannot enable notifications.")
        
        await asyncio.sleep(1.0)

    async def disconnect(self) -> None:
        """Closes the connection to the Divoom device."""
        if self.client and self.client.is_connected:
            try:
                await self.client.disconnect()
                self.logger.info(
                    "Disconnected from Divoom device at %s", self.mac)
            except Exception as e:
                self.logger.error(
                    "Error disconnecting from %s: %s", self.mac, e)

    def _handle_ios_le_notification(self, data: bytes) -> bool:
        """Handles notifications for the iOS LE Protocol."""
        if len(data) >= constants.IOS_LE_MIN_DATA_LENGTH and data[0:4] == bytes(constants.IOS_LE_HEADER):
            self.logger.info(
                f"iOS LE Protocol response found. Full data: {data.hex()}")

            data_length = int.from_bytes(data[constants.IOS_LE_DATA_LENGTH_START:constants.IOS_LE_DATA_LENGTH_END], byteorder='little')
            command_identifier = data[constants.IOS_LE_COMMAND_IDENTIFIER]
            packet_number = int.from_bytes(data[constants.IOS_LE_PACKET_NUMBER_START:constants.IOS_LE_PACKET_NUMBER_END], byteorder='little')
            response_data = data[constants.IOS_LE_DATA_OFFSET:-constants.IOS_LE_CHECKSUM_LENGTH]
            checksum = int.from_bytes(data[-constants.IOS_LE_CHECKSUM_LENGTH:], byteorder='little')

            self.logger.info(
                f"Parsed iOS LE response: Cmd ID: 0x{command_identifier:02x}, Packet Num: {packet_number}, Data: {response_data.hex()}, Checksum: 0x{checksum:04x}")

            self.logger.debug(
                f"Notification Handler: Expected command: 0x{self._expected_response_command:02x if self._expected_response_command else 'None'}, Received command: 0x{command_identifier:02x}")

            response_payload = {'command_id': command_identifier, 'payload': response_data}
            expected_cmd = self._expected_response_command

            is_expected_response = expected_cmd is not None and command_identifier == expected_cmd
            is_generic_ack = expected_cmd is not None and command_identifier == 0x33 and expected_cmd in constants.GENERIC_ACK_COMMANDS

            if is_expected_response or is_generic_ack:
                self.notification_queue.put_nowait(response_payload)
                self._expected_response_command = None
                return True
            else:
                self.logger.warning(
                    f"Response command 0x{command_identifier:02x} does not match expected command 0x{expected_cmd:02x if expected_cmd else 'None'}.")

        else:
            self.logger.warning(
                f"Unrecognized notification data (not iOS LE Protocol format): {data.hex()}")
        return False

    def _handle_basic_protocol_notification(self, data: bytes) -> bool:
        """Handles notifications for the Basic Protocol by parsing framed messages."""
        self.message_buf.extend(data)
        
        while len(self.message_buf) >= 7: # Minimum length for a valid message
            start_index = -1
            try:
                start_index = self.message_buf.index(constants.MESSAGE_START_BYTE)
            except ValueError:
                self.logger.debug("No start byte found in buffer, clearing.")
                self.message_buf.clear()
                return False

            if start_index > 0:
                self.logger.warning(f"Discarding {start_index} bytes of junk data from start of buffer.")
                self.message_buf = self.message_buf[start_index:]

            if len(self.message_buf) < 4: # Need at least START, LEN_L, LEN_H, CMD
                self.logger.debug("Buffer too short for a full header.")
                return False

            length = int.from_bytes(bytes(self.message_buf[1:3]), byteorder='little')
            
            # Total message length is START(1) + LEN(2) + payload/checksum(length) + END(1) = length + 4
            total_message_len = 4 + length

            if len(self.message_buf) < total_message_len:
                self.logger.debug(f"Incomplete message. Have {len(self.message_buf)}, need {total_message_len}.")
                return False

            # We have a full message
            message = self.message_buf[:total_message_len]
            self.message_buf = self.message_buf[total_message_len:] # Consume message from buffer

            if message[-1] != constants.MESSAGE_END_BYTE:
                self.logger.warning(f"Message missing END byte. Discarding: {bytes(message).hex()}")
                continue # Look for the next message

            # According to protocol docs, responses are framed with 0x04 <CMD> 0x55
            # The command we are waiting for is at index 4, not 3.
            if len(message) > 5 and message[3] == 0x04 and message[5] == 0x55:
                command_id = message[4]
                payload = message[6:-2] # Payload starts after the 0x55 byte
                self.logger.info(f"Parsed Divoom Response. Cmd: 0x{command_id:02x}, Payload: {bytes(payload).hex()}")
            else:
                # This is not a standard response, maybe a different kind of notification
                # For now, we'll parse it with the old logic for backward compatibility
                command_id = message[3]
                payload = message[4:-2]
                self.logger.info(f"Parsed Non-Standard Notification. Cmd: 0x{command_id:02x}, Payload: {bytes(payload).hex()}")

            # Validate checksum
            checksum_input = message[1:-3]
            calculated_checksum = sum(checksum_input)
            received_checksum = int.from_bytes(bytes(message[-3:-1]), byteorder='little')
            if received_checksum != calculated_checksum:
                self.logger.warning(f"Checksum mismatch! Rcv: {received_checksum}, Calc: {calculated_checksum}. Msg: {bytes(message).hex()}")
                continue

            response_payload = {'command_id': command_id, 'payload': payload}
            expected_cmd = self._expected_response_command
            
            is_expected_response = expected_cmd is not None and command_id == expected_cmd
            is_generic_ack = expected_cmd is not None and command_id == 0x33 and expected_cmd in constants.GENERIC_ACK_COMMANDS

            if is_expected_response:
                self.notification_queue.put_nowait(response_payload)
                self._expected_response_command = None # Clear expectation only on direct match
                return True
            elif is_generic_ack:
                # It's an ack, but not the final data. Don't clear the expected command.
                # We can choose to queue it or ignore it. For now, let's log and ignore.
                self.logger.debug(f"Received generic ACK (0x33) for command 0x{expected_cmd:02x}. Awaiting final data response.")
                return True # Handled, but not finished
            else:
                expected_cmd_str = f"0x{expected_cmd:02x}" if expected_cmd is not None else "None"
                self.logger.warning(f"Response command 0x{command_id:02x} does not match expected {expected_cmd_str}")
        
        return False

    def notification_handler(self, sender: int, data: bytearray) -> None:
        """Handler for GATT notifications, attempting to parse Basic Protocol responses."""
        self.logger.debug(f"Notification Handler: self.use_ios_le_protocol = {self.use_ios_le_protocol}")
        expected_cmd_str = f"0x{self._expected_response_command:02x}" if self._expected_response_command is not None else "None"
        self.logger.debug(f"Notification Handler: Current expected command: {expected_cmd_str}")
        self.logger.debug("THIS IS MY NOTIFICATION HANDLER")
        self.logger.debug(f"ALL INCOMING NOTIFICATION DATA: {data.hex()}")
        self.logger.debug(f"Notification received from {sender}: {data.hex()}")
        self.message_buf.append(data)

        self.logger.info(f"Raw notification data: {data.hex()}")

        if self.use_ios_le_protocol:
            self._handle_ios_le_notification(data)
        else:
            self._handle_basic_protocol_notification(data)

    async def wait_for_response(self, command_id: int, timeout: int = 10) -> bytes | None:
        """Waits for a specific command response from the notification queue."""
        self.logger.debug(f"Polling for response to command ID 0x{command_id:02x} for {timeout}s...")
        end_time = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < end_time:
            try:
                # Check the queue for a response without blocking
                response = self.notification_queue.get_nowait()
                response_cmd_id = response.get('command_id')

                is_expected_response = response_cmd_id == command_id
                is_generic_ack = response_cmd_id == 0x33 and command_id in constants.GENERIC_ACK_COMMANDS

                if is_expected_response or is_generic_ack:
                    self.logger.debug(f"Got matching response for command ID 0x{command_id:02x} (Received 0x{response_cmd_id:02x})")
                    return response.get('payload')
                else:
                    self.logger.warning(f"Got unexpected response. Expected 0x{command_id:02x}, got 0x{response_cmd_id:02x}. Re-queueing.")
                    # This is not the response we were looking for, put it back.
                    self.notification_queue.put_nowait(response) # Re-queue and wait
            except asyncio.QueueEmpty:
                # Queue is empty, sleep for a short duration to yield control to the event loop
                await asyncio.sleep(0.1)
        
        self.logger.warning(
            f"Timeout polling for notification response to command ID: 0x{command_id:02x}")
        return None

    async def send_command_and_wait_for_response(self, command: int | str, args: list | None = None, timeout: int = 10) -> bytes | None:
        self.logger.debug(
            f"Entering send_command_and_wait_for_response for command: {command}")
        if self.client is None or not self.client.is_connected:
            self.logger.error(
                f"Cannot send command '{command}': Not connected to a Divoom device.")
            return None

        command_id = constants.COMMANDS.get(command, command) if isinstance(command, str) else command

        while not self.notification_queue.empty():
            self.notification_queue.get_nowait()
            self.logger.debug("Cleared a stale notification from the queue.")

        self._expected_response_command = command_id

        await self.send_command(command, args, write_with_response=True)
        
        return await self.wait_for_response(command_id, timeout)

    async def send_command(self, command: int | str, args: list | None = None, write_with_response: bool = False) -> bool:
        """Send command with optional arguments"""
        if args is None:
            args = []
        if isinstance(command, str):
            command_name = command
            command = constants.COMMANDS[command]
        else:
            command_name = f"0x{command:02x}"

        self.logger.debug(
            f"Sending command: {command_name} (0x{command:02x}) with args: {args}")

        payload_bytes = [command] + args

        try:
            return await self.send_payload(payload_bytes, write_with_response=write_with_response)
        except Exception as e:
            self.logger.error(
                f"Error calling send_payload for command {command_name}: {e}")
            return False

    async def _send_ios_le_payload(self, payload_bytes: list, write_with_response: bool) -> bool:
        """Sends a payload using the iOS LE protocol."""
        full_message_hex = self._make_message_ios_le(payload_bytes)
        message_bytes = bytes.fromhex(full_message_hex)
        try:
            self.logger.debug(
                f"{self.type} PAYLOAD OUT (iOS LE): {full_message_hex}")
            self.logger.debug(
                f"Raw message bytes being sent (iOS LE): {message_bytes.hex()}")
            await self.client.write_gatt_char(self.WRITE_CHARACTERISTIC_UUID, message_bytes, response=write_with_response)
            return True
        except Exception as e:
            self.logger.error(f"Error sending iOS LE payload: {e}")
            return False

    async def _send_basic_protocol_payload(self, payload_bytes: list, write_with_response: bool) -> bool:
        """Sends a payload using the Basic Protocol."""
        full_message_hex = self._make_message(payload_bytes)

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
                    chunk_response = write_with_response and (
                        i == len(chunks) - 1)
                    await self.client.write_gatt_char(self.WRITE_CHARACTERISTIC_UUID, message_bytes, response=chunk_response)
                    await asyncio.sleep(0.05)
                except Exception as e:
                    self.logger.error(
                        f"Error sending chunk {i+1}: {e}")
                    success = False
                    break
            return success
        else:
            try:
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
                return False

    async def send_payload(self, payload_bytes: list, max_retries: int = 3, retry_delay: float = 0.1, write_with_response: bool = False) -> bool:
        """Send raw payload to the Divoom device using the Timebox Evo protocol."""
        for attempt in range(max_retries):
            if self.client is None or not self.client.is_connected:
                self.logger.warning(
                    f"Attempt {attempt + 1}: Not connected to a Divoom device. Retrying in {retry_delay}s...")
                await asyncio.sleep(retry_delay)
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
                if await self._send_ios_le_payload(payload_bytes, write_with_response):
                    return True
                elif attempt == max_retries - 1:
                    return False
                await asyncio.sleep(retry_delay)
            else:
                if await self._send_basic_protocol_payload(payload_bytes, write_with_response):
                    return True
                elif attempt == max_retries - 1:
                    return False
                await asyncio.sleep(retry_delay)
        return False

    def _int2hexlittle(self, value: int) -> str:
        byte1 = (value & 0xFF)
        byte2 = ((value >> 8) & 0xFF)
        return f"{byte1:02x}{byte2:02x}"

    def _escape_payload(self, payload_bytes: list) -> list:
        """
        Escape payload bytes for SPP/basic framing.
        """
        escaped = []
        for b in payload_bytes:
            if b == constants.ESCAPE_BYTE_1:
                escaped.extend(constants.ESCAPE_SEQUENCE_1)
            elif b == constants.ESCAPE_BYTE_2:
                escaped.extend(constants.ESCAPE_SEQUENCE_2)
            elif b == constants.ESCAPE_BYTE_3:
                escaped.extend(constants.ESCAPE_SEQUENCE_3)
            else:
                escaped.append(b)
        return escaped

    def _getCRC(self, data_bytes: list) -> str:
        """
        Calculates the checksum for a list of byte values.
        """
        sum_val = sum(data_bytes)
        return self._int2hexlittle(sum_val)

    def _make_message(self, payload_bytes: list) -> str:
        """Make a complete message from the payload data using the Timebox Evo protocol."""
        working_payload = payload_bytes
        if getattr(self, "escapePayload", False):
            working_payload = self._escape_payload(payload_bytes)

        length_value = len(working_payload) + constants.MESSAGE_CHECKSUM_LENGTH

        length_bytes = list(length_value.to_bytes(2, byteorder='little'))
        length_hex = "".join(f"{b:02x}" for b in length_bytes)

        checksum_input_bytes = length_bytes + working_payload
        checksum_hex = self._getCRC(checksum_input_bytes)

        payload_hex = "".join(f"{b:02x}" for b in working_payload)

        final_message_hex = f"{constants.MESSAGE_START_BYTE:02x}{length_hex}{payload_hex}{checksum_hex}{constants.MESSAGE_END_BYTE:02x}"

        return final_message_hex

    def _make_message_ios_le(self, payload_bytes: list, packet_number: int = 0x00000000) -> str:
        """Make a complete message from the payload data using the iOS LE protocol."""
        header = constants.IOS_LE_MESSAGE_HEADER
        command_identifier = payload_bytes[0]
        data_bytes = payload_bytes
        packet_number_bytes = list(
            packet_number.to_bytes(constants.IOS_LE_MESSAGE_PACKET_NUM_LENGTH, byteorder='little'))
        data_length_value = constants.IOS_LE_MESSAGE_CMD_ID_LENGTH + constants.IOS_LE_MESSAGE_PACKET_NUM_LENGTH + len(data_bytes) + constants.IOS_LE_MESSAGE_CHECKSUM_LENGTH
        data_length_bytes = list(
            data_length_value.to_bytes(2, byteorder='little'))
        checksum_input = data_length_bytes + \
            [command_identifier] + packet_number_bytes + data_bytes
        checksum_value = sum(checksum_input)
        checksum_bytes = list(checksum_value.to_bytes(constants.IOS_LE_MESSAGE_CHECKSUM_LENGTH, byteorder='little'))
        final_message_bytes = header + data_length_bytes + \
            [command_identifier] + packet_number_bytes + \
            data_bytes + checksum_bytes
        return "".join(f"{b:02x}" for b in final_message_bytes)
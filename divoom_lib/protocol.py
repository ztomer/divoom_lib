
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List, Tuple, Optional, Dict, Any

from bleak import BleakClient
from bleak.exc import BleakError
from bleak.backends.device import BLEDevice
from bleak.backends.characteristic import BleakGATTCharacteristic


from divoom_lib import models
from divoom_lib import framing
from divoom_lib.utils import cache
from divoom_lib.exceptions import (
    DeviceAddressMissingError,
    CharacteristicConfigError,
    DeviceConnectionError,
)
from divoom_lib.utils import discovery


class DivoomProtocol:
    """Base class for Divoom Bluetooth communication."""

    def __init__(self, mac: str | None = None, logger: logging.Logger | None = None, write_characteristic_uuid: str | None = None, notify_characteristic_uuid: str | None = None, read_characteristic_uuid: str | None = None, spp_characteristic_uuid: str | None = None, escapePayload: bool = False, use_ios_le_protocol: bool = False, device_name: str | None = None, client: BleakClient | None = None) -> None:
        self.type = models.DEFAULT_DEVICE_TYPE  # Default to Ditoo
        self.screensize = models.DEFAULT_SCREEN_SIZE
        self.chunksize = models.DEFAULT_CHUNK_SIZE
        self.colorpalette = None
        self.mac = mac
        self.device_name = device_name  # Store device name
        self.WRITE_CHARACTERISTIC_UUID = write_characteristic_uuid
        self.NOTIFY_CHARACTERISTIC_UUID = notify_characteristic_uuid
        self.READ_CHARACTERISTIC_UUID = read_characteristic_uuid
        self.SPP_CHARACTERISTIC_UUID = spp_characteristic_uuid if spp_characteristic_uuid else models.DEFAULT_SPP_CHARACTERISTIC_UUID
        self.escapePayload = escapePayload
        # Initialize client internally only if mac is provided, or use provided client
        self.client = client if client else (BleakClient(self.mac) if self.mac else None)
        self.use_ios_le_protocol = bool(use_ios_le_protocol)
        self.notification_queue = asyncio.Queue()
        # New attribute to store the expected command ID
        self._expected_response_command = None
        self.message_buf = bytearray()
        self.max_reconnect_attempts = models.DEFAULT_MAX_RECONNECT_ATTEMPTS  # Increased from default
        self.reconnect_delay = models.DEFAULT_RECONNECT_DELAY  # Increased from default

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

    @asynccontextmanager
    async def _framing_context(self, use_ios: bool, escape: bool):
        """
        An async context manager to temporarily set framing preferences.
        Ensures original preferences are restored afterwards.
        """
        prev_use_ios = self.use_ios_le_protocol
        prev_escape = getattr(self, "escapePayload", False)

        self.use_ios_le_protocol = use_ios
        self.escapePayload = escape
        try:
            yield
        finally:
            self.use_ios_le_protocol = prev_use_ios
            self.escapePayload = prev_escape

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
        """
        Open a connection to the Divoom device using bleak.

        This method establishes a Bluetooth Low Energy (BLE) connection to the device
        specified by the MAC address. It also starts notifications on the notify
        characteristic to receive responses from the device.

        Raises:
            ValueError: If the MAC address is not provided or if characteristic UUIDs are missing.
            ConnectionError: If the connection to the device fails.
        """
        if not self.mac:
            self.logger.error("No MAC address provided or discovered. Cannot connect.")
            raise DeviceAddressMissingError("No MAC address provided or discovered. Cannot connect.")

        if not all([self.WRITE_CHARACTERISTIC_UUID, self.NOTIFY_CHARACTERISTIC_UUID, self.READ_CHARACTERISTIC_UUID]):
            self.logger.error("Characteristic UUIDs not fully set. Cannot connect.")
            raise CharacteristicConfigError("Characteristic UUIDs not fully set. Cannot connect.")

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
                raise DeviceConnectionError(f"Failed to connect to {self.mac}: {e}")

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
        """
        Closes the connection to the Divoom device.

        This method disconnects the BLE client if it is currently connected.
        It logs the disconnection event and handles any exceptions that might occur
        during the disconnection process.
        """
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
        parsed = framing.parse_ios_le_notification(data)
        if parsed is not None:
            command_identifier = parsed['command_id']
            response_data = parsed['payload']

            if self.logger.isEnabledFor(logging.INFO):
                self.logger.info(
                    "Parsed iOS LE response: Cmd ID: 0x%02x, Packet Num: %s, Data: %s, Checksum: 0x%04x",
                    command_identifier, parsed['packet_number'], response_data.hex(), parsed['checksum'])

            response_payload = {'command_id': command_identifier, 'payload': response_data}
            expected_cmd = self._expected_response_command

            is_expected_response = expected_cmd is not None and command_identifier == expected_cmd
            is_generic_ack = expected_cmd is not None and command_identifier == models.GENERIC_ACK_COMMAND_ID and expected_cmd in models.GENERIC_ACK_COMMANDS

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

    def _handle_basic_protocol_notification(self, new_data: bytearray) -> bool:
        """Handles notifications for the Basic Protocol by parsing framed messages."""
        self.message_buf.extend(new_data)
        if models.MESSAGE_START_BYTE not in self.message_buf:
            self.logger.debug("No start byte found in buffer, clearing.")
            self.message_buf.clear()
            return False
        msgs, self.message_buf = framing.parse_basic_protocol_frames(self.message_buf)
        for response_payload in msgs:
            self.notification_queue.put_nowait(response_payload)
        return True

    def notification_handler(self, sender: int, data: bytearray) -> None:
        """Handler for GATT notifications, attempting to parse Basic Protocol responses."""
        self.logger.debug(f"Notification Handler: self.use_ios_le_protocol = {self.use_ios_le_protocol}")
        expected_cmd_str = f"0x{self._expected_response_command:02x}" if self._expected_response_command is not None else "None"
        self.logger.debug(f"Notification Handler: Current expected command: {expected_cmd_str}")
        self.logger.debug("THIS IS MY NOTIFICATION HANDLER")
        self.logger.debug(f"ALL INCOMING NOTIFICATION DATA: {data.hex()}")
        self.logger.debug(f"Notification received from {sender}: {data.hex()}")

        self.logger.info(f"Raw notification data: {data.hex()}")

        if self.use_ios_le_protocol:
            self._handle_ios_le_notification(data)
        else:
            self._handle_basic_protocol_notification(data)

    async def wait_for_response(self, command_id: int, timeout: int = 10) -> bytes | None:
        """Waits for a specific command response from the notification queue."""
        self.logger.debug(f"Waiting for response to command ID 0x{command_id:02x} for {timeout}s...")
        loop = asyncio.get_running_loop()
        end_time = loop.time() + timeout
        while True:
            remaining = end_time - loop.time()
            if remaining <= 0:
                break
            try:
                # Block until a notification arrives or the deadline passes.
                response = await asyncio.wait_for(self.notification_queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                break

            response_cmd_id = response.get('command_id')
            is_expected_response = response_cmd_id == command_id
            is_generic_ack = response_cmd_id == models.GENERIC_ACK_COMMAND_ID and command_id in models.GENERIC_ACK_COMMANDS

            if is_expected_response:
                self.logger.debug(f"Got matching response for command ID 0x{command_id:02x} (Received 0x{response_cmd_id:02x})")
                self._expected_response_command = None # Clear expectation on final match
                return response.get('payload')
            elif is_generic_ack:
                self.logger.debug(f"Received generic ACK (0x{models.GENERIC_ACK_COMMAND_ID:02x}) for command 0x{command_id:02x}. Continuing to wait for final data response.")
                # Don't return, continue waiting for the actual data response
            else:
                self.logger.warning(f"Got unexpected response. Expected 0x{command_id:02x}, got 0x{response_cmd_id:02x}. Discarding.")
                # This is not the response we were looking for, discard it.
                # Do not re-queue, as it might be an unsolicited message.

        self.logger.warning(
            f"Timeout waiting for notification response to command ID: 0x{command_id:02x}")
        return None
    async def send_command_and_wait_for_response(self, command: int | str, args: list | None = None, timeout: int = 10) -> bytes | None:
        """
        Sends a command to the device and waits for a response.

        This method sends a command to the Divoom device and waits for a matching response
        from the notification queue. It handles the command ID resolution (string to int)
        and manages the expected response command logic.

        Args:
            command (int | str): The command to send. Can be a command ID (int) or a command name (str).
            args (list | None): A list of arguments to include in the command payload. Defaults to None.
            timeout (int): The maximum time to wait for a response in seconds. Defaults to 10.

        Returns:
            bytes | None: The payload of the response if received within the timeout, or None if timed out.
        """
        self.logger.debug(
            f"Entering send_command_and_wait_for_response for command: {command}")
        if self.client is None or not self.client.is_connected:
            self.logger.error(
                f"Cannot send command '{command}': Not connected to a Divoom device.")
            return None

        command_id = models.COMMANDS.get(command, command) if isinstance(command, str) else command

        while not self.notification_queue.empty():
            self.notification_queue.get_nowait()
            self.logger.debug("Cleared a stale notification from the queue.")

        self._expected_response_command = command_id
        self.logger.debug(f"Set _expected_response_command to 0x{self._expected_response_command:02x}")

        await self.send_command(command, args, write_with_response=True)

        response_payload = await self.wait_for_response(command_id, timeout)
        self.logger.debug(f"send_command_and_wait_for_response returning with payload: {response_payload}")
        return response_payload

    async def send_command(self, command: int | str, args: list | None = None, write_with_response: bool = False) -> bool:
        """
        Send command with optional arguments.

        This method sends a command to the Divoom device. It resolves the command name to
        its ID if a string is provided.

        Args:
            command (int | str): The command to send. Can be a command ID (int) or a command name (str).
            args (list | None): A list of arguments to include in the command payload. Defaults to None.
            write_with_response (bool): Whether to request a response from the BLE characteristic. Defaults to False.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        if args is None:
            args = []
        if isinstance(command, str):
            command_name = command
            command = models.COMMANDS[command]
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
        message_bytes = self._make_message_ios_le(payload_bytes)
        try:
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug("%s PAYLOAD OUT (iOS LE): %s", self.type, message_bytes.hex())
            await self.client.write_gatt_char(self.WRITE_CHARACTERISTIC_UUID, message_bytes, response=write_with_response)
            return True
        except Exception as e:
            self.logger.error(f"Error sending iOS LE payload: {e}")
            return False

    async def _send_basic_protocol_payload(self, payload_bytes: list, write_with_response: bool) -> bool:
        """Sends a payload using the Basic Protocol."""
        full_message = self._make_message(payload_bytes)

        chunk_size = self.chunksize

        if len(full_message) > chunk_size:
            self.logger.debug(
                f"Message too long ({len(full_message)} bytes), splitting into chunks of {chunk_size} bytes.")
            chunks = [full_message[i:i + chunk_size]
                      for i in range(0, len(full_message), chunk_size)]

            success = True
            for i, chunk in enumerate(chunks):
                try:
                    if self.logger.isEnabledFor(logging.DEBUG):
                        self.logger.debug("%s PAYLOAD OUT (Chunk %d/%d): %s", self.type, i + 1, len(chunks), chunk.hex())
                    chunk_response = write_with_response and (
                        i == len(chunks) - 1)
                    await self.client.write_gatt_char(self.WRITE_CHARACTERISTIC_UUID, chunk, response=chunk_response)
                    await asyncio.sleep(0.05)
                except Exception as e:
                    self.logger.error(
                        f"Error sending chunk {i+1}: {e}")
                    success = False
                    break
            return success
        else:
            try:
                if self.logger.isEnabledFor(logging.DEBUG):
                    self.logger.debug("%s PAYLOAD OUT: %s (char %s)", self.type, full_message.hex(), self.WRITE_CHARACTERISTIC_UUID)
                await self.client.write_gatt_char(self.WRITE_CHARACTERISTIC_UUID, full_message, response=write_with_response)
                return True
            except Exception as e:
                self.logger.error(f"Error sending payload: {e}")
                return False

    async def send_payload(self, payload_bytes: list, max_retries: int = 3, retry_delay: float = 0.1, write_with_response: bool = False) -> bool:
        """
        Send raw payload to the Divoom device using the configured protocol.

        This method sends a raw payload of bytes to the Divoom device. It handles
        reconnection attempts if the client is disconnected and supports both
        Basic and iOS LE protocols.

        Args:
            payload_bytes (list): The list of bytes to send as the payload.
            max_retries (int): The maximum number of retries if sending fails. Defaults to 3.
            retry_delay (float): The delay in seconds between retries. Defaults to 0.1.
            write_with_response (bool): Whether to request a response from the BLE characteristic. Defaults to False.

        Returns:
            bool: True if the payload was sent successfully, False otherwise.
        """
        for attempt in range(max_retries):
            # Exponential backoff between attempts: retry_delay, 2x, 4x, ...
            backoff = retry_delay * (2 ** attempt)
            if self.client is None or not self.client.is_connected:
                self.logger.warning(
                    f"Attempt {attempt + 1}: Not connected to a Divoom device. Retrying in {backoff}s...")
                await asyncio.sleep(backoff)
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
                await asyncio.sleep(backoff)
            else:
                if await self._send_basic_protocol_payload(payload_bytes, write_with_response):
                    return True
                elif attempt == max_retries - 1:
                    return False
                await asyncio.sleep(backoff)
        return False

    def _int2hexlittle(self, value: int) -> str:
        return framing.int2hexlittle(value)

    def _escape_payload(self, payload_bytes: list) -> list:
        return framing.escape_payload(payload_bytes)

    def _getCRC(self, data_bytes: list) -> str:
        return framing.get_checksum(data_bytes)

    def _make_message(self, payload_bytes: list) -> bytes:
        escape = getattr(self, "escapePayload", False)
        return framing.encode_basic_payload(payload_bytes, escape=escape)

    def _make_message_ios_le(self, payload_bytes: list, packet_number: int = 0x00000000) -> bytes:
        return framing.encode_ios_le_payload(payload_bytes, packet_number=packet_number)

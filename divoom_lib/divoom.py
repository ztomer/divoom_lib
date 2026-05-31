import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List, Tuple, Optional, Dict, Any

from bleak import BleakClient
from bleak.exc import BleakError

from . import models, framing
from .exceptions import (
    DeviceAddressMissingError,
    CharacteristicConfigError,
    DeviceConnectionError,
)
from .display.light import Light
from .display.animation import Animation
from .display.drawing import Drawing
from .display.text import Text
from .system.device import Device
from .system.time import Time
from .system.bluetooth import Bluetooth
from .media.music import Music
from .media.radio import Radio
from .scheduling.alarm import Alarm
from .scheduling.sleep import Sleep
from .scheduling.timeplan import Timeplan
from .tools.scoreboard import Scoreboard
from .tools.timer import Timer
from .tools.countdown import Countdown
from .tools.noise import Noise
from .display import Display
from .system import System
from .tool import Tool
from .game import Game

def _get_cache_module(cache_mod=None):
    if cache_mod is not None:
        return cache_mod
    from .utils import cache as cache_mod
    return cache_mod

class Divoom:
    """
    A class to interact with a Divoom device over Bluetooth Low Energy (BLE).

    This class provides methods to connect to a Divoom device, send commands,
    and control its various features like display, channels, and system settings.

    Usage::

        import asyncio
        from divoom_lib import Divoom
        from divoom_lib.models import DivoomConfig

        async def main():
            device_address = "XX:XX:XX:XX:XX:XX"  # Replace with your device's address
            config = DivoomConfig(mac=device_address)
            divoom = Divoom(config)

            try:
                await divoom.connect()
                await divoom.light.show_light(color=(255, 0, 0))
            finally:
                if divoom.is_connected:
                    await divoom.disconnect()

        if __name__ == "__main__":
            asyncio.run(main())
    """
    def __init__(self, config: Optional[models.DivoomConfig] = None, mac: Optional[str] = None, logger: Optional[object] = None, **kwargs) -> None:
        """
        Initializes the Divoom device controller.

        Args:
            config (DivoomConfig, optional): The configuration object for the Divoom device.
            mac (str, optional): The MAC address of the device.
            logger (logging.Logger, optional): The logger to use.
            **kwargs: Backward-compatible keyword arguments.
        """
        if config is not None and isinstance(config, models.DivoomConfig):
            cfg = config
        else:
            mac_addr = mac
            if mac_addr is None and isinstance(config, str):
                mac_addr = config
            
            cfg = models.DivoomConfig(
                mac=mac_addr,
                logger=logger or kwargs.get('logger'),
                write_characteristic_uuid=kwargs.get('write_characteristic_uuid', "49535343-8841-43f4-a8d4-ecbe34729bb3"),
                notify_characteristic_uuid=kwargs.get('notify_characteristic_uuid', "49535343-1e4d-4bd9-ba61-23c647249616"),
                read_characteristic_uuid=kwargs.get('read_characteristic_uuid', "49535343-1e4d-4bd9-ba61-23c647249616"),
                spp_characteristic_uuid=kwargs.get('spp_characteristic_uuid'),
                escapePayload=kwargs.get('escapePayload', False),
                use_ios_le_protocol=kwargs.get('use_ios_le_protocol', False),
                device_name=kwargs.get('device_name'),
                client=kwargs.get('client')
            )

        self.mac = cfg.mac
        self.device_name = cfg.device_name
        self.WRITE_CHARACTERISTIC_UUID = cfg.write_characteristic_uuid
        self.NOTIFY_CHARACTERISTIC_UUID = cfg.notify_characteristic_uuid
        self.READ_CHARACTERISTIC_UUID = cfg.read_characteristic_uuid
        self.SPP_CHARACTERISTIC_UUID = cfg.spp_characteristic_uuid if cfg.spp_characteristic_uuid else models.DEFAULT_SPP_CHARACTERISTIC_UUID
        self.escapePayload = cfg.escapePayload
        self.client = cfg.client if cfg.client else (BleakClient(self.mac) if self.mac else None)
        self.use_ios_le_protocol = bool(cfg.use_ios_le_protocol)
        self.notification_queue = asyncio.Queue()
        self._expected_response_command = None
        self.message_buf = bytearray()
        self.max_reconnect_attempts = models.DEFAULT_MAX_RECONNECT_ATTEMPTS
        self.reconnect_delay = models.DEFAULT_RECONNECT_DELAY

        if cfg.logger is None:
            log = logging.getLogger(self.mac)
            log.setLevel(logging.DEBUG)
            if not log.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter('%(levelname)s:%(name)s:%(message)s')
                handler.setFormatter(formatter)
                log.addHandler(handler)
            self.logger = log
        else:
            self.logger = cfg.logger

        self.light = Light(self)
        self.animation = Animation(self)
        self.drawing = Drawing(self)
        self.text = Text(self)

        self.device = Device(self)
        self.time = Time(self)
        self.bluetooth = Bluetooth(self)

        self.music = Music(self)
        self.radio = Radio(self)

        self.alarm = Alarm(self)
        self.sleep = Sleep(self)
        self.timeplan = Timeplan(self)

        self.scoreboard = Scoreboard(self)
        self.timer = Timer(self)
        self.countdown = Countdown(self)
        self.noise = Noise(self)

        self.display = Display(self)
        self.system = System(self)
        self.tool = Tool(self)
        self.game = Game(self)

        self.logger.debug("Divoom.__init__ called. protocol and modules initialized.")

    @classmethod
    def from_config(cls, config: models.DivoomConfig) -> "Divoom":
        """Create a Divoom from a fully-formed :class:`DivoomConfig` (preferred)."""
        return cls(config=config)

    @classmethod
    def from_mac(cls, mac: str, logger: Optional[object] = None, **kwargs) -> "Divoom":
        """Create a Divoom from a MAC address and optional overrides.

        Convenience factory for the common case; wraps the keyword-argument
        construction path so callers don't have to build a DivoomConfig.
        """
        return cls(mac=mac, logger=logger, **kwargs)

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
        from .utils.converters import color_to_rgb_list
        return color_to_rgb_list(color_input)

    async def connect(self) -> None:
        """
        Open a connection to the Divoom device using bleak.

        This method establishes a Bluetooth Low Energy (BLE) connection to the device
        specified by the MAC address in the configuration. It also starts notifications
        on the notify characteristic to receive responses from the device.

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

        if self.NOTIFY_CHARACTERISTIC_UUID:
            await self.client.start_notify(self.NOTIFY_CHARACTERISTIC_UUID, self.notification_handler)
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

    def notification_handler(self, sender: int, data: bytearray) -> None:
        """Wrapper for _notification_handler to support backwards-compatible tests."""
        self._notification_handler(sender, data)

    def _notification_handler(self, sender: int, data: bytearray) -> None:
        """Handler for GATT notifications, attempting to parse Basic Protocol responses."""
        if self.logger.isEnabledFor(logging.DEBUG):
            expected_cmd_str = f"0x{self._expected_response_command:02x}" if self._expected_response_command is not None else "None"
            self.logger.debug(
                "Notification from %s: use_ios_le=%s expected=%s data=%s",
                sender, self.use_ios_le_protocol, expected_cmd_str, data.hex())
        elif self.logger.isEnabledFor(logging.INFO):
            self.logger.info("Raw notification data: %s", data.hex())

        if self.use_ios_le_protocol:
            self._handle_ios_le_notification(data)
        else:
            self._handle_basic_protocol_notification(data)

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
                    f"Response command 0x{command_identifier:02x} does not match expected command {f'0x{expected_cmd:02x}' if expected_cmd is not None else 'None'}.")
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

    async def wait_for_response(self, command_id: int, timeout: float = 3.0) -> bytes | None:
        """Backward-compatible wrapper for _wait_for_response."""
        return await self._wait_for_response(command_id, timeout)

    async def _wait_for_response(self, command_id: int, timeout: int = 10) -> bytes | None:
        """Waits for a specific command response from the notification queue."""
        self.logger.debug(f"Waiting for response to command ID 0x{command_id:02x} for {timeout}s...")
        loop = asyncio.get_running_loop()
        end_time = loop.time() + timeout
        while True:
            remaining = end_time - loop.time()
            if remaining <= 0:
                break
            try:
                response = await asyncio.wait_for(self.notification_queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                break

            response_cmd_id = response.get('command_id')
            is_expected_response = response_cmd_id == command_id
            is_generic_ack = response_cmd_id == models.GENERIC_ACK_COMMAND_ID and command_id in models.GENERIC_ACK_COMMANDS

            if is_expected_response:
                self.logger.debug(f"Got matching response for command ID 0x{command_id:02x} (Received 0x{response_cmd_id:02x})")
                self._expected_response_command = None
                return response.get('payload')
            elif is_generic_ack:
                self.logger.debug(f"Received generic ACK (0x33) for command 0x{command_id:02x}. Continuing to wait for final data response.")
            else:
                self.logger.warning(f"Got unexpected response. Expected 0x{command_id:02x}, got 0x{response_cmd_id:02x}. Discarding.")

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

        response_payload = await self._wait_for_response(command_id, timeout)
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
            return await self._send_payload(payload_bytes, write_with_response=write_with_response)
        except Exception as e:
            self.logger.error(
                f"Error calling send_payload for command {command_name}: {e}")
            return False

    async def send_payload(self, payload_bytes: list, max_retries: int = 3, **kwargs) -> bool:
        """Backward-compatible wrapper for _send_payload."""
        return await self._send_payload(payload_bytes, max_retries=max_retries, **kwargs)

    async def _send_payload(self, payload_bytes: list, max_retries: int = 3, retry_delay: float = 0.1, write_with_response: bool = False) -> bool:
        """Send raw payload to the Divoom device."""
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

    async def _send_ios_le_payload(self, payload_bytes: list, write_with_response: bool) -> bool:
        """Sends a payload using the iOS LE protocol."""
        message_bytes = self._make_message_ios_le(payload_bytes)
        try:
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug("PAYLOAD OUT (iOS LE): %s", message_bytes.hex())
            await self.client.write_gatt_char(self.WRITE_CHARACTERISTIC_UUID, message_bytes, response=write_with_response)
            return True
        except Exception as e:
            self.logger.error(f"Error sending iOS LE payload: {e}")
            return False

    async def _send_basic_protocol_payload(self, payload_bytes: list, write_with_response: bool) -> bool:
        """Sends a payload using the Basic Protocol."""
        full_message = self._make_message(payload_bytes)

        chunk_size = models.DEFAULT_CHUNK_SIZE

        if len(full_message) > chunk_size:
            self.logger.debug(
                f"Message too long ({len(full_message)} bytes), splitting into chunks of {chunk_size} bytes.")
            chunks = [full_message[i:i + chunk_size]
                      for i in range(0, len(full_message), chunk_size)]

            success = True
            for i, chunk in enumerate(chunks):
                try:
                    if self.logger.isEnabledFor(logging.DEBUG):
                        self.logger.debug("PAYLOAD OUT (Chunk %d/%d): %s", i + 1, len(chunks), chunk.hex())
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
                    self.logger.debug("PAYLOAD OUT: %s (char %s)", full_message.hex(), self.WRITE_CHARACTERISTIC_UUID)
                await self.client.write_gatt_char(self.WRITE_CHARACTERISTIC_UUID, full_message, response=write_with_response)
                return True
            except Exception as e:
                self.logger.error(f"Error sending payload: {e}")
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

    async def _try_send_command_with_framing(self, command_id: int, payload: list, timeout: int = 3, use_ios: bool = False, escape: bool = False):
        self.use_ios_le_protocol = use_ios
        self.escapePayload = escape
        return await self.send_command_and_wait_for_response(command_id, payload, timeout=timeout)

    async def _send_diagnostic_payload(self, write_uuid: str, args_payload: list, cache_data: dict, cache_dir: str, device_id: str, cache_mod: Any = None):
        cache_mod = _get_cache_module(cache_mod)

        self.WRITE_CHARACTERISTIC_UUID = write_uuid

        # 1. Try SPP first (escaped)
        resp = await self._try_send_command_with_framing(0x45, args_payload, timeout=3, use_ios=False, escape=True)
        if resp is not None:
            self.use_ios_le_protocol = False
            self.escapePayload = True
            existing = cache_data or {}
            existing.update({
                "write_characteristic_uuid": write_uuid,
                "ack_characteristic_uuid": self.NOTIFY_CHARACTERISTIC_UUID,
                "last_successful_payload": [f"{b:02x}" for b in args_payload],
                "last_successful_use_ios_le": False,
                "escapePayload": True,
            })
            try:
                await asyncio.to_thread(cache_mod.save_device_cache, cache_dir, device_id, existing)
            except OSError:
                pass
            return True

        # 2. Try iOS-LE fallback (non-escaped)
        resp = await self._try_send_command_with_framing(0x45, args_payload, timeout=3, use_ios=True, escape=False)
        if resp is not None:
            self.use_ios_le_protocol = True
            self.escapePayload = False
            existing = cache_data or {}
            existing.update({
                "write_characteristic_uuid": write_uuid,
                "ack_characteristic_uuid": self.NOTIFY_CHARACTERISTIC_UUID,
                "last_successful_payload": [f"{b:02x}" for b in args_payload],
                "last_successful_use_ios_le": True,
                "escapePayload": False,
            })
            try:
                await asyncio.to_thread(cache_mod.save_device_cache, cache_dir, device_id, existing)
            except OSError:
                pass
            return True

        return False

    async def _handle_cached_payload(self, write_uuid: str, cached_data: dict, cache_dir: str, device_id: str, cache_mod: Any = None):
        cache_mod = _get_cache_module(cache_mod)

        payload_hex = cached_data.get("last_successful_payload")
        if not payload_hex:
            return False

        try:
            payload = [int(x, 16) for x in payload_hex]
        except Exception:
            return False

        self.WRITE_CHARACTERISTIC_UUID = write_uuid
        use_ios = bool(cached_data.get("last_successful_use_ios_le", False))
        escape = bool(cached_data.get("escapePayload", False))

        resp = await self._try_send_command_with_framing(0x45, payload, timeout=3, use_ios=use_ios, escape=escape)
        if resp is not None:
            self.use_ios_le_protocol = use_ios
            self.escapePayload = escape
            existing = cached_data or {}
            existing.update({
                "write_characteristic_uuid": write_uuid,
                "ack_characteristic_uuid": self.NOTIFY_CHARACTERISTIC_UUID,
                "last_successful_payload": payload_hex,
                "last_successful_use_ios_le": use_ios,
                "escapePayload": escape,
            })
            try:
                await asyncio.to_thread(cache_mod.save_device_cache, cache_dir, device_id, existing)
            except OSError:
                pass
            return True
        return False

    async def probe_write_characteristics_and_try_channel_switch(self, write_chars: list, notify_chars: list, read_chars: list, cached_data: dict, cache_dir: str, device_id: str, colors: list = None, cache_mod: Any = None):
        cache_mod = _get_cache_module(cache_mod)

        colors = colors or [
            (0xFF, 0x00, 0x00),
            (0x00, 0xFF, 0x00),
            (0x00, 0x00, 0xFF),
            (0xFF, 0xFF, 0x00),
            (0xFF, 0x00, 0xFF),
            (0x00, 0xFF, 0xFF),
        ]

        for idx, ch in enumerate(write_chars):
            uuid = ch.uuid
            self.WRITE_CHARACTERISTIC_UUID = uuid

            # 1. Try cached payload first
            if cached_data and cached_data.get("last_successful_payload"):
                if await self._handle_cached_payload(uuid, cached_data, cache_dir, device_id, cache_mod):
                    return uuid

            # 2. Try diagnostic color payload
            r, g, b = colors[idx % len(colors)]
            args_payload = [0x01, r, g, b, 100, 0x00, 0x01]
            if await self._send_diagnostic_payload(uuid, args_payload, cached_data, cache_dir, device_id, cache_mod):
                return uuid

        # Fallback if nothing else worked
        try:
            await self.send_command(0x05, [0x09])
            await asyncio.sleep(0.1)
            await self.send_command(0x8a, [0x02])
            await asyncio.sleep(0.1)

            # Try SPP
            resp = await self._try_send_command_with_framing(0x45, [0x02], timeout=3, use_ios=False, escape=True)
            if resp is not None:
                self.use_ios_le_protocol = False
                self.escapePayload = True
                return None

            # Try iOS-LE
            resp = await self._try_send_command_with_framing(0x45, [0x02], timeout=3, use_ios=True, escape=False)
            if resp is not None:
                self.use_ios_le_protocol = True
                self.escapePayload = False
                return None
        except Exception:
            pass

        return None

    async def set_canonical_light(self, cache_dir: str, device_id: str, cache_mod: Any = None, rgb: list = None):
        cache_mod = _get_cache_module(cache_mod)

        rgb = rgb or [0xFF, 0xFF, 0xFF]
        args = [0x01] + rgb + [100, 0x00, 0x01]

        # 1. Try SPP
        resp = await self._try_send_command_with_framing(0x45, args, timeout=3, use_ios=False, escape=True)
        if resp is not None:
            self.use_ios_le_protocol = False
            self.escapePayload = True
            try:
                existing = await asyncio.to_thread(cache_mod.load_device_cache, cache_dir, device_id) or {}
                existing.update({
                    "last_successful_payload": [f"{b:02x}" for b in args],
                    "last_successful_use_ios_le": False,
                    "escapePayload": True,
                })
                await asyncio.to_thread(cache_mod.save_device_cache, cache_dir, device_id, existing)
            except OSError:
                pass
            return True

        # 2. Try iOS-LE
        resp = await self._try_send_command_with_framing(0x45, args, timeout=3, use_ios=True, escape=False)
        if resp is not None:
            self.use_ios_le_protocol = True
            self.escapePayload = False
            try:
                existing = await asyncio.to_thread(cache_mod.load_device_cache, cache_dir, device_id) or {}
                existing.update({
                    "last_successful_payload": [f"{b:02x}" for b in args],
                    "last_successful_use_ios_le": True,
                    "escapePayload": False,
                })
                await asyncio.to_thread(cache_mod.save_device_cache, cache_dir, device_id, existing)
            except OSError:
                pass
            return True

        return False
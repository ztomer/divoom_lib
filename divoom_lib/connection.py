# divoom_lib/connection.py

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional, Any
from bleak.exc import BleakError

from . import models, framing
from .exceptions import (
    DeviceAddressMissingError,
    CharacteristicConfigError,
    DeviceConnectionError,
)

def _get_cache_module(cache_mod=None):
    if cache_mod is not None:
        return cache_mod
    from .utils import cache as cache_mod
    return cache_mod

class DivoomConnection:
    """
    Handles BLE connection, queues, notification parsing, and raw sending
    on behalf of the Divoom orchestrator facade.
    """
    def __init__(self, divoom: Any, cfg: models.DivoomConfig):
        self._divoom = divoom
        self.mac = cfg.mac
        self.device_name = cfg.device_name
        self.WRITE_CHARACTERISTIC_UUID = cfg.write_characteristic_uuid
        self.NOTIFY_CHARACTERISTIC_UUID = cfg.notify_characteristic_uuid
        self.READ_CHARACTERISTIC_UUID = cfg.read_characteristic_uuid
        self.SPP_CHARACTERISTIC_UUID = cfg.spp_characteristic_uuid if cfg.spp_characteristic_uuid else models.DEFAULT_SPP_CHARACTERISTIC_UUID
        self.escapePayload = cfg.escapePayload
        self.use_ios_le_protocol = bool(cfg.use_ios_le_protocol)
        
        if cfg.client:
            self.client = cfg.client
        elif self.mac:
            from .divoom import BleakClient
            self.client = BleakClient(self.mac)
        else:
            self.client = None
        self.notification_queue = asyncio.Queue()
        self._expected_response_command = None
        self.message_buf = bytearray()
        self.max_reconnect_attempts = models.DEFAULT_MAX_RECONNECT_ATTEMPTS
        self.reconnect_delay = models.DEFAULT_RECONNECT_DELAY
        self.logger = divoom.logger

    @property
    def is_connected(self) -> bool:
        return bool(self.client and self.client.is_connected)

    async def connect(self) -> None:
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
            from .divoom import BleakClient
            self.client = BleakClient(self.mac)

        if not self.client.is_connected:
            try:
                await self.client.connect()
                self.logger.info(f"Connected to Divoom device at {self.mac}")
            except Exception as e:
                self.logger.error(f"Failed to connect to {self.mac}: {e}")
                raise DeviceConnectionError(f"Failed to connect to {self.mac}: {e}")

        if self.NOTIFY_CHARACTERISTIC_UUID:
            await self.client.start_notify(self.NOTIFY_CHARACTERISTIC_UUID, self._divoom.notification_handler)
            self.logger.info(f"Enabled notifications for {self.NOTIFY_CHARACTERISTIC_UUID}")
        else:
            self.logger.warning("No notify characteristic UUID set. Cannot enable notifications.")

        await asyncio.sleep(1.0)

    async def disconnect(self) -> None:
        if self.client and self.client.is_connected:
            try:
                await self.client.disconnect()
                self.logger.info("Disconnected from Divoom device at %s", self.mac)
            except Exception as e:
                self.logger.error("Error disconnecting from %s: %s", self.mac, e)

    def notification_handler(self, sender: int, data: bytearray) -> None:
        self._notification_handler(sender, data)

    def _notification_handler(self, sender: int, data: bytearray) -> None:
        if self.logger.isEnabledFor(logging.DEBUG):
            expected_cmd_str = f"0x{self._expected_response_command:02x}" if self._expected_response_command is not None else "None"
            self.logger.debug(
                "Notification from %s: use_ios_le=%s expected=%s data=%s",
                sender, self.use_ios_le_protocol, expected_cmd_str, data.hex())
        elif self.logger.isEnabledFor(logging.INFO):
            self.logger.info("Raw notification data: %s", data.hex())

        # Protocol-agnostic notification handling based on actual packet structure
        if len(data) >= 4 and data[0:4] == bytes(models.IOS_LE_HEADER):
            self._handle_ios_le_notification(data)
        else:
            self._handle_basic_protocol_notification(data)

    def _handle_ios_le_notification(self, data: bytes) -> bool:
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
            self.logger.warning(f"Unrecognized notification data (not iOS LE Protocol format): {data.hex()}")
        return False

    def _handle_basic_protocol_notification(self, new_data: bytearray) -> bool:
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
        return await self._divoom._wait_for_response(command_id, timeout)

    async def _wait_for_response(self, command_id: int, timeout: float = 10.0) -> bytes | None:
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

        self.logger.warning(f"Timeout waiting for notification response to command ID: 0x{command_id:02x}")
        return None

    async def send_command_and_wait_for_response(self, command: int | str, args: list | None = None, timeout: float = 10.0) -> bytes | None:
        if self.client is None or not self.client.is_connected:
            self.logger.error(f"Cannot send command '{command}': Not connected to a Divoom device.")
            return None

        command_id = models.COMMANDS.get(command, command) if isinstance(command, str) else command

        while not self.notification_queue.empty():
            self.notification_queue.get_nowait()
            self.logger.debug("Cleared a stale notification from the queue.")

        self._expected_response_command = command_id
        await self._divoom.send_command(command, args, write_with_response=True)
        return await self._divoom._wait_for_response(command_id, timeout)

    async def send_command(self, command: int | str, args: list | None = None, write_with_response: bool = False) -> bool:
        if args is None:
            args = []
        if isinstance(command, str):
            command_name = command
            command = models.COMMANDS[command]
        else:
            command_name = f"0x{command:02x}"

        self.logger.debug(f"Sending command: {command_name} (0x{command:02x}) with args: {args}")
        payload_bytes = [command] + args

        try:
            return await self._divoom._send_payload(payload_bytes, write_with_response=write_with_response)
        except Exception as e:
            self.logger.error(f"Error calling send_payload for command {command_name}: {e}")
            return False

    async def send_payload(self, payload_bytes: list, max_retries: int = 3, **kwargs) -> bool:
        return await self._divoom._send_payload(payload_bytes, max_retries=max_retries, **kwargs)

    async def _send_payload(self, payload_bytes: list, max_retries: int = 3, retry_delay: float = 0.1, write_with_response: bool = False) -> bool:
        for attempt in range(max_retries):
            backoff = retry_delay * (2 ** attempt)
            if self.client is None or not self.client.is_connected:
                self.logger.warning(f"Attempt {attempt + 1}: Not connected to a Divoom device. Retrying in {backoff}s...")
                await asyncio.sleep(backoff)
                if not self.client or not self.client.is_connected:
                    try:
                        await self._divoom.connect()
                        self.logger.info(f"Attempt {attempt + 1}: Reconnected to Divoom device at {self.mac}")
                    except Exception as e:
                        self.logger.error(f"Attempt {attempt + 1}: Failed to reconnect: {e}")
                        if attempt == max_retries - 1:
                            self.logger.error("Max retries reached. Giving up.")
                            return False
                        continue

            if self.use_ios_le_protocol:
                if await self._divoom._send_ios_le_payload(payload_bytes, write_with_response):
                    return True
                elif attempt == max_retries - 1:
                    return False
                await asyncio.sleep(backoff)
            else:
                if await self._divoom._send_basic_protocol_payload(payload_bytes, write_with_response):
                    return True
                elif attempt == max_retries - 1:
                    return False
                await asyncio.sleep(backoff)
        return False

    async def _send_ios_le_payload(self, payload_bytes: list, write_with_response: bool) -> bool:
        message_bytes = self._divoom._make_message_ios_le(payload_bytes)
        try:
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug("PAYLOAD OUT (iOS LE): %s", message_bytes.hex())
            await self.client.write_gatt_char(self.WRITE_CHARACTERISTIC_UUID, message_bytes, response=write_with_response)
            return True
        except Exception as e:
            self.logger.error(f"Error sending iOS LE payload: {e}")
            return False

    async def _send_basic_protocol_payload(self, payload_bytes: list, write_with_response: bool) -> bool:
        full_message = self._divoom._make_message(payload_bytes)
        chunk_size = models.DEFAULT_CHUNK_SIZE

        if len(full_message) > chunk_size:
            self.logger.debug(f"Message too long ({len(full_message)} bytes), splitting into chunks of {chunk_size} bytes.")
            chunks = [full_message[i:i + chunk_size] for i in range(0, len(full_message), chunk_size)]

            success = True
            for i, chunk in enumerate(chunks):
                try:
                    if self.logger.isEnabledFor(logging.DEBUG):
                        self.logger.debug("PAYLOAD OUT (Chunk %d/%d): %s", i + 1, len(chunks), chunk.hex())
                    chunk_response = write_with_response and (i == len(chunks) - 1)
                    await self.client.write_gatt_char(self.WRITE_CHARACTERISTIC_UUID, chunk, response=chunk_response)
                    await asyncio.sleep(0.05)
                except Exception as e:
                    self.logger.error(f"Error sending chunk {i+1}: {e}")
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

    def _make_message(self, payload_bytes: list) -> bytes:
        return framing.encode_basic_payload(payload_bytes, escape=self.escapePayload)

    def _make_message_ios_le(self, payload_bytes: list, packet_number: int = 0x00000000) -> bytes:
        return framing.encode_ios_le_payload(payload_bytes, packet_number=packet_number)

    async def _try_send_command_with_framing(self, command_id: int, payload: list, timeout: float = 3.0, use_ios: bool = False, escape: bool = False):
        self.use_ios_le_protocol = use_ios
        self.escapePayload = escape
        return await self._divoom.send_command_and_wait_for_response(command_id, payload, timeout=timeout)
 
    async def _send_diagnostic_payload(self, write_uuid: str, args_payload: list, cache_data: dict, cache_dir: str, device_id: str, cache_mod: Any = None):
        cache_mod = _get_cache_module(cache_mod)
        self.WRITE_CHARACTERISTIC_UUID = write_uuid
 
        # 1. Try SPP first (escaped)
        resp = await self._divoom._try_send_command_with_framing(0x45, args_payload, timeout=3.0, use_ios=False, escape=True)
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
        resp = await self._divoom._try_send_command_with_framing(0x45, args_payload, timeout=3.0, use_ios=True, escape=False)
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

        resp = await self._divoom._try_send_command_with_framing(0x45, payload, timeout=3.0, use_ios=use_ios, escape=escape)
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

            # Try cached payload first
            if cached_data and cached_data.get("last_successful_payload"):
                if await self._handle_cached_payload(uuid, cached_data, cache_dir, device_id, cache_mod):
                    return uuid

            # Try diagnostic color payload
            r, g, b = colors[idx % len(colors)]
            args_payload = [0x01, r, g, b, 100, 0x00, 0x01]
            if await self._send_diagnostic_payload(uuid, args_payload, cached_data, cache_dir, device_id, cache_mod):
                return uuid

        # Fallback if nothing else worked
        try:
            await self._divoom.send_command(0x05, [0x09])
            await asyncio.sleep(0.1)
            await self._divoom.send_command(0x8a, [0x02])
            await asyncio.sleep(0.1)
 
            # Try SPP
            resp = await self._divoom._try_send_command_with_framing(0x45, [0x02], timeout=3.0, use_ios=False, escape=True)
            if resp is not None:
                self.use_ios_le_protocol = False
                self.escapePayload = True
                return None
 
            # Try iOS-LE
            resp = await self._divoom._try_send_command_with_framing(0x45, [0x02], timeout=3.0, use_ios=True, escape=False)
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
        resp = await self._divoom._try_send_command_with_framing(0x45, args, timeout=3.0, use_ios=False, escape=True)
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
        resp = await self._divoom._try_send_command_with_framing(0x45, args, timeout=3.0, use_ios=True, escape=False)
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

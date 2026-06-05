# divoom_lib/ble_transport.py

import asyncio
import logging
import time
import os
from typing import Optional, Any
from .divoom import BleakClient
from bleak.exc import BleakError

from . import models, framing
from .transport_interface import DeviceTransport
from .exceptions import (
    DeviceAddressMissingError,
    CharacteristicConfigError,
    DeviceConnectionError,
)

class BLETransport(DeviceTransport):
    """
    Bluetooth Low Energy (BLE) transport client for Divoom devices.
    Implements the DeviceTransport interface.
    """
    def __init__(self, cfg: models.DivoomConfig, logger: logging.Logger, divoom: Any = None) -> None:
        self.mac = cfg.mac
        self.device_name = cfg.device_name
        self.logger = logger
        self._divoom = divoom
        
        self.WRITE_CHARACTERISTIC_UUID = cfg.write_characteristic_uuid
        self.NOTIFY_CHARACTERISTIC_UUID = cfg.notify_characteristic_uuid
        self.READ_CHARACTERISTIC_UUID = cfg.read_characteristic_uuid
        self.SPP_CHARACTERISTIC_UUID = cfg.spp_characteristic_uuid if cfg.spp_characteristic_uuid else models.DEFAULT_SPP_CHARACTERISTIC_UUID
        self.escapePayload = cfg.escapePayload
        self.use_ios_le_protocol = cfg.use_ios_le_protocol

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
        self._write_lock = asyncio.Lock()
        self._last_write_time = 0.0

    @property
    def is_connected(self) -> bool:
        return bool(self.client and self.client.is_connected)

    async def connect(self) -> None:
        if not self.mac:
            self.logger.error("No MAC address provided or discovered. Cannot connect.")
            raise DeviceAddressMissingError("No MAC address provided or discovered. Cannot connect.")

        is_mock = (self.client and "MockBleakClient" in self.client.__class__.__name__) or os.environ.get("DIVOOM_MOCK_BLE") in ("1", "true", "yes")

        # Resolve device name if not set
        if not is_mock and not self.device_name:
            if len(self.mac) == 17 and ("-" in self.mac or ":" in self.mac):
                try:
                    from IOBluetooth import IOBluetoothDevice
                    dev = IOBluetoothDevice.deviceWithAddressString_(self.mac.replace(":", "-"))
                    if dev:
                        self.device_name = dev.getName()
                except Exception:
                    pass
            if not self.device_name:
                try:
                    import json
                    from pathlib import Path
                    cache_file = Path.home() / ".config" / "divoom-control" / "discovered_devices.json"
                    if cache_file.exists():
                        devices = json.loads(cache_file.read_text(encoding="utf-8"))
                        for d in devices:
                            if d.get("address") == self.mac:
                                self.device_name = d.get("name")
                                break
                except Exception as e:
                    self.logger.debug(f"Failed to load device name from cache: {e}")

        if not all([self.WRITE_CHARACTERISTIC_UUID, self.NOTIFY_CHARACTERISTIC_UUID, self.READ_CHARACTERISTIC_UUID]):
            self.logger.error("Characteristic UUIDs not fully set. Cannot connect.")
            raise CharacteristicConfigError("Characteristic UUIDs not fully set. Cannot connect.")

        if self.client and self.client.is_connected:
            self.logger.info(f"Client already connected to {self.mac}. Skipping connection.")
            return

        if not is_mock:
            if not self.client or getattr(self.client, "address", None) != self.mac:
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
            cb = self._divoom.notification_handler if (self._divoom and hasattr(self._divoom, "notification_handler")) else self.notification_handler
            await self.client.start_notify(self.NOTIFY_CHARACTERISTIC_UUID, cb)
            self.logger.info(f"Enabled notifications for {self.NOTIFY_CHARACTERISTIC_UUID}")
        else:
            self.logger.warning("No notify characteristic UUID set. Cannot enable notifications.")

        await asyncio.sleep(1.0)

        # Dynamic Auto-Probing of BLE Protocol
        if self.use_ios_le_protocol is None:
            self.logger.info("use_ios_le_protocol not set. Probing BLE protocol format...")
            self.use_ios_le_protocol = True
            self.escapePayload = False
            self._expected_response_command = 0x46
            payload_bytes = [0x46]
            
            try:
                if await self._send_ios_le_payload(payload_bytes, write_with_response=True):
                    resp = await self.wait_for_response(0x46, timeout=1.5)
                    if resp is not None:
                        self.logger.info("Protocol probe succeeded: Detected iOS-LE Protocol BLE!")
                        self._expected_response_command = None
                        return
            except Exception as e:
                self.logger.debug(f"iOS-LE probe write raised: {e}")
            
            self.use_ios_le_protocol = False
            self.escapePayload = False
            self._expected_response_command = 0x46
            
            try:
                if await self._send_basic_protocol_payload(payload_bytes, write_with_response=True):
                    resp = await self.wait_for_response(0x46, timeout=1.5)
                    if resp is not None:
                        self.logger.info("Protocol probe succeeded: Detected Basic Protocol BLE!")
                        self._expected_response_command = None
                        return
            except Exception as e:
                self.logger.debug(f"Basic probe write raised: {e}")
            
            self.logger.info("Both BLE protocol probes failed. Defaulting to BLE Basic Protocol.")
            self.use_ios_le_protocol = False
            self.escapePayload = False
            self._expected_response_command = None

    async def disconnect(self) -> None:
        if self.client and self.client.is_connected:
            try:
                await self.client.disconnect()
                self.logger.info("Disconnected from Divoom device at %s", self.mac)
            except Exception as e:
                self.logger.error("Error disconnecting from %s: %s", self.mac, e)

    def notification_handler(self, sender: int, data: bytearray) -> None:
        if self.logger.isEnabledFor(logging.DEBUG):
            expected_cmd_str = f"0x{self._expected_response_command:02x}" if self._expected_response_command is not None else "None"
            self.logger.debug(
                "Notification from %s: use_ios_le=%s expected=%s data=%s",
                sender, self.use_ios_le_protocol, expected_cmd_str, data.hex())
        elif self.logger.isEnabledFor(logging.INFO):
            self.logger.info("Raw notification data: %s", data.hex())

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

    async def wait_for_response(self, command_id: int, timeout: float = 10.0) -> bytes | None:
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
        if not self.is_connected:
            self.logger.error(f"Cannot send command '{command}': Not connected to a Divoom device.")
            return None

        command_id = models.COMMANDS.get(command, command) if isinstance(command, str) else command

        while not self.notification_queue.empty():
            self.notification_queue.get_nowait()
            self.logger.debug("Cleared a stale notification from the queue.")

        self._expected_response_command = command_id
        await self.send_command(command, args, write_with_response=True)
        return await self.wait_for_response(command_id, timeout)

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
            return await self.send_payload(payload_bytes, write_with_response=write_with_response)
        except Exception as e:
            self.logger.error(f"Error calling send_payload for command {command_name}: {e}")
            return False

    async def send_payload(self, payload_bytes: list, max_retries: int = 3, **kwargs) -> bool:
        async with self._write_lock:
            now = time.time()
            elapsed = now - self._last_write_time
            if elapsed < 0.05:
                await asyncio.sleep(0.05 - elapsed)
            
            try:
                res = await self._send_payload_locked(payload_bytes, max_retries, **kwargs)
                return res
            finally:
                self._last_write_time = time.time()

    async def _send_payload_locked(self, payload_bytes: list, max_retries: int = 3, retry_delay: float = 0.1, write_with_response: bool = False) -> bool:
        for attempt in range(max_retries):
            backoff = retry_delay * (2 ** attempt)
            if not self.is_connected:
                self.logger.warning(f"Attempt {attempt + 1}: Not connected to a Divoom device. Retrying in {backoff}s...")
                await asyncio.sleep(backoff)
                if not self.is_connected:
                    try:
                        if self._divoom:
                            await self._divoom.connect()
                        else:
                            await self.connect()
                        self.logger.info(f"Attempt {attempt + 1}: Reconnected to Divoom device")
                    except Exception as e:
                        self.logger.error(f"Attempt {attempt + 1}: Failed to reconnect: {e}")
                        if attempt == max_retries - 1:
                            self.logger.error("Max retries reached. Giving up.")
                            return False
                        continue

            if self.use_ios_le_protocol:
                send_func = self._divoom._send_ios_le_payload if (self._divoom and hasattr(self._divoom, "_send_ios_le_payload")) else self._send_ios_le_payload
                if await send_func(payload_bytes, write_with_response):
                    return True
                elif attempt == max_retries - 1:
                    return False
                await asyncio.sleep(backoff)
            else:
                send_func = self._divoom._send_basic_protocol_payload if (self._divoom and hasattr(self._divoom, "_send_basic_protocol_payload")) else self._send_basic_protocol_payload
                if await send_func(payload_bytes, write_with_response):
                    return True
                elif attempt == max_retries - 1:
                    return False
                await asyncio.sleep(backoff)
        return False

    async def _send_ios_le_payload(self, payload_bytes: list, write_with_response: bool) -> bool:
        message_bytes = framing.encode_ios_le_payload(payload_bytes)
        try:
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug("PAYLOAD OUT (iOS LE): %s", message_bytes.hex())
            await self.client.write_gatt_char(self.WRITE_CHARACTERISTIC_UUID, message_bytes, response=write_with_response)
            return True
        except Exception as e:
            self.logger.error(f"Error sending iOS LE payload: {e}")
            return False

    async def _send_basic_protocol_payload(self, payload_bytes: list, write_with_response: bool) -> bool:
        full_message = framing.encode_basic_payload(payload_bytes, escape=self.escapePayload)
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

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
        self.max_reconnect_attempts = models.DEFAULT_MAX_RECONNECT_ATTEMPTS
        self.reconnect_delay = models.DEFAULT_RECONNECT_DELAY
        self.logger = divoom.logger

        self._use_spp = False
        self._spp_client = None
        self._spp_rx_task = None
        self._write_lock = asyncio.Lock()
        self._last_write_time = 0.0

    @property
    def is_connected(self) -> bool:
        if self._use_spp:
            return bool(self._spp_client and self._spp_client.is_connected)
        return bool(self.client and self.client.is_connected)

    @property
    def use_spp(self) -> bool:
        return self._use_spp

    async def connect(self) -> None:
        if not self.mac:
            self.logger.error("No MAC address provided or discovered. Cannot connect.")
            raise DeviceAddressMissingError("No MAC address provided or discovered. Cannot connect.")

        import os
        is_mock = (self.client and "MockBleakClient" in self.client.__class__.__name__) or os.environ.get("DIVOOM_MOCK_BLE") in ("1", "true", "yes")

        # Dynamically resolve device name if not set
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

        # Check if it is a classic device and configure SPP transport
        if not is_mock and self.device_name and not self.use_ios_le_protocol:
            name_lower = self.device_name.lower()
            if any(kw in name_lower for kw in ["timoo", "tivoo", "ditoo", "pixoo", "timebox", "divoom"]):
                if "pixoo 64" not in name_lower and "pixoo-64" not in name_lower:
                    self._use_spp = True

        if self._use_spp:
            if not self._spp_client:
                from .bt_spp_transport import BTSppTransport
                from . import spp_connection
                classic_mac = spp_connection.resolve_classic_mac(self.device_name, self.mac, log=self.logger)
                if classic_mac:
                    name_lower = self.device_name.lower()
                    device_kind = "default"
                    if "pixoo" in name_lower:
                        device_kind = "pixoo"
                    elif "timoo" in name_lower:
                        device_kind = "timoo"
                    elif "ditoo" in name_lower:
                        device_kind = "ditoo"
                    elif "tivoo" in name_lower:
                        device_kind = "tivoo"
                    self._spp_client = BTSppTransport(mac_address=classic_mac, device_kind=device_kind, logger=self.logger, device_name=self.device_name)
                    self.logger.info(f"Initialized BTSppTransport for {self.device_name} with classic MAC {classic_mac} (kind: {device_kind})")
                else:
                    self.logger.warning(f"Could not resolve Bluetooth Classic MAC for {self.device_name} (address: {self.mac}). Falling back to BLE.")
                    self._use_spp = False

        if self._use_spp:
            self.use_ios_le_protocol = False
            self.escapePayload = True
            if self._spp_client.is_connected:
                self.logger.info(f"SPP Client already connected to {self._spp_client.mac_address}. Skipping.")
                return
            try:
                await self._spp_client.connect()
                self.logger.info(f"Connected to Divoom device via BT Classic SPP at {self._spp_client.mac_address}")
                from . import spp_connection
                self._spp_rx_task = asyncio.create_task(spp_connection.read_spp_notifications_loop(self))
            except Exception as e:
                self.logger.error(f"Failed to connect via SPP to {self._spp_client.mac_address}: {e}")
                raise DeviceConnectionError(f"Failed to connect via SPP to {self._spp_client.mac_address}: {e}")
            return

        # BLE path validation
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

        # Dynamic Auto-Probing of BLE Protocol
        if self.use_ios_le_protocol is None and not self._use_spp:
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
                        return
            except Exception as e:
                self.logger.debug(f"Basic probe write raised: {e}")
            
            self.logger.info("Both BLE protocol probes failed. Defaulting to BLE Basic Protocol.")
            self.use_ios_le_protocol = False
            self.escapePayload = False

    async def disconnect(self) -> None:
        if self._use_spp:
            from . import spp_connection
            await spp_connection.disconnect_spp(self)
            return

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
        if not self.is_connected:
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
        async with self._write_lock:
            is_lan = getattr(self, "lan", None) is not None
            if not self._use_spp and not is_lan:
                now = time.time()
                elapsed = now - self._last_write_time
                if elapsed < 0.05:
                    await asyncio.sleep(0.05 - elapsed)
            
            try:
                res = await self._send_payload_locked(payload_bytes, max_retries, retry_delay, write_with_response)
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
                        await self._divoom.connect()
                        self.logger.info(f"Attempt {attempt + 1}: Reconnected to Divoom device")
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
        if self._use_spp:
            try:
                if self.logger.isEnabledFor(logging.DEBUG):
                    self.logger.debug("PAYLOAD OUT (SPP iOS LE): %s", bytes(payload_bytes).hex())
                await self._spp_client.send(payload_bytes, framing=self._spp_client.FRAMING_IOS_LE)
                return True
            except Exception as e:
                self.logger.error(f"Error sending iOS LE SPP payload: {e}")
                return False

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
        if self._use_spp:
            try:
                if self.logger.isEnabledFor(logging.DEBUG):
                    self.logger.debug("PAYLOAD OUT (SPP Basic): %s", bytes(payload_bytes).hex())
                await self._spp_client.send(payload_bytes, framing=self._spp_client.FRAMING_BASIC)
                return True
            except Exception as e:
                self.logger.error(f"Error sending Basic SPP payload: {e}")
                return False

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

    async def probe_write_characteristics_and_try_channel_switch(self, write_chars: list, notify_chars: list, read_chars: list, cached_data: dict, cache_dir: str, device_id: str, colors: list = None, cache_mod: Any = None):
        from . import probing
        return await probing.probe_write_characteristics_and_try_channel_switch(self, write_chars, notify_chars, read_chars, cached_data, cache_dir, device_id, colors, cache_mod)

    async def set_canonical_light(self, cache_dir: str, device_id: str, cache_mod: Any = None, rgb: list = None):
        from . import probing
        return await probing.set_canonical_light(self, cache_dir, device_id, cache_mod, rgb)

    async def _try_send_command_with_framing(self, command_id: int, payload: list, timeout: float = 3.0, use_ios: bool = False, escape: bool = False):
        from . import probing
        return await probing._try_send_command_with_framing(self, command_id, payload, timeout=timeout, use_ios=use_ios, escape=escape)

    async def _send_diagnostic_payload(self, write_uuid: str, args_payload: list, cache_data: dict, cache_dir: str, device_id: str, cache_mod: Any = None):
        from . import probing
        return await probing._send_diagnostic_payload(self, write_uuid, args_payload, cache_data, cache_dir, device_id, cache_mod)

    async def _handle_cached_payload(self, write_uuid: str, cached_data: dict, cache_dir: str, device_id: str, cache_mod: Any = None):
        from . import probing
        return await probing._handle_cached_payload(self, write_uuid, cached_data, cache_dir, device_id, cache_mod)



from divoom_lib.protocol import DivoomProtocol
from . import models
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

import asyncio
import logging
from bleak import BleakClient
from bleak.exc import BleakError

class Divoom:
    """
    A class to interact with a Divoom device over Bluetooth Low Energy (BLE).

    This class provides methods to connect to a Divoom device, send commands,
    and control its various features like display, channels, and system settings.
    """
    def __init__(self, mac: str | None = None, logger: logging.Logger | None = None, write_characteristic_uuid: str = "49535343-8841-43f4-a8d4-ecbe34729bb3", notify_characteristic_uuid: str = "49535343-1e4d-4bd9-ba61-23c647249616", read_characteristic_uuid: str = "49535343-1e4d-4bd9-ba61-23c647249616", spp_characteristic_uuid: str | None = None, escapePayload: bool = False, use_ios_le_protocol: bool = False, device_name: str | None = None, client: BleakClient | None = None) -> None:
        """
        Initializes the Divoom device controller.

        Args:
            mac (str | None): The MAC address of the Divoom device.
            logger (logging.Logger | None): An optional logger instance.
            write_characteristic_uuid (str): The UUID of the write characteristic.
            notify_characteristic_uuid (str): The UUID of the notify characteristic.
            read_characteristic_uuid (str | None): The UUID of the read characteristic.
            spp_characteristic_uuid (str | None): The UUID of the SPP characteristic.
            escapePayload (bool): Whether to escape the payload.
            use_ios_le_protocol (bool): Whether to use the iOS LE protocol.
            device_name (str | None): The name of the Divoom device.
        """
        self.protocol = DivoomProtocol(mac, logger, write_characteristic_uuid, notify_characteristic_uuid, read_characteristic_uuid, spp_characteristic_uuid, escapePayload, use_ios_le_protocol, device_name=device_name, client=client)
        
        self.light = Light(self.protocol)
        self.animation = Animation(self.protocol)
        self.drawing = Drawing(self.protocol)
        self.text = Text(self.protocol)
        
        self.device = Device(self.protocol)
        self.time = Time(self.protocol)
        self.bluetooth = Bluetooth(self.protocol)

        self.music = Music(self.protocol)
        self.radio = Radio(self.protocol)

        self.alarm = Alarm(self.protocol)
        self.sleep = Sleep(self.protocol)
        self.timeplan = Timeplan(self.protocol)

        self.scoreboard = Scoreboard(self.protocol)
        self.timer = Timer(self.protocol)
        self.countdown = Countdown(self.protocol)
        self.noise = Noise(self.protocol)

        self.logger = self.protocol.logger
        self.logger.debug("Divoom.__init__ called. protocol and modules initialized.")

    async def _try_send_command_with_framing(self, command_id: int, payload: list, timeout: int, use_ios: bool, escape: bool) -> bytes | None:
        """
        Helper function to send a command with specified framing options and return the response.
        """
        async with self.protocol._framing_context(use_ios, escape):
            resp = await self.protocol.send_command_and_wait_for_response(command_id, payload, timeout=timeout)
        return resp

    async def _send_diagnostic_payload(self, uuid: str, args_payload: list, device_cache: dict, cache_dir: str, device_id: str, cache_util) -> bool:
        """
        Sends a diagnostic color payload with SPP and iOS-LE framing and updates cache.
        Returns True if a response is received, False otherwise.
        """
        self.logger.info(f"Sending diagnostic color payload to {uuid}: {args_payload}")

        # SPP attempt
        resp_spp = await self._try_send_command_with_framing(
            models.COMMANDS["set light mode"],
            args_payload,
            timeout=3,
            use_ios=False,
            escape=True
        )
        if resp_spp is not None:
            self.logger.info(f"Response to SPP diagnostic payload on {uuid}: {resp_spp}")
            existing = device_cache or {}
            existing.update({
                "write_characteristic_uuid": uuid,
                "ack_characteristic_uuid": self.protocol.NOTIFY_CHARACTERISTIC_UUID,
                "last_successful_payload": [f"{b:02x}" for b in args_payload],
                "last_successful_use_ios_le": False,
                "escapePayload": True,
            })
            cache_util.save_device_cache(cache_dir, device_id, existing)
            return True

        # iOS-LE attempt
        resp_ios = await self._try_send_command_with_framing(
            models.COMMANDS["set light mode"],
            args_payload,
            timeout=3,
            use_ios=True,
            escape=getattr(self.protocol, "escapePayload", False) # Use current escapePayload setting
        )
        if resp_ios is not None:
            self.logger.info(f"Response to iOS-LE diagnostic payload on {uuid}: {resp_ios}")
            existing = device_cache or {}
            existing.update({
                "write_characteristic_uuid": uuid,
                "ack_characteristic_uuid": self.protocol.NOTIFY_CHARACTERISTIC_UUID,
                "last_successful_payload": [f"{b:02x}" for b in args_payload],
                "last_successful_use_ios_le": True,
                "escapePayload": getattr(self.protocol, "escapePayload", False),
            })
            cache_util.save_device_cache(cache_dir, device_id, existing)
            return True
        return False

    async def _handle_cached_payload(self, uuid: str, device_cache: dict, cache_dir: str, device_id: str, cache_util) -> bool:
        """
        Attempts to send a cached payload and updates the cache if successful.
        Returns True if a response is received, False otherwise.
        """
        if device_cache and device_cache.get("last_successful_payload"):
            payload_hex = device_cache.get("last_successful_payload")
            try:
                payload = [int(x, 16) for x in payload_hex]
            except Exception:
                payload = None

            if payload:
                resp = await self._try_send_command_with_framing(
                    models.COMMANDS["set light mode"],
                    payload,
                    timeout=3,
                    use_ios=bool(device_cache.get("last_successful_use_ios_le", self.protocol.use_ios_le_protocol)),
                    escape=bool(device_cache.get("escapePayload", self.protocol.escapePayload))
                )
                if resp is not None:
                    self.logger.info(f"Saved payload produced a response on {uuid}: {resp}")
                    # persist mapping and payload
                    existing = device_cache or {}
                    existing.update({
                        "write_characteristic_uuid": uuid,
                        "ack_characteristic_uuid": self.protocol.NOTIFY_CHARACTERISTIC_UUID,
                        "last_successful_payload": [f"{b:02x}" for b in payload],
                        "last_successful_use_ios_le": self.protocol.use_ios_le_protocol,
                        "escapePayload": self.protocol.escapePayload,
                    })
                    cache_util.save_device_cache(cache_dir, device_id, existing)
                    return True
        return False

    async def probe_write_characteristics_and_try_channel_switch(self, write_chars: list, notify_chars: list, read_chars: list, device_cache: dict, cache_dir: str, device_id: str, args: list, cache_util) -> str | None:
        """
        Probes write characteristics to find a working one and tries to switch channels.

        This method iterates through a list of write characteristics and attempts to
        send commands to find one that elicits a response from the device. It uses
        a cache to store and retrieve successful payloads. If no characteristic
        responds, it attempts a fallback channel switch sequence.

        Args:
            write_chars (list): A list of write characteristics to probe.
            notify_chars (list): A list of notify characteristics.
            read_chars (list): A list of read characteristics.
            device_cache (dict): A dictionary containing cached device information.
            cache_dir (str): The directory where the cache is stored.
            device_id (str): The ID of the device.
            args (list): A list of arguments for the command.
            cache_util: The cache utility object.

        Returns:
            str | None: The UUID of the working write characteristic, or None if none was found.
        """
        if not write_chars:
            self.logger.info("No writeable characteristics to probe.")
            return None

        colors = [
            (0xFF, 0x00, 0x00), (0x00, 0xFF, 0x00), (0x00, 0x00, 0xFF),
            (0xFF, 0xFF, 0x00), (0xFF, 0x00, 0xFF), (0x00, 0xFF, 0xFF),
        ]

        for idx, ch in enumerate(write_chars):
            uuid = ch.uuid
            self.logger.info(f"Probing write characteristic {uuid} ({idx+1}/{len(write_chars)})")
            prev_write = getattr(self.protocol, "WRITE_CHARACTERISTIC_UUID", None)
            self.protocol.WRITE_CHARACTERISTIC_UUID = uuid

            # 1) If cache has a saved payload, try that first on this characteristic
            if await self._handle_cached_payload(uuid, device_cache, cache_dir, device_id, cache_util):
                return uuid

            # 2) Send a distinguishing color payload for this characteristic
            r, g, b = colors[idx % len(colors)]
            args_payload = [models.PAYLOAD_START_BYTE_COLOR_MODE, r, g, b, 100, models.PAYLOAD_COLOR_MODE_UNKNOWN_BYTE_1, models.PAYLOAD_COLOR_MODE_UNKNOWN_BYTE_2]
            if await self._send_diagnostic_payload(uuid, args_payload, device_cache, cache_dir, device_id, cache_util):
                return uuid

            # restore previous write char if none succeeded for this char
            self.protocol.WRITE_CHARACTERISTIC_UUID = prev_write

        # Nothing produced a response during probing. Attempt fallback channel switch.
        self.logger.info("No write characteristic produced a response during probe. Falling back to single-character channel-switch attempt.")
        try:
            self.logger.info("Attempting channel-switch sequence: set work mode, power-on channel, then switch to channel 0x02")
            await self.protocol.send_command(models.COMMANDS["set work mode"], [models.WORK_MODE_CHANNEL_9])
            await asyncio.sleep(1.0)
            await self.protocol.send_command(models.COMMANDS["set poweron channel"], [models.CHANNEL_ID_2])
            await asyncio.sleep(1.0)

            # Try SPP first, then iOS-LE fallback for channel switch
            res = await self._try_send_command_with_framing(
                models.COMMANDS["set light mode"], [models.CHANNEL_ID_2], timeout=3, use_ios=False, escape=True
            )
            if res is not None:
                self.logger.info(f"Channel switch (SPP) succeeded: response={res}")
                return None # Or return a specific indicator if needed
            else:
                self.logger.info("No response for SPP channel switch; trying iOS-LE framing...")
                res2 = await self._try_send_command_with_framing(
                    models.COMMANDS["set light mode"], [models.CHANNEL_ID_2], timeout=3, use_ios=True, escape=getattr(self.protocol, "escapePayload", False)
                )
                if res2 is not None:
                    self.logger.info(f"Channel switch (iOS-LE) succeeded: response={res2}")
                    return None # Or return a specific indicator if needed
                else:
                    self.logger.info("Channel switch did not produce a response with either framing.")
        except (asyncio.TimeoutError, BleakError, RuntimeError, OSError) as e:
            self.logger.error(f"Error during channel-switch sequence: {e}")
        
        return None

    async def set_canonical_light(self, cache_dir: str, device_id: str, cache_util, rgb: list | None = None):
        """
        Sets a canonical light mode payload to the device.

        This method sends a standard 7-byte payload to set the light mode,
        trying both SPP and iOS-LE framing. If successful, it caches the
        working payload and framing method.

        Args:
            cache_dir (str): The directory where the cache is stored.
            device_id (str): The ID of the device.
            cache_util: The cache utility object.
            rgb (list | None): A list of three integers representing the RGB color.
                               Defaults to white [0xFF, 0xFF, 0xFF].

        Returns:
            bool: True if the command was successful, False otherwise.
        """
        # Build canonical 7-byte payload: [mode(1), R,G,B, brightness, effect_mode, on_off]
        mode = 0x01
        if rgb is None:
            rgb = [0xFF, 0xFF, 0xFF] # Default to white
        brightness = 100
        effect_mode = 0x00
        power_state = 0x01
        args = [mode] + rgb + [brightness, effect_mode, power_state]

        self.logger.info(
            f"Attempting canonical Light Mode payload: {[hex(x) for x in args]} (SPP)")
        ok = await self._try_send_command_with_framing(
            models.COMMANDS["set light mode"],
            args,
            timeout=3,
            use_ios=False,
            escape=self.protocol.escapePayload
        )
        if ok is not None:
            self.logger.info(f"Canonical (SPP) response: {ok}")
            # Save successful payload to cache
            try:
                existing = cache_util.load_device_cache(cache_dir, device_id) or {}
                existing.update({
                    "last_successful_payload": [f"{b:02x}" for b in args],
                    "last_successful_use_ios_le": False,
                    "escapePayload": self.protocol.escapePayload,
                })
                cache_util.save_device_cache(cache_dir, device_id, existing)
                self.logger.info(f"Persisted canonical SPP payload to cache for {device_id}")
            except OSError as e:
                self.logger.warning(f"Warning: failed to persist canonical payload: {e}")
            return True

        self.logger.info("No response for canonical (SPP). Trying iOS-LE framing...")
        ok2 = await self._try_send_command_with_framing(
            models.COMMANDS["set light mode"],
            args,
            timeout=3,
            use_ios=True,
            escape=self.protocol.escapePayload
        )
        if ok2 is not None:
            self.logger.info(f"Canonical (iOS-LE) response: {ok2}")
            try:
                existing = cache_util.load_device_cache(cache_dir, device_id) or {}
                existing.update({
                    "last_successful_payload": [f"{b:02x}" for b in args],
                    "last_successful_use_ios_le": True,
                    "escapePayload": self.protocol.escapePayload,
                })
                cache_util.save_device_cache(cache_dir, device_id, existing)
                self.logger.info(
                    f"Persisted canonical iOS-LE payload to cache for {device_id}")
            except OSError as e:
                self.logger.warning(f"Warning: failed to persist canonical payload: {e}")
            return True

        self.logger.info("Canonical payload did not produce a response.")
        return False

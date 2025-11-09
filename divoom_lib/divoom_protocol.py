from divoom_lib.base import DivoomBase

import asyncio
import json
import os
from pathlib import Path
import logging
import datetime
from bleak import BleakScanner, BleakClient
from bleak.exc import BleakError

from divoom_lib.utils import cache
from divoom_lib.utils import discovery


class Divoom(DivoomBase):
    """Class Divoom encapsulates the Divoom Bluetooth communication."""
    def __init__(self, mac=None, logger=None, write_characteristic_uuid="49535343-8841-43f4-a8d4-ecbe34729bb3", notify_characteristic_uuid="49535343-1e4d-4bd9-ba61-23c647249616", read_characteristic_uuid=None, spp_characteristic_uuid=None, escapePayload=False, use_ios_le_protocol=True, device_name=None):
        super().__init__(mac, logger, write_characteristic_uuid, notify_characteristic_uuid, read_characteristic_uuid, spp_characteristic_uuid, escapePayload, use_ios_le_protocol, device_name=device_name)
        self.logger.debug("Divoom.__init__ called. super().__init__ completed.")
        self.logger.debug(f"Divoom MRO: {Divoom.__mro__}")
        if hasattr(DivoomBase, 'send_command_and_wait_for_response'):
            self.logger.debug("DivoomBase HAS 'send_command_and_wait_for_response' attribute.")
        else:
            self.logger.error("DivoomBase DOES NOT HAVE 'send_command_and_wait_for_response' attribute.")

        if hasattr(self, 'send_command_and_wait_for_response'):
            self.logger.debug("Divoom instance HAS 'send_command_and_wait_for_response' attribute.")
        else:
            self.logger.error("Divoom instance DOES NOT HAVE 'send_command_and_wait_for_response' attribute.")


    async def probe_write_characteristics_and_try_channel_switch(self, write_chars: list, notify_chars: list, read_chars: list, cache: dict, cache_dir: str, device_id: str, args) -> str | None:
        """
        Probes discovered write characteristics to find one that elicits responses.
        Will send distinct colors per characteristic.
        """
        if not write_chars:
            self.logger.info("No writeable characteristics to probe.")
            return None

        colors = [
            (0xFF, 0x00, 0x00),
            (0x00, 0xFF, 0x00),
            (0x00, 0x00, 0xFF),
            (0xFF, 0xFF, 0x00),
            (0xFF, 0x00, 0xFF),
            (0x00, 0xFF, 0xFF),
        ]

        for idx, ch in enumerate(write_chars):
            uuid = ch.uuid
            self.logger.info(
                f"Probing write characteristic {uuid} ({idx+1}/{len(write_chars)})")
            # Temporarily set div instance to use this write characteristic
            prev_write = getattr(self, "WRITE_CHARACTERISTIC_UUID", None)
            self.WRITE_CHARACTERISTIC_UUID = uuid

            # 1) If cache has a saved payload, try that first on this characteristic
            if cache and cache.get("last_successful_payload"):
                payload_hex = cache.get("last_successful_payload")
                try:
                    payload = [int(x, 16) for x in payload_hex]
                except Exception:
                    payload = None
                if payload:
                    # Use stored framing preference for this attempt
                    prev_use_ios = self.use_ios_le_protocol
                    prev_escape = getattr(self, "escapePayload", False)
                    self.use_ios_le_protocol = bool(
                        cache.get("last_successful_use_ios_le", self.use_ios_le_protocol))
                    self.escapePayload = bool(
                        cache.get("escapePayload", self.escapePayload))
                    self.logger.info(
                        f"Trying saved payload on {uuid}: {[hex(x) for x in payload]} (use_ios={self.use_ios_le_protocol} escape={self.escapePayload})")
                    resp = await self.send_command_and_wait_for_response(0x45, payload, timeout=3)
                    # restore framing prefs
                    self.use_ios_le_protocol = prev_use_ios
                    self.escapePayload = prev_escape
                    if resp is not None:
                        self.logger.info(
                            f"Saved payload produced a response on {uuid}: {resp}")
                        # persist mapping and payload
                        existing = cache or {}
                        existing.update({
                            "write_characteristic_uuid": uuid,
                            "ack_characteristic_uuid": self.NOTIFY_CHARACTERISTIC_UUID,
                            "last_successful_payload": [f"{b:02x}" for b in payload],
                            "last_successful_use_ios_le": self.use_ios_le_protocol,
                            "escapePayload": self.escapePayload,
                        })
                        cache.save_device_cache(
                            cache_dir, device_id, existing)
                        return uuid

            # 2) Send a distinguishing color payload for this characteristic
            r, g, b = colors[idx % len(colors)]
            args_payload = [0x01, r, g, b, 100, 0x00, 0x01]
            self.logger.info(
                f"Sending diagnostic color payload to {uuid}: R={r} G={g} B={b}")

            # Try SPP first (escaped), then iOS-LE fallback
            prev_escape = getattr(self, "escapePayload", False)
            prev_use_ios = self.use_ios_le_protocol

            # SPP attempt
            self.escapePayload = True
            self.use_ios_le_protocol = False
            resp_spp = await self.send_command_and_wait_for_response(0x45, args_payload, timeout=3)
            if resp_spp is not None:
                self.logger.info(
                    f"Response to SPP diagnostic payload on {uuid}: {resp_spp}")
                existing = cache or {}
                existing.update({
                    "write_characteristic_uuid": uuid,
                    "ack_characteristic_uuid": self.NOTIFY_CHARACTERISTIC_UUID,
                    "last_successful_payload": [f"{b:02x}" for b in args_payload],
                    "last_successful_use_ios_le": False,
                    "escapePayload": self.escapePayload,
                })
                cache.save_device_cache(cache_dir, device_id, existing)
                # restore prefs
                self.escapePayload = prev_escape
                self.use_ios_le_protocol = prev_use_ios
                return uuid

            # iOS-LE attempt
            self.escapePayload = prev_escape
            self.use_ios_le_protocol = True
            resp_ios = await self.send_command_and_wait_for_response(0x45, args_payload, timeout=3)
            # restore prefs
            self.escapePayload = prev_escape
            self.use_ios_le_protocol = prev_use_ios
            if resp_ios is not None:
                self.logger.info(
                    f"Response to iOS-LE diagnostic payload on {uuid}: {resp_ios}")
                existing = cache or {}
                existing.update({
                    "write_characteristic_uuid": uuid,
                    "ack_characteristic_uuid": self.NOTIFY_CHARACTERISTIC_UUID,
                    "last_successful_payload": [f"{b:02x}" for b in args_payload],
                    "last_successful_use_ios_le": True,
                    "escapePayload": self.escapePayload,
                })
                cache.save_device_cache(cache_dir, device_id, existing)
                return uuid

            # restore previous write char if none succeeded for this char
            self.WRITE_CHARACTERISTIC_UUID = prev_write

        # Nothing produced a response during probing. Attempt fallback channel switch.
        self.logger.info("No write characteristic produced a response during probe. Falling back to single-character channel-switch attempt.")
        try:
            self.logger.info(
                "Attempting channel-switch sequence: set work mode, power-on channel, then switch to channel 0x02")
            await self.send_command(0x05, [0x09])
            await asyncio.sleep(1.0)
            await self.send_command(0x8a, [0x02])
            await asyncio.sleep(1.0)
            prev_escape = getattr(self, "escapePayload", False)
            self.escapePayload = True
            self.use_ios_le_protocol = False
            res = await self.send_command_and_wait_for_response(0x45, [0x02], timeout=3)
            if res is not None:
                self.logger.info(
                    f"Channel switch (SPP) succeeded: response={res}")
            else:
                self.logger.info(
                    "No response for SPP channel switch; trying iOS-LE framing...")
                self.escapePayload = prev_escape
                self.use_ios_le_protocol = True
                res2 = await self.send_command_and_wait_for_response(0x45, [0x02], timeout=3)
                if res2 is not None:
                    self.logger.info(
                        f"Channel switch (iOS-LE) succeeded: response={res2}")
                else:
                    self.logger.info(
                        "Channel switch did not produce a response with either framing.")
            self.escapePayload = prev_escape
        except (asyncio.TimeoutError, BleakError, RuntimeError, OSError) as e:
            self.logger.error(f"Error during channel-switch sequence: {e}")
        
        return None
        """If cache contains a last_successful_payload entry, try it once."""
        if not cache:
            self.logger.info("No device cache available.")
            return False

        payload_hex = cache.get("last_successful_payload")
        if not payload_hex:
            self.logger.info("No saved payload in cache.")
            return False

        try:
            payload = [int(x, 16) for x in payload_hex]
        except ValueError as e:
            self.logger.error(f"Failed to decode saved payload: {e}")
            return False

        use_ios = bool(cache.get("last_successful_use_ios_le", True))
        write_char = cache.get("write_characteristic_uuid")
        if write_char:
            self.WRITE_CHARACTERISTIC_UUID = write_char

        # Apply saved framing/escaping preferences to the divoom instance
        self.use_ios_le_protocol = use_ios
        self.escapePayload = bool(
            cache.get("escapePayload", self.escapePayload))

        self.logger.info(
            f"Trying saved payload on {self.mac} using {'iOS-LE' if use_ios else 'SPP'} framing: {payload}")
        # send_command expects a command id; saved payload is inner args for 0x45
        res = await self.send_command_and_wait_for_response(0x45, payload, timeout=4)
        if res is not None:
            self.logger.info(f"Saved payload produced a response: {res}")
            # Persist successful payload and framing preferences
            try:
                existing = cache or {}
                existing.update({
                    "last_successful_payload": payload_hex,
                    "last_successful_use_ios_le": bool(use_ios),
                    "escapePayload": self.escapePayload,
                })
                cache.save_device_cache(cache_dir, device_id, existing)
                self.logger.info(f"Persisted successful payload to cache for {device_id}")
            except OSError as e:
                self.logger.warning(f"Warning: failed to persist successful payload: {e}")
            return True
        else:
            self.logger.info("Saved payload did not elicit a response (timeout or no notify)")



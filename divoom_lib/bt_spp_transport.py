"""
bt_spp_transport.py — Bluetooth Classic RFCOMM SPP transport for Divoom devices.

Transport: 🔵 BT Classic SPP (RFCOMM channel over Bluetooth 2.x/EDR)

Used by the official Divoom iOS/Android apps (per APK reverse-engineering at
``references/apk/decompiled_src/sources/com/divoom/Divoom/bluetooth/c.java:36``
and ``p.java:18``) for Timoo/Ditoo/Tivoo (channel 2) and Pixoo-16x16 (channel 1).
BLE does not work for these devices — they speak BT Classic only.

Dependencies:
    pyobjc-framework-IOBluetooth >= 10.0  (MIT, v12.2 verified)

Workarounds baked in:
    * Chromium FB13705522 — the delegate holds a strong self-reference so it
      survives across the run-loop turn that delivers the open/data callbacks.
    * Dedicated background thread pumping ``NSRunLoop.runUntilDate:`` with
      ``NSRunLoopCommonModes`` (Bluetooth sources may not register in
      ``NSDefaultRunLoopMode``).

macOS daemon caveat (Phase 8 of docs/CODE_REVIEW.md):
    This transport is BLOCKED on macOS Tahoe 26.5.1 by a known SPP
    reconnection bug in ``IOUserBluetoothSerialDriver`` (DriverKit
    extension, root-owned). ``openRFCOMMChannelAsync_`` returns
    ``kIOReturnSuccess`` but the open callback never fires, and
    ``writeSync`` on the "open" channel returns ``kIOReturnNotOpen``
    (-536870195). Fix: ``sudo pkill bluetoothd`` (drops keyboard/mouse/
    headphones) or wait for the macOS 27 release.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
from dataclasses import dataclass, field
from typing import Optional

from . import framing
from .framing import (
    encode_basic_payload,
    encode_ios_le_payload,
    parse_basic_protocol_frames,
    parse_ios_le_notification,
)


# ── Channel IDs (per official Divoom APK analysis) ────────────────────────────
# Pixoo 16x16 uses RFCOMM channel 1; Timoo, Ditoo, Tivoo, Tivoo-Max use 2.
# Channel 2 is the SPP data channel; channel 1 on Tivoo-class is a beacon
# stream (FF 55 02 00 EE 10) that does NOT respond to HP+/iOS-LE commands.
DEFAULT_RFCOMM_CHANNEL_IDS: dict[str, int] = {
    "pixoo": 1,
    "timoo": 2,
    "ditoo": 2,
    "tivoo": 2,
    "tivoo_max": 2,
    "default": 2,
}


# ── Public data types ────────────────────────────────────────────────────────


@dataclass
class BtSppNotification:
    """A single notification received from the device over RFCOMM."""

    command_id: int
    payload: bytes
    framing: str  # "basic" or "ios_le"
    packet_number: int = 0
    raw: bytes = field(default=b"")


class BtSppTransportError(RuntimeError):
    """Raised when the BT Classic SPP transport fails to open/write/read."""


# ── Transport ────────────────────────────────────────────────────────────────


class BTSppTransport:
    """
    Async wrapper around macOS IOBluetooth RFCOMM SPP for Divoom devices.

    Transport: 🔵 BT Classic SPP (RFCOMM, channel 1=Pixoo, 2=Timoo/Ditoo/Tivoo)

    Usage::

        from divoom_lib.bt_spp_transport import BTSppTransport

        async def main():
            spp = BTSppTransport(mac_address="11-75-58-54-b9-13")
            await spp.connect()
            try:
                await spp.send([0x45])  # set light color, basic SPP
                notif = await spp.read_notification(timeout=2.0)
                print(f"got {notif.command_id:#x} -> {notif.payload.hex()}")
            finally:
                await spp.disconnect()

    Note: this transport is currently blocked on macOS Tahoe 26.5.1 by a
    kernel-side SPP reconnection bug. See ``docs/CODE_REVIEW.md`` Phase 8.
    """

    # ── Tunables ──────────────────────────────────────────────────────────────

    OPEN_TIMEOUT_S: float = 8.0
    DEFAULT_READ_TIMEOUT_S: float = 3.0
    FRAMING_BASIC: str = "basic"
    FRAMING_IOS_LE: str = "ios_le"

    # ── Construction ──────────────────────────────────────────────────────────

    def __init__(
        self,
        mac_address: str,
        channel_id: int | None = None,
        device_kind: str = "default",
        logger: logging.Logger | None = None,
        device_name: str | None = None,
    ) -> None:
        """
        Args:
            mac_address:  BT Classic MAC in the form ``"11-75-58-54-b9-13"``.
                          (NOT the BLE UUID — that's a different identifier.)
            channel_id:   RFCOMM channel number. ``None`` (default) looks up
                          the channel via ``device_kind`` (Pixoo → 1,
                          Timoo/Ditoo/Tivoo → 2). Pass an int to override.
            device_kind:  One of the keys in ``DEFAULT_RFCOMM_CHANNEL_IDS``.
            logger:       Optional logger.
            device_name:  Optional device name (e.g. "Timoo-audio-4") used to match macOS serial ports.
        """
        self.mac_address = mac_address
        self.device_name = device_name
        self.channel_id = (
            channel_id
            if channel_id is not None
            else DEFAULT_RFCOMM_CHANNEL_IDS.get(device_kind, 2)
        )
        self.logger = logger or logging.getLogger("divoom.bt_spp")

        self._device = None  # IOBluetoothDevice
        self._channel = None  # IOBluetoothRFCOMMChannel
        self._delegate = None  # RFCOMMDelegate (held alive)
        self._runloop_thread: Optional[threading.Thread] = None
        self._runloop = None  # NSRunLoop on the background thread
        self._open_event = threading.Event()
        self._close_event = threading.Event()
        self._rx_queue: queue.Queue[BtSppNotification] = queue.Queue()
        self._rx_buf = bytearray()
        self._write_lock = threading.Lock()
        self._last_error: Optional[str] = None

        # macOS Serial (pyserial) fallback driver state
        self._serial_port = None
        self._serial_read_thread: Optional[threading.Thread] = None

    # ── Public API ────────────────────────────────────────────────────────────

    def _find_serial_port(self) -> str | None:
        if not self.device_name:
            return None
        import glob
        ports = glob.glob("/dev/cu.*")
        
        # Exact match (case insensitive, alphanumeric only)
        sanitized_target = self.device_name.lower().replace("-", "").replace(" ", "").replace("_", "")
        for p in ports:
            sanitized_p = p.lower().replace("-", "").replace(" ", "").replace("_", "")
            if sanitized_target in sanitized_p or sanitized_p in sanitized_target:
                return p
        
        # Prefix match
        parts = self.device_name.split("-")
        prefix = parts[0].strip()
        if len(prefix) >= 3:
            for p in ports:
                if prefix.lower() in p.lower():
                    return p
        return None

    def _serial_read_loop(self) -> None:
        while not self._close_event.is_set():
            port = self._serial_port
            if not port or not port.is_open:
                break
            try:
                # Small chunk read, blocking with timeout on serial
                chunk = port.read(32)
                if chunk:
                    self._on_data(chunk)
            except Exception as e:
                self.logger.debug(f"Serial read loop exception: {e}")
                break

    async def connect(self) -> None:
        """
        Open the RFCOMM channel.

        Raises:
            BtSppTransportError: if the open does not complete within
                ``OPEN_TIMEOUT_S`` or returns a non-zero status.
        """
        if self.is_connected:
            self.logger.debug("BTSppTransport already connected")
            return

        self._close_event.clear()
        self._rx_queue = queue.Queue()
        self._rx_buf = bytearray()

        # macOS Tahoe SPP bug workaround: Try standard POSIX serial port (pyserial) first
        import sys
        if sys.platform == "darwin":
            try:
                import serial
                port = self._find_serial_port()
                if port:
                    self.logger.info(f"macOS: Found matching virtual serial port: {port}. Connecting...")
                    self._serial_port = serial.Serial(port, 115200, timeout=1.0)
                    self.logger.info("macOS: Connected. Stabilizing serial link for 2.0 seconds...")
                    await asyncio.sleep(2.0)
                    
                    self._serial_read_thread = threading.Thread(
                        target=self._serial_read_loop, name="bt-spp-serial-read", daemon=True
                    )
                    self._serial_read_thread.start()
                    self.logger.info(f"macOS: Serial transport connected successfully on {port}!")
                    return
            except Exception as e:
                self.logger.warning(f"macOS: Serial transport connection failed: {e}. Falling back to IOBluetooth...")
                if self._serial_port:
                    try:
                        self._serial_port.close()
                    except Exception:
                        pass
                    self._serial_port = None

        self._start_runloop()
        # Run the IOBluetooth call on the background thread so the async
        # callback's NSRunLoop is the one that's pumping.
        await asyncio.to_thread(self._open_blocking)
        if not self._open_event.wait(timeout=self.OPEN_TIMEOUT_S):
            raise BtSppTransportError(
                f"RFCOMM open to {self.mac_address} channel {self.channel_id} "
                f"timed out after {self.OPEN_TIMEOUT_S}s. This is the macOS "
                f"Tahoe SPP reconnection bug — see docs/CODE_REVIEW.md Phase 8."
            )
        if self._last_error:
            raise BtSppTransportError(
                f"RFCOMM open to {self.mac_address} channel {self.channel_id} "
                f"failed: {self._last_error}"
            )
        self.logger.info(
            f"BT Classic SPP open: {self.mac_address} channel {self.channel_id} "
            f"mtu={self._channel.getMTU()}"
        )

    async def disconnect(self) -> None:
        """Close the RFCOMM channel or serial port and tear down threads."""
        self._close_event.set()
        
        # 1. Serial port cleanup
        if self._serial_port:
            try:
                self._serial_port.close()
            except Exception as e:
                self.logger.debug(f"serial close raised: {e}")
            self._serial_port = None
        if self._serial_read_thread is not None:
            await asyncio.to_thread(self._serial_read_thread.join, 2.0)
            self._serial_read_thread = None

        # 2. IOBluetooth cleanup
        if self._channel is not None:
            try:
                self._channel.close()
            except Exception as e:
                self.logger.debug(f"close() raised: {e}")
            self._channel = None
        if self._runloop_thread is not None:
            await asyncio.to_thread(self._runloop_thread.join, 2.0)
            self._runloop_thread = None
            
        self._device = None
        self._delegate = None
        self._runloop = None
        self._open_event.clear()

    async def send(
        self,
        payload: list[int],
        framing: str = FRAMING_BASIC,
        packet_number: int = 0,
    ) -> None:
        """
        Send a single command.

        Args:
            payload:       ``[cmd, data...]`` byte list.
            framing:       ``FRAMING_BASIC`` (default, ``0x01 … 0x02``) or
                           ``FRAMING_IOS_LE`` (the iOS-LE wire format).
            packet_number: Used only by iOS-LE.
        """
        if not self.is_connected:
            raise BtSppTransportError("not connected; call connect() first")
        
        if framing == self.FRAMING_BASIC:
            frame = encode_basic_payload(payload)
        elif framing == self.FRAMING_IOS_LE:
            frame = encode_ios_le_payload(payload, packet_number=packet_number)
        else:
            raise ValueError(f"unknown framing: {framing!r}")

        # Serial transport route
        if self._serial_port and self._serial_port.is_open:
            def _do_serial_write():
                with self._write_lock:
                    if self._serial_port is None:
                        raise BtSppTransportError("serial port closed during write")
                    self._serial_port.write(frame)
                    self._serial_port.flush()

            await asyncio.to_thread(_do_serial_write)
            self.logger.debug(f"[BT-SPP-Serial 🔵] sent ({framing}): {frame.hex()}")
            return

        # IOBluetooth fallback route
        def _do_write():
            with self._write_lock:
                if self._channel is None:
                    raise BtSppTransportError("channel closed during write")
                rc = self._channel.writeSync_length_(frame, len(frame))
                if rc != 0:
                    raise BtSppTransportError(
                        f"writeSync_length_ returned {rc} (0x{rc & 0xFFFFFFFF:08X})"
                    )

        await asyncio.to_thread(_do_write)
        self.logger.debug(f"[BT-SPP 🔵] sent ({framing}): {frame.hex()}")

    async def read_notification(
        self, timeout: float = DEFAULT_READ_TIMEOUT_S
    ) -> BtSppNotification:
        """
        Wait for the next parsed notification from the device.

        Args:
            timeout: seconds to wait before raising ``asyncio.TimeoutError``.
        """
        loop = asyncio.get_running_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, self._rx_queue.get, True, timeout),
                timeout=timeout + 0.5,
            )
        except queue.Empty:
            raise asyncio.TimeoutError(
                f"no notification within {timeout}s on {self.mac_address}"
            )

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        if self._serial_port is not None:
            return self._serial_port.is_open and not self._close_event.is_set()
        return self._channel is not None and not self._close_event.is_set()

    @property
    def mtu(self) -> int:
        if self._serial_port is not None:
            return 200 # Standard MTU for Divoom Serial
        return int(self._channel.getMTU()) if self._channel else 0

    # ── Internal: run-loop thread + ObjC glue ─────────────────────────────────

    def _start_runloop(self) -> None:
        if self._runloop_thread is not None and self._runloop_thread.is_alive():
            return
        self._open_event.clear()
        self._close_event.clear()
        self._rx_queue = queue.Queue()
        self._rx_buf = bytearray()
        self._runloop_thread = threading.Thread(
            target=self._runloop_main, name="bt-spp-runloop", daemon=True
        )
        self._runloop_thread.start()
        # Wait for the run loop to be ready
        for _ in range(50):
            if self._runloop is not None:
                return
            import time as _t
            _t.sleep(0.02)

    def _runloop_main(self) -> None:
        import objc
        from Foundation import (
            NSDate,
            NSRunLoop,
            NSRunLoopCommonModes,
        )

        self._runloop = NSRunLoop.currentRunLoop()
        # Pump common modes — Bluetooth sources may not register in the
        # default mode. Each turn is a 50 ms slice.
        while not self._close_event.is_set():
            self._runloop.runMode_beforeDate_(
                NSRunLoopCommonModes,
                NSDate.dateWithTimeIntervalSinceNow_(0.05),
            )
        # Hold a reference to objc so the import isn't optimized away.
        _ = objc.__name__

    def _discover_rfcomm_channel(self, device) -> int | None:
        try:
            self.logger.debug(f"Performing SDP query for {self.mac_address} to find RFCOMM channel...")
            device.performSDPQuery_(None)
            import time
            services = []
            for _ in range(30):
                services = device.services() or []
                if services:
                    break
                time.sleep(0.1)
            
            for s in services:
                try:
                    name = s.getServiceName()
                    if name and "serial" in name.lower():
                        rfcomm_channel = -1
                        try:
                            rc, chan = s.getRFCOMMChannelID_(None)
                            if rc == 0:
                                rfcomm_channel = chan
                        except Exception:
                            try:
                                rfcomm_channel = s.getRFCOMMChannelID()
                            except Exception:
                                pass
                        if rfcomm_channel > 0:
                            return rfcomm_channel
                except Exception:
                    pass

            for s in services:
                try:
                    rfcomm_channel = -1
                    try:
                        rc, chan = s.getRFCOMMChannelID_(None)
                        if rc == 0:
                            rfcomm_channel = chan
                    except Exception:
                        try:
                            rfcomm_channel = s.getRFCOMMChannelID()
                        except Exception:
                            pass
                    if rfcomm_channel > 0:
                        return rfcomm_channel
                except Exception:
                    pass
        except Exception as e:
            self.logger.warning(f"Error during SDP query discovery: {e}")
        return None

    def _open_blocking(self) -> None:
        """Run on the run-loop thread (via to_thread). Opens the channel."""
        import objc
        from IOBluetooth import IOBluetoothDevice
        from Foundation import NSObject

        outer = self

        class _Delegate(NSObject):
            """RFCOMM channel delegate. Must be at module scope to be findable
            by the ObjC runtime; using a closure keeps it scoped to this call.
            """

            def init(self):
                self = objc.super(_Delegate, self).init()
                # Strong self-ref per Chromium FB13705522 workaround.
                self._self_ref = self
                return self

            def rfcommChannelOpenComplete_status_(self, ch, status):
                status = int(status)
                if status != 0:
                    outer._last_error = f"open status={status} (0x{status & 0xFFFFFFFF:08X})"
                outer._open_event.set()

            def rfcommChannelData_data_length_(self, ch, data, length):
                n = int(length) if length else 0
                if not n:
                    return
                chunk = bytes(data[:n])
                outer._on_data(chunk)

            def rfcommChannelClosed_(self, ch):
                outer._close_event.set()

        try:
            device = IOBluetoothDevice.deviceWithAddressString_(self.mac_address)
            if device is None:
                self._last_error = (
                    f"IOBluetoothDevice.deviceWithAddressString_ returned nil "
                    f"for {self.mac_address!r}"
                )
                self._open_event.set()
                return
            self._device = device

            # Dynamically discover RFCOMM channel from SDP query if possible
            discovered_channel = self._discover_rfcomm_channel(device)
            if discovered_channel is not None:
                if discovered_channel != self.channel_id:
                    self.logger.info(
                        f"SDP Query: Overriding default RFCOMM channel {self.channel_id} "
                        f"with discovered channel {discovered_channel} for {self.mac_address}"
                    )
                    self.channel_id = discovered_channel

            delegate = _Delegate.alloc().init()
            # Retain on the outer to keep it alive even if PyObjC autoreleases.
            delegate.retain()
            self._delegate = delegate

            rc, channel = device.openRFCOMMChannelAsync_withChannelID_delegate_(
                None, self.channel_id, delegate
            )
            rc = int(rc)
            if rc != 0:
                self._last_error = (
                    f"openRFCOMMChannelAsync_ returned {rc} (0x{rc & 0xFFFFFFFF:08X})"
                )
                self._open_event.set()
                return
            self._channel = channel
            # If open doesn't actually fire the callback (macOS daemon bug),
            # the timeout in connect() will raise. Don't pre-empt it here.
        except Exception as e:
            self._last_error = f"exception in _open_blocking: {e!r}"
            self._open_event.set()

    def _on_data(self, chunk: bytes) -> None:
        """Called on the run-loop thread for every inbound chunk."""
        from . import models

        self._rx_buf.extend(chunk)
        # Try iOS-LE first — it's a fixed-size framed format.
        # Use the length field (bytes 4..5) to know exactly where the frame
        # ends; the parser is given only the slice, not the whole buffer,
        # otherwise it would consume bytes from the next frame.
        while (
            len(self._rx_buf) >= models.IOS_LE_MIN_DATA_LENGTH
            and bytes(self._rx_buf[:4]) == bytes(models.IOS_LE_HEADER)
        ):
            length_field = int.from_bytes(self._rx_buf[4:6], "little")
            frame_len = length_field + 7
            if len(self._rx_buf) < frame_len:
                break  # incomplete iOS-LE frame
            parsed = parse_ios_le_notification(bytes(self._rx_buf[:frame_len]))
            if parsed is None:
                # Malformed header — drop the leading 0xFE so we can resync.
                del self._rx_buf[0]
                continue
            raw = bytes(self._rx_buf[:frame_len])
            del self._rx_buf[:frame_len]
            self._rx_queue.put(
                BtSppNotification(
                    command_id=parsed["command_id"],
                    payload=parsed["payload"],
                    framing=self.FRAMING_IOS_LE,
                    packet_number=parsed["packet_number"],
                    raw=raw,
                )
            )
        # Then drain basic SPP frames — the parser modifies the buffer
        # in place, so only call it when there's something to chew on.
        if self._rx_buf and (
            len(self._rx_buf) < 4
            or bytes(self._rx_buf[:4]) != bytes(models.IOS_LE_HEADER)
        ):
            msgs, remaining = parse_basic_protocol_frames(bytearray(self._rx_buf))
            self._rx_buf = bytearray(remaining)
            for m in msgs:
                self._rx_queue.put(
                    BtSppNotification(
                        command_id=m["command_id"],
                        payload=bytes(m["payload"]),
                        framing=self.FRAMING_BASIC,
                        raw=b"",
                    )
                )

    # ── Async context manager sugar ──────────────────────────────────────────

    async def __aenter__(self) -> "BTSppTransport":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.disconnect()

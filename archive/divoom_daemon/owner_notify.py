"""Notification-sender concern for the daemon's DeviceOwner.

Split out of ``device_owner.py`` (R44/BLE-hardening housekeeping) to keep that
module under the 500-LOC budget. NotificationService calls
``send_notification``; it prefers an injected sender and otherwise drives the
BLE device directly on a throwaway loop.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("divoom_daemon.device_owner")


class OwnerNotifyMixin:
    """Provides ``send_notification`` for NotificationService. Expects the host
    to define ``_device_sender``, ``_device``, and ``mac``."""

    def send_notification(self, app_type: int, text: str) -> None:
        if self._device_sender is not None:
            self._device_sender(app_type, text)
            return
        self._send_to_device_ble(app_type, text)

    def _send_to_device_ble(self, app_type: int, text: str) -> None:
        # Route through the daemon's ONE device loop + command queue — NEVER a
        # private throwaway loop. A Divoom built/driven on a throwaway loop binds
        # its bleak client to THAT loop, so the persistent device loop can no longer
        # use self._device ("Future attached to a different loop") and two loops
        # driving one GATT link corrupt it. _ensure_device_async manages self._device
        # on the loop with honest is_alive + bounded reconnect; _run_device's
        # result-timeout bounds a wedged push (the old throwaway path had NO timeout).
        # We RAISE on no-reachable-device so NotificationService records routed=False
        # (it keys routed off raise-vs-no-raise; the old `return` lied routed=True).
        if getattr(self, "_loop", None) is None:
            self._device_loop()

        async def _do():
            dev = await self._ensure_device_async(self.mac)
            if dev is None:
                raise RuntimeError("no Divoom device to route notification to")
            if text:
                await dev.notification.show_notification_text(int(app_type), text)
            else:
                await dev.notification.show_notification(int(app_type))

        self._run_device(_do())

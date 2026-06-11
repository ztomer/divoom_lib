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
        import asyncio
        from divoom_lib.divoom import Divoom
        from divoom_lib.utils import discovery

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            if not getattr(self, "_device", None) or not self._device.is_connected:
                mac = self.mac
                if not mac:
                    from divoom_daemon.daemon_config import load_daemon_config
                    devs = loop.run_until_complete(discovery.discover_all_divoom_devices(
                        timeout=load_daemon_config().reconnect_scan_timeout))
                    if not devs:
                        return
                    mac = devs[0]["address"]
                self._device = Divoom(mac=mac, logger=logger, use_ios_le_protocol=False)
                loop.run_until_complete(self._device.connect())
            if text:
                loop.run_until_complete(self._device.notification.show_notification_text(int(app_type), text))
            else:
                loop.run_until_complete(self._device.notification.show_notification(int(app_type)))
        finally:
            loop.close()

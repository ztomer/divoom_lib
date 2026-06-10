"""Notification monitoring service — macOS Notification Center listener + routing."""
from __future__ import annotations

import logging
import sys
from typing import Callable, Optional

from divoom_daemon.daemon_protocol import make_status_event, make_notification_event

logger = logging.getLogger("divoom_daemon.notification_service")

STATE_ACTIVE = "active"
STATE_IDLE = "idle"
STATE_ERROR = "error"


class NotificationService:
    """Manages the macOS notification monitor lifecycle, routes notifications to
    the device, and pushes events to subscribers via a broadcast callback."""

    def __init__(
        self,
        *,
        broadcast: Callable[[dict], None],
        send_notification: Callable[[int, str], None],
        monitor=None,
    ):
        self._broadcast = broadcast
        self._send_notification = send_notification
        self._monitor = monitor
        self._error: Optional[str] = None

    # ── monitor (lazy, macOS) ────────────────────────────────────────────
    def _get_monitor(self):
        if self._monitor is None:
            from divoom_daemon.macos_notifications import MacAppRouter, MacNotificationMonitor
            self._monitor = MacNotificationMonitor(router=MacAppRouter(), poll_interval=1.0)
        return self._monitor

    # ── status / events ──────────────────────────────────────────────────
    def _state(self) -> str:
        if self._error:
            return STATE_ERROR
        mon = self._monitor
        return STATE_ACTIVE if (mon is not None and mon.is_running) else STATE_IDLE

    def _counters(self) -> dict:
        mon = self._monitor
        if mon is None:
            return {"seen": 0, "routed": 0, "dropped": 0}
        return {
            "seen": getattr(mon, "records_seen", 0),
            "routed": getattr(mon, "records_routed", 0),
            "dropped": getattr(mon, "records_dropped", 0),
        }

    def status_event(self) -> dict:
        return make_status_event(self._state(), self._counters(), self._error)

    # ── notification sink (monitor -> device + broadcast) ────────────────
    def _sink(self, app_type: int, title: str, body: str) -> None:
        text = ""
        if title or body:
            text = (title or body or "").strip().splitlines()[0] if (title or body) else ""
        routed = True
        try:
            self._send_notification(app_type, text)
        except Exception as e:
            logger.debug(f"device send failed: {e}")
            routed = False
        self._broadcast(make_notification_event(app_type, title or "", text, routed))
        self._broadcast(self.status_event())

    # ── commands ─────────────────────────────────────────────────────────
    def start(self) -> dict:
        if self._monitor is None and sys.platform != "darwin":
            self._error = None
            logger.info("notification monitor unsupported on %s; running idle", sys.platform)
            ev = self.status_event()
            self._broadcast(ev)
            return {"success": True, **ev, "unsupported": True}
        try:
            mon = self._get_monitor()
            if not mon.is_running:
                mon.start(sink=self._sink)
            self._error = None
        except Exception as e:
            self._error = str(e)
            logger.warning(f"start_notifications: {e}")
        ev = self.status_event()
        self._broadcast(ev)
        return {"success": self._error is None, **ev, "error": self._error}

    def stop(self) -> dict:
        mon = self._monitor
        if mon is not None and mon.is_running:
            mon.stop()
        self._error = None
        ev = self.status_event()
        self._broadcast(ev)
        return {"success": True, **ev}

    def set_routing(self, args: dict) -> dict:
        try:
            from divoom_daemon.macos_notifications import save_routing_table, MacAppRouter
            rules = args.get("rules") or []
            save_routing_table([tuple(r) for r in rules])
            mon = self._get_monitor()
            mon._router = MacAppRouter(rules=[tuple(r) for r in rules])
            return {"success": True}
        except Exception as e:
            logger.warning(f"set_routing: {e}")
            return {"success": False, "error": str(e)}

    def stop_monitor(self) -> None:
        mon = self._monitor
        if mon is not None and getattr(mon, "is_running", False):
            mon.stop()

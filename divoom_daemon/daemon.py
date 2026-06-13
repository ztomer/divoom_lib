"""Headless Divoom daemon (R16) — the single owner of the device connection and
the macOS notification monitor + routing.

It listens to the OS notification stream, routes notifications to the device, and
emits events over a Unix socket. The GUI and the menubar are thin *clients*
(`gui/daemon_protocol.DaemonClient`): they send request/response commands and
`subscribe` for live status/notification events. This keeps the always-on job
out of the GUI presentation layer.

Run it with ``divoom-control daemon`` (see `divoom_lib/cli.py`).

The monitor and the device-sender are injectable so the socket/broadcast core is
testable without AppKit or a real BLE device.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Callable, Optional

from divoom_daemon.daemon_protocol import DEFAULT_SOCKET_PATH
from divoom_daemon.socket_server import SocketServer
from divoom_daemon.notification_service import NotificationService
from divoom_daemon.device_owner import DeviceOwner

logger = logging.getLogger("divoom_daemon")

# Notification-listener states (re-exported for test compatibility).
STATE_ACTIVE = "active"
STATE_IDLE = "idle"
STATE_ERROR = "error"


class DivoomDaemon:
    def __init__(
        self,
        mac: Optional[str] = None,
        socket_path: str = DEFAULT_SOCKET_PATH,
        *,
        monitor=None,
        device_sender: Optional[Callable[[int, str], None]] = None,
        device=None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        token: Optional[str] = None,
    ):
        self.socket_path = socket_path
        self.host = host
        self.port = port
        self.token = token if token is not None else (os.environ.get("DIVOOM_DAEMON_TOKEN") or None)
        self._registry: dict[str, Callable[[dict], dict]] = {}
        self._device_owner = DeviceOwner(
            mac=mac,
            device=device,
            device_sender=device_sender,
        )
        self._socket_server = SocketServer(
            socket_path=socket_path,
            host=host, port=port,
            token=self.token,
            command_handler=self.handle_command,
            status_event_factory=self.status_event,
        )
        self._notifier = NotificationService(
            broadcast=self._socket_server.broadcast,
            send_notification=self._device_owner.send_notification,
            monitor=monitor,
        )

    # ── command registry ─────────────────────────────────────────────────
    def _init_registry(self) -> None:
        r: dict[str, Callable[[dict], dict]] = {}
        r["ping"] = lambda _: {"success": True}
        r["get_status"] = lambda _: {"success": True, **self.status_event()}
        r["notification_status"] = r["get_status"]
        r["start_notifications"] = lambda _: self._notifier.start()
        r["stop_notifications"] = lambda _: self._notifier.stop()
        r["set_routing"] = self._notifier.set_routing
        r["device_call"] = self._device_owner.device_call
        r["exclusive_start"] = self._device_owner.exclusive_start
        r["exclusive_end"] = self._device_owner.exclusive_end
        r["connect"] = self._device_owner.connect
        r["disconnect"] = lambda _: self._device_owner.disconnect()
        r["device_status"] = lambda _: self._device_owner.device_status()
        r["scan"] = self._device_owner.scan
        r["wall_configure"] = self._device_owner.wall_configure
        r["probe_lan"] = lambda _: self._device_owner.probe_lan()
        r["live_job_start"] = self._device_owner.live_job_start
        r["live_job_stop"] = self._device_owner.live_job_stop
        r["live_job_list"] = self._device_owner.live_job_list
        r["live_jobs_stop_for"] = self._device_owner.live_jobs_stop_for
        r["set_device_activity"] = self._device_owner.set_device_activity
        r["get_device_activity"] = self._device_owner.get_device_activity
        r["sync_artwork"] = self._device_owner.sync_artwork
        r["custom_art_push"] = self._device_owner.custom_art_push
        r["custom_art_query_page"] = self._device_owner.custom_art_query_page
        r["hot_update"] = self._device_owner.hot_update
        r["hot_update_progress"] = self._device_owner.hot_update_progress
        r["shutdown"] = self._cmd_shutdown
        self._registry = r

    def _cmd_shutdown(self, _args: dict) -> dict:
        """Stop the daemon process. Replies first, broadcasts a ``shutdown``
        event so subscribers (menubar, dashboard) can follow it down, then stops
        the server shortly after so the client receives the ack (a clean kill
        switch for the single-owner daemon)."""
        from divoom_daemon.daemon_protocol import EVENT_SHUTDOWN
        try:
            self.broadcast({"type": EVENT_SHUTDOWN})
        except Exception:
            pass
        def _later():
            import time
            time.sleep(0.25)
            try:
                self.stop()
            except Exception:
                pass
        threading.Thread(target=_later, daemon=True).start()
        return {"success": True, "shutting_down": True}

    def handle_command(self, command: str, args: dict) -> dict:
        if not self._registry:
            self._init_registry()
        handler = self._registry.get(command)
        if handler is None:
            return {"success": False, "error": f"unknown command: {command}"}
        return handler(args)

    def _cleanup(self) -> None:
        self._notifier.stop_monitor()
        self._device_owner.stop()

    def status_event(self) -> dict:
        return self._notifier.status_event()

    # ── subscriber fan-out (delegated to SocketServer) ───────────────────
    def broadcast(self, event: dict) -> None:
        self._socket_server.broadcast(event)

    # ── lifecycle ────────────────────────────────────────────────────────
    def serve_forever(self) -> None:
        try:
            self._socket_server.serve_forever()
        finally:
            self._cleanup()

    def stop(self) -> None:
        self._socket_server.stop()
        self._cleanup()


def run(mac: Optional[str] = None, socket_path: str = DEFAULT_SOCKET_PATH,
        host: Optional[str] = None, port: Optional[int] = None,
        token: Optional[str] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    daemon = DivoomDaemon(mac=mac, socket_path=socket_path,
                          host=host, port=port, token=token)
    # Auto-start the notification listener on launch (best-effort; idle on non-mac).
    daemon._notifier.start()
    try:
        daemon.serve_forever()
    except KeyboardInterrupt:
        daemon.stop()
    return 0

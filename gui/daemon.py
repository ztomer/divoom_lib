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
import socket
import threading
from pathlib import Path
from typing import Callable, Optional

from gui.daemon_protocol import (
    DEFAULT_SOCKET_PATH,
    SUBSCRIBE_COMMAND,
    encode_message,
    iter_messages,
    make_status_event,
    make_notification_event,
)

logger = logging.getLogger("divoom_daemon")

# Notification-listener states (shared vocabulary with menubar_status).
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
    ):
        self.mac = mac
        self.socket_path = socket_path
        self._monitor = monitor                 # injectable; lazily built if None
        self._device_sender = device_sender     # injectable; default = real BLE send
        self._subscribers: list[socket.socket] = []
        self._sub_lock = threading.Lock()
        self._server: Optional[socket.socket] = None
        self._running = False
        self._error: Optional[str] = None

    # ── monitor (lazy, macOS) ────────────────────────────────────────────
    def _get_monitor(self):
        if self._monitor is None:
            from gui.macos_notifications import MacAppRouter, MacNotificationMonitor
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
        return make_status_event(self._state(), self._counters())

    # ── notification sink (monitor -> device + broadcast) ────────────────
    def _sink(self, app_type: int, title: str, body: str) -> None:
        text = ""
        if title or body:
            text = (title or body or "").strip().splitlines()[0] if (title or body) else ""
        routed = True
        try:
            self._send_to_device(app_type, text)
        except Exception as e:
            logger.debug(f"device send failed: {e}")
            routed = False
        self.broadcast(make_notification_event(app_type, title or "", text, routed))
        self.broadcast(self.status_event())

    def _send_to_device(self, app_type: int, text: str) -> None:
        if self._device_sender is not None:
            self._device_sender(app_type, text)
            return
        self._send_to_device_ble(app_type, text)  # pragma: no cover (needs BLE)

    def _send_to_device_ble(self, app_type: int, text: str) -> None:  # pragma: no cover
        import asyncio
        from divoom_lib.divoom import Divoom
        from divoom_lib.utils import discovery

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            if not getattr(self, "_device", None) or not self._device.is_connected:
                mac = self.mac
                if not mac:
                    devs = loop.run_until_complete(discovery.discover_all_divoom_devices(timeout=3.0))
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

    # ── commands (request/response) ──────────────────────────────────────
    def handle_command(self, command: str, args: dict) -> dict:
        if command == "ping":
            return {"success": True}
        if command == "get_status":
            return {"success": True, **self.status_event()}
        if command == "start_notifications":
            return self._cmd_start()
        if command == "stop_notifications":
            return self._cmd_stop()
        if command == "set_routing":
            return self._cmd_set_routing(args)
        return {"success": False, "error": f"unknown command: {command}"}

    def _cmd_start(self) -> dict:
        try:
            mon = self._get_monitor()
            if not mon.is_running:
                mon.start(sink=self._sink)
            self._error = None
        except Exception as e:
            self._error = str(e)
            logger.warning(f"start_notifications: {e}")
        ev = self.status_event()
        self.broadcast(ev)
        return {"success": self._error is None, **ev, "error": self._error}

    def _cmd_stop(self) -> dict:
        mon = self._monitor
        if mon is not None and mon.is_running:
            mon.stop()
        self._error = None
        ev = self.status_event()
        self.broadcast(ev)
        return {"success": True, **ev}

    def _cmd_set_routing(self, args: dict) -> dict:
        try:
            from gui.macos_notifications import save_routing_table, MacAppRouter
            rules = args.get("rules") or []
            save_routing_table([tuple(r) for r in rules])
            mon = self._get_monitor()
            mon._router = MacAppRouter(rules=[tuple(r) for r in rules])
            return {"success": True}
        except Exception as e:
            logger.warning(f"set_routing: {e}")
            return {"success": False, "error": str(e)}

    # ── subscriber fan-out ───────────────────────────────────────────────
    def broadcast(self, event: dict) -> None:
        data = encode_message(event)
        with self._sub_lock:
            dead = []
            for conn in self._subscribers:
                try:
                    conn.sendall(data)
                except OSError:
                    dead.append(conn)
            for conn in dead:
                self._subscribers.remove(conn)
                try:
                    conn.close()
                except OSError:
                    pass

    def _add_subscriber(self, conn: socket.socket) -> None:
        with self._sub_lock:
            self._subscribers.append(conn)

    def _remove_subscriber(self, conn: socket.socket) -> None:
        with self._sub_lock:
            if conn in self._subscribers:
                self._subscribers.remove(conn)

    # ── connection handling ──────────────────────────────────────────────
    def _handle_conn(self, conn: socket.socket) -> None:
        try:
            conn.settimeout(5.0)
            buf = b""
            while b"\n" not in buf:
                chunk = conn.recv(4096)
                if not chunk:
                    conn.close()
                    return
                buf += chunk
            msgs, _ = iter_messages(buf)
            if not msgs:
                conn.close()
                return
            req = msgs[0]
            command = req.get("command")
            args = req.get("args", {}) or {}

            if command == SUBSCRIBE_COMMAND:
                # Held-open stream: send current status, then block until close.
                conn.settimeout(None)
                self._add_subscriber(conn)
                try:
                    conn.sendall(encode_message(self.status_event()))
                    while self._running:
                        if not conn.recv(4096):  # client closed
                            break
                finally:
                    self._remove_subscriber(conn)
                    conn.close()
                return

            reply = self.handle_command(command, args)
            conn.sendall(encode_message(reply))
            conn.close()
        except OSError as e:
            logger.debug(f"conn error: {e}")
            try:
                conn.close()
            except OSError:
                pass

    def serve_forever(self) -> None:
        if os.path.exists(self.socket_path):
            try:
                os.remove(self.socket_path)
            except OSError:
                pass
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(self.socket_path)
        self._server.listen(8)
        self._running = True
        logger.info(f"Divoom daemon listening on {self.socket_path}")
        try:
            while self._running:
                self._server.settimeout(1.0)
                try:
                    conn, _ = self._server.accept()
                except socket.timeout:
                    continue
                threading.Thread(target=self._handle_conn, args=(conn,), daemon=True).start()
        finally:
            self.stop()

    def stop(self) -> None:
        self._running = False
        mon = self._monitor
        if mon is not None and mon.is_running:
            mon.stop()
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass
            self._server = None


def run(mac: Optional[str] = None, socket_path: str = DEFAULT_SOCKET_PATH) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    daemon = DivoomDaemon(mac=mac, socket_path=socket_path)
    # Auto-start the notification listener on launch (best-effort; idle on non-mac).
    daemon._cmd_start()
    try:
        daemon.serve_forever()
    except KeyboardInterrupt:
        daemon.stop()
    return 0

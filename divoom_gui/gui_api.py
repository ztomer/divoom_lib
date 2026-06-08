import json
import logging
import asyncio
import sys
import webview
from pathlib import Path

from divoom_lib import divoom_auth

from presets_manager import PresetsManagerMixin
from media_sync import MediaSyncMixin
from scanner_mixin import ScannerMixin

from divoom_gui.api import AsyncLoopThread
from divoom_gui.api.connection import ConnectionApi
from divoom_gui.api.lighting import LightingApi
from divoom_gui.api.tools import ToolsApi
from divoom_gui.api.widgets import WidgetsApi
from divoom_gui.api.window import WindowApi

logger = logging.getLogger("divoom_gui")

class DivoomGuiAPI(MediaSyncMixin, PresetsManagerMixin, ScannerMixin):
    """The PyWebView JS api bridge orchestrator."""
    def __init__(self) -> None:
        self.loop_thread = AsyncLoopThread()
        self.loop_thread.start()
        self.loop_thread.ready.wait()

        self.current_divoom = None
        self.discovered_list = []
        self.wall_slots = {}
        self.wall_instance = None
        self.cached_creds = None
        self.device_pw = 0
        self.device_id = 0
        self.window = None

        self.music_sync_active = False
        self.music_thread = None
        self.current_track_cache = None
        self.current_target_mode = "single"

        self._daemon_client = None

        try:
            self.cached_creds = divoom_auth.get_credentials()
        except Exception as e:
            logger.warning(f"Failed to load credentials on startup: {e}")

        device_cache_path = Path.home() / ".config" / "divoom-control" / "virtual_device.json"
        if not device_cache_path.exists():
            device_cache_path = Path(__file__).parent.parent / "api_scraper" / "divoom_docs" / "virtual_device.json"
        if device_cache_path.exists():
            try:
                device_info = json.loads(device_cache_path.read_text(encoding="utf-8"))
                self.device_id = device_info.get("BluetoothDeviceId", 0)
                self.device_pw = device_info.get("DevicePassword", 0)
                logger.info(f"Loaded virtual device: DeviceId={self.device_id}")
            except Exception as e:
                logger.warning(f"Failed to load virtual device: {e}")

        self._wire_collaborators()

    def _wire_collaborators(self):
        _state = lambda: self.__dict__
        _dc = lambda: self._daemon_client
        self.connection = ConnectionApi(self.loop_thread, _dc, _state)
        self.lighting = LightingApi(self.loop_thread, _dc, _state)
        self.tools = ToolsApi(self.loop_thread, _dc, _state)
        self.widgets = WidgetsApi(self.loop_thread, _dc, _state)
        self.window_mgr = WindowApi(self.loop_thread, _dc, _state)

    def _client(self):
        """Return a live DaemonClient, auto-spawning the daemon if needed (R17
        P5). Cached; ``None`` only if the daemon can't be reached/started."""
        from divoom_gui.daemon_bridge import ensure_daemon
        if self._daemon_client is None:
            self._daemon_client = ensure_daemon()
        return self._daemon_client

    def _run_async(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop_thread.loop)
        return future.result()

    def _schedule_async(self, coro) -> None:
        """Fire-and-forget: schedule ``coro`` on the main asyncio loop
        without blocking the caller. Used by the macOS notification
        monitor's polling thread (which must not block on BLE)."""
        asyncio.run_coroutine_threadsafe(coro, self.loop_thread.loop)

    def get_transport_status(self) -> str:
        return self.connection.get_transport_status()

    def save_lan_config(self, device_ip: str, local_token: int) -> bool:
        return self.connection.save_lan_config(device_ip, local_token)

    def probe_lan(self) -> str:
        return self.connection.probe_lan()

    def minimize_window(self) -> None:
        self.window_mgr.minimize_window()

    def maximize_window(self) -> None:
        self.window_mgr.maximize_window()

    def close_window(self) -> None:
        self.window_mgr.close_window()

    def set_solid_light(self, color: str, brightness: int, mode_type: int = 0) -> bool:
        return self.lighting.set_solid_light(color, brightness, mode_type)

    def set_clock(self, style: int, color: str = None) -> bool:
        return self.lighting.set_clock(style, color)

    def switch_channel(self, channel: str) -> bool:
        return self.lighting.switch_channel(channel)

    def set_vj_effect(self, number: int) -> bool:
        return self.lighting.set_vj_effect(number)

    def set_visualization(self, number: int) -> bool:
        return self.lighting.set_visualization(number)

    def push_text(self, text: str, color: str = "#FFFFFF", font_size: int = 1,
                  speed: int = 50, effect_style: int = 1) -> bool:
        return self.lighting.push_text(text, color, font_size, speed, effect_style)

    def get_alarms(self) -> str:
        return self.tools.get_alarms()

    def set_alarm(self, index: int, enabled, hour: int, minute: int,
                  week: int = 0, mode: int = 0, trigger_mode: int = 0) -> bool:
        return self.tools.set_alarm(index, enabled, hour, minute, week, mode, trigger_mode)

    def start_sleep(self, minutes: int = 30, color: str = "#2040ff", volume: int = 10) -> bool:
        return self.tools.start_sleep(minutes, color, volume)

    def stop_sleep(self) -> bool:
        return self.tools.stop_sleep()

    def set_timer(self, action: str = "start") -> bool:
        return self.tools.set_timer(action)

    def set_countdown(self, action: str = "start", minutes: int = 5, seconds: int = 0) -> bool:
        return self.tools.set_countdown(action, minutes, seconds)

    def set_noise(self, action: str = "start") -> bool:
        return self.tools.set_noise(action)

    def set_hour_type(self, is_24h) -> bool:
        return self.tools.set_hour_type(is_24h)

    def set_temp_unit(self, fahrenheit) -> bool:
        return self.tools.set_temp_unit(fahrenheit)

    def sync_time(self) -> bool:
        return self.tools.sync_time()

    def set_device_name(self, name: str) -> bool:
        return self.tools.set_device_name(name)

    def set_auto_power_off(self, minutes: int) -> bool:
        return self.tools.set_auto_power_off(minutes)

    def set_low_power(self, on) -> bool:
        return self.tools.set_low_power(on)

    def push_weather(self) -> bool:
        return self.widgets.push_weather()

    def get_weather(self) -> dict:
        return self.widgets.get_weather()

    def set_fm_frequency(self, freq_x10: int) -> bool:
        return self.tools.set_fm_frequency(freq_x10)

    def set_memorial(self, index, enabled, month, day, hour, minute, title="") -> bool:
        return self.tools.set_memorial(index, enabled, month, day, hour, minute, title)

    def set_timeplan(self, index, enabled, hour, minute, week=0, channel=0) -> bool:
        return self.tools.set_timeplan(index, enabled, hour, minute, week, channel)

    def set_screen_dir(self, direction) -> bool:
        return self.tools.set_screen_dir(direction)

    def set_screen_mirror(self, on) -> bool:
        return self.tools.set_screen_mirror(on)

    def factory_reset(self, confirm="") -> bool:
        if str(confirm) != "RESET":
            logger.warning("factory_reset refused: missing/invalid confirm token")
            return False
        return self.tools.factory_reset(confirm)

    def send_notification(self, app_type, text="") -> bool:
        t = int(app_type)
        if not (1 <= t <= 14):
            logger.warning(f"send_notification: app_type {t} out of range 1-14")
            return False
        return self.tools.send_notification(t, text)

    # ── Round 13 §3: macOS notification mirroring ────────────────────────
    # The monitor runs in a daemon thread that polls the macOS Notification
    # Center SQLite DB. The sink callback (called on the polling thread)
    # schedules the BLE send on the main asyncio loop via _schedule_async
    # so the polling thread never blocks on BLE roundtrips.

    def _notification_monitor(self):
        """Lazy accessor for the macOS monitor singleton. Imports
        ``divoom_daemon.macos_notifications`` lazily so non-macOS hosts don't
        fail to import this module."""
        if not hasattr(self, "_mac_monitor") or self._mac_monitor is None:
            from divoom_daemon.macos_notifications import MacAppRouter, MacNotificationMonitor
            router = MacAppRouter()
            self._mac_monitor = MacNotificationMonitor(router=router, poll_interval=1.0)
        return self._mac_monitor

    def _notification_sink(self, app_type: int, title: str, body: str) -> None:
        """Sink for the monitor. Truncates to a single line of text and
        schedules a fire-and-forget BLE send."""
        text = (title or body or "").strip().splitlines()[0] if (title or body) else ""
        self._schedule_async(self._send_notification_async(app_type, text))

    async def _send_notification_async(self, app_type: int, text: str) -> None:
        """Coroutines run on the main loop. Logs + sends; ignores failures
        (we'd rather drop a notification than back up the polling thread)."""
        d = self.current_divoom
        if d is None or not d.is_connected:
            return
        try:
            if text:
                await d.notification.show_notification_text(int(app_type), text)
            else:
                await d.notification.show_notification(int(app_type))
        except Exception as e:
            logger.debug(f"_send_notification_async: {e}")

    def _push_menubar_status(self, status: dict) -> dict:
        """Best-effort, event-driven push of the listener status to the menubar
        agent over its Unix socket (R15 §6 — the menubar does NOT poll). Returns
        `status` unchanged so callers can ``return self._push_menubar_status(...)``.
        Silent no-op if the menubar agent isn't running."""
        try:
            from divoom_daemon.menubar_status import derive_state, push_notification_status
            push_notification_status(derive_state(status), status.get("counters"))
        except Exception as e:
            logger.debug(f"menubar status push skipped: {e}")
        return status

    def start_notification_listener(self) -> dict:
        """Start polling the macOS Notification Center DB. Returns a
        status dict for the JS side (``{running, db_path, error?}``).
        Safe to call multiple times; no-op if already running."""
        if sys.platform != "darwin":
            return self._push_menubar_status({"running": False, "error": "macOS only"})
        try:
            monitor = self._notification_monitor()
            if monitor.is_running:
                return self._push_menubar_status({"running": True, "db_path": str(monitor.db_path)})
            monitor.start(sink=self._notification_sink)
            return self._push_menubar_status({"running": True, "db_path": str(monitor.db_path)})
        except FileNotFoundError as e:
            logger.warning(f"start_notification_listener: {e}")
            return self._push_menubar_status({"running": False, "error": str(e)})
        except Exception as e:
            logger.exception(f"start_notification_listener: {e}")
            return self._push_menubar_status({"running": False, "error": str(e)})

    def stop_notification_listener(self) -> dict:
        """Stop the polling thread. No-op if not running."""
        if not hasattr(self, "_mac_monitor") or self._mac_monitor is None:
            return self._push_menubar_status({"running": False})
        self._mac_monitor.stop()
        return self._push_menubar_status({"running": False})

    def is_notification_listener_running(self) -> bool:
        if not hasattr(self, "_mac_monitor") or self._mac_monitor is None:
            return False
        return self._mac_monitor.is_running

    def get_notification_listener_status(self) -> dict:
        """Rich status snapshot for the Settings → Devices card.

        Returns a dict the JS side can render directly::

            {
              "platform_supported": bool,    # False on non-darwin
              "running": bool,
              "db_path": str | None,         # macOS Notification Center DB
              "routing_path": str,           # ~/.config/divoom-control/...
              "rules": [[substr, app_type], ...],
              "counters": {"seen": int, "routed": int, "dropped": int},
              "error": str | None,
            }
        """
        from divoom_daemon.macos_notifications import ROUTING_PATH, load_routing_table
        if sys.platform != "darwin":
            return {
                "platform_supported": False,
                "running": False,
                "db_path": None,
                "routing_path": str(ROUTING_PATH),
                "rules": [list(r) for r in load_routing_table()],
                "counters": {"seen": 0, "routed": 0, "dropped": 0},
                "error": "macOS notifications are only supported on macOS",
            }
        monitor = self._notification_monitor()
        rules = [list(r) for r in monitor._router.rules]
        return {
            "platform_supported": True,
            "running": monitor.is_running,
            "db_path": str(monitor.db_path) if monitor.db_path else None,
            "routing_path": str(ROUTING_PATH),
            "rules": rules,
            "counters": {
                "seen":    monitor.records_seen,
                "routed":  monitor.records_routed,
                "dropped": monitor.records_dropped,
            },
            "error": None,
        }

    def save_notification_routing(self, json_text: str) -> dict:
        """Save a user-edited routing table. Persists to disk and
        hot-reloads the running monitor's router (no listener restart
        required).

        Returns ``{"rules": [[substr, app_type], ...], "error": str|None}``.

        On parse / validation error, returns the *previous* rule list
        unchanged and a non-null ``error`` string — the GUI shows the
        error and keeps the user's draft.
        """
        from divoom_daemon.macos_notifications import (
            ROUTING_PATH, load_routing_table, save_routing_table,
        )
        import json as _json
        try:
            parsed = _json.loads(json_text) if json_text.strip() else []
        except _json.JSONDecodeError as e:
            return {"rules": [list(r) for r in load_routing_table()], "error": f"Invalid JSON: {e}"}
        try:
            path = save_routing_table(
                [(s, int(t)) for s, t in parsed], path=ROUTING_PATH
            )
        except (ValueError, TypeError) as e:
            return {
                "rules": [list(r) for r in load_routing_table()],
                "error": f"Invalid routing entries: {e}",
            }
        # Hot-reload the running monitor's router.
        monitor = self._notification_monitor()
        from divoom_daemon.macos_notifications import MacAppRouter
        monitor._router = MacAppRouter.from_file(path)
        logger.info(f"save_notification_routing: saved {len(parsed)} rules to {path}")
        return {
            "rules": [list(r) for r in load_routing_table(path)],
            "error": None,
        }

    def display_wall_image(self, file_path: str, cell_size: int) -> bool:
        return self.lighting.display_wall_image(file_path, cell_size)

    def display_custom_art(self, file_path: str) -> bool:
        return self.lighting.display_custom_art(file_path)

    def set_brightness(self, brightness: int) -> bool:
        return self.lighting.set_brightness(brightness)

    def set_volume(self, volume: int) -> bool:
        return self.lighting.set_volume(volume)

    def open_file_dialog(self) -> str | None:
        logger.info("Opening native file dialog...")
        try:
            if not self.window:
                logger.error("No webview window reference available.")
                return None
            
            file_types = ('Image files (*.png;*.jpg;*.jpeg;*.gif)', 'All files (*.*)')
            result = self.window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=file_types
            )
            
            if result and len(result) > 0:
                logger.info(f"Selected file: {result[0]}")
                return result[0]
            return None
        except Exception as e:
            logger.error(f"Error opening file dialog: {e}")
            return None

    def get_brightness(self) -> int | None:
        return self.tools.get_brightness()

    def get_work_mode(self) -> int | None:
        return self.tools.get_work_mode()

    def get_scoreboard_state(self) -> dict | None:
        return self.tools.get_scoreboard_state()

    def get_volume(self) -> int | None:
        return self.tools.get_volume()

    def set_scoreboard(self, on_off: int, red: int = 0, blue: int = 0) -> bool:
        return self.tools.set_scoreboard(on_off, red, blue)

    # ── Round 15 §5: MCP server subprocess control ────────────────────
    #
    # The GUI spawns ``python -m divoom_lib.cli mcp-server --mac <MAC>``
    # as a subprocess and tracks it via MCPController. pywebview's
    # event loop and the MCP server's stdio loop would otherwise fight
    # over file descriptors — subprocess isolation is the clean fix.

    def start_mcp_server(self, mac: str = "") -> dict:
        """Start the MCP stdio server subprocess (R15 §5).

        ``mac`` is optional; falls back to the active device's MAC if
        empty. Returns a status dict (see ``mcp_server_status()``)."""
        from divoom_gui.mcp_control import MCPController, status_to_dict
        ctl = MCPController.instance()
        target_mac = mac or (self.current_divoom.mac if self.current_divoom else "")
        if not target_mac:
            return status_to_dict(ctl.status()) | {"error": "no MAC available"}
        return status_to_dict(ctl.start(mac=target_mac))

    def stop_mcp_server(self) -> dict:
        """Stop the MCP server subprocess (no-op if not running)."""
        from divoom_gui.mcp_control import MCPController, status_to_dict
        ctl = MCPController.instance()
        return status_to_dict(ctl.stop())

    def is_mcp_server_running(self) -> bool:
        """True if the subprocess is alive."""
        from divoom_gui.mcp_control import MCPController
        return MCPController.instance().is_running()

    def mcp_server_status(self) -> dict:
        """Snapshot of the subprocess state (JSON-friendly)."""
        from divoom_gui.mcp_control import MCPController, status_to_dict
        return status_to_dict(MCPController.instance().status())

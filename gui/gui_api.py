# gui/gui_api.py

import json
import logging
import asyncio
import webview
import threading
import time
from pathlib import Path

from divoom_lib.divoom import Divoom
from divoom_lib.wall import DivoomWall
from divoom_lib import divoom_auth

# Import mixins
from presets_manager import PresetsManagerMixin
from media_sync import MediaSyncMixin
from scanner_mixin import ScannerMixin

logger = logging.getLogger("divoom_gui")

class AsyncLoopThread(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.loop = asyncio.new_event_loop()
        self.ready = threading.Event()

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.ready.set()
        self.loop.run_forever()

    def stop(self):
        self.loop.call_soon_threadsafe(self.loop.stop)

class DivoomGuiAPI(MediaSyncMixin, PresetsManagerMixin, ScannerMixin):
    """The PyWebView JS api bridge orchestrator."""
    def __init__(self) -> None:
        self.loop_thread = AsyncLoopThread()
        self.loop_thread.start()
        self.loop_thread.ready.wait()

        self.current_divoom = None
        self.discovered_list = []
        self.wall_slots = {}  # "mac" -> {"x": x, "y": y, "width": w, "height": h, "size": size}
        self.wall_instance = None
        self.cached_creds = None
        self.device_pw = 0
        self.device_id = 0
        self.window = None  # Reference to pywebview Window instance

        self.music_sync_active = False
        self.music_thread = None
        self.current_track_cache = None
        self.current_target_mode = "single"

        # Load credentials on startup
        try:
            self.cached_creds = divoom_auth.get_credentials()
        except Exception as e:
            logger.warning(f"Failed to load credentials on startup: {e}")

        # Load virtual device details for gallery API
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

    def _run_async(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop_thread.loop)
        return future.result()

    def get_transport_status(self) -> str:
        """Return live status of all four transport layers as JSON."""
        ble_connected = bool(self.current_divoom and self.current_divoom.is_connected)
        lan_ip = self.current_divoom.lan.device_ip if (self.current_divoom and self.current_divoom.lan) else None
        cloud_ok = bool(self.cached_creds and self.cached_creds.is_valid())
        return json.dumps({
            "ble": {"available": ble_connected, "label": "Bluetooth", "badge": "🔵", "color": "#3b82f6", "description": "Bluetooth — 100% local, never leaves your machine.", "detail": self.current_divoom._conn.mac if ble_connected and self.current_divoom else None},
            "lan": {"available": bool(lan_ip), "label": "Local Network", "badge": "🟢", "color": "#22c55e", "description": "Local Network — 100% local, WiFi-capable devices only.", "detail": f"{lan_ip}:9000" if lan_ip else "No device IP configured"},
            "cloud": {"available": cloud_ok, "label": "Divoom Cloud", "badge": "🟡", "color": "#f59e0b", "description": "Divoom Cloud — appin.divoom-gz.com, Divoom's servers, requires account.", "detail": "Authenticated" if cloud_ok else "Not authenticated"},
            "external": {"available": True, "label": "Public Cloud", "badge": "🔴", "color": "#ef4444", "description": "Public Cloud — 3rd-party APIs (weather, stocks), no login required.", "detail": "Available"}
        })

    def save_lan_config(self, device_ip: str, local_token: int) -> bool:
        logger.info(f"GUI Action: Saving LAN config ip={device_ip} token={local_token}...")
        try:
            import configparser
            config_file = Path.home() / ".config" / "divoom-control" / "config.ini"
            config_file.parent.mkdir(parents=True, exist_ok=True)
            cfg = configparser.ConfigParser()
            if config_file.exists():
                cfg.read(config_file)
            if "lan" not in cfg:
                cfg["lan"] = {}
            cfg["lan"]["device_ip"] = device_ip
            cfg["lan"]["local_token"] = str(local_token)
            with open(config_file, "w") as f:
                cfg.write(f)

            # Hot-attach to current device if connected
            if self.current_divoom and device_ip:
                from divoom_lib.lan_transport import LanTransport
                self.current_divoom._lan = LanTransport(
                    device_ip=device_ip,
                    local_token=local_token,
                    logger=logger,
                )
            return True
        except Exception as e:
            logger.error(f"Failed to save LAN config: {e}")
            return False

    def probe_lan(self) -> str:
        logger.info("GUI Action: Probing LAN transport reachability...")
        try:
            if not self.current_divoom or not self.current_divoom.lan:
                return json.dumps({"reachable": False, "detail": "No LAN IP configured. Save a device IP first."})
            ok = self._run_async(self.current_divoom.lan.probe())
            ip = self.current_divoom.lan.device_ip
            return json.dumps({
                "reachable": ok,
                "detail": f"{'✓ Connected' if ok else '✗ Unreachable'} — {ip}:9000",
            })
        except Exception as e:
            return json.dumps({"reachable": False, "detail": str(e)})

    def minimize_window(self) -> None:
        if self.window:
            self.window.minimize()

    def maximize_window(self) -> None:
        if self.window:
            self.window.toggle_fullscreen()

    def close_window(self) -> None:
        if hasattr(self, "loop_thread"):
            self.loop_thread.stop()
        if self.window:
            def _destroy():
                time.sleep(0.1)
                self.window.destroy()
            threading.Thread(target=_destroy, daemon=True).start()

    def set_solid_light(self, color: str, brightness: int, mode_type: int = 0) -> bool:
        logger.info(f"GUI Action: Applying solid light {color} (brightness={brightness}, mode_type={mode_type})...")
        try:
            if getattr(self, "current_target_mode", "single") == "wall":
                if not self._rebuild_wall_instance():
                    return False
                return self._run_async(self.wall_instance.set_light(color, brightness))
            elif self.current_divoom:
                return self._run_async(self.current_divoom.display.show_light(color, brightness, True, mode_type))
            return False
        except Exception as e:
            logger.error(f"Light setting failed: {e}")
            return False

    def set_clock(self, style: int, color: str = None) -> bool:
        logger.info(f"GUI Action: Applying clock style {style} with color {color}...")
        try:
            if getattr(self, "current_target_mode", "single") == "wall":
                if not self._rebuild_wall_instance():
                    return False
                return self._run_async(self.wall_instance.show_clock(clock=style))
            elif self.current_divoom:
                return self._run_async(self.current_divoom.display.show_clock(clock=style, color=color))
            return False
        except Exception as e:
            logger.error(f"Clock setting failed: {e}")
            return False

    def switch_channel(self, channel: str) -> bool:
        logger.info(f"GUI Action: Switching channel to {channel}...")
        try:
            if getattr(self, "current_target_mode", "single") == "wall":
                if not self._rebuild_wall_instance():
                    return False
                tasks = []
                for divoom, _, _, _, _, _ in self.wall_instance.devices:
                    tasks.append(divoom.display.switch_channel(channel))
                
                async def run_switch():
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    return all(res is True or isinstance(res, dict) for res in results)
                
                return self._run_async(run_switch())

            target = self.current_divoom
            if not target:
                return False
            return self._run_async(target.display.switch_channel(channel))
        except Exception as e:
            logger.error(f"Channel switch failed: {e}")
            return False

    def set_vj_effect(self, number: int) -> bool:
        logger.info(f"GUI Action: Applying VJ effect {number}...")
        try:
            if getattr(self, "current_target_mode", "single") == "wall":
                if not self._rebuild_wall_instance():
                    return False
                return self._run_async(self.wall_instance.show_effects(number=int(number)))
            target = self.current_divoom
            if not target:
                return False
            return self._run_async(target.display.show_effects(number=int(number)))
        except Exception as e:
            logger.error(f"VJ effect failed: {e}")
            return False

    def set_visualization(self, number: int) -> bool:
        logger.info(f"GUI Action: Applying visualizer {number}...")
        try:
            if getattr(self, "current_target_mode", "single") == "wall":
                if not self._rebuild_wall_instance():
                    return False
                return self._run_async(self.wall_instance.show_visualization(number=int(number)))
            target = self.current_divoom
            if not target:
                return False
            return self._run_async(target.display.show_visualization(number=int(number)))
        except Exception as e:
            logger.error(f"Visualizer failed: {e}")
            return False

    def display_wall_image(self, file_path: str, cell_size: int) -> bool:
        logger.info(f"GUI Action: Push display wall asset {file_path!r} (cell size={cell_size})...")
        try:
            if not self._rebuild_wall_instance(cell_size):
                return False
            return self._run_async(self.wall_instance.show_image(file_path))
        except Exception as e:
            logger.error(f"Wall display failed: {e}")
            return False

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

    def set_brightness(self, brightness: int) -> bool:
        logger.info(f"GUI Action: Setting brightness to {brightness}...")
        try:
            val = int(brightness)
            if getattr(self, "current_target_mode", "single") == "wall":
                if not self._rebuild_wall_instance():
                    return False
                tasks = []
                for divoom, _, _, _, _, _ in self.wall_instance.devices:
                    if divoom.lan:
                        tasks.append(divoom.lan.set_brightness(val))
                    else:
                        tasks.append(divoom.device.set_brightness(val))

                async def run_brightness():
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    return all(res is True or isinstance(res, dict) for res in results)

                return self._run_async(run_brightness())

            target = self.current_divoom
            if not target:
                return False
            if target.lan:
                return self._run_async(target.lan.set_brightness(val))
            else:
                return self._run_async(target.device.set_brightness(val))
        except Exception as e:
            logger.error(f"Brightness setting failed: {e}")
            return False

    def get_brightness(self) -> int | None:
        """Read the device's current brightness (0-100). Returns None on failure.

        New in Round 7 (docs/PLANNING_ROUND7.md §3). Used by the appbar
        brightness slider to initialize to the actual device value on
        startup, matching the volume-slider pattern from Round 6.

        Wire: 0x46 get light mode (parsed by divoom_lib.device.get_brightness).
        LAN devices return a dict from the LAN transport; we extract the
        'brightness' field if present, else fall back to None.
        """
        logger.info("GUI Action: Getting current brightness...")
        try:
            target = self.current_divoom
            if not target:
                return None
            return self._run_async(target.device.get_brightness())
        except Exception as e:
            logger.error(f"Brightness get failed: {e}")
            return None

    def get_work_mode(self) -> int | None:
        """Read the device's current work mode (0-15). Returns None on failure.

        New in Round 7. Used by the Control Panel to highlight the
        channel card that matches the device's currently-active channel.
        Wire: 0x13 get work mode. Returns the work mode integer
        (0=clock, 1=lightning, 2=cloud, 3=vj, 4=visualizer, 5=design,
        6=scoreboard, 7=animation, etc.).
        """
        logger.info("GUI Action: Getting current work mode...")
        try:
            target = self.current_divoom
            if not target:
                return None
            return self._run_async(target.device.get_work_mode())
        except Exception as e:
            logger.error(f"Work mode get failed: {e}")
            return None

    def get_scoreboard_state(self) -> dict | None:
        """Read the current scoreboard state from the device.

        New in Round 7. Returns a dict with `on_off`, `red_score`,
        `blue_score` keys, or None on failure. Used by the scoreboard
        panel to initialize the red/blue inputs to the actual device
        state (matching the volume/brightness slider patterns).

        Wire: 0x71 0x04 (get tool info, TOOL_TYPE_SCORE).
        """
        logger.info("GUI Action: Getting current scoreboard state...")
        try:
            target = self.current_divoom
            if not target:
                return None
            return self._run_async(target.scoreboard.get_scoreboard())
        except Exception as e:
            logger.error(f"Scoreboard get failed: {e}")
            return None

    def set_volume(self, volume: int) -> bool:
        """Set the device volume (0-15).

        New in Round 6 (docs/PLANNING_ROUND5.md §6.1). The wire command
        is 0x08 set volume. Validated to 0-15; out-of-range is clamped.
        """
        logger.info(f"GUI Action: Setting volume to {volume}...")
        try:
            val = max(0, min(15, int(volume)))
            if getattr(self, "current_target_mode", "single") == "wall":
                if not self._rebuild_wall_instance():
                    return False
                tasks = []
                for divoom, _, _, _, _, _ in self.wall_instance.devices:
                    tasks.append(divoom.music.set_volume(val))

                async def run_volume():
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    return all(res is True for res in results)

                return self._run_async(run_volume())

            target = self.current_divoom
            if not target:
                return False
            return self._run_async(target.music.set_volume(val))
        except Exception as e:
            logger.error(f"Volume setting failed: {e}")
            return False

    def get_volume(self) -> int | None:
        """Read the device volume (0-15). Returns None on failure.

        New in Round 6. Used by the appbar volume slider to initialize
        to the actual device value on startup. Wire command is 0x09
        get volume.
        """
        logger.info("GUI Action: Getting current volume...")
        try:
            target = self.current_divoom
            if not target:
                return None
            return self._run_async(target.music.get_volume())
        except Exception as e:
            logger.error(f"Volume get failed: {e}")
            return None

    def set_scoreboard(self, on_off: int, red: int = 0, blue: int = 0) -> bool:
        """Set the scoreboard tool (0x72 set tool, TOOL_TYPE_SCORE).

        New in Round 6 (docs/PLANNING_ROUND5.md §6.1). The scoreboard
        is a tool, not a channel — it has its own panel in the Control
        Center and its own show/hide buttons. Wire details in
        divoom_lib/tools/scoreboard.py.
        """
        logger.info(f"GUI Action: Setting scoreboard on_off={on_off} red={red} blue={blue}...")
        try:
            target = self.current_divoom
            if not target:
                return False
            return self._run_async(target.scoreboard.set_scoreboard(int(on_off), int(red), int(blue)))
        except Exception as e:
            logger.error(f"Scoreboard set failed: {e}")
            return False

    def display_custom_art(self, file_path: str) -> bool:
        logger.info(f"GUI Action: Pushing custom art {file_path!r}...")
        try:
            if getattr(self, "current_target_mode", "single") == "wall":
                if not self._rebuild_wall_instance():
                    return False
                return self._run_async(self.wall_instance.show_image(file_path))
            
            target = self.current_divoom
            if not target:
                return False
            return self._run_async(target.display.show_image(file_path))
        except Exception as e:
            logger.error(f"Failed to display custom art: {e}")
            return False

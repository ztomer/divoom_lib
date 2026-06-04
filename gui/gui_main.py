#!/usr/bin/env python3
"""
gui_main.py — Divoom Desktop GUI controller backend.
Launches the premium frameless PyWebView dashboard, exposing Divoom's core BLE features
and coordinate display wall capabilities to the HTML/CSS/JS frontend.
"""

import os
import sys
import json
import asyncio
import logging
import webview
import threading
import time
from pathlib import Path
from bleak import BleakScanner

# Add divoom-control paths
sys.path.append(str(Path(__file__).parent))
sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "api_scraper"))

from divoom_lib.divoom import Divoom
from divoom_lib.utils import discovery
from divoom_lib.wall import DivoomWall
from divoom_lib import divoom_auth

# Import mixins for modularity and <= 500 LOC compliance
from presets_manager import PresetsManagerMixin
from media_sync import MediaSyncMixin

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
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

class DivoomGuiAPI(MediaSyncMixin, PresetsManagerMixin):
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

    # ── Transport Status (4-badge panel) ──────────────────────────────────────

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
        """
        Save LAN device IP and token to config and attach LAN transport.
        """
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
        """
        Test LAN reachability. Returns JSON with {reachable: bool, detail: str}.
        """
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

    # ── Frameless Window State Controllers ────────────────────────────────────────

    def minimize_window(self) -> None:
        logger.info("GUI Action: Minimizing window...")
        if self.window:
            self.window.minimize()

    def maximize_window(self) -> None:
        logger.info("GUI Action: Toggling fullscreen...")
        if self.window:
            self.window.toggle_fullscreen()

    def close_window(self) -> None:
        logger.info("GUI Action: Closing window...")
        if hasattr(self, "loop_thread"):
            self.loop_thread.stop()
        if self.window:
            def _destroy():
                time.sleep(0.1)
                self.window.destroy()
            threading.Thread(target=_destroy, daemon=True).start()

    def drag_window(self, delta_x: int, delta_y: int) -> None:
        """Move the window relatively by delta_x and delta_y."""
        if self.window:
            try:
                self.window.move(self.window.x + int(delta_x), self.window.y + int(delta_y))
            except Exception as e:
                logger.error(f"Failed to drag window: {e}")

    # ── Device Scanner Core (asyncio.run Thread-Safe) ──────────────────────────────

    def scan_devices(self) -> str:
        """Scan BLE devices and return discovered Divoom screens as JSON."""
        return self.scan_devices_with_config(timeout=15, limit=4)

    def save_scan_settings(self, timeout: int, limit: int) -> bool:
        """Persist scan timeout + device limit to config.ini.

        Called both before a scan and on settings-field changes, so the values
        are remembered across sessions even without triggering a scan.
        """
        try:
            import configparser
            config_file = Path.home() / ".config" / "divoom-control" / "config.ini"
            config_file.parent.mkdir(parents=True, exist_ok=True)
            cfg = configparser.ConfigParser()
            if config_file.exists():
                cfg.read(config_file)
            if "gui" not in cfg:
                cfg["gui"] = {}
            cfg["gui"]["timeout"] = str(int(timeout))
            cfg["gui"]["limit"] = str(int(limit))
            with open(config_file, "w") as f:
                cfg.write(f)
            return True
        except Exception as e:
            logger.warning(f"Failed to save scan config: {e}")
            return False

    def scan_devices_with_config(self, timeout: int, limit: int) -> str:
        """Scan BLE devices with custom timeouts and device limit."""
        logger.info(f"GUI Action: Scanning devices with timeout={timeout}, limit={limit}...")

        # Save scanner limits into config.ini for next time
        self.save_scan_settings(timeout, limit)

        # Hardware-free mode: return a deterministic mock device.
        if os.environ.get("DIVOOM_MOCK_BLE") in ("1", "true", "yes"):
            mock = [{"name": "Pixoo-Mock", "address": "AA:BB:CC:DD:EE:FF"}]
            try:
                cache_file = Path.home() / ".config" / "divoom-control" / "discovered_devices.json"
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(json.dumps(mock), encoding="utf-8")
            except Exception:
                pass
            return json.dumps(mock)

        # Scan using Bleak cleanly inside thread-safe asyncio.run context
        try:
            if limit > 0:
                discovered = []
                divoom_keywords = ["timoo", "tivoo", "timebox", "pixoo", "ditoo", "backpack", "timegate"]
                
                def detection_callback(device, advertisement_data):
                    if device.name:
                        name_lower = device.name.lower()
                        is_divoom = any(kw in name_lower for kw in divoom_keywords)
                        if is_divoom:
                            if not any(d["address"] == device.address for d in discovered):
                                discovered.append({
                                    "name": device.name,
                                    "address": device.address
                                })
                                logger.info(f"Scanner: Found Divoom device: {device.name} ({device.address})")
                
                async def run_scan():
                    scanner = BleakScanner(detection_callback=detection_callback)
                    await scanner.start()
                    elapsed = 0.0
                    while elapsed < timeout and len(discovered) < limit:
                        await asyncio.sleep(0.5)
                        elapsed += 0.5
                    await scanner.stop()
                    return discovered
                    
                results = self._run_async(run_scan())
                if not results:
                    results = self._run_async(discovery.discover_all_divoom_devices(timeout=float(timeout)))
                    results = results[:limit]
            else:
                results = self._run_async(discovery.discover_all_divoom_devices(timeout=float(timeout)))
                
            self.discovered_list = results
            try:
                cache_file = Path.home() / ".config" / "divoom-control" / "discovered_devices.json"
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
                logger.info(f"Scanner: Cached {len(results)} discovered devices to discovered_devices.json")
                
                # Save the number of detected screens to config.ini for the next session
                import configparser
                config_file = Path.home() / ".config" / "divoom-control" / "config.ini"
                cfg = configparser.ConfigParser()
                if config_file.exists():
                    cfg.read(config_file)
                if "gui" not in cfg:
                    cfg["gui"] = {}
                cfg["gui"]["last_detected_count"] = str(len(results))
                with open(config_file, "w") as f:
                    cfg.write(f)
            except Exception as ce:
                logger.warning(f"Failed to cache discovered devices or count: {ce}")
            return json.dumps(results)
        except Exception as e:
            logger.error(f"Device scan failed: {e}")
            return json.dumps([])

    def connect_single_device(self, address: str) -> bool:
        """Establishes connection to a single BLE or Wi-Fi (LAN) screen."""
        logger.info(f"GUI Action: Connecting to single device {address}...")
        try:
            connected = False
            if address == "MatrixWall":
                self.current_target_mode = "wall"
                logger.info("Switched to multi-screen display wall mode.")
                connected = True
                
            else:
                self.current_target_mode = "single"
                if self.current_divoom and self.current_divoom.is_connected:
                    self._run_async(self.current_divoom.disconnect())
                    
                if address.startswith("LAN:"):
                    ip = address.split("LAN:")[1]
                    local_token = 0
                    
                    # Retrieve token from saved LAN devices if configured
                    presets_file = self._get_presets_file()
                    if presets_file.exists():
                        try:
                            presets = json.loads(presets_file.read_text(encoding="utf-8"))
                            devices = presets.get("lan_devices", [])
                            for d in devices:
                                if d.get("ip") == ip:
                                    local_token = int(d.get("token", 0))
                                    break
                        except Exception:
                            pass
                    
                    self.current_divoom = Divoom(mac=None, lan_ip=ip, lan_token=local_token, logger=logger)
                    from divoom_lib.lan_transport import LanTransport
                    self.current_divoom._lan = LanTransport(device_ip=ip, local_token=local_token, logger=logger)
                    
                    reachable = self._run_async(self.current_divoom._lan.probe())
                    if not reachable:
                        logger.error(f"LAN Device at {ip} is unreachable")
                        self.current_divoom = None
                        return False
                    connected = True
                else:
                    client = None
                    if os.environ.get("DIVOOM_MOCK_BLE") in ("1", "true", "yes"):
                        # Hardware-free mode: inject a MockBleakClient so the full
                        # bridge → Divoom → framing pipeline is driveable without
                        # a real device / Bluetooth permission.
                        import sys as _sys
                        _sys.path.append(str(Path(__file__).parent.parent / "scripts"))
                        from mock_device import MockBleakClient
                        client = MockBleakClient(address)
                        logger.info("DIVOOM_MOCK_BLE: using MockBleakClient")
                    device_name = None
                    for d in self.discovered_list:
                        if d.get("address") == address:
                            device_name = d.get("name")
                            break
                    if not device_name:
                        try:
                            import json
                            from pathlib import Path
                            cache_file = Path.home() / ".config" / "divoom-control" / "discovered_devices.json"
                            if cache_file.exists():
                                devices = json.loads(cache_file.read_text(encoding="utf-8"))
                                for d in devices:
                                    if d.get("address") == address:
                                        device_name = d.get("name")
                                        break
                        except Exception:
                            pass

                    self.current_divoom = Divoom(mac=address, client=client, logger=logger, use_ios_le_protocol=True, device_name=device_name)
                    self._run_async(self.current_divoom.connect())
                    connected = True

            if connected:
                # Save successful connection in config.ini
                try:
                    import configparser
                    config_file = Path.home() / ".config" / "divoom-control" / "config.ini"
                    config_file.parent.mkdir(parents=True, exist_ok=True)
                    cfg = configparser.ConfigParser()
                    if config_file.exists():
                        cfg.read(config_file)
                    if "gui" not in cfg:
                        cfg["gui"] = {}
                    cfg["gui"]["last_connected_device"] = address
                    with open(config_file, "w") as f:
                        cfg.write(f)
                    logger.info(f"Saved last active connection: {address}")
                except Exception as save_err:
                    logger.warning(f"Failed to persist active connection: {save_err}")
                return True
            return False
        except Exception as e:
            logger.error(f"Single connect failed: {e}")
            self.current_divoom = None
            return False

    # ── Display Coordinate Wall (Free-Form Crops) ──────────────────────────────

    def update_wall_slots(self, slots_json: str) -> None:
        """Syncs drag-and-drop free-form coordinates from JS and persists as last active."""
        logger.info(f"GUI Action: Syncing free-form layout slots: {slots_json}")
        self.wall_slots = json.loads(slots_json)
        self.wall_instance = None # Invalidate to force rebuild on next display wall call
        
        # Persist as last active
        try:
            presets_file = self._get_presets_file()
            presets = {}
            if presets_file.exists():
                try:
                    presets = json.loads(presets_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            presets["_last_active_slots_"] = self.wall_slots
            presets_file.write_text(json.dumps(presets, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to save last active slots: {e}")

    def _rebuild_wall_instance(self, cell_size: int = 16) -> bool:
        """Internal helper to construct free-form DivoomWall coordinator from assigned coordinates."""
        if not self.wall_slots:
            return False
            
        if self.wall_instance and self.wall_instance.is_connected:
            return True
            
        logger.info("Rebuilding free-form DivoomWall coordinator instance...")
        configs = [{
            "mac": mac,
            "x": int(s.get("x", 0)), "y": int(s.get("y", 0)),
            "size": int(s.get("size", cell_size)),
            "width": int(s.get("width", 120)), "height": int(s.get("height", 120))
        } for mac, s in self.wall_slots.items()]
            
        try:
            self.wall_instance = DivoomWall(configs, custom_logger=logger)
            self._run_async(self.wall_instance.connect())
            return True
        except Exception as e:
            logger.error(f"Failed to build display wall: {e}")
            self.wall_instance = None
            return False

    def set_solid_light(self, color: str, brightness: int) -> bool:
        """Sets ambient solid lighting across active screen(s) / display wall."""
        logger.info(f"GUI Action: Applying solid light {color} (brightness={brightness})...")
        try:
            if getattr(self, "current_target_mode", "single") == "wall":
                if not self._rebuild_wall_instance():
                    return False
                return self._run_async(self.wall_instance.set_light(color, brightness))
            elif self.current_divoom:
                return self._run_async(self.current_divoom.display.show_light(color, brightness, True))
            return False
        except Exception as e:
            logger.error(f"Light setting failed: {e}")
            return False

    def set_clock(self, style: int, color: str = None) -> bool:
        """Sets clock display channel across active screen(s) / display wall."""
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
        """Switches display active channel mode (Clock, Visualizer, VJ, Design)."""
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
        """Select a specific VJ effect (0-15) on the active screen(s)/wall.

        Effect indices map to divoom_lib VJEffectType (Sparkles..RainbowShapes).
        """
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
        """Select a specific Music EQ / visualizer pattern on the active screen(s)/wall."""
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
        """Crops, splits, and displays coordinate grid screen wall artworks."""
        logger.info(f"GUI Action: Push display wall asset {file_path!r} (cell size={cell_size})...")
        try:
            if not self._rebuild_wall_instance(cell_size):
                return False
            return self._run_async(self.wall_instance.show_image(file_path))
        except Exception as e:
            logger.error(f"Wall display failed: {e}")
            return False

def main():
    api = DivoomGuiAPI()
    web_ui_dir = Path(__file__).parent / "web_ui"
    index_html = web_ui_dir / "index.html"

    # Optional headless control surface (instrumentation / scripting / E2E).
    # Enable with DIVOOM_CONTROL_SERVER=1 (port via DIVOOM_CONTROL_PORT).
    if os.environ.get("DIVOOM_CONTROL_SERVER") in ("1", "true", "yes"):
        try:
            from control_server import serve_in_background
            port = int(os.environ.get("DIVOOM_CONTROL_PORT", "8787"))
            serve_in_background(api, port=port)
            logger.info(f"Control server enabled on http://127.0.0.1:{port}")
        except Exception as e:
            logger.warning(f"Failed to start control server: {e}")

    # Optional Unix-domain-socket control surface (DIVOOM_CONTROL_SOCKET=/path).
    sock_path = os.environ.get("DIVOOM_CONTROL_SOCKET")
    if sock_path:
        try:
            from control_server import serve_unix_in_background
            serve_unix_in_background(api, sock_path)
            logger.info(f"Control server enabled on unix:{sock_path}")
        except Exception as e:
            logger.warning(f"Failed to start unix control server: {e}")

    logger.info("Starting Divoom Desktop GUI window in frameless mode...")
    
    window = webview.create_window(
        title="Divoom Control Center",
        url=str(index_html),
        js_api=api,
        width=1024,
        height=768,
        resizable=True,
        frameless=True,  # Integrated custom Appbar
        # easy_drag operates at the native window level and is NOT blocked by
        # CSS -webkit-app-region: no-drag, so it dragged the whole window when
        # moving canvas nodes (regression). Window movement is handled instead
        # by the titlebar's `-webkit-app-region: drag` region (see style.css).
        easy_drag=False,
        background_color="#0a0b10"
    )
    api.window = window
    webview.start()

if __name__ == "__main__":
    main()

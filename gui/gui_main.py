#!/usr/bin/env python3
"""
gui_main.py — Divoom Desktop GUI controller backend.
Launches the premium PyWebView dashboard, exposing Divoom's core BLE features
and coordinate display wall capabilities to the HTML/CSS/JS frontend.
"""

import sys
import json
import asyncio
import logging
import urllib.request
import struct
import webview
from pathlib import Path

# Add divoom-control paths
sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "api_scraper"))

import divoom_auth
from divoom_lib.divoom import Divoom
from divoom_lib.utils import discovery
from divoom_lib.wall import DivoomWall

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("divoom_gui")

class DivoomGuiAPI:
    def __init__(self) -> None:
        self.current_divoom = None
        self.discovered_list = []
        self.wall_slots = {}  # "x_y" -> "mac"
        self.wall_instance = None
        self.cached_creds = None
        self.device_pw = 0
        self.device_id = 0
        
        # Load virtual device details for gallery API
        device_cache_path = Path(__file__).parent.parent / "api_scraper" / "divoom_docs" / "virtual_device.json"
        if device_cache_path.exists():
            try:
                device_info = json.loads(device_cache_path.read_text(encoding="utf-8"))
                self.device_id = device_info.get("BluetoothDeviceId", 0)
                self.device_pw = device_info.get("DevicePassword", 0)
            except Exception as e:
                logger.warning(f"Failed to load virtual device: {e}")

    def _get_async_loop(self):
        """Helper to get or create an event loop in the GUI thread."""
        try:
            return asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop

    def scan_devices(self) -> str:
        """Scan BLE devices and return discovered Divoom screens as JSON."""
        logger.info("GUI Action: Scanning devices...")
        loop = self._get_async_loop()
        try:
            results = loop.run_until_complete(discovery.discover_all_divoom_devices(timeout=4.0))
            self.discovered_list = results
            return json.dumps(results)
        except Exception as e:
            logger.error(f"Device scan failed: {e}")
            return json.dumps([])

    def connect_single_device(self, address: str) -> bool:
        """Establishes connection to a single BLE screen."""
        logger.info(f"GUI Action: Connecting to single device {address}...")
        loop = self._get_async_loop()
        try:
            if self.current_divoom and self.current_divoom.is_connected:
                loop.run_until_complete(self.current_divoom.disconnect())
                
            self.current_divoom = Divoom(mac=address, logger=logger, use_ios_le_protocol=False)
            loop.run_until_complete(self.current_divoom.connect())
            return True
        except Exception as e:
            logger.error(f"Single connect failed: {e}")
            self.current_divoom = None
            return False

    def update_wall_slots(self, slots_json: str) -> None:
        """Syncs drag-and-drop grid slot coordinate assignments from JS."""
        logger.info(f"GUI Action: Syncing wall grid layout: {slots_json}")
        self.wall_slots = json.loads(slots_json)
        self.wall_instance = None # Invalidate to force rebuild on next display wall call

    def _rebuild_wall_instance(self, cell_size: int = 16) -> bool:
        """Internal helper to construct DivoomWall coordinator from assigned grid slots."""
        if not self.wall_slots:
            return False
            
        if self.wall_instance and self.wall_instance.is_connected:
            return True
            
        logger.info("Rebuilding DivoomWall coordinator instance...")
        configs = []
        for key, mac in self.wall_slots.items():
            x_str, y_str = key.split("_")
            configs.append({
                "mac": mac,
                "x": int(x_str),
                "y": int(y_str),
                "size": cell_size
            })
            
        try:
            self.wall_instance = DivoomWall(configs, custom_logger=logger)
            loop = self._get_async_loop()
            loop.run_until_complete(self.wall_instance.connect())
            return True
        except Exception as e:
            logger.error(f"Failed to build display wall: {e}")
            self.wall_instance = None
            return False

    def set_solid_light(self, color: str, brightness: int) -> bool:
        """Sets ambient solid lighting across active screen(s) / display wall."""
        logger.info(f"GUI Action: Applying solid light {color} (brightness={brightness})...")
        loop = self._get_async_loop()
        try:
            if self.wall_slots:
                if not self._rebuild_wall_instance():
                    return False
                return loop.run_until_complete(self.wall_instance.set_light(color, brightness))
            elif self.current_divoom and self.current_divoom.is_connected:
                return loop.run_until_complete(self.current_divoom.display.show_light(color, brightness))
            return False
        except Exception as e:
            logger.error(f"Light setting failed: {e}")
            return False

    def set_clock(self, style: int) -> bool:
        """Sets clock display channel across active screen(s) / display wall."""
        logger.info(f"GUI Action: Applying clock style {style}...")
        loop = self._get_async_loop()
        try:
            if self.wall_slots:
                if not self._rebuild_wall_instance():
                    return False
                return loop.run_until_complete(self.wall_instance.show_clock(clock=style))
            elif self.current_divoom and self.current_divoom.is_connected:
                return loop.run_until_complete(self.current_divoom.display.show_clock(clock=style))
            return False
        except Exception as e:
            logger.error(f"Clock setting failed: {e}")
            return False

    def switch_channel(self, channel: str) -> bool:
        """Switches display active channel mode (Clock, Visualizer, VJ, Design)."""
        logger.info(f"GUI Action: Switching channel to {channel}...")
        loop = self._get_async_loop()
        try:
            target = self.current_divoom
            if not target or not target.is_connected:
                if self.wall_slots:
                    if not self._rebuild_wall_instance():
                        return False
                    # Use the first slot device as default
                    target = self.wall_instance.devices[0][0]
                else:
                    return False
                    
            if channel == "clock":
                return loop.run_until_complete(target.display.show_clock())
            elif channel == "visualizer":
                return loop.run_until_complete(target.display.show_visualization(number=0))
            elif channel == "vj":
                return loop.run_until_complete(target.display.show_effects(number=0))
            elif channel == "design":
                return loop.run_until_complete(target.display.show_design())
            return False
        except Exception as e:
            logger.error(f"Channel switch failed: {e}")
            return False

    def display_wall_image(self, file_path: str, cell_size: int) -> bool:
        """Crops, splits, and displays coordinate grid screen wall artworks."""
        logger.info(f"GUI Action: Push display wall asset {file_path!r} (cell size={cell_size})...")
        loop = self._get_async_loop()
        try:
            if not self._rebuild_wall_instance(cell_size):
                return False
            return loop.run_until_complete(self.wall_instance.show_image(file_path))
        except Exception as e:
            logger.error(f"Wall display failed: {e}")
            return False

    def fetch_gallery(self, classify: int) -> str:
        """Fetches popular community gallery artworks from Divoom Cloud."""
        logger.info(f"GUI Action: Fetching gallery classify={classify}...")
        try:
            if not self.cached_creds:
                self.cached_creds = divoom_auth.get_credentials()
                
            body = {
                "Command": "GetCategoryFileListV2",
                "Token": self.cached_creds.token,
                "UserId": self.cached_creds.user_id,
                "DeviceId": self.device_id,
                "Classify": classify,
                "FileSort": 1,   # Popular
                "FileType": 5,   # All
                "FileSize": 127, # All sizes
                "Version": 19,
                "StartNum": 1,
                "EndNum": 30,
                "RefreshIndex": 0
            }
            if self.device_pw:
                body["DevicePassword"] = self.device_pw

            url = "https://appin.divoom-gz.com/GetCategoryFileListV2"
            payload = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "User-Agent": "okhttp/4.12.0",
                },
                method="POST"
            )
            
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                file_list = data.get("FileList", [])
                
                results = []
                for item in file_list:
                    results.append({
                        "name": item.get("FileName", "unnamed"),
                        "file_id": item.get("FileId"),
                        "likes": item.get("LikeCnt", 0),
                        "magic": item.get("FileType", 3)
                    })
                return json.dumps(results)
        except Exception as e:
            logger.error(f"Gallery fetch failed: {e}")
            return json.dumps([])

    def batch_sync_artwork(self, artwork_json: str) -> bool:
        """Syncs the selected artwork to all active devices in parallel."""
        logger.info(f"GUI Action: Batch syncing artwork details: {artwork_json}")
        loop = self._get_async_loop()
        try:
            art = json.loads(artwork_json)
            file_id = art["file_id"]
            
            # Download file
            logger.info(f"Downloading gallery asset from CDN: {file_id}...")
            dl_url = f"https://fin.divoom-gz.com/{file_id}"
            d_req = urllib.request.Request(dl_url, headers={"User-Agent": "okhttp/4.12.0"})
            
            with urllib.request.urlopen(d_req, timeout=10) as d_resp:
                file_bytes = d_resp.read()
                if len(file_bytes) < 4:
                    return False
                
                # Broad-sync the downloaded payload directly to all arranged screens
                targets = []
                if self.wall_slots:
                    if not self._rebuild_wall_instance():
                        return False
                    targets = [d for d, _, _, _ in self.wall_instance.devices]
                elif self.current_divoom and self.current_divoom.is_connected:
                    targets = [self.current_divoom]
                else:
                    return False
                    
                sync_tasks = []
                for divoom in targets:
                    from monthly_best_daemon import stream_raw_bin_payload
                    sync_tasks.append(stream_raw_bin_payload(divoom, file_bytes))
                    
                results = loop.run_until_complete(asyncio.gather(*sync_tasks, return_exceptions=True))
                return all(res is True for res in results)
        except Exception as e:
            logger.error(f"Batch sync failed: {e}")
            return False

def main():
    api = DivoomGuiAPI()
    web_ui_dir = Path(__file__).parent / "web_ui"
    index_html = web_ui_dir / "index.html"
    
    logger.info("Starting Divoom Desktop GUI window...")
    
    webview.create_window(
        title="Divoom Control Center",
        url=str(index_html),
        js_api=api,
        width=1024,
        height=720,
        resizable=True,
        background_color="#0a0b10"
    )
    webview.start()

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
gui_main.py — Divoom Desktop GUI controller backend.
Launches the premium frameless PyWebView dashboard, exposing Divoom's core BLE features
and coordinate display wall capabilities to the HTML/CSS/JS frontend.
"""

import sys
import json
import asyncio
import logging
import urllib.request
import struct
import webview
import threading
import time
from pathlib import Path
from bleak import BleakScanner

# Add divoom-control paths
sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "api_scraper"))

import divoom_auth
from divoom_lib.divoom import Divoom
from divoom_lib.utils import discovery, media_source
from divoom_lib.wall import DivoomWall

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("divoom_gui")

class DivoomGuiAPI:
    def __init__(self) -> None:
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
        
        # Load virtual device details for gallery API
        device_cache_path = Path(__file__).parent.parent / "api_scraper" / "divoom_docs" / "virtual_device.json"
        if device_cache_path.exists():
            try:
                device_info = json.loads(device_cache_path.read_text(encoding="utf-8"))
                self.device_id = device_info.get("BluetoothDeviceId", 0)
                self.device_pw = device_info.get("DevicePassword", 0)
            except Exception as e:
                logger.warning(f"Failed to load virtual device: {e}")

    # ── Transport Status (4-badge panel) ──────────────────────────────────────

    def get_transport_status(self) -> str:
        """
        Return live status of all four transport layers as JSON.

        Called by the JS sidebar every 5 seconds to drive the 4-badge panel.
        Each transport includes: available (bool), label, badge, color, description.

        Transport legend:
            🔵 BLE   — Bluetooth, 100 % local
            🟢 LAN   — Wi-Fi HTTP :9000, 100 % local
            🟡 Cloud — appin.divoom-gz.com, Divoom's servers
            🔴 Ext   — 3rd-party APIs (weather, stocks)
        """
        ble_connected = bool(
            self.current_divoom and self.current_divoom.is_connected
        )
        lan_ip = None
        lan_ok = False
        if self.current_divoom and self.current_divoom.lan:
            lan_ip = self.current_divoom.lan.device_ip
            lan_ok = True

        cloud_ok = bool(self.cached_creds and self.cached_creds.is_valid())

        return json.dumps({
            "ble":  {
                "available":   ble_connected,
                "label":       "BLE",
                "badge":       "🔵",
                "color":       "#3b82f6",
                "description": "Bluetooth — 100 % local, never leaves your device.",
                "detail":      self.current_divoom._conn.mac if ble_connected and self.current_divoom else None,
            },
            "lan": {
                "available":   lan_ok,
                "label":       "LAN",
                "badge":       "🟢",
                "color":       "#22c55e",
                "description": "Wi-Fi HTTP :9000 — 100 % local, WiFi-capable devices only.",
                "detail":      f"{lan_ip}:9000" if lan_ip else "No device IP configured",
            },
            "cloud": {
                "available":   cloud_ok,
                "label":       "Divoom Cloud",
                "badge":       "🟡",
                "color":       "#f59e0b",
                "description": "appin.divoom-gz.com — Divoom's servers, requires account.",
                "detail":      "Authenticated" if cloud_ok else "Not authenticated",
            },
            "external": {
                "available":   True,
                "label":       "External",
                "badge":       "🔴",
                "color":       "#ef4444",
                "description": "3rd-party APIs (weather, stocks) — no login required.",
                "detail":      "Available",
            },
        })

    def save_lan_config(self, device_ip: str, local_token: int) -> bool:
        """
        Save LAN device IP and token to config and attach LAN transport to
        the current Divoom instance.

        Transport: 🟢 LAN — configures local Wi-Fi HTTP transport.
        """
        logger.info(f"GUI Action: Saving LAN config ip={device_ip} token={local_token}...")
        try:
            import configparser
            config_file = Path(__file__).parent.parent / "config.ini"
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

        Transport: 🟢 LAN
        """
        logger.info("GUI Action: Probing LAN transport reachability...")
        try:
            if not self.current_divoom or not self.current_divoom.lan:
                return json.dumps({"reachable": False, "detail": "No LAN IP configured. Save a device IP first."})
            ok = asyncio.run(self.current_divoom.lan.probe())
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
        if self.window:
            def _destroy():
                time.sleep(0.1)
                self.window.destroy()
            threading.Thread(target=_destroy, daemon=True).start()

    # ── Device Scanner Core (asyncio.run Thread-Safe) ──────────────────────────────

    def scan_devices(self) -> str:
        """Scan BLE devices and return discovered Divoom screens as JSON."""
        return self.scan_devices_with_config(timeout=15, limit=4)

    def scan_devices_with_config(self, timeout: int, limit: int) -> str:
        """Scan BLE devices with custom timeouts and device limit."""
        logger.info(f"GUI Action: Scanning devices with timeout={timeout}, limit={limit}...")
        
        # Save scanner limits into config.ini for next time
        try:
            import configparser
            config_file = Path(__file__).parent.parent / "config.ini"
            cfg = configparser.ConfigParser()
            if config_file.exists():
                cfg.read(config_file)
            if "gui" not in cfg:
                cfg["gui"] = {}
            cfg["gui"]["timeout"] = str(timeout)
            cfg["gui"]["limit"] = str(limit)
            with open(config_file, "w") as f:
                cfg.write(f)
        except Exception as e:
            logger.warning(f"Failed to save scan config: {e}")

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
                    
                results = asyncio.run(run_scan())
                if not results:
                    results = asyncio.run(discovery.discover_all_divoom_devices(timeout=float(timeout)))
                    results = results[:limit]
            else:
                results = asyncio.run(discovery.discover_all_divoom_devices(timeout=float(timeout)))
                
            self.discovered_list = results
            return json.dumps(results)
        except Exception as e:
            logger.error(f"Device scan failed: {e}")
            return json.dumps([])

    def connect_single_device(self, address: str) -> bool:
        """Establishes connection to a single BLE screen."""
        logger.info(f"GUI Action: Connecting to single device {address}...")
        try:
            if self.current_divoom and self.current_divoom.is_connected:
                asyncio.run(self.current_divoom.disconnect())
                
            self.current_divoom = Divoom(mac=address, logger=logger, use_ios_le_protocol=False)
            asyncio.run(self.current_divoom.connect())
            return True
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
            presets_file = Path(__file__).parent / "presets.json"
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
        configs = []
        for mac, slot in self.wall_slots.items():
            configs.append({
                "mac": mac,
                "x": int(slot.get("x", 0)),
                "y": int(slot.get("y", 0)),
                "size": int(slot.get("size", cell_size)),
                "width": int(slot.get("width", 120)),
                "height": int(slot.get("height", 120))
            })
            
        try:
            self.wall_instance = DivoomWall(configs, custom_logger=logger)
            asyncio.run(self.wall_instance.connect())
            return True
        except Exception as e:
            logger.error(f"Failed to build display wall: {e}")
            self.wall_instance = None
            return False

    def set_solid_light(self, color: str, brightness: int) -> bool:
        """Sets ambient solid lighting across active screen(s) / display wall."""
        logger.info(f"GUI Action: Applying solid light {color} (brightness={brightness})...")
        try:
            if self.wall_slots:
                if not self._rebuild_wall_instance():
                    return False
                return asyncio.run(self.wall_instance.set_light(color, brightness))
            elif self.current_divoom and self.current_divoom.is_connected:
                return asyncio.run(self.current_divoom.display.show_light(color, brightness))
            return False
        except Exception as e:
            logger.error(f"Light setting failed: {e}")
            return False

    def set_clock(self, style: int) -> bool:
        """Sets clock display channel across active screen(s) / display wall."""
        logger.info(f"GUI Action: Applying clock style {style}...")
        try:
            if self.wall_slots:
                if not self._rebuild_wall_instance():
                    return False
                return asyncio.run(self.wall_instance.show_clock(clock=style))
            elif self.current_divoom and self.current_divoom.is_connected:
                return asyncio.run(self.current_divoom.display.show_clock(clock=style))
            return False
        except Exception as e:
            logger.error(f"Clock setting failed: {e}")
            return False

    def switch_channel(self, channel: str) -> bool:
        """Switches display active channel mode (Clock, Visualizer, VJ, Design)."""
        logger.info(f"GUI Action: Switching channel to {channel}...")
        try:
            target = self.current_divoom
            if not target or not target.is_connected:
                if self.wall_slots:
                    if not self._rebuild_wall_instance():
                        return False
                    target = self.wall_instance.devices[0][0]
                else:
                    return False
                    
            if channel == "clock":
                return asyncio.run(target.display.show_clock())
            elif channel == "visualizer":
                return asyncio.run(target.display.show_visualization(number=0))
            elif channel == "vj":
                return asyncio.run(target.display.show_effects(number=0))
            elif channel == "design":
                return asyncio.run(target.display.show_design())
            return False
        except Exception as e:
            logger.error(f"Channel switch failed: {e}")
            return False

    def display_wall_image(self, file_path: str, cell_size: int) -> bool:
        """Crops, splits, and displays coordinate grid screen wall artworks."""
        logger.info(f"GUI Action: Push display wall asset {file_path!r} (cell size={cell_size})...")
        try:
            if not self._rebuild_wall_instance(cell_size):
                return False
            return asyncio.run(self.wall_instance.show_image(file_path))
        except Exception as e:
            logger.error(f"Wall display failed: {e}")
            return False

    # ── Cloud Gallery & Previews Cache ───────────────────────────────────────────

    # ── Cloud Gallery & Previews Cache ───────────────────────────────────────────

    def _get_device_size(self, address: str) -> int:
        for d in self.discovered_list:
            if d.get("address") == address:
                name = d.get("name", "").lower()
                if "64" in name:
                    return 64
                return 16
        return 16

    def _extract_gif_from_magic_43(self, file_data: bytes) -> bytes | None:
        if len(file_data) < 10 or file_data[0] != 43:
            return None
        try:
            text_len = struct.unpack("<I", file_data[6:10])[0]
            text_start = 10
            text_end = text_start + text_len
            
            gif_len_offset = text_end
            if len(file_data) < gif_len_offset + 4:
                return None
                
            gif_len = struct.unpack("<I", file_data[gif_len_offset:gif_len_offset+4])[0]
            gif_start = gif_len_offset + 4
            gif_end = gif_start + gif_len
            
            if gif_end > len(file_data):
                gif_end = len(file_data)
                
            gif_data = file_data[gif_start:gif_end]
            if gif_data.startswith(b"GIF89a") or gif_data.startswith(b"GIF87a"):
                return gif_data
        except Exception as e:
            logger.warning(f"Failed to extract GIF: {e}")
        return None

    def fetch_gallery(self, classify: int, target_size: int = 16) -> str:
        """
        Fetches popular community gallery artworks and caches previews locally.
        Filters by active connected device grid size to prevent hardware scaling mismatch.
        """
        logger.info(f"GUI Action: Fetching gallery classify={classify} target_size={target_size}...")
        try:
            if not self.cached_creds:
                self.cached_creds = divoom_auth.get_credentials()
                
            # FileSize bitmask: 1=16px, 2=32px, 4=64px
            file_size_bitmask = 127
            if target_size == 16:
                file_size_bitmask = 1
            elif target_size == 32:
                file_size_bitmask = 2
            elif target_size == 64:
                file_size_bitmask = 4
                
            body = {
                "Command": "GetCategoryFileListV2",
                "Token": self.cached_creds.token,
                "UserId": self.cached_creds.user_id,
                "DeviceId": self.device_id,
                "Classify": classify,
                "FileSort": 1,
                "FileType": 5,
                "FileSize": file_size_bitmask,
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
                
                cache_dir = Path(__file__).parent / "web_ui" / "assets" / "cache_gallery"
                cache_dir.mkdir(parents=True, exist_ok=True)
                
                results = []
                for item in file_list:
                    file_id = item.get("FileId")
                    pixel_amb_id = item.get("PixelAmbId")
                    preview_url = ""
                    
                    if file_id:
                        safe_filename = file_id.replace("/", "_")
                        cache_file = cache_dir / safe_filename
                        
                        if not cache_file.exists():
                            try:
                                dl_url = f"https://fin.divoom-gz.com/{file_id}"
                                req_dl = urllib.request.Request(dl_url, headers={"User-Agent": "okhttp/4.12.0"})
                                with urllib.request.urlopen(req_dl, timeout=5) as dl_resp:
                                    raw_bytes = dl_resp.read()
                                    
                                    extracted_gif = self._extract_gif_from_magic_43(raw_bytes)
                                    if extracted_gif:
                                        cache_file = cache_file.with_suffix(".gif")
                                        cache_file.write_bytes(extracted_gif)
                                        logger.info(f"Gallery Cache: Extracted Magic 43 GIF to {cache_file.name}")
                                    elif raw_bytes.startswith(b"GIF89a") or raw_bytes.startswith(b"GIF87a"):
                                        cache_file = cache_file.with_suffix(".gif")
                                        cache_file.write_bytes(raw_bytes)
                                        logger.info(f"Gallery Cache: Saved standard GIF to {cache_file.name}")
                                    else:
                                        if pixel_amb_id:
                                            fallback_filename = pixel_amb_id.replace("/", "_")
                                            cache_file = cache_dir / fallback_filename
                                            if not cache_file.exists():
                                                dl_url_fb = f"https://fin.divoom-gz.com/{pixel_amb_id}"
                                                req_dl_fb = urllib.request.Request(dl_url_fb, headers={"User-Agent": "okhttp/4.12.0"})
                                                with urllib.request.urlopen(req_dl_fb, timeout=5) as dl_resp_fb:
                                                    cache_file.write_bytes(dl_resp_fb.read())
                                        else:
                                            cache_file = cache_file.with_suffix(".bin")
                                            cache_file.write_bytes(raw_bytes)
                            except Exception as dl_err:
                                logger.warning(f"Failed to cache preview for {file_id}: {dl_err}")
                        
                        for ext in [".gif", "", ".png", ".bin"]:
                            possible_file = cache_file.with_suffix(ext) if ext else cache_file
                            if possible_file.exists():
                                preview_url = f"assets/cache_gallery/{possible_file.name}"
                                break
                    
                    results.append({
                        "name": item.get("FileName", "unnamed"),
                        "file_id": file_id,
                        "likes": item.get("LikeCnt", 0),
                        "magic": item.get("FileType", 3),
                        "preview_url": preview_url
                    })
                return json.dumps(results)
        except Exception as e:
            logger.error(f"Gallery fetch failed: {e}")
            return json.dumps([])

    def batch_sync_artwork(self, artwork_json: str) -> bool:
        """Syncs the selected artwork to all active devices in parallel with automatic PIL resizing."""
        logger.info(f"GUI Action: Batch syncing artwork details: {artwork_json}")
        try:
            art = json.loads(artwork_json)
            file_id = art["file_id"]
            
            logger.info(f"Downloading gallery asset from CDN: {file_id}...")
            dl_url = f"https://fin.divoom-gz.com/{file_id}"
            d_req = urllib.request.Request(dl_url, headers={"User-Agent": "okhttp/4.12.0"})
            
            with urllib.request.urlopen(d_req, timeout=10) as d_resp:
                file_bytes = d_resp.read()
                if len(file_bytes) < 4:
                    return False
                
                targets = []
                if self.wall_slots:
                    if not self._rebuild_wall_instance():
                        return False
                    targets = [d for d, _, _, _, _, _ in self.wall_instance.devices]
                elif self.current_divoom and self.current_divoom.is_connected:
                    targets = [self.current_divoom]
                else:
                    return False
                    
                extracted_gif = self._extract_gif_from_magic_43(file_bytes)
                is_gif = False
                gif_data = None
                
                if extracted_gif:
                    is_gif = True
                    gif_data = extracted_gif
                elif file_bytes.startswith(b"GIF89a") or file_bytes.startswith(b"GIF87a"):
                    is_gif = True
                    gif_data = file_bytes
                
                async def run_sync():
                    sync_tasks = []
                    for divoom in targets:
                        if is_gif:
                            target_size = self._get_device_size(divoom._conn.mac)
                            temp_dir = Path(__file__).parent.parent / "scratch"
                            temp_dir.mkdir(parents=True, exist_ok=True)
                            
                            temp_input = temp_dir / f"sync_in_{divoom._conn.mac}.gif"
                            temp_input.write_bytes(gif_data)
                            
                            temp_output = temp_dir / f"sync_out_{divoom._conn.mac}.gif"
                            
                            try:
                                from PIL import Image
                                with Image.open(temp_input) as img:
                                    frames = []
                                    durations = []
                                    for frame_idx in range(img.n_frames):
                                        img.seek(frame_idx)
                                        resized_frame = img.resize((target_size, target_size), Image.Resampling.NEAREST)
                                        frames.append(resized_frame.convert("RGB"))
                                        durations.append(img.info.get("duration", 100))
                                    
                                    frames[0].save(
                                        temp_output,
                                        save_all=True,
                                        append_images=frames[1:],
                                        duration=durations,
                                        loop=0
                                    )
                                logger.info(f"Sync: Resized GIF to {target_size}x{target_size} for {divoom._conn.mac}")
                                sync_tasks.append(divoom.display.show_image(str(temp_output)))
                            except Exception as resize_err:
                                logger.error(f"Failed to resize GIF: {resize_err}")
                                sync_tasks.append(divoom.display.show_image(str(temp_input)))
                        else:
                            from monthly_best_daemon import stream_raw_bin_payload
                            sync_tasks.append(stream_raw_bin_payload(divoom, file_bytes))
                            
                    results = await asyncio.gather(*sync_tasks, return_exceptions=True)
                    return all(res is True for res in results)
                    
                return asyncio.run(run_sync())
        except Exception as e:
            logger.error(f"Batch sync failed: {e}")
            return False

    # ── Live macOS Music Integration ─────────────────────────────────────────────
    
    def _music_sync_loop(self):
        """Background thread polling macOS active playback and streaming artwork."""
        last_track = None
        last_artist = None
        while self.music_sync_active:
            try:
                track_info = media_source.get_current_playing_track()
                if track_info:
                    track = track_info.get("track")
                    artist = track_info.get("artist")
                    source = track_info.get("source")
                    
                    if track != last_track or artist != last_artist:
                        logger.info(f"Music Sync: New track: {track} by {artist} ({source})")
                        last_track = track
                        last_artist = artist
                        
                        art_url = media_source.fetch_album_art_url(track, artist)
                        if art_url:
                            size = 16
                            out_path = media_source.render_and_downsample_artwork(art_url, size=size)
                            if out_path and out_path.exists():
                                logger.info(f"Music Sync: Push cover art frame: {out_path}")
                                try:
                                    if self.wall_slots:
                                        if self._rebuild_wall_instance(size):
                                            asyncio.run(self.wall_instance.show_image(str(out_path)))
                                    elif self.current_divoom and self.current_divoom.is_connected:
                                        asyncio.run(self.current_divoom.display.show_image(str(out_path)))
                                except Exception as e:
                                    logger.error(f"Failed to stream artwork: {e}")
                                    
                            self.current_track_cache = {
                                "track": track,
                                "artist": artist,
                                "source": source,
                                "artwork_url": art_url
                            }
                        else:
                            self.current_track_cache = {
                                "track": track,
                                "artist": artist,
                                "source": source,
                                "artwork_url": ""
                            }
                else:
                    self.current_track_cache = None
            except Exception as e:
                logger.error(f"Music sync error: {e}")
            time.sleep(3.0)

    def toggle_music_sync(self, enable: bool) -> bool:
        logger.info(f"GUI Action: Toggle music sync to {enable}")
        self.music_sync_active = enable
        if enable:
            if not self.music_thread or not self.music_thread.is_alive():
                self.music_thread = threading.Thread(target=self._music_sync_loop, daemon=True)
                self.music_thread.start()
        return True

    def get_current_track_info(self) -> str:
        if self.current_track_cache:
            return json.dumps(self.current_track_cache)
        return json.dumps({})

    # ── Yahoo Finance Ticker Integration ──────────────────────────────────────────
    
    def apply_stock_ticker(self, symbol: str) -> str:
        logger.info(f"GUI Action: Applying stock ticker for {symbol}...")
        try:
            data = media_source.fetch_stock_ticker(symbol)
            if not data:
                return json.dumps({"success": False})
                
            size = 16
            frame_path = media_source.render_stock_ticker_frame(symbol, data, size=size)
            
            res = False
            if self.wall_slots:
                if self._rebuild_wall_instance(size):
                    res = asyncio.run(self.wall_instance.show_image(str(frame_path)))
            elif self.current_divoom and self.current_divoom.is_connected:
                res = asyncio.run(self.current_divoom.display.show_image(str(frame_path)))
                
            return json.dumps({
                "success": res,
                "price": data["price"],
                "change": data["change"],
                "pct_change": data["pct_change"]
            })
        except Exception as e:
            logger.error(f"Failed to apply stock ticker: {e}")
            return json.dumps({"success": False, "error": str(e)})

    # ── Credentials & Config/Preset Persistence ──────────────────────────────────
    
    def save_credentials(self, email: str, password: str) -> bool:
        logger.info(f"GUI Action: Saving cloud credentials for {email}...")
        try:
            import configparser
            config_file = Path(__file__).parent.parent / "config.ini"
            cfg = configparser.ConfigParser()
            if config_file.exists():
                cfg.read(config_file)
            if "divoom" not in cfg:
                cfg["divoom"] = {}
            cfg["divoom"]["email"] = email
            cfg["divoom"]["password"] = password
            
            with open(config_file, "w") as f:
                cfg.write(f)
                
            auth_cache = Path(__file__).parent.parent / "api_scraper" / "divoom_docs" / "auth_token.json"
            if auth_cache.exists():
                auth_cache.unlink()
                
            self.cached_creds = divoom_auth.get_credentials(force_refresh=True)
            return self.cached_creds.is_valid()
        except Exception as e:
            logger.error(f"Failed to save credentials: {e}")
            return False

    def load_config(self) -> str:
        logger.info("GUI Action: Loading configurations...")
        try:
            import configparser
            config_file = Path(__file__).parent.parent / "config.ini"
            cfg = configparser.ConfigParser()
            email = ""
            timeout = 15
            limit = 4
            lan_ip = ""
            lan_token = 0
            
            if config_file.exists():
                cfg.read(config_file)
                email = cfg.get("divoom", "email", fallback="")
                timeout = int(cfg.get("gui", "timeout", fallback="15"))
                limit = int(cfg.get("gui", "limit", fallback="4"))
                lan_ip = cfg.get("lan", "device_ip", fallback="")
                lan_token = int(cfg.get("lan", "local_token", fallback="0"))
                
            presets_file = Path(__file__).parent / "presets.json"
            slots = {}
            if presets_file.exists():
                try:
                    data = json.loads(presets_file.read_text(encoding="utf-8"))
                    slots = data.get("_last_active_slots_", {})
                except Exception:
                    pass
                    
            return json.dumps({
                "email": email,
                "timeout": timeout,
                "limit": limit,
                "slots": slots,
                "lan_ip": lan_ip,
                "lan_token": lan_token,
            })
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return json.dumps({})


    def save_preset(self, name: str, slots_json: str) -> bool:
        logger.info(f"GUI Action: Saving layout preset '{name}'...")
        try:
            presets_file = Path(__file__).parent / "presets.json"
            presets = {}
            if presets_file.exists():
                try:
                    presets = json.loads(presets_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            presets[name] = json.loads(slots_json)
            presets_file.write_text(json.dumps(presets, indent=2), encoding="utf-8")
            return True
        except Exception as e:
            logger.error(f"Failed to save preset: {e}")
            return False

    def load_preset_names(self) -> str:
        logger.info("GUI Action: Loading preset names...")
        try:
            presets_file = Path(__file__).parent / "presets.json"
            if presets_file.exists():
                try:
                    presets = json.loads(presets_file.read_text(encoding="utf-8"))
                    names = [k for k in presets.keys() if k != "_last_active_slots_"]
                    return json.dumps(names)
                except Exception:
                    pass
            return json.dumps([])
        except Exception as e:
            logger.error(f"Failed to load preset names: {e}")
            return json.dumps([])

    def load_preset_by_name(self, name: str) -> str:
        logger.info(f"GUI Action: Loading preset '{name}'...")
        try:
            presets_file = Path(__file__).parent / "presets.json"
            if presets_file.exists():
                try:
                    presets = json.loads(presets_file.read_text(encoding="utf-8"))
                    slots = presets.get(name, {})
                    return json.dumps(slots)
                except Exception:
                    pass
            return json.dumps({})
        except Exception as e:
            logger.error(f"Failed to load preset '{name}': {e}")
            return json.dumps({})

def main():
    api = DivoomGuiAPI()
    web_ui_dir = Path(__file__).parent / "web_ui"
    index_html = web_ui_dir / "index.html"
    
    logger.info("Starting Divoom Desktop GUI window in frameless mode...")
    
    window = webview.create_window(
        title="Divoom Control Center",
        url=str(index_html),
        js_api=api,
        width=1024,
        height=768,
        resizable=True,
        frameless=True,  # Integrated custom Appbar
        background_color="#0a0b10"
    )
    api.window = window
    webview.start()

if __name__ == "__main__":
    main()

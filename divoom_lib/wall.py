#!/usr/bin/env python3
"""
wall.py — Multi-device display wall coordinator.
Splits images/animations into quadrants and streams them in parallel to multiple Divoom BLE screens.
"""

import asyncio
import logging
import tempfile
from pathlib import Path
from PIL import Image, ImageSequence
from typing import List, Dict, Any

from divoom_lib.divoom import Divoom
from divoom_lib.models import DeviceSlot

logger = logging.getLogger(__name__)


def wall_resolution(panel_resolution: int, grid_cols: int, grid_rows: int) -> tuple[int, int]:
    """Compute the **composite** wall canvas size from the per-panel resolution
    and the grid dimensions. This is the size of the source image you'd push
    to a wall (it gets split into per-panel slices).

     `panel_resolution` is the per-panel pixel dimension (16/32/64) — see
    `divoom_lib.models.capabilities.Capabilities.panel_resolution`. It is
    NOT the wall canvas size.

    Examples:
        # 2x2 wall of 16×16 panels (e.g. four Pixoos):
        wall_resolution(16, 2, 2)  # → (32, 32)
        # 2x1 wall of 32×32 panels (e.g. two TivooMax side-by-side):
        wall_resolution(32, 2, 1)  # → (64, 32)
        # 4x2 wall of 32×32 panels (e.g. eight Timoos):
        wall_resolution(32, 4, 2)  # → (128, 64)
    """
    if panel_resolution not in (16, 32, 64):
        raise ValueError(f"panel_resolution must be 16, 32, or 64; got {panel_resolution}")
    if grid_cols < 1 or grid_rows < 1:
        raise ValueError(f"grid must be at least 1×1; got {grid_cols}×{grid_rows}")
    return (panel_resolution * grid_cols, panel_resolution * grid_rows)

class DivoomWall:
    """
    Coordinates multiple Divoom screens arranged in a 2D grid to act as a single unified display.
    
    Usage::
    
        from divoom_lib.wall import DivoomWall
        
        # Configure devices in a 2x2 grid (each 16x16 pixels)
        configs = [
            {"mac": "AA:BB:CC:DD:EE:01", "x": 0, "y": 0, "size": 16}, # Top-left
            {"mac": "AA:BB:CC:DD:EE:02", "x": 1, "y": 0, "size": 16}, # Top-right
            {"mac": "AA:BB:CC:DD:EE:03", "x": 0, "y": 1, "size": 16}, # Bottom-left
            {"mac": "AA:BB:CC:DD:EE:04", "x": 1, "y": 1, "size": 16}  # Bottom-right
        ]
        
        wall = DivoomWall(configs)
        await wall.connect()
        await wall.show_image("large_animation.gif")
        await wall.disconnect()
    """
    def __init__(self, device_configs: List[Dict[str, Any]], custom_logger: logging.Logger | None = None) -> None:
        """
        Initializes the DivoomWall coordinator.
        
        Args:
            device_configs (list): Configuration for each screen in the display wall.
                                   Format: [{"mac": str, "x": int, "y": int, "size": int}]
        """
        self.logger = custom_logger or logger
        self.device_configs = device_configs
        self.devices: List[DeviceSlot] = []
        self.last_previews: Dict[str, bytes] = {}
        
        # Calculate composite bounding box
        self.is_free_form = any("width" in config for config in self.device_configs)
        
        if self.is_free_form:
            self.min_x = min(config.get("x", 0) for config in self.device_configs)
            self.min_y = min(config.get("y", 0) for config in self.device_configs)
            max_x = max(config.get("x", 0) + config.get("width", 120) for config in self.device_configs)
            max_y = max(config.get("y", 0) + config.get("height", 120) for config in self.device_configs)
            
            self.total_width = max_x - self.min_x
            self.total_height = max_y - self.min_y
            self.grid_unit_size = self.device_configs[0].get("size", 16) if self.device_configs else 16
            
            for config in self.device_configs:
                mac = config["mac"]
                x = config.get("x", 0)
                y = config.get("y", 0)
                size = config.get("size", 16)
                width = config.get("width", 120)
                height = config.get("height", 120)
                
                divoom = Divoom(mac=mac, logger=self.logger, use_ios_le_protocol=True)
                # Store absolute bounding box: (divoom, x, y, size, width, height)
                self.devices.append(DeviceSlot(device=divoom, x=x, y=y, size=size, width=width, height=height))
        else:
            max_x_slot = 0
            max_y_slot = 0
            
            for config in self.device_configs:
                mac = config["mac"]
                x = config.get("x", 0)
                y = config.get("y", 0)
                size = config.get("size", 16)
                
                divoom = Divoom(mac=mac, logger=self.logger, use_ios_le_protocol=True)
                self.devices.append(DeviceSlot(device=divoom, x=x, y=y, size=size))
                
                if x + 1 > max_x_slot:
                    max_x_slot = x + 1
                if y + 1 > max_y_slot:
                    max_y_slot = y + 1
                    
            self.grid_unit_size = self.device_configs[0].get("size", 16) if self.device_configs else 16
            self.total_width = max_x_slot * self.grid_unit_size
            self.total_height = max_y_slot * self.grid_unit_size
            self.min_x = 0
            self.min_y = 0
            
        self.logger.info(f"Initialized DivoomWall (composite canvas size: {self.total_width}x{self.total_height} pixels)")

    async def connect(self) -> None:
        """Establishes connections to all wall Divoom devices in parallel."""
        self.logger.info("Connecting to all Divoom display wall devices...")
        connect_tasks = []
        for slot in self.devices:
            self.logger.info(f"Connecting to screen at Slot ({slot.x}, {slot.y}) MAC: {slot.device.mac}...")
            connect_tasks.append(slot.device.connect())
        await asyncio.gather(*connect_tasks)
        self.logger.info("All display wall devices connected successfully.")

    async def disconnect(self) -> None:
        """Disconnects all wall Divoom devices in parallel."""
        self.logger.info("Disconnecting from all Divoom display wall devices...")
        disconnect_tasks = []
        for slot in self.devices:
            disconnect_tasks.append(slot.device.disconnect())
        await asyncio.gather(*disconnect_tasks)
        self.logger.info("All display wall devices disconnected.")

    @property
    def is_connected(self) -> bool:
        """Returns True if all Divoom wall devices are connected."""
        return all(s.device.is_connected for s in self.devices)

    async def show_image(self, file_path: str, time: int | None = None) -> bool:
        """
        Splits and displays a static image or animation on the unified display wall.
        Resizes the source image/GIF to the wall's composite resolution, cuts it into quadrants,
        and pushes each quadrant to the corresponding BLE screen.
        """
        if not Path(file_path).exists():
            self.logger.error(f"Image path not found: {file_path}")
            return False
            
        self.logger.info(f"Processing asset {file_path!r} for display wall...")
        
        # Resolve cache directory under ~/.config/divoom-control/cache_wall
        cache_dir = Path.home() / ".config" / "divoom-control" / "cache_wall"
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        import hashlib
        # Compute a unique key based on file path, size, and modification time
        file_hash = hashlib.md5(str(file_path).encode("utf-8")).hexdigest()[:8]
        try:
            stat = Path(file_path).stat()
            key = f"{Path(file_path).stem}_{file_hash}_{stat.st_size}_{int(stat.st_mtime)}"
        except Exception:
            key = f"{Path(file_path).stem}_{file_hash}"
            
        main_img = Image.open(file_path)
        is_ani = hasattr(main_img, 'is_animated') and main_img.is_animated
        
        display_tasks = []
        
        for slot in self.devices:
            divoom = slot.device
            x = slot.x
            y = slot.y
            size = slot.size
            width = slot.width
            height = slot.height
            
            if self.is_free_form:
                left = x - self.min_x
                upper = y - self.min_y
                right = left + width
                lower = upper + height
            else:
                left = x * size
                upper = y * size
                right = left + size
                lower = upper + size
            
            mac_clean = divoom.mac.replace(":", "_").replace("-", "_")
            ext = ".gif" if is_ani else ".png"
            cached_file_path = cache_dir / f"{key}_{mac_clean}{ext}"
            temp_path_str = str(cached_file_path)
            
            if cached_file_path.exists():
                self.logger.info(f"Using cached wall split: {cached_file_path}")
            else:
                self.logger.info(f"Cropping slots bounding box: Left={left}, Upper={upper}, Right={right}, Lower={lower}")
                if is_ani:
                    frames = []
                    for frame in ImageSequence.Iterator(main_img):
                        resized_frame = frame.resize((self.total_width, self.total_height), Image.NEAREST)
                        cropped_frame = resized_frame.crop((left, upper, right, lower))
                        if self.is_free_form:
                            cropped_frame = cropped_frame.resize((size, size), Image.NEAREST)
                        frames.append(cropped_frame)
                    
                    frames[0].save(
                        cached_file_path,
                        save_all=True,
                        append_images=frames[1:],
                        duration=main_img.info.get('duration', 100),
                        loop=main_img.info.get('loop', 0)
                    )
                else:
                    resized_img = main_img.resize((self.total_width, self.total_height), Image.NEAREST)
                    cropped_img = resized_img.crop((left, upper, right, lower))
                    if self.is_free_form:
                        cropped_img = cropped_img.resize((size, size), Image.NEAREST)
                    cropped_img.save(cached_file_path)
            
            try:
                self.last_previews[slot.device.mac] = Path(temp_path_str).read_bytes()
            except Exception as ex:
                self.logger.warning(f"Failed to cache preview bytes for {slot.device.mac}: {ex}")
                
            display_tasks.append(divoom.display.show_image(temp_path_str, time=time))
            
        # Execute all BLE streams concurrently
        self.logger.info(f"Streaming splits concurrently to {len(self.devices)} screens...")
        results = await asyncio.gather(*display_tasks, return_exceptions=True)
        
        # Check results
        all_ok = True
        for idx, res in enumerate(results):
            slot = self.devices[idx]
            if isinstance(res, Exception):
                self.logger.error(f"Failed to display slot ({slot.x}, {slot.y}) on device {slot.device.mac}: {res}")
                all_ok = False
            elif not res:
                self.logger.error(f"Failed to display slot ({slot.x}, {slot.y}) on device {slot.device.mac}")
                all_ok = False
                
        return all_ok
            
    async def set_light(self, color: str, brightness: int = 100) -> bool:
        """Sets a unified solid light color across all screens in the wall."""
        self.logger.info(f"Setting solid light {color} across all screens...")
        tasks = []
        for slot in self.devices:
            tasks.append(slot.device.display.show_light(color=color, brightness=brightness))
        results = await asyncio.gather(*tasks)
        return all(results)

    async def show_clock(self, clock: int = 0) -> bool:
        """Displays clock style on all screens in the wall."""
        self.logger.info(f"Displaying clock style {clock} across all screens...")
        tasks = []
        for slot in self.devices:
            tasks.append(slot.device.display.show_clock(clock=clock))
        results = await asyncio.gather(*tasks)
        return all(results)

    async def show_effects(self, number: int = 0) -> bool:
        """Displays VJ effect style on all screens in the wall."""
        self.logger.info(f"Displaying VJ effect {number} across all screens...")
        tasks = []
        for slot in self.devices:
            tasks.append(slot.device.display.show_effects(number=number))
        results = await asyncio.gather(*tasks)
        return all(results)

    async def show_visualization(self, number: int = 0) -> bool:
        """Displays visualization EQ style on all screens in the wall."""
        self.logger.info(f"Displaying visualization EQ {number} across all screens...")
        tasks = []
        for slot in self.devices:
            tasks.append(slot.device.display.show_visualization(number=number))
        results = await asyncio.gather(*tasks)
        return all(results)

    async def set_brightness(self, brightness: int) -> bool:
        """Sets brightness across all screens (LAN transport when available,
        else BLE), matching the GUI's per-device transport choice."""
        self.logger.info(f"Setting brightness {brightness} across all screens...")
        tasks = []
        for slot in self.devices:
            if getattr(slot.device, "lan", None):
                tasks.append(slot.device.lan.set_brightness(brightness))
            else:
                tasks.append(slot.device.device.set_brightness(brightness))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return all(res is True or isinstance(res, dict) for res in results)

    async def set_volume(self, volume: int) -> bool:
        """Sets volume across all screens in the wall."""
        self.logger.info(f"Setting volume {volume} across all screens...")
        tasks = []
        for slot in self.devices:
            tasks.append(slot.device.music.set_volume(volume))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return all(res is True for res in results)

    async def switch_channel(self, channel: str) -> bool:
        """Switches all screens in the wall to the same channel."""
        self.logger.info(f"Switching all screens to channel {channel}...")
        tasks = []
        for slot in self.devices:
            tasks.append(slot.device.display.switch_channel(channel))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return all(res is True or isinstance(res, dict) for res in results)

    async def push_text(self, text: str, color: str = "#FFFFFF", font_size: int = 1,
                        speed: int = 50, effect_style: int = 1) -> bool:
        """Pushes the same scrolling text to every screen, using each screen's
        own pixel size for the display box (the LPWA 0x87 sequence)."""
        from divoom_lib.models import (
            LPWA_CONTROL_DISPLAY_BOX, LPWA_CONTROL_FONT, LPWA_CONTROL_COLOR,
            LPWA_CONTROL_SPEED, LPWA_CONTROL_EFFECTS, LPWA_CONTROL_CONTENT,
        )
        self.logger.info(f"Pushing text {text!r} across all screens...")

        async def _push(divoom, size: int) -> bool:
            t = divoom.text
            box = 0
            await t.set_light_phone_word_attr(LPWA_CONTROL_DISPLAY_BOX, x=0, y=0,
                                              width=size, height=size, text_box_id=box)
            await t.set_light_phone_word_attr(LPWA_CONTROL_FONT, font_size=int(font_size), text_box_id=box)
            await t.set_light_phone_word_attr(LPWA_CONTROL_COLOR, color=color, text_box_id=box)
            await t.set_light_phone_word_attr(LPWA_CONTROL_SPEED, speed=int(speed), text_box_id=box)
            await t.set_light_phone_word_attr(LPWA_CONTROL_EFFECTS, effect_style=int(effect_style))
            res = await t.set_light_phone_word_attr(LPWA_CONTROL_CONTENT, text_content=str(text), text_box_id=box)
            return res is not False

        results = []
        for slot in self.devices:
            divoom = slot.device
            sz = slot.size
            results.append(await _push(divoom, int(sz)))
        return all(results)

    def get_last_previews(self) -> dict:
        """Return base64 Data URLs of the last images/GIFs pushed to the slots."""
        import base64
        res = {}
        for mac, data in self.last_previews.items():
            if not data:
                continue
            mime = "image/gif" if data.startswith(b"GIF8") else "image/png"
            res[mac] = f"data:{mime};base64,{base64.b64encode(data).decode('utf-8')}"
        return res

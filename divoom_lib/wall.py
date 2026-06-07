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
from typing import List, Dict, Any, Tuple

from divoom_lib.divoom import Divoom

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
        self.devices: List[Tuple[Divoom, int, int, int]] = []
        
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
                self.devices.append((divoom, x, y, size, width, height))
        else:
            max_x_slot = 0
            max_y_slot = 0
            
            for config in self.device_configs:
                mac = config["mac"]
                x = config.get("x", 0)
                y = config.get("y", 0)
                size = config.get("size", 16)
                
                divoom = Divoom(mac=mac, logger=self.logger, use_ios_le_protocol=True)
                self.devices.append((divoom, x, y, size, 0, 0)) # Mock width, height
                
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
        for divoom, x, y, size, width, height in self.devices:
            self.logger.info(f"Connecting to screen at Slot ({x}, {y}) MAC: {divoom.mac}...")
            connect_tasks.append(divoom.connect())
        await asyncio.gather(*connect_tasks)
        self.logger.info("All display wall devices connected successfully.")

    async def disconnect(self) -> None:
        """Disconnects all wall Divoom devices in parallel."""
        self.logger.info("Disconnecting from all Divoom display wall devices...")
        disconnect_tasks = []
        for divoom, x, y, size, width, height in self.devices:
            disconnect_tasks.append(divoom.disconnect())
        await asyncio.gather(*disconnect_tasks)
        self.logger.info("All display wall devices disconnected.")

    @property
    def is_connected(self) -> bool:
        """Returns True if all Divoom wall devices are connected."""
        return all(d.is_connected for d, _, _, _, _, _ in self.devices)

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
        
        # Load and resize the main asset to the wall's composite resolution
        main_img = Image.open(file_path)
        
        display_tasks = []
        temp_files: List[Path] = []
        
        # Generate temporary files for each cropped quadrant and dispatch them
        with tempfile.TemporaryDirectory() as temp_dir:
            for device_tuple in self.devices:
                divoom, x, y, size, width, height = device_tuple
                
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
                
                # Perform the crop
                self.logger.info(f"Cropping slots bounding box: Left={left}, Upper={upper}, Right={right}, Lower={lower}")
                
                # Check if image is animated
                if hasattr(main_img, 'is_animated') and main_img.is_animated:
                    # Construct a new animated GIF for this quadrant
                    frames = []
                    for frame in ImageSequence.Iterator(main_img):
                        resized_frame = frame.resize((self.total_width, self.total_height), Image.NEAREST)
                        cropped_frame = resized_frame.crop((left, upper, right, lower))
                        if self.is_free_form:
                            cropped_frame = cropped_frame.resize((size, size), Image.NEAREST)
                        frames.append(cropped_frame)
                        
                    # Save cropped GIF
                    cropped_gif_path = Path(temp_dir) / f"quad_{x}_{y}.gif"
                    frames[0].save(
                        cropped_gif_path,
                        save_all=True,
                        append_images=frames[1:],
                        duration=main_img.info.get('duration', 100),
                        loop=main_img.info.get('loop', 0)
                    )
                    temp_path_str = str(cropped_gif_path)
                else:
                    # Process static image
                    resized_img = main_img.resize((self.total_width, self.total_height), Image.NEAREST)
                    cropped_img = resized_img.crop((left, upper, right, lower))
                    if self.is_free_form:
                        cropped_img = cropped_img.resize((size, size), Image.NEAREST)
                    
                    cropped_img_path = Path(temp_dir) / f"quad_{x}_{y}.png"
                    cropped_img.save(cropped_img_path)
                    temp_path_str = str(cropped_img_path)
                
                # We need to preserve the files until the async BLE show_image call completes
                # So we save a copy of the bytes out of the temp dir lifecycle if needed,
                # or we just read the bytes immediately into memory to avoid cleanup issues.
                # Fortunately, we can pass a byte buffer/in-memory file or we can do it inside this block.
                # Let's read the cropped file into memory and use it. Wait! Does show_image accept a path?
                # Yes, show_image expects a path string. So we will block/await here inside the block,
                # ensuring the temp files are not deleted until display completes!
                display_tasks.append(divoom.display.show_image(temp_path_str, time=time))
                
            # Execute all BLE streams concurrently
            self.logger.info(f"Streaming splits concurrently to {len(self.devices)} screens...")
            results = await asyncio.gather(*display_tasks, return_exceptions=True)
            
            # Check results
            all_ok = True
            for idx, res in enumerate(results):
                divoom, x, y, size, width, height = self.devices[idx]
                if isinstance(res, Exception):
                    self.logger.error(f"Failed to display slot ({x}, {y}) on device {divoom.mac}: {res}")
                    all_ok = False
                elif not res:
                    self.logger.error(f"Failed to display slot ({x}, {y}) on device {divoom.mac}")
                    all_ok = False
                    
            return all_ok
            
    async def set_light(self, color: str, brightness: int = 100) -> bool:
        """Sets a unified solid light color across all screens in the wall."""
        self.logger.info(f"Setting solid light {color} across all screens...")
        tasks = []
        for divoom, x, y, size, width, height in self.devices:
            tasks.append(divoom.display.show_light(color=color, brightness=brightness))
        results = await asyncio.gather(*tasks)
        return all(results)
        
    async def show_clock(self, clock: int = 0) -> bool:
        """Displays clock style on all screens in the wall."""
        self.logger.info(f"Displaying clock style {clock} across all screens...")
        tasks = []
        for divoom, x, y, size, width, height in self.devices:
            tasks.append(divoom.display.show_clock(clock=clock))
        results = await asyncio.gather(*tasks)
        return all(results)

    async def show_effects(self, number: int = 0) -> bool:
        """Displays VJ effect style on all screens in the wall."""
        self.logger.info(f"Displaying VJ effect {number} across all screens...")
        tasks = []
        for divoom, x, y, size, width, height in self.devices:
            tasks.append(divoom.display.show_effects(number=number))
        results = await asyncio.gather(*tasks)
        return all(results)

    async def show_visualization(self, number: int = 0) -> bool:
        """Displays visualization EQ style on all screens in the wall."""
        self.logger.info(f"Displaying visualization EQ {number} across all screens...")
        tasks = []
        for divoom, x, y, size, width, height in self.devices:
            tasks.append(divoom.display.show_visualization(number=number))
        results = await asyncio.gather(*tasks)
        return all(results)

    async def set_brightness(self, brightness: int) -> bool:
        """Sets brightness across all screens (LAN transport when available,
        else BLE), matching the GUI's per-device transport choice."""
        self.logger.info(f"Setting brightness {brightness} across all screens...")
        tasks = []
        for divoom, x, y, size, width, height in self.devices:
            if getattr(divoom, "lan", None):
                tasks.append(divoom.lan.set_brightness(brightness))
            else:
                tasks.append(divoom.device.set_brightness(brightness))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return all(res is True or isinstance(res, dict) for res in results)

    async def set_volume(self, volume: int) -> bool:
        """Sets volume across all screens in the wall."""
        self.logger.info(f"Setting volume {volume} across all screens...")
        tasks = []
        for divoom, x, y, size, width, height in self.devices:
            tasks.append(divoom.music.set_volume(volume))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return all(res is True for res in results)

    async def switch_channel(self, channel: str) -> bool:
        """Switches all screens in the wall to the same channel."""
        self.logger.info(f"Switching all screens to channel {channel}...")
        tasks = []
        for divoom, x, y, size, width, height in self.devices:
            tasks.append(divoom.display.switch_channel(channel))
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
        for entry in self.devices:
            divoom = entry[0]
            sz = entry[3] if len(entry) > 3 else 16
            results.append(await _push(divoom, int(sz)))
        return all(results)

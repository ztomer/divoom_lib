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
        max_x_slot = 0
        max_y_slot = 0
        
        for config in self.device_configs:
            mac = config["mac"]
            x = config.get("x", 0)
            y = config.get("y", 0)
            size = config.get("size", 16)
            
            divoom = Divoom(mac=mac, logger=self.logger, use_ios_le_protocol=False)
            self.devices.append((divoom, x, y, size))
            
            if x + 1 > max_x_slot:
                max_x_slot = x + 1
            if y + 1 > max_y_slot:
                max_y_slot = y + 1
                
        # Assume all devices are of the same size for uniform grid resolution calculation
        self.grid_unit_size = self.device_configs[0].get("size", 16) if self.device_configs else 16
        self.total_width = max_x_slot * self.grid_unit_size
        self.total_height = max_y_slot * self.grid_unit_size
        
        self.logger.info(f"Initialized DivoomWall with grid layout of {max_x_slot}x{max_y_slot} units "
                          f"(composite canvas size: {self.total_width}x{self.total_height} pixels)")

    async def connect(self) -> None:
        """Establishes connections to all wall Divoom devices in parallel."""
        self.logger.info("Connecting to all Divoom display wall devices...")
        connect_tasks = []
        for divoom, x, y, size in self.devices:
            self.logger.info(f"Connecting to screen at Slot ({x}, {y}) MAC: {divoom.mac}...")
            connect_tasks.append(divoom.connect())
        await asyncio.gather(*connect_tasks)
        self.logger.info("All display wall devices connected successfully.")

    async def disconnect(self) -> None:
        """Disconnects all wall Divoom devices in parallel."""
        self.logger.info("Disconnecting from all Divoom display wall devices...")
        disconnect_tasks = []
        for divoom, x, y, size in self.devices:
            disconnect_tasks.append(divoom.disconnect())
        await asyncio.gather(*disconnect_tasks)
        self.logger.info("All display wall devices disconnected.")

    @property
    def is_connected(self) -> bool:
        """Returns True if all Divoom wall devices are connected."""
        return all(d.is_connected for d, _, _, _ in self.devices)

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
            for divoom, x, y, size in self.devices:
                left = x * size
                upper = y * size
                right = left + size
                lower = upper + size
                
                # Perform the crop
                self.logger.info(f"Cropping slot ({x}, {y}) bounding box: Left={left}, Upper={upper}, Right={right}, Lower={lower}")
                
                # Check if image is animated
                if hasattr(main_img, 'is_animated') and main_img.is_animated:
                    # Construct a new animated GIF for this quadrant
                    frames = []
                    for frame in ImageSequence.Iterator(main_img):
                        resized_frame = frame.resize((self.total_width, self.total_height), Image.NEAREST)
                        cropped_frame = resized_frame.crop((left, upper, right, lower))
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
                divoom, x, y, _ = self.devices[idx]
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
        for divoom, x, y, _ in self.devices:
            tasks.append(divoom.display.show_light(color=color, brightness=brightness))
        results = await asyncio.gather(*tasks)
        return all(results)
        
    async def show_clock(self, clock: int = 0) -> bool:
        """Displays clock style on all screens in the wall."""
        self.logger.info(f"Displaying clock style {clock} across all screens...")
        tasks = []
        for divoom, x, y, _ in self.devices:
            tasks.append(divoom.display.show_clock(clock=clock))
        results = await asyncio.gather(*tasks)
        return all(results)

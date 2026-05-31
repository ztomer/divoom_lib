# Divoom Desktop Control Center & Virtual Display Wall

The `divoom-control` library includes a modern, high-performance Desktop Dashboard GUI and a virtual multi-device display wall coordinator. This documentation outlines how to configure, run, and programmatically integrate these features.

---

## 1. Desktop GUI Dashboard

The Desktop Dashboard is built using an embedded HTML/CSS/JS viewport via **PyWebView** powered by a robust Python backend bridge (`api_scraper/gui_main.py`).

### Capabilities
- **Active BLE Scanner**: Discovery tool scanning nearby BLE devices and identifying them by known Divoom signatures.
- **Ambient Light Controller**: A solid color pick grid plus Custom Color spectrum selection, linked with an active brightness slider to control ambient moods.
- **Active Channel Switcher**: Direct buttons to switch active device displays to Clock Mode, Music EQ (Visualizer), VJ Effects, and custom uploader art.
- **Visual Display Wall Arranger**: A visual canvas slot arrangement panel. Select grid dimensions (rows/cols) and slot resolutions (e.g. 16x16, 32x32) to map discovered Divoom screens into slots.
- **Batch Monthly Best Sync**: Fetches community-voted public artwork lists from Divoom Cloud and synchronizes/replicates them across all screens at once in parallel tasks.

### To Launch the Dashboard
Run the main controller file using python:
```bash
python3 api_scraper/gui_main.py
```

---

## 2. Multi-Device Display Wall (`DivoomWall`)

The `DivoomWall` class (`divoom_lib/wall.py`) allows multiple physical Divoom screens arranged in 2D space to act as a single virtual display canvas.

### Bounding Box Slot Mapping
Coordinates are mapped using standard grid positions:
```
Slot (0,0) [Top-Left]  --> Slot (1,0) [Top-Right]
       |                         |
Slot (0,1) [Bottom-Left] --> Slot (1,1) [Bottom-Right]
```

### Cropping & Split Pipeline
When you send a large image/GIF to the display wall:
1. The coordinator resizes the source image/GIF to the wall's **composite resolution** (e.g., a 2x2 grid of 16x16 devices is resized to 32x32 pixels) using `Image.NEAREST` pixel-art scaling.
2. The image is cropped into quadrants corresponding to each device's grid coordinates:
   - Device `(x, y)` gets cropped at boundaries: `[x * size, y * size, (x + 1) * size, (y + 1) * size]`.
3. For animated GIFs, the coordinator builds a new separate animated GIF for each quadrant, seeking frames and compiling them in memory.
4. Quad-segments are pushed concurrently to BLE screens using `asyncio.gather` tasks.

### Programmable Library API
You can integrate multi-screen split displays programmatically in your own scripts:

```python
import asyncio
from divoom_lib.wall import DivoomWall

async def main():
    # Setup coordinates for a 1x2 display wall (width=32, height=16)
    configs = [
        {"mac": "AA:BB:CC:DD:EE:01", "x": 0, "y": 0, "size": 16}, # Left screen
        {"mac": "AA:BB:CC:DD:EE:02", "x": 1, "y": 0, "size": 16}  # Right screen
    ]
    
    wall = DivoomWall(configs)
    
    # Connect to both clients concurrently
    await wall.connect()
    
    # Broadcast solid color light
    await wall.set_light("FF00cc", brightness=100)
    await asyncio.sleep(3.0)
    
    # Stream a split pixel art animation GIF
    await wall.show_image("pixel_scenery_32x16.gif")
    
    # Disconnect when done
    await wall.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
```

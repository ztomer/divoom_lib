# Divoom Control Center: Added Features & Architecture Plan

This document provides a comprehensive blueprint and reference for all the advanced features, modules, and integrations added to the `divoom-control` library.

---

## 1. Unified Directory & GUI Restructuring
To enforce a clean separation of concerns between Divoom API reverse-engineering scripts and the Desktop GUI Dashboard, we moved and refactored the graphical components:

*   **GUI Workspace Directory**: Created the standalone `/gui` directory at the root of the workspace.
*   **Legacy Cleanup**: Removed `api_scraper/gui_main.py` and the legacy directory `api_scraper/web_ui` to keep the scraper workspace pristine.
*   **Web Dashboard Assets**: Grouped all HTML, CSS, JS, and graphical assets inside `/gui/web_ui/`.
*   **Launcher Script**: Placed `run_gui.sh` in the workspace root for direct execution.

### Directory Mapping
```
├── run_gui.sh                        # Root launcher script
├── config.ini                        # Main user credentials and scanner settings
├── gui/
│   ├── gui_main.py                   # PyWebView GUI Bridge and background workers
│   ├── menubar.py                    # macOS Cocoa status bar agent & socket server
│   ├── presets.json                  # Saved coordinate matrix presets
│   └── web_ui/
│       ├── index.html                # Premium Dashboard layout (glassmorphism tabs)
│       ├── style.css                 # Stunning cyberpunk styles & clock face mocks
│       ├── app.js                    # UI events binder, scan config, presets picker
│       └── assets/
│           ├── timoo.png             # Beautiful Imagen Divoom Timoo mockup
│           ├── ditoo.png             # Beautiful Imagen Divoom Ditoo mockup
│           ├── pixoo.png             # Beautiful Imagen Divoom Pixoo mockup
│           └── timebox.png           # Beautiful Imagen Divoom Timebox mockup
```

---

## 2. Desktop GUI Dashboard (PyWebView Fronted)
The Web GUI dashboard is wrapped in a native macOS viewport window via PyWebView. It provides a stunning glassmorphic Cyberpunk Slate aesthetic using modern typography (Google Fonts *Inter* & *Outfit*).

### Premium Interface Core Capabilities:
1.  **BLE Scanner Configs**: Fully customizable timeout slider and target device scanner limit. Stops discovery immediately when the device threshold is reached to avoid delays.
2.  **Active Device Spec Banner**: Dynamically detects the name of the connected BLE device, queries the hardware database, and updates a beautiful display banner containing the MAC address, grid size, speaker specifications, and a visual device mockup.
3.  **Ambient Light & Custom Colors**: High-quality color swatch palette with a custom RGB color spectrum picker and a brightness slider.
4.  **Clock Face Presets**: Fully responsive card selection showing previews for *Simple*, *Minimal*, *Cyber*, and *Grid* clock style presets.
5.  **Interactive Display Wall Arranger**: A coordinate matrix drag-and-drop workspace that displays beautiful high-res mockup images of Divoom models in their assigned grid positions.
6.  **Presets Load & Save**: Allows users to save their physical display wall grid configurations under a custom name, persisting layouts to `gui/presets.json` and loading them from a clean dropdown menu.
7.  **Divoom Cloud Credentials settings**: Tab to configure, save, and validate credentials, writing them to `config.ini` and validating via HMAC-UTC authentication.

---

## 3. Multi-Device Display Wall Coordinator (`DivoomWall`)
The library has been extended with a robust display coordinator, `DivoomWall` (defined in [wall.py](file:///Users/ztomer/Projects/divoom-control/divoom_lib/wall.py)), which stitches multiple physical BLE screens together to act as a single high-resolution canvas.

### Pipeline:
1.  **Layout Compilation**: Coordinates are loaded as an active coordinate grid mapping slots to device BLE addresses (e.g. `{"0_0": "address1", "1_0": "address2"}`).
2.  **Pillow Image Splitting**: Resizes large source images or animated GIFs to the wall's **composite resolution** (e.g. 32x32 pixels for a 2x2 grid of 16x16 devices) using crisp `Image.NEAREST` scaling.
3.  **Boundary Cropping**: Crops individual quadrants on boundaries matching device placement:
    $$\text{Crop Boundaries} = [x \times \text{size}, y \times \text{size}, (x + 1) \times \text{size}, (y + 1) \times \text{size}]$$
4.  **Concurrent BLE Streaming**: Leverages `asyncio.gather` to concurrently stream cropped animation chunks/frames in parallel to each physical BLE screen.

---

## 4. Live Media & Data Sources
We built `divoom_lib/utils/media_source.py` to scrape, parse, and render live external content:

1.  **Live macOS Music Album Downsampler**:
    *   Uses **macOS AppleScript (`osascript`)** to poll Spotify and Apple Music playback in the background without sandboxing restrictions.
    *   Queries **iTunes Search API** to fetch high-resolution album artwork URLs.
    *   Downloads and downsamples cover art on-the-fly using crisp `NEAREST` Pillow scaling.
    *   Automatically streams the resized cover frame to active screens.
2.  **Yahoo Finance Stock & Crypto Ticker**:
    *   Queries the Yahoo Finance public API for regular market prices, price change values, and percentage changes (e.g. for tickers like `BTC-USD`, `AAPL`, `TSLA`).
    *   Renders a beautiful retro frame onto a $16 \times 16$ or $32 \times 32$ dark slate canvas, displaying the ticker symbol, current price, and green up-arrows or red down-arrows indicating trends.

---

## 5. Divoom Hardware Database
Implemented in `divoom_lib/utils/devices_db.py`, this database catalogs known Divoom models and their features to drive smart UI layouts:

| Model ID | BLE Prefix | Resolution | Width/Height | Built-in Speaker | Battery | Screen Size | Graphical Asset |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Timoo** | `timoo` | $16\text{px}$ | $16 \times 16$ | Yes | Yes | 4.3" | `timoo.png` |
| **Ditoo** | `ditoo` | $16\text{px}$ | $16 \times 16$ | Yes | Yes | 3.5" | `ditoo.png` |
| **Pixoo** | `pixoo` | $16\text{px}$ | $16 \times 16$ | No | Yes | 8.6" | `pixoo.png` |
| **Timebox** | `timebox` | $16\text{px}$ | $16 \times 16$ | Yes | Yes | 3.9" | `timebox.png` |
| **Tivoo** | `tivoo` | $16\text{px}$ | $16 \times 16$ | Yes | Yes | 2.5" | `tivoo.png` |
| **Pixoo 64** | `pixoo64` | $64\text{px}$ | $64 \times 64$ | No | No | 10.3" | `pixoo64.png` |
| **TimeGate** | `timegate` | $128\text{px}$ | $128 \times 32$ | No | No | 10.5" | `timegate.png` |

---

## 6. Cocoa macOS Menubar Agent & IPC Server
Implemented in `gui/menubar.py` using **native PyObjC Cocoa framework**:

*   **Status Item**: Creates a native system menubar item with a neat unicode emoji status icon (`👾`).
*   **Menu Options**:
    1.  **Launch Dashboard**: Launches the main PyWebView controller.
    2.  **UNIX Socket IPC Server Toggle**: Starts or stops a fast local UNIX Domain Socket server at `/tmp/divoom.sock`.
    3.  **Quit**: Gracefully disconnects active Bluetooth channels and shuts down the process.
*   **Unix Domain Socket IPC**: Listens for incoming JSON socket frames and processes them concurrently:
    *   `{"command": "set_light", "args": {"color": "00FFCC", "brightness": 100}}`
    *   `{"command": "set_clock", "args": {"style": 2}}`
    *   `{"command": "show_image", "args": {"file_path": "/path/to/image.png"}}`
*   **Model Context Protocol (MCP) Server**: Provides JSON-RPC tools and prompts to integrate with AI coding assistants (like Gemini, Antigravity, or Claude Desktop) to let agents control local Divoom screens!

---

## 7. Execution and Launch Instructions

### Launch the Desktop GUI Dashboard
Simply run the shell script in the workspace root:
```bash
./run_gui.sh
```

### Launch the macOS System Menubar Agent
Run using python3:
```bash
python3 gui/menubar.py
```

### Stream IPC commands using UNIX Sockets
Send a JSON packet to the local socket:
```bash
echo '{"command": "set_light", "args": {"color": "FF00CC", "brightness": 80}}' | nc -U /tmp/divoom.sock
```

### Run automated display wall tests
Confirm the matrix crops and async channels remain fully functional:
```bash
pytest tests/test_wall.py
```

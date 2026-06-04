#!/usr/bin/env python3
"""
gui_main.py — Divoom Desktop GUI launcher.
Launches the custom frameless PyWebView window.
"""

import os
import sys
import logging
import webview
from pathlib import Path

# Add divoom-control paths
sys.path.append(str(Path(__file__).parent))
sys.path.append(str(Path(__file__).parent.parent))

from gui_api import DivoomGuiAPI
from divoom_lib.divoom import Divoom
from divoom_lib.wall import DivoomWall
from bleak import BleakScanner
from divoom_lib import divoom_auth

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("divoom_gui")

def main():
    api = DivoomGuiAPI()
    web_ui_dir = Path(__file__).parent / "web_ui"
    index_html = web_ui_dir / "index.html"

    # Optional headless control server surface (E2E testing)
    if os.environ.get("DIVOOM_CONTROL_SERVER") in ("1", "true", "yes"):
        try:
            from control_server import serve_in_background
            port = int(os.environ.get("DIVOOM_CONTROL_PORT", "8787"))
            serve_in_background(api, port=port)
            logger.info(f"Control server enabled on http://127.0.0.1:{port}")
        except Exception as e:
            logger.warning(f"Failed to start control server: {e}")

    # Optional Unix-domain-socket control surface
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
        easy_drag=False,
        background_color="#0a0b10"
    )
    api.window = window
    webview.start()

if __name__ == "__main__":
    main()

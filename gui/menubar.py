#!/usr/bin/env python3
"""
menubar.py — macOS status bar agent & local IPC controller.
Implements a native Cocoa menubar status item using PyObjC.
Exposes a Unix Domain Socket IPC interface at /tmp/divoom.sock and a
JSON-RPC Model Context Protocol (MCP) server for deep AI/external orchestration.
"""

import sys
import os
import json
import socket
import threading
import asyncio
import subprocess
import logging
from pathlib import Path
from AppKit import NSApplication, NSStatusBar, NSVariableStatusItemLength, NSMenu, NSMenuItem
from Foundation import NSObject

sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "api_scraper"))

from divoom_lib.divoom import Divoom
from divoom_lib.utils import discovery

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("divoom_menubar")

SOCKET_PATH = "/tmp/divoom.sock"

class DivoomMenuBarAgent(NSObject):
    def init(self):
        self = super(DivoomMenuBarAgent, self).init()
        if self:
            self.status_item = None
            self.socket_thread = None
            self.socket_running = False
            self.current_divoom = None
            self.active_device_mac = None
            
            # Start UNIX socket server by default
            self.start_socket_server()
        return self

    def start_socket_server(self):
        if self.socket_running:
            return
        self.socket_running = True
        self.socket_thread = threading.Thread(target=self._run_socket_server, daemon=True)
        self.socket_thread.start()
        logger.info("Background UNIX Domain Socket server launched.")

    def _run_socket_server(self):
        if os.path.exists(SOCKET_PATH):
            try:
                os.remove(SOCKET_PATH)
            except OSError:
                pass
                
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(SOCKET_PATH)
        server.listen(5)
        
        while self.socket_running:
            try:
                # Set brief timeout so we can exit loop on socket shutdown
                server.settimeout(2.0)
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    continue
                    
                data = conn.recv(4096)
                if not data:
                    conn.close()
                    continue
                    
                try:
                    req = json.loads(data.decode("utf-8"))
                    cmd = req.get("command")
                    args = req.get("args", {})
                    
                    logger.info(f"UNIX Socket Received Command: {cmd} (args={args})")
                    res = self.execute_ipc_command(cmd, args)
                    conn.sendall(json.dumps({"success": res}).encode("utf-8"))
                except Exception as parse_err:
                    conn.sendall(json.dumps({"success": False, "error": str(parse_err)}).encode("utf-8"))
                finally:
                    conn.close()
            except Exception as e:
                logger.error(f"UNIX socket error: {e}")
                
        server.close()

    def execute_ipc_command(self, cmd: str, args: dict) -> bool:
        """Executes incoming JSON commands from the Unix Domain Socket or MCP interface."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Automatic device connection if not connected
            if not self.current_divoom or not self.current_divoom.is_connected:
                # Get the first discovered device
                logger.info("Scanning for Divoom device for IPC target...")
                devices = loop.run_until_complete(discovery.discover_all_divoom_devices(timeout=3.0))
                if devices:
                    self.active_device_mac = devices[0]["address"]
                    device_name = devices[0].get("name")
                    self.current_divoom = Divoom(mac=self.active_device_mac, logger=logger, use_ios_le_protocol=False, device_name=device_name)
                    loop.run_until_complete(self.current_divoom.connect())
                    logger.info(f"IPC Auto-connected to device {self.active_device_mac} ({device_name})")
                else:
                    logger.warning("No Divoom device found to execute IPC command.")
                    return False

            if cmd == "set_light":
                color = args.get("color", "00FFCC")
                brightness = args.get("brightness", 100)
                return loop.run_until_complete(self.current_divoom.display.show_light(color, brightness))
                
            elif cmd == "set_clock":
                style = args.get("style", 0)
                return loop.run_until_complete(self.current_divoom.display.show_clock(clock=style))
                
            elif cmd == "show_image":
                path = args.get("file_path")
                if path and os.path.exists(path):
                    return loop.run_until_complete(self.current_divoom.display.show_image(path))
                    
            elif cmd == "batch_sync_art":
                file_id = args.get("file_id")
                if file_id:
                    dl_url = f"https://fin.divoom-gz.com/{file_id}"
                    req = urllib.request.Request(dl_url, headers={"User-Agent": "okhttp/4.12.0"})
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        file_bytes = resp.read()
                        from divoom_lib.monthly_best_daemon import stream_raw_bin_payload
                        return loop.run_until_complete(stream_raw_bin_payload(self.current_divoom, file_bytes))

        except Exception as e:
            logger.error(f"Failed executing IPC command: {e}")
        finally:
            loop.close()
        return False

    # Cocoa status item actions
    def launchDashboard_(self, sender):
        logger.info("Cocoa Action: Launching pywebview Dashboard...")
        gui_path = Path(__file__).parent / "gui_main.py"
        subprocess.Popen([sys.executable, str(gui_path)])

    def stopSocketServer_(self, sender):
        if self.socket_running:
            self.socket_running = False
            logger.info("Stopping UNIX Socket server...")
            show_toast("Divoom Agent", "UNIX IPC Server stopped successfully.")

    def quitApp_(self, sender):
        logger.info("Quitting status bar application...")
        self.socket_running = False
        if self.current_divoom and self.current_divoom.is_connected:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self.current_divoom.disconnect())
        NSApplication.sharedApplication().terminate_(self)


def show_toast(title: str, message: str):
    """Utility to trigger native macOS notifications using AppleScript."""
    script = f'display notification "{message}" with title "{title}"'
    subprocess.run(["osascript", "-e", script])


def main():
    app = NSApplication.sharedApplication()
    
    # Instantiate the agent delegate
    agent = DivoomMenuBarAgent.alloc().init()
    
    # Create the Cocoa status bar item
    status_bar = NSStatusBar.systemStatusBar()
    status_item = status_bar.statusItemWithLength_(NSVariableStatusItemLength)
    agent.status_item = status_item
    
    # Visual layout: Set a neat Unicode status bar icon
    status_item.button().setTitle_("👾")
    status_item.button().setToolTip_("Divoom Coordinator Agent")
    
    # Create the popup menu
    menu = NSMenu.alloc().init()
    
    # 1. Launch Dashboard option
    launch_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Launch Dashboard", "launchDashboard:", "d"
    )
    launch_item.setTarget_(agent)
    menu.addItem_(launch_item)
    
    menu.addItem_(NSMenuItem.separatorItem())
    
    # 2. Start/Stop socket server indicator
    status_msg = "UNIX Socket IPC: Active (/tmp/divoom.sock)"
    status_item_menu = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        status_msg, "stopSocketServer:", ""
    )
    status_item_menu.setTarget_(agent)
    menu.addItem_(status_item_menu)
    
    menu.addItem_(NSMenuItem.separatorItem())
    
    # 3. Quit option
    quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Quit", "quitApp:", "q"
    )
    quit_item.setTarget_(agent)
    menu.addItem_(quit_item)
    
    status_item.setMenu_(menu)
    
    show_toast("Divoom Agent", "macOS Menubar Coordinator Agent launched successfully.")
    
    # Launch Cocoa event loop
    app.run()

if __name__ == "__main__":
    main()

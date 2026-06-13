#!/usr/bin/env python3
"""
menubar.py — macOS status bar agent (R15 §6).

A native Cocoa menubar status item using PyObjC. Connects to the daemon
as a client (no BLE, no socket server). Subscribes to daemon-pushed
notification-listener status events to update the title. Exposes menu
actions to control the notification listener and open the GUI.
"""
import sys
import os
import subprocess
import logging
from pathlib import Path
import objc
from AppKit import (
    NSApplication, NSStatusBar, NSVariableStatusItemLength, NSMenu, NSMenuItem,
    NSColor, NSForegroundColorAttributeName, NSBackgroundColorAttributeName,
    NSImage,
)

# R46 #3: per-device activity → (SF Symbol, friendly label) for the menubar
# tiles. Glyph-only for now (the daemon supplies the kind; real-frame thumbnails
# are a follow-up). Unknown kinds fall back to a generic dot.
_ACTIVITY_GLYPH = {
    "clock": ("clock", "Clock"),
    "visualizer": ("waveform", "EQ visualizer"),
    "eq": ("waveform", "EQ visualizer"),
    "vj": ("sparkles", "VJ effects"),
    "scoreboard": ("sportscourt", "Scoreboard"),
    "text": ("textformat", "Text"),
    "ambient": ("lightbulb", "Ambient"),
    "design": ("square.grid.2x2", "Custom art"),
    "custom": ("square.grid.2x2", "Custom art"),
    "music": ("music.note", "Now playing"),
    "stocks": ("chart.line.uptrend.xyaxis", "Stocks"),
    "stock": ("chart.line.uptrend.xyaxis", "Stocks"),
    "sysmon": ("cpu", "System monitor"),
    "weather": ("cloud.sun", "Weather"),
    "idle": ("moon.zzz", "Idle"),
}
_DEVICE_ITEM_TAG = 4600   # device rows + their trailing separator

# App brand accent (web_ui/style.css --primary "Braun Tuner Orange"). The menu-bar
# item uses the same orange background + white text as the app's active controls
# for visual consistency.
BRAND_ORANGE = "#ff5a1f"
from Foundation import NSObject, NSAttributedString

sys.path.append(str(Path(__file__).parent.parent))

from divoom_menubar.menubar_client import (
    MenubarClient,
    STATE_IDLE,
    format_status_title,
    status_color,
    hex_to_rgb01,
    open_notifications_command,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("divoom_menubar")


class DivoomMenuBarAgent(NSObject):
    def init(self):
        # PyObjC NSObject subclasses must chain through objc.super(...).init(),
        # not Python's builtin super() — the latter raises
        # "'super' object has no attribute 'init'" (crashes the menubar on launch).
        self = objc.super(DivoomMenuBarAgent, self).init()
        if self:
            self.status_item = None
            self.menu = None
            self.client = MenubarClient()
            self.client.set_status_callback(self._on_status_change)
            self.client.set_shutdown_callback(self._on_daemon_shutdown)
            self.client.start()
        return self

    def _on_status_change(self, status: dict) -> None:
        """Called from the subscribe thread — must hop to main thread for UI."""
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "updateStatusTitle:", None, False
        )

    # R46 #3: rebuild the per-device tiles right before the menu opens (NSMenu
    # delegate). One row per device: an SF Symbol glyph for what it's showing +
    # "Name — Activity". Pulled fresh from the daemon so it reflects reality even
    # when the dashboard is closed.
    def menuNeedsUpdate_(self, menu):
        try:
            self._rebuild_device_section(menu)
        except Exception as e:
            logger.debug("device section rebuild failed: %s", e)

    def _rebuild_device_section(self, menu):
        # Drop the previous device rows + their separator.
        for item in list(menu.itemArray()):
            if item.tag() == _DEVICE_ITEM_TAG:
                menu.removeItem_(item)
        activity = {}
        try:
            activity = self.client.device_activity()
        except Exception:
            activity = {}
        if not activity:
            return
        # Insert at the top (above Launch Dashboard), newest activity first.
        rows = sorted(activity.items(), key=lambda kv: kv[1].get("at", 0), reverse=True)
        idx = 0
        for mac, info in rows:
            kind = (info.get("kind") or "idle").lower()
            symbol, label = _ACTIVITY_GLYPH.get(kind, ("circle.dashed", kind.title() or "—"))
            name = info.get("name") or mac
            row = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                f"{name} — {label}", None, "")
            row.setTag_(_DEVICE_ITEM_TAG)
            row.setEnabled_(False)
            try:
                img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(symbol, label)
                if img is not None:
                    row.setImage_(img)
            except Exception:
                pass
            menu.insertItem_atIndex_(row, idx)
            idx += 1
        if idx > 0:
            sep = NSMenuItem.separatorItem()
            sep.setTag_(_DEVICE_ITEM_TAG)
            menu.insertItem_atIndex_(sep, idx)

    # Cocoa status item actions
    def updateStatusTitle_(self, sender):
        """Render the status-item title from self.client.status. MUST run
        on the main thread (Cocoa UI)."""
        if self.status_item is None:
            return
        status = self.client.status
        state = status.get("state", STATE_IDLE)
        error = status.get("error")
        title = format_status_title(state)

        # Tooltip updates dynamically
        tooltip = "Divoom Coordinator Agent"
        if error:
            tooltip += f"\nError: {error}"
        self.status_item.button().setToolTip_(tooltip)

        # Dynamically manage error menu item if self.menu is available
        if self.menu is not None:
            first_item = self.menu.itemAtIndex_(0) if self.menu.numberOfItems() > 0 else None
            is_error_item = first_item and first_item.title().startswith("Error: ")

            if error:
                err_title = f"Error: {error}"
                if is_error_item:
                    first_item.setTitle_(err_title)
                else:
                    err_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                        err_title, "", ""
                    )
                    err_item.setEnabled_(False)
                    self.menu.insertItem_atIndex_(err_item, 0)
                    sep = NSMenuItem.separatorItem()
                    self.menu.insertItem_atIndex_(sep, 1)
            else:
                if is_error_item:
                    self.menu.removeItemAtIndex_(0)
                    next_item = self.menu.itemAtIndex_(0) if self.menu.numberOfItems() > 0 else None
                    if next_item and next_item.isSeparatorItem():
                        self.menu.removeItemAtIndex_(0)

        try:
            # App-consistent look: orange background + white text (matches the
            # app's active controls). Leading/trailing spaces give the orange
            # fill some breathing room. State is conveyed by the title text.
            r, g, b = hex_to_rgb01(BRAND_ORANGE)
            orange = NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, 1.0)
            white = NSColor.whiteColor()
            attrs = {
                NSForegroundColorAttributeName: white,
                NSBackgroundColorAttributeName: orange,
            }
            attributed = NSAttributedString.alloc().initWithString_attributes_(f" {title} ", attrs)
            self.status_item.button().setAttributedTitle_(attributed)
        except Exception as e:
            logger.warning(f"updateStatusTitle: falling back to plain title ({e})")
            self.status_item.button().setTitle_(title)

    def openNotifications_(self, sender):
        """Open the GUI focused on Live Widgets -> Notifications (R15 §6)."""
        logger.info("Cocoa Action: Opening Notifications view...")
        gui_path = Path(__file__).parent.parent / "divoom_gui" / "gui_main.py"
        subprocess.Popen(open_notifications_command(sys.executable, str(gui_path)))

    def startNotifications_(self, sender):
        logger.info("Cocoa Action: Starting notification listener...")
        # Disable the menu item briefly while the command runs
        sender.setEnabled_(False)
        result = self.client.start_notifications()
        logger.info(f"start_notifications result: {result}")
        sender.setEnabled_(True)

    def stopNotifications_(self, sender):
        logger.info("Cocoa Action: Stopping notification listener...")
        sender.setEnabled_(False)
        result = self.client.stop_notifications()
        logger.info(f"stop_notifications result: {result}")
        sender.setEnabled_(True)

    def launchDashboard_(self, sender):
        logger.info("Cocoa Action: Launching pywebview Dashboard...")
        gui_path = Path(__file__).parent.parent / "divoom_gui" / "gui_main.py"
        subprocess.Popen([sys.executable, str(gui_path)])

    def quitApp_(self, sender):
        # R40 §9: when the lifecycles are shared (keep-alive OFF), 'Quit Divoom'
        # stops the daemon — which broadcasts a shutdown event so the dashboard
        # closes too. When keep-alive is ON, just exit the menubar and leave the
        # daemon (and any dashboard) running.
        from divoom_lib.lifecycle_config import (
            get_keep_daemon_alive, should_stop_daemon_on_menubar_quit)
        keep = get_keep_daemon_alive()
        if should_stop_daemon_on_menubar_quit(keep):
            logger.info("Quitting Divoom: stopping daemon (shared lifecycle)...")
            try:
                from divoom_daemon.daemon_protocol import DaemonClient, DEFAULT_SOCKET_PATH
                DaemonClient(DEFAULT_SOCKET_PATH, timeout=1.0).shutdown()
            except Exception as e:
                logger.debug(f"daemon shutdown on quit skipped: {e}")
        else:
            logger.info("Quitting menu bar only (keep-daemon-alive is on)...")
        self.client.stop()
        NSApplication.sharedApplication().terminate_(self)

    def _on_daemon_shutdown(self) -> None:
        """Daemon broadcast a shutdown (e.g. the dashboard quit and brought the
        shared lifecycle down). Follow it down unless keep-alive is set."""
        from divoom_lib.lifecycle_config import (
            get_keep_daemon_alive, should_follow_daemon_shutdown)
        if should_follow_daemon_shutdown(get_keep_daemon_alive()):
            logger.info("Daemon shut down; menu bar following (shared lifecycle).")
            self.performSelectorOnMainThread_withObject_waitUntilDone_(
                "terminateFromEvent:", None, False)

    def terminateFromEvent_(self, sender):
        self.client.stop()
        NSApplication.sharedApplication().terminate_(self)


def main():
    # R24 #1: single-instance — if a menu-bar agent is already running, don't
    # start a second status item.
    try:
        existing = subprocess.run(
            ["pgrep", "-f", "divoom_lib.cli menubar"], capture_output=True, text=True)
        others = [p for p in existing.stdout.split() if p and int(p) != os.getpid()]
        if existing.returncode == 0 and others:
            logger.info("A Divoom menu-bar agent is already running; exiting.")
            return
    except Exception:
        pass

    app = NSApplication.sharedApplication()
    # R24 #2: status-bar agent — no Dock icon (accessory activation policy).
    try:
        from AppKit import NSApplicationActivationPolicyAccessory
        app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except Exception as e:
        logger.debug(f"setActivationPolicy(accessory) failed: {e}")

    # Instantiate the agent delegate
    agent = DivoomMenuBarAgent.alloc().init()

    # Create the Cocoa status bar item
    status_bar = NSStatusBar.systemStatusBar()
    status_item = status_bar.statusItemWithLength_(NSVariableStatusItemLength)
    agent.status_item = status_item

    # Visual layout: title reflects the notification-listener state (R15 §6).
    status_item.button().setToolTip_("Divoom Coordinator Agent")
    agent.updateStatusTitle_(None)  # initial "Divoom (idle)"

    # Create the popup menu
    menu = NSMenu.alloc().init()
    agent.menu = menu
    # R46 #3: the agent is the menu delegate so menuNeedsUpdate_ can refresh the
    # per-device tiles each time the menu opens.
    menu.setDelegate_(agent)

    # 1. Launch Dashboard option
    launch_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Launch Dashboard", "launchDashboard:", "d"
    )
    launch_item.setTarget_(agent)
    menu.addItem_(launch_item)

    # 1b. Open Notifications view (R15 §6)
    notif_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Open Notifications...", "openNotifications:", "n"
    )
    notif_item.setTarget_(agent)
    menu.addItem_(notif_item)

    menu.addItem_(NSMenuItem.separatorItem())

    # 2. Notification listener controls
    start_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Start Notifications", "startNotifications:", ""
    )
    start_item.setTarget_(agent)
    menu.addItem_(start_item)

    stop_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Stop Notifications", "stopNotifications:", ""
    )
    stop_item.setTarget_(agent)
    menu.addItem_(stop_item)

    menu.addItem_(NSMenuItem.separatorItem())

    # 3. Quit option — also stops the daemon (the single-owner kill switch).
    quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Quit Divoom (stop daemon)", "quitApp:", "q"
    )
    quit_item.setTarget_(agent)
    menu.addItem_(quit_item)

    status_item.setMenu_(menu)

    # No "launched successfully" toast — a routine successful startup isn't worth
    # interrupting the user with a system notification. The status item appearing
    # is feedback enough. (Toasts are reserved for things the user actually needs
    # to act on.)

    # Launch Cocoa event loop
    app.run()


if __name__ == "__main__":
    main()
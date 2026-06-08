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


def _pywebview_1820_bug_present() -> bool:
    """Detect whether pywebview's cocoa `BrowserView.move` still has
    the multi-monitor drag bug from upstream issue #1820.

    The bug (May 2026, present in 6.2.1): the cocoa backend's
    `BrowserView.move` does
        AppKit.NSPoint(self.screen.origin.x + x, self.screen.origin.y + flipped_y)
    but the JS in `webview/js/customize.js:44-48` sends absolute
    screen coordinates (`x = ev.screenX - initialX`), so the X is
    double-counted on multi-monitor setups and the window jumps
    off-screen mid-drag.

    The fix (upstream-recommended): drop the `self.screen.origin.x`
    term, or replace with the primary screen's origin. Any fix
    necessarily changes the literal token `self.screen.origin.x + x`
    inside the NSPoint call, so we can use that token's presence
    as a robust detection signal.

    Returns:
        True if the installed pywebview's `BrowserView.move` still
        contains the bug token and the downstream monkey-patch
        should be applied. False if the bug is not detectable
        (non-cocoa backend, source not introspectable) or if the
        upstream fix has shipped.

    The detection is intentionally narrow: matching on the exact
    bug token (`self.screen.origin.x + x`) means any plausible
    upstream fix (drop the term, replace with primary screen
    reference, rewrite the call) will not match, and the
    monkey-patch will be skipped cleanly. See
    `docs/DRAG_FIX_HISTORY.md` for the full journey.
    """
    try:
        import inspect
        from webview.platforms.cocoa import BrowserView
        src = inspect.getsource(BrowserView.move)
    except (ImportError, OSError, TypeError):
        return False

    return "self.screen.origin.x + x" in src


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Divoom Control Center")
    # R15 §6: the menubar "Open Notifications..." item launches with these so the
    # GUI opens straight to a given tab/card.
    parser.add_argument("--tab", default=None, help="nav tab to pre-select (e.g. data-sources)")
    parser.add_argument("--card", default=None, help="card to focus within the tab (e.g. notifications)")
    cli_args, _ = parser.parse_known_args()

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

    # Workaround for pywebview upstream issue #1820
    # (https://github.com/r0x0r/pywebview/issues/1820, May 2026):
    # BrowserView.move in the cocoa backend double-counts the window's
    # screen origin on multi-monitor setups, causing the window to
    # jump off the visible workspace mid-drag. The recommended
    # downstream patch drops the `self.screen.origin.x` term from the
    # NSPoint calculation. This is a no-op on single-monitor setups
    # (where screen.origin = (0, 0)) and matches the JS-side contract
    # that drag deltas are applied relative to the live window
    # position tracked by the host.
    #
    # The detection is source-based: if the literal token
    # `self.screen.origin.x + x` is no longer in BrowserView.move's
    # source, the upstream fix has shipped and the patch is skipped
    # (idempotent). See docs/DRAG_FIX_HISTORY.md for the journey.
    if sys.platform == "darwin":
        try:
            from webview.platforms.cocoa import BrowserView
            import AppKit

            if _pywebview_1820_bug_present():
                def _patched_move(self, x, y):
                    flipped_y = self.screen.size.height - y
                    self.window.setFrameTopLeftPoint_(
                        AppKit.NSPoint(x, self.screen.origin.y + flipped_y)
                    )

                BrowserView.move = _patched_move
                logger.info("Applied pywebview #1820 multi-monitor drag patch")
            else:
                logger.info("pywebview #1820 already fixed upstream; skipping patch")
        except ImportError:
            logger.warning("Could not check pywebview #1820 patch (AppKit not available)")

    import time
    from urllib.parse import urlencode
    query = {"t": int(time.time())}
    if cli_args.tab:
        query["tab"] = cli_args.tab
    if cli_args.card:
        query["card"] = cli_args.card
    url_str = f"{index_html.as_uri()}?{urlencode(query)}"
    window = webview.create_window(
        title="Divoom Control Center",
        url=url_str,
        js_api=api,
        width=1024,
        height=768,
        resizable=True,
        frameless=True,  # Integrated custom Appbar
        easy_drag=False,
        background_color="#0a0b10"
    )
    api.window = window
    _spawn_menubar_agent()
    webview.start()


def _spawn_menubar_agent() -> None:
    """Best-effort: launch the macOS menu-bar agent alongside the GUI so its
    status item appears on launch. Detached + dupe-guarded; never blocks or
    fails the GUI if it can't start. macOS only."""
    if sys.platform != "darwin":
        return
    try:
        import subprocess
        # Don't spawn a second status item if one is already running.
        existing = subprocess.run(
            ["pgrep", "-f", "divoom_lib.cli menubar"],
            capture_output=True, text=True,
        )
        if existing.returncode == 0 and existing.stdout.strip():
            logger.info("Menu-bar agent already running; not spawning another.")
            return
        repo_root = Path(__file__).resolve().parents[1]
        subprocess.Popen(
            [sys.executable, "-m", "divoom_lib.cli", "menubar"],
            cwd=str(repo_root),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        logger.info("Launched macOS menu-bar agent.")
    except Exception as e:
        logger.warning(f"Could not launch menu-bar agent: {e}")

if __name__ == "__main__":
    main()

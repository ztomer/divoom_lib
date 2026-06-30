#!/usr/bin/env python3
"""
gui_main.py — Divoom Desktop GUI launcher.
Launches the custom frameless PyWebView window.
"""

import os
import sys
import threading
import logging
import webview
from pathlib import Path

# Add divoom-control paths
sys.path.append(str(Path(__file__).parent))
sys.path.append(str(Path(__file__).parent.parent))

from divoom_gui.gui_api import DivoomGuiAPI
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


_GUI_LOCK_FH = None  # kept open for the process lifetime to hold the lock


def _ensure_single_instance() -> bool:
    """True if we got the single-instance lock; False if a Control Center is
    already running (R24 #1 — prevents the menubar 'Launch Dashboard' →
    dashboard → menubar runaway)."""
    global _GUI_LOCK_FH
    try:
        import fcntl
        import tempfile
        fh = open(os.path.join(tempfile.gettempdir(), "divoom_gui.lock"), "w")
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fh.write(str(os.getpid()))
        fh.flush()
        _GUI_LOCK_FH = fh
        return True
    except (OSError, BlockingIOError):
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Divoom Control Center")
    # R15 §6: the menubar "Open Notifications..." item launches with these so the
    # GUI opens straight to a given tab/card.
    parser.add_argument("--tab", default=None, help="nav tab to pre-select (e.g. data-sources)")
    parser.add_argument("--card", default=None, help="card to focus within the tab (e.g. notifications)")
    cli_args, _ = parser.parse_known_args()

    if sys.platform == "darwin" and not _ensure_single_instance():
        logger.info("A Divoom Control Center is already running; focusing it and exiting.")
        try:
            import subprocess
            subprocess.run(["osascript", "-e", 'tell application "Python" to activate'],
                           check=False, capture_output=True)
        except Exception:
            pass
        return

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
        width=1080,   # R24 #8: fits 3 columns in Monthly Best
        height=768,
        resizable=True,
        frameless=True,  # Integrated custom Appbar
        easy_drag=False,
        background_color="#0a0b10",
        min_size=(1050, 400),
    )
    api.window = window
    # R24: spawn the daemon EAGERLY, BEFORE webview.start(), so it's ready when
    # the GUI first asks. The daemon's Bluetooth grant no longer depends on WHO
    # spawns it: `spawn_daemon` uses macOS TCC responsibility-disclaim so the
    # daemon is always attributed to the granted `python3.14` binary, not
    # pywebview's ungranted `Python.app` host (see daemon_bridge for the why).
    if sys.platform == "darwin":
        try:
            from divoom_gui.daemon_bridge import ensure_daemon
            ensure_daemon(detach=True)
            logger.info("Eagerly spawned daemon (TCC-disclaimed, granted python identity) before GUI host.")
        except Exception as e:
            logger.warning(f"eager daemon spawn failed: {e}")
    _spawn_menubar_agent()
    # Prime TCC prompts up front from the foreground app — esp. Automation
    # (AppleScript control of Music/Spotify) for the cover-art widget, whose
    # prompt was otherwise raised invisibly by the headless daemon.
    try:
        from divoom_gui.permissions import prime_permissions
        prime_permissions()
    except Exception as e:
        logger.debug(f"permission priming skipped: {e}")
    # R40 §9: follow the daemon down if it shuts down while we're open AND the
    # lifecycles are shared (keep-alive off) — e.g. the menu bar's 'Quit Divoom'.
    _start_shutdown_follower(window)

    # R52: stop the daemon EXACTLY ONCE. Both the `closing` event and the
    # post-start block (and, indirectly, the shutdown follower) used to each send
    # a shutdown, so one quit produced a "shut down → close → shut down" cascade
    # in the logs and re-triggered the follower. The guard collapses it to one.
    _shutdown_sent = threading.Event()

    def _stop_daemon_once(reason: str) -> None:
        if _shutdown_sent.is_set():
            return
        _shutdown_sent.set()
        try:
            from divoom_lib.lifecycle_config import (
                get_keep_daemon_alive, should_stop_daemon_on_dashboard_quit)
            if should_stop_daemon_on_dashboard_quit(get_keep_daemon_alive()):
                from divoom_daemon.daemon_protocol import DaemonClient, DEFAULT_SOCKET_PATH
                logger.info(f"{reason}; stopping daemon (shared lifecycle).")
                DaemonClient(DEFAULT_SOCKET_PATH, timeout=1.0).shutdown()
        except Exception as e:
            logger.debug(f"daemon shutdown skipped: {e}")

    window.events.closing += lambda: _stop_daemon_once("Dashboard closing")
    webview.start()

    # webview.start() blocks until the window closes. On close, when lifecycles
    # are shared, stop the daemon too (which broadcasts → the menu bar follows).
    _stop_daemon_once("Dashboard closed")

    # R52: the GUI is a thin client — the daemon (a separate process) owns the
    # BLE connection and has already been told to stop. pywebview/WebKit can leave
    # the host process alive after the window is destroyed (an in-flight js_api
    # call, a lingering Cocoa run loop), so force a clean exit rather than hang.
    logger.info("Dashboard exited; terminating GUI host.")
    os._exit(0)


def _start_shutdown_follower(window) -> None:
    """Subscribe to the daemon's shutdown event on a daemon thread; if it fires
    while keep-alive is OFF, close the dashboard window. Event-driven — no
    polling."""
    def _run():
        try:
            from divoom_daemon.daemon_protocol import (
                DaemonClient, DEFAULT_SOCKET_PATH, EVENT_SHUTDOWN)
            from divoom_lib.lifecycle_config import (
                get_keep_daemon_alive, should_follow_daemon_shutdown)

            def on_event(ev: dict) -> None:
                if ev.get("type") == EVENT_SHUTDOWN and \
                        should_follow_daemon_shutdown(get_keep_daemon_alive()):
                    logger.info("Daemon shut down; closing dashboard (shared lifecycle).")
                    try:
                        window.destroy()
                    except Exception:
                        pass
            DaemonClient(DEFAULT_SOCKET_PATH, timeout=2.0).subscribe(on_event)
        except Exception as e:
            logger.debug(f"shutdown follower stopped: {e}")

    threading.Thread(target=_run, daemon=True, name="shutdown-follower").start()


def _resolve_menubar_binary() -> "str | None":
    """Locate the native Rust menubar binary (divoom-menubar), mirroring the
    daemon resolver: env override → py2app bundle Resources → dev build tree."""
    override = os.environ.get("DIVOOM_MENUBAR_BINARY")
    if override and Path(override).exists():
        return override
    rp = os.environ.get("RESOURCEPATH")  # set by py2app inside the .app bundle
    if rp:
        cand = Path(rp) / "divoom-menubar"
        if cand.exists():
            return str(cand)
    repo_root = Path(__file__).resolve().parents[1]
    for folder in ("release", "debug"):
        p = repo_root / "native-port" / "divoom-menubar" / "target" / folder / "divoom-menubar"
        if p.exists():
            return str(p)
    return None


def _spawn_menubar_agent() -> None:
    """Best-effort: launch the native Rust menu-bar agent (divoom-menubar)
    alongside the GUI so its status item appears on launch. The agent talks to the
    daemon over the socket and relaunches THIS GUI on demand, so we hand it our
    launch command via env (DIVOOM_GUI_PYTHON/SCRIPT). Detached + dupe-guarded;
    never blocks or fails the GUI if it can't start. macOS only."""
    if sys.platform != "darwin":
        return
    try:
        import subprocess
        # Don't spawn a second status item if one is already running.
        existing = subprocess.run(
            ["pgrep", "-f", "divoom-menubar"],
            capture_output=True, text=True,
        )
        if existing.returncode == 0 and existing.stdout.strip():
            logger.info("Menu-bar agent already running; not spawning another.")
            return
        binary = _resolve_menubar_binary()
        if not binary:
            logger.warning("Native menu-bar binary (divoom-menubar) not found; "
                           "build it with ./build.sh. No menu-bar this session.")
            return
        # In a py2app .app, sys.executable is the GUI stub — hand the agent the
        # bundled python + this script so its "Launch Dashboard" reopens the GUI.
        from divoom_daemon.daemon_client import bundle_python
        gui_python = bundle_python() or sys.executable
        env = dict(os.environ)
        env["DIVOOM_GUI_PYTHON"] = gui_python
        env["DIVOOM_GUI_SCRIPT"] = str(Path(__file__).resolve())
        subprocess.Popen(
            [binary],
            env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        logger.info("Launched native Rust menu-bar agent (divoom-menubar).")
    except Exception as e:
        logger.warning(f"Could not launch menu-bar agent: {e}")

if __name__ == "__main__":
    main()

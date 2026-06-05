"""
Instrumented test for the frameless window drag handler.

Regression test for: "can't move the window" — this broke at least once
in commit f2d2507d (and possibly earlier). The test loads the real
`gui/web_ui/index.html` in headless Chromium via Playwright, injects a
stub `pywebview` global, and verifies that a mouse drag on the appbar
results in `drag_window` being called with non-zero deltas.

Requires:
    pip install playwright
    playwright install chromium

Runs in the normal pytest suite (no flag needed). Falls back to a
skip-with-reason if Playwright or chromium is unavailable.
"""
import contextlib
import http.server
import os
import socket
import socketserver
import threading
import time
from pathlib import Path

import pytest

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


WEB_UI_DIR = Path(__file__).resolve().parents[1] / "gui" / "web_ui"


def _free_port() -> int:
    """Bind to port 0, read assigned port, release."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        pass


@contextlib.contextmanager
def _serve_directory(directory: Path):
    """Serve `directory` over HTTP on a free port. Yields the base URL."""
    port = _free_port()
    handler = lambda *a, **kw: _QuietHandler(*a, directory=str(directory), **kw)
    httpd = socketserver.TCPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/index.html"
    finally:
        httpd.shutdown()
        httpd.server_close()


pytestmark = pytest.mark.skipif(
    sync_playwright is None,
    reason="playwright not installed (pip install playwright && playwright install chromium)",
)


@pytest.fixture(scope="module")
def browser():
    """Single Chromium instance for the whole test module."""
    if sync_playwright is None:
        yield None
        return
    with sync_playwright() as p:
        with p.chromium.launch(headless=True) as b:
            yield b


def test_appbar_drag_calls_drag_window(browser):
    """
    Real event flow: mousedown on .integrated-appbar → mousemove → mouseup.
    Expects window.pywebview.api.drag_window to be called multiple times with
    deltas that are non-trivially non-zero. We don't assert exact delta values
    because Playwright's smooth-move interpolation and the appbar's position
    can produce sub-pixel rounding; the regression we care about is "handler
    is wired" + "deltas are reasonable (no all-zero, no NaN)".
    """
    if browser is None:
        pytest.skip("playwright not available")
    if not WEB_UI_DIR.exists():
        pytest.skip(f"web_ui dir not found at {WEB_UI_DIR}")

    with _serve_directory(WEB_UI_DIR) as url:
        context = browser.new_context(viewport={"width": 1024, "height": 768})
        # Inject stub pywebview before any page script runs.
        context.add_init_script("""
            window._dragCalls = [];
            window._dragAttached = false;
            window.pywebview = {
                api: {
                    minimize_window: () => {},
                    maximize_window: () => {},
                    close_window: () => {},
                    drag_window: (dx, dy) => window._dragCalls.push([dx, dy]),
                }
            };
        """)
        page = context.new_page()

        # Forward console messages so we see JS errors from app.js/widgets.js.
        console_errors = []
        page.on("pageerror", lambda exc: console_errors.append(str(exc)))
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        page.goto(url, wait_until="domcontentloaded")

        # Wait for the appbar handler to be attached.
        page.wait_for_selector(".integrated-appbar", state="visible", timeout=5000)

        # .appbar-drag-spacer is the natural drag target.
        spacer = page.query_selector(".appbar-drag-spacer")
        target = spacer if spacer else page.query_selector(".integrated-appbar")
        assert target is not None, "could not find drag target inside .integrated-appbar"

        box = target.bounding_box()
        assert box is not None
        cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2

        # Simulate a real drag: mousedown → mousemove → mouseup.
        # Single move (no steps) so we get one mousemove per Python call.
        page.mouse.move(cx, cy)
        page.mouse.down()
        page.mouse.move(cx + 80, cy + 40)
        time.sleep(0.05)
        page.mouse.up()

        # Give the event loop a tick to process the final move.
        page.wait_for_timeout(50)

        calls = page.evaluate("window._dragCalls")
        assert calls, (
            f"drag_window was never called. "
            f"console errors: {console_errors}"
        )
        # 1) At least one call (one per mousemove).
        assert len(calls) >= 1, f"expected at least one drag call, got {len(calls)}: {calls}"
        # 2) No NaN, no Infinity, no absurd values.
        for dx, dy in calls:
            assert dx == dx and dy == dy, f"NaN in drag calls: {calls}"  # NaN check
            assert abs(dx) < 1e6 and abs(dy) < 1e6, f"absurd delta: {calls}"
        # 3) The call(s) should reflect a rightward + downward drag.
        #    Headless Chromium sometimes coalesces mousemoves; we just need at
        #    least one positive dx and one positive dy across all calls.
        all_dx = [c[0] for c in calls]
        all_dy = [c[1] for c in calls]
        assert any(dx > 0 for dx in all_dx), f"expected rightward drag, got {calls}"
        assert any(dy > 0 for dy in all_dy), f"expected downward drag, got {calls}"

        # Filter out errors that aren't related to the drag handler. The
        # test environment doesn't load the full app API surface (load_config,
        # apply_system_stats, etc.) — those errors are expected and not
        # related to the regression we're guarding against.
        DRAG_UNRELATED = ("load_config", "apply_system_stats", "get_audio_levels",
                          "get_current_track_info", "get_transport_status",
                          "scan_devices_with_config", "load_lan_devices",
                          "get_tickers", "get_ticker_preview",
                          "apply_stock_ticker", "toggle_music_sync",
                          "toggle_sysmon_sync", "toggle_stocks_sync",
                          "toggle_audio_visualizer", "set_brightness",
                          "is not a function")
        drag_errors = [e for e in console_errors
                       if not any(needle in e for needle in DRAG_UNRELATED)]
        assert not drag_errors, f"drag-related JS errors: {drag_errors}"

        context.close()


def test_appbar_drag_ignores_button_clicks(browser):
    """
    Clicking a button inside the appbar (e.g. minimize) must NOT start a drag.
    This guards against regressions where a `closest("button, select, input")`
    check is removed.
    """
    if browser is None:
        pytest.skip("playwright not available")

    with _serve_directory(WEB_UI_DIR) as url:
        context = browser.new_context(viewport={"width": 1024, "height": 768})
        context.add_init_script("""
            window._dragCalls = [];
            window.pywebview = {
                api: {
                    minimize_window: () => {},
                    maximize_window: () => {},
                    close_window: () => {},
                    drag_window: (dx, dy) => window._dragCalls.push([dx, dy]),
                }
            };
        """)
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_selector("#win-min", state="visible", timeout=5000)

        btn = page.query_selector("#win-min")
        assert btn is not None
        box = btn.bounding_box()
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down()
        page.mouse.move(box["x"] + 50, box["y"] + 20)
        page.mouse.up()
        page.wait_for_timeout(50)

        calls = page.evaluate("window._dragCalls")
        assert calls == [], (
            f"clicking #win-min must not trigger drag, but got {calls}"
        )
        context.close()

"""Local REST control interface for the Divoom GUI bridge.

Wraps a ``DivoomGuiAPI`` instance and exposes every public bridge method over a
localhost HTTP API. This makes the whole app **driveable headlessly** — for
automated end-to-end tests, scripting, the "run headless" hot-channel daemon
(item 4.d), and instrumented verification of features that otherwise need the
PyWebView window.

Design:
- Reflection-based dispatch: any public (non-underscore) callable on the wrapped
  API object is invokable as ``POST /api/<method>``; no per-method boilerplate,
  so new bridge methods are exposed automatically.
- Bound to 127.0.0.1 by default (local instrumentation only). An optional bearer
  token (``DIVOOM_CONTROL_TOKEN``) can gate access.

Endpoints:
- ``GET  /health``        → ``{"ok": true}``
- ``GET  /api``           → list of callable methods + signatures
- ``POST /api/<method>``  → body is a JSON object (kwargs) or array (positional);
                            returns ``{"ok": true, "result": ...}``

Run standalone:  ``python gui/control_server.py --port 8787``
"""

from __future__ import annotations

import inspect
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logger = logging.getLogger("divoom.control_server")

# Methods that require the live PyWebView window or would block — not useful (or
# safe) to drive over the headless control API.
_DENYLIST = {"run", "stop", "minimize_window", "maximize_window", "close_window"}


def list_methods(api) -> list[dict]:
    """Return metadata for every invokable public method on ``api``."""
    out = []
    for name in dir(api):
        if name.startswith("_") or name in _DENYLIST:
            continue
        attr = getattr(api, name, None)
        if not callable(attr):
            continue
        try:
            sig = str(inspect.signature(attr))
        except (TypeError, ValueError):
            sig = "(...)"
        out.append({"name": name, "signature": sig})
    return out


def _maybe_json(value):
    """Many bridge methods return a JSON *string*; decode it for convenience."""
    if isinstance(value, (str, bytes)):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value.decode() if isinstance(value, bytes) else value
    return value


def make_handler(api, token: str | None):
    methods = {m["name"] for m in list_methods(api)}

    class Handler(BaseHTTPRequestHandler):
        server_version = "DivoomControl/1.0"

        def log_message(self, fmt, *args):  # quieter logging
            logger.debug("%s - %s", self.address_string(), fmt % args)

        def _send(self, code: int, payload: dict):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            if not token:
                return True
            return self.headers.get("Authorization") == f"Bearer {token}"

        def do_GET(self):
            if self.path == "/health":
                return self._send(200, {"ok": True})
            if self.path == "/api":
                if not self._authorized():
                    return self._send(401, {"ok": False, "error": "unauthorized"})
                return self._send(200, {"ok": True, "methods": list_methods(api)})
            return self._send(404, {"ok": False, "error": "not found"})

        def do_POST(self):
            if not self._authorized():
                return self._send(401, {"ok": False, "error": "unauthorized"})
            if not self.path.startswith("/api/"):
                return self._send(404, {"ok": False, "error": "not found"})
            method = self.path[len("/api/"):].strip("/")
            if method not in methods:
                return self._send(404, {"ok": False, "error": f"unknown method {method!r}"})

            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            args, kwargs = [], {}
            if raw:
                try:
                    parsed = json.loads(raw)
                except ValueError as e:
                    return self._send(400, {"ok": False, "error": f"bad JSON: {e}"})
                if isinstance(parsed, dict):
                    kwargs = parsed
                elif isinstance(parsed, list):
                    args = parsed
                else:
                    args = [parsed]

            try:
                result = getattr(api, method)(*args, **kwargs)
                return self._send(200, {"ok": True, "result": _maybe_json(result)})
            except TypeError as e:
                return self._send(400, {"ok": False, "error": str(e)})
            except Exception as e:  # bridge methods already log; surface the message
                logger.exception("control API method %s failed", method)
                return self._send(500, {"ok": False, "error": str(e)})

    return Handler


def serve(api, host: str = "127.0.0.1", port: int = 8787, token: str | None = None):
    """Start a blocking control server. Returns the server (call in a thread)."""
    if token is None:
        token = os.environ.get("DIVOOM_CONTROL_TOKEN") or None
    httpd = ThreadingHTTPServer((host, port), make_handler(api, token))
    logger.info("Divoom control server listening on http://%s:%d", host, port)
    return httpd


def serve_in_background(api, host: str = "127.0.0.1", port: int = 8787, token: str | None = None):
    """Start the control server on a daemon thread; returns (httpd, thread)."""
    httpd = serve(api, host, port, token)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True, name="divoom-control")
    thread.start()
    return httpd, thread


def _build_api():
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent))
    from gui_main import DivoomGuiAPI
    return DivoomGuiAPI()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Divoom GUI control REST server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--token", default=None, help="optional bearer token")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    api = _build_api()
    httpd = serve(api, args.host, args.port, args.token)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()

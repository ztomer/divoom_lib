"""End-to-end tests for the local REST control interface."""

import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "gui"))

from control_server import serve_in_background, list_methods  # noqa: E402


class FakeApi:
    """Stand-in bridge with the shapes the real API uses."""

    def set_vj_effect(self, number: int) -> bool:
        self.last_vj = number
        return True

    def scan_devices_with_config(self, timeout: int, limit: int) -> str:
        # Mirrors real methods that return a JSON string.
        return json.dumps([{"name": "Pixoo-mock", "timeout": timeout, "limit": limit}])

    def explode(self):
        raise RuntimeError("boom")

    def _private(self):  # must NOT be exposed
        return "secret"


@pytest.fixture
def server():
    api = FakeApi()
    httpd, thread = serve_in_background(api, host="127.0.0.1", port=0)
    port = httpd.server_address[1]
    yield api, f"http://127.0.0.1:{port}"
    httpd.shutdown()


def _get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.status, json.loads(r.read())


def _post(url, payload):
    data = json.dumps(payload).encode() if payload is not None else b""
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_health(server):
    _, base = server
    status, body = _get(f"{base}/health")
    assert status == 200 and body == {"ok": True}


def test_method_listing_excludes_private(server):
    _, base = server
    status, body = _get(f"{base}/api")
    assert status == 200 and body["ok"]
    names = {m["name"] for m in body["methods"]}
    assert "set_vj_effect" in names
    assert "scan_devices_with_config" in names
    assert "_private" not in names


def test_post_kwargs(server):
    api, base = server
    status, body = _post(f"{base}/api/set_vj_effect", {"number": 7})
    assert status == 200 and body == {"ok": True, "result": True}
    assert api.last_vj == 7


def test_post_positional_and_json_string_decoded(server):
    _, base = server
    # Positional args via JSON array; result is a JSON *string* that the server
    # decodes into structured JSON for the caller.
    status, body = _post(f"{base}/api/scan_devices_with_config", [3, 2])
    assert status == 200
    assert body["ok"] and body["result"][0] == {"name": "Pixoo-mock", "timeout": 3, "limit": 2}


def test_unknown_method_404(server):
    _, base = server
    status, body = _post(f"{base}/api/does_not_exist", {})
    assert status == 404 and not body["ok"]


def test_method_error_surfaces_500(server):
    _, base = server
    status, body = _post(f"{base}/api/explode", {})
    assert status == 500 and not body["ok"] and "boom" in body["error"]


def test_lists_real_api_surface():
    """The reflection layer exposes the real Control Center bridges."""
    import gui_main
    from unittest.mock import patch
    with patch("pathlib.Path.exists", return_value=False):
        api = gui_main.DivoomGuiAPI()
    names = {m["name"] for m in list_methods(api)}
    for expected in ("set_vj_effect", "set_visualization", "set_clock",
                     "switch_channel", "set_solid_light", "scan_devices_with_config"):
        assert expected in names, f"{expected} not exposed"
    # window controls are denylisted
    assert "close_window" not in names


def test_unix_socket_server():
    """Serve over a Unix domain socket and invoke via cs.call client utility."""
    import os
    import control_server as cs

    sock_path = "/tmp/t_div.sock"
    api = FakeApi()
    
    # Start server in background
    httpd, thread = cs.serve_unix_in_background(api, sock_path)
    try:
        # Call via UNIX socket client connection
        res = cs.call("set_vj_effect", 42, socket_path=sock_path)
        assert res is True
        assert api.last_vj == 42
    finally:
        httpd.shutdown()
        if os.path.exists(sock_path):
            os.unlink(sock_path)

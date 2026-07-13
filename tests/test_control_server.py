"""End-to-end tests for the local REST control interface."""

import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "divoom_gui"))

# Import under the QUALIFIED package name first. gui_main.py and the rest of
# this test file import the bare top-level ``control_server`` (via the
# sys.path trick above), which loads the same file under a *different*
# module identity than ``divoom_gui.control_server``. coverage.py tracks
# lines by file path so both work at runtime, but pytest-cov's per-module
# ``--cov=divoom_gui.control_server`` arg needs the dotted name resolvable
# via import machinery to attribute the file at all — without this import,
# `--cov=divoom_gui.control_server` reports "module was never imported" and
# silently drops ALL coverage data for this file (verified: it shows zero
# lines instead of partial coverage). Keep this import so the module Miss
# count in `pytest --cov=divoom_gui.control_server` reflects reality.
import divoom_gui.control_server  # noqa: F401,E402

from control_server import serve_in_background, list_methods  # noqa: E402
import control_server as cs  # noqa: E402


class FakeApi:
    """Stand-in bridge with the shapes the real API uses."""

    def set_vj_effect(self, number: int) -> bool:
        self.last_vj = number
        return True

    def scan_devices(self, timeout: int, limit: int) -> str:
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
    assert "scan_devices" in names
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
    status, body = _post(f"{base}/api/scan_devices", [3, 2])
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
                     "switch_channel", "set_solid_light", "scan_devices"):
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


# ── R61: coverage push — token auth, error edges, client helpers ───────────


class _SigFailApi:
    """An attribute whose signature can't be introspected (builtin), plus a
    fixed-arity method to trigger a TypeError from a bad call."""

    boom = dict().update  # inspect.signature() raises ValueError for this builtin

    def fixed_arity(self, x: int) -> int:
        return x + 1


@pytest.fixture
def token_server():
    api = FakeApi()
    httpd, thread = serve_in_background(api, host="127.0.0.1", port=0, token="secret-tok")
    port = httpd.server_address[1]
    yield api, f"http://127.0.0.1:{port}"
    httpd.shutdown()


def _get_auth(url, token=None):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _post_auth(url, payload, token=None, raw=False):
    if raw:
        data = payload
    else:
        data = json.dumps(payload).encode() if payload is not None else b""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_get_api_requires_token_when_configured(token_server):
    """L90/97: with a token configured, GET /api without (or with the wrong)
    Authorization header is rejected; the right header is accepted."""
    _, base = token_server
    status, body = _get_auth(f"{base}/api")  # no header at all
    assert status == 401 and not body["ok"]
    status, body = _get_auth(f"{base}/api", token="wrong")
    assert status == 401 and not body["ok"]
    status, body = _get_auth(f"{base}/api", token="secret-tok")
    assert status == 200 and body["ok"]


def test_post_requires_token_when_configured(token_server):
    """L102-103: POST is also gated behind the token."""
    _, base = token_server
    status, body = _post_auth(f"{base}/api/set_vj_effect", {"number": 1})  # no header
    assert status == 401 and not body["ok"]
    status, body = _post_auth(f"{base}/api/set_vj_effect", {"number": 1}, token="secret-tok")
    assert status == 200 and body["ok"]


def test_get_unknown_path_404(server):
    """L99: GET a path that's neither /health nor /api."""
    _, base = server
    status, body = _get_auth(f"{base}/nope")
    assert status == 404 and not body["ok"]


def test_post_path_not_under_api_404(server):
    """L104-105: POST to a path that doesn't start with /api/."""
    _, base = server
    status, body = _post(f"{base}/not-api/set_vj_effect", {})
    assert status == 404 and not body["ok"]


def test_post_malformed_json_body_400(server):
    """L115-117: an unparsable JSON body is rejected with 400, not a crash."""
    _, base = server
    status, body = _post_auth(f"{base}/api/set_vj_effect", b"{not json", raw=True)
    assert status == 400 and not body["ok"] and "bad JSON" in body["error"]


def test_post_scalar_json_body_becomes_single_positional_arg(server):
    """L118-123: a bare JSON scalar (not dict/list) is wrapped as one
    positional arg."""
    api, base = server
    status, body = _post_auth(f"{base}/api/set_vj_effect", b"7", raw=True)
    assert status == 200 and body["ok"] and body["result"] is True
    assert api.last_vj == 7


def test_post_empty_body_calls_with_no_args_and_typeerror_maps_to_400(server):
    """L113->125 (raw falsy skips body parsing) + L128-129 (a TypeError from
    the call — here a missing required arg — surfaces as 400, not 500)."""
    _, base = server
    status, body = _post(f"{base}/api/set_vj_effect", None)
    assert status == 400 and not body["ok"]
    assert "argument" in body["error"] or "positional" in body["error"]


def test_list_methods_handles_uninspectable_signature():
    """L54-55: inspect.signature() can raise for some builtins; list_methods
    must fall back to a placeholder signature instead of blowing up."""
    out = {m["name"]: m["signature"] for m in list_methods(_SigFailApi())}
    assert out["boom"] == "(...)"
    assert "fixed_arity" in out


def test_maybe_json_returns_raw_string_when_not_json():
    """L65-66: a non-JSON string result is returned as-is (not decoded)."""
    assert cs._maybe_json("not json at all") == "not json at all"


def test_maybe_json_decodes_bytes_when_not_json():
    """L65-66 (bytes branch): non-JSON bytes are decoded to str, not left as
    bytes (which json can't serialize in the HTTP reply)."""
    assert cs._maybe_json(b"not json bytes") == "not json bytes"


def test_serve_with_explicit_token_skips_env_lookup(monkeypatch):
    """L139-140 branch: passing an explicit token means the env var is never
    consulted."""
    monkeypatch.setenv("DIVOOM_CONTROL_TOKEN", "env-token-should-be-ignored")
    api = FakeApi()
    httpd, thread = cs.serve_in_background(api, port=0, token="explicit-token")
    try:
        port = httpd.server_address[1]
        status, body = _get_auth(f"http://127.0.0.1:{port}/api", token="explicit-token")
        assert status == 200 and body["ok"]
        status, body = _get_auth(f"http://127.0.0.1:{port}/api", token="env-token-should-be-ignored")
        assert status == 401
    finally:
        httpd.shutdown()


def test_serve_unix_with_explicit_token_and_pre_existing_socket_file():
    """L166-169: an explicit token skips the env lookup, and a stale file
    already sitting at socket_path is unlinked before binding.

    Uses a short /tmp path directly (not tmp_path) — AF_UNIX rejects
    pytest's long tmp_path on macOS."""
    import time as _time
    sock_path = f"/tmp/t_div_stale_{os.getpid()}_{_time.time_ns()}.sock"
    Path(sock_path).write_text("stale, not a socket")  # pre-existing file
    api = FakeApi()
    httpd, thread = cs.serve_unix_in_background(api, sock_path, token="unix-tok")
    try:
        res = cs.call("set_vj_effect", 5, socket_path=sock_path, token="unix-tok")
        assert res is True and api.last_vj == 5
        with pytest.raises(RuntimeError):
            cs.call("set_vj_effect", 5, socket_path=sock_path, token="wrong")
    finally:
        httpd.shutdown()
        if os.path.exists(sock_path):
            os.unlink(sock_path)


def test_call_over_tcp_base_url(server):
    """L223-228: the `call()` client helper's TCP branch (base_url, not a
    unix socket)."""
    api, base = server
    res = cs.call("set_vj_effect", 9, base_url=base)
    assert res is True and api.last_vj == 9


def test_call_raises_runtime_error_on_failure(server):
    """L230-231: call() raises RuntimeError when the server replies not-ok."""
    _, base = server
    with pytest.raises(RuntimeError):
        cs.call("does_not_exist", base_url=base)


def test_build_api_constructs_real_gui_api():
    """L236-240: _build_api() wires up the real DivoomGuiAPI (used by the
    `python control_server.py` standalone entrypoint)."""
    from unittest.mock import patch
    with patch("pathlib.Path.exists", return_value=False):
        api = cs._build_api()
    import gui_main
    assert isinstance(api, gui_main.DivoomGuiAPI)

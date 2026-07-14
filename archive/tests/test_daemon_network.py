"""R19 — the daemon as a headless network server: TCP listener alongside the
Unix socket, token auth, and binary blobs over the wire (remote clients have no
shared filesystem). All tests use a fake device, no BLE.
"""
import os
import socket as _socket
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "divoom_gui"))

from archive.divoom_daemon.daemon import DivoomDaemon
from divoom_daemon.daemon_protocol import DaemonClient
from divoom_gui.daemon_bridge import DaemonDeviceProxy


class _Facade:
    def __init__(self, calls):
        self._calls = calls

    async def show_light(self, color, brightness):
        self._calls.append(("display.show_light", color, brightness))
        return True

    async def show_image(self, path):
        # Record the path + its bytes so blob materialization can be verified.
        with open(path, "rb") as f:
            self._calls.append(("display.show_image", path, f.read()))
        return True


class FakeDevice:
    def __init__(self):
        self.is_connected = True
        self.calls = []
        self.display = _Facade(self.calls)

    async def connect(self):
        self.is_connected = True

    async def disconnect(self):
        self.is_connected = False


def _free_port() -> int:
    s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def net_daemon():
    sp = f"/tmp/divoom_net_{os.getpid()}.sock"
    if os.path.exists(sp):
        os.remove(sp)
    port = _free_port()
    dev = FakeDevice()
    d = DivoomDaemon(socket_path=sp, monitor=object(), device=dev,
                     host="127.0.0.1", port=port, token="s3cr3t")
    t = threading.Thread(target=d.serve_forever, daemon=True)
    t.start()
    # Wait for the TCP port to be accepting.
    deadline = time.time() + 3.0
    while time.time() < deadline:
        try:
            _socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.02)
    try:
        yield d, dev, sp, port
    finally:
        d.stop()
        t.join(timeout=3.0)
        if os.path.exists(sp):
            os.remove(sp)


def test_tcp_with_valid_token(net_daemon):
    _, dev, _sp, port = net_daemon
    c = DaemonClient(host="127.0.0.1", port=port, token="s3cr3t")
    assert c.is_remote is True
    reply = c.device_call("display.show_light", ["00FFCC", 100])
    assert reply["success"] is True
    assert dev.calls[0] == ("display.show_light", "00FFCC", 100)


def test_tcp_wrong_token_rejected(net_daemon):
    _, _dev, _sp, port = net_daemon
    c = DaemonClient(host="127.0.0.1", port=port, token="WRONG")
    reply = c.device_call("display.show_light", ["00FFCC", 100])
    assert reply["success"] is False
    assert "unauthorized" in reply.get("error", "")


def test_tcp_missing_token_rejected(net_daemon):
    _, _dev, _sp, port = net_daemon
    c = DaemonClient(host="127.0.0.1", port=port, token=None)
    reply = c.device_call("display.show_light", ["00FFCC", 100])
    assert reply["success"] is False
    assert "unauthorized" in reply.get("error", "")


def test_unix_socket_still_trusted_without_token(net_daemon):
    _, dev, sp, _port = net_daemon
    c = DaemonClient(sp)  # local Unix: no token required
    assert c.is_remote is False
    reply = c.device_call("display.show_light", ["112233", 50])
    assert reply["success"] is True


def test_blob_is_materialized_and_substituted(net_daemon, tmp_path):
    """A remote device_call with a blob writes the bytes to a daemon-side temp
    file and substitutes the path into the arg the device receives."""
    _, dev, _sp, port = net_daemon
    payload = b"\x89PNG\r\n\x1a\n-fake-image-bytes"
    c = DaemonClient(host="127.0.0.1", port=port, token="s3cr3t")
    reply = c.device_call("display.show_image", ["ignored.png"],
                          blobs={0: payload})
    assert reply["success"] is True
    name, used_path, seen_bytes = dev.calls[-1]
    assert name == "display.show_image"
    assert used_path != "ignored.png"          # substituted with a temp path
    assert seen_bytes == payload               # daemon wrote our exact bytes


def test_remote_proxy_blobifies_local_file(net_daemon, tmp_path):
    """DaemonDeviceProxy over a remote client auto-ships a local file arg as a
    blob (the daemon has no access to the client's filesystem)."""
    _, dev, _sp, port = net_daemon
    img = tmp_path / "frame.png"
    img.write_bytes(b"GIF89a-proxy-bytes")
    c = DaemonClient(host="127.0.0.1", port=port, token="s3cr3t")
    proxy = DaemonDeviceProxy(c)
    import asyncio
    asyncio.new_event_loop().run_until_complete(proxy.display.show_image(str(img)))
    name, used_path, seen_bytes = dev.calls[-1]
    assert name == "display.show_image"
    assert seen_bytes == b"GIF89a-proxy-bytes"

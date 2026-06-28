"""Integration parity tests for the native Rust daemon (divoomd).

Spawns the compiled Rust divoomd binary and drives it using the Python DaemonClient
to assert that all notification/status commands produce identical JSON structures to the Python daemon.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))

from divoom_daemon.daemon_protocol import DaemonClient


@pytest.fixture
def rust_daemon_ctx():
    # Locate the compiled Rust binary
    repo_root = Path(__file__).parent.parent
    bin_path = repo_root / "native-port" / "divoomd" / "target" / "debug" / "divoomd"
    
    # Fallback to release binary if debug is not compiled (but we compile debug in tests)
    if not bin_path.exists():
        bin_path = repo_root / "native-port" / "divoomd" / "target" / "release" / "divoomd"
        
    if not bin_path.exists():
        pytest.skip(f"Rust binary not found at {bin_path}. Run cargo build first.")

    sp = f"/tmp/divoomd_parity_{os.getpid()}.sock"
    if os.path.exists(sp):
        os.remove(sp)

    # Spawn divoomd as a subprocess
    proc = subprocess.Popen(
        [str(bin_path), "--socket", sp],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # Wait for the socket to be bound
    bound = False
    for _ in range(50):
        if os.path.exists(sp):
            bound = True
            break
        time.sleep(0.05)

    if not bound:
        proc.kill()
        stdout, stderr = proc.communicate(timeout=1.0)
        pytest.fail(f"Rust daemon failed to bind to {sp}. stdout: {stdout}, stderr: {stderr}")

    try:
        yield DaemonClient(sp)
    finally:
        # Shutdown cleanly via socket or SIGTERM
        try:
            DaemonClient(sp).send_command("shutdown")
        except Exception:
            pass
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()
        if os.path.exists(sp):
            os.remove(sp)


def test_rust_ping(rust_daemon_ctx):
    client = rust_daemon_ctx
    reply = client.send_command("ping")
    assert reply["success"] is True
    # The native daemon returns {"success": true, "pong": true}
    assert reply.get("pong") is True


def test_rust_get_status(rust_daemon_ctx):
    client = rust_daemon_ctx
    reply = client.send_command("get_status")
    assert reply["success"] is True
    assert "uptime_s" in reply
    assert reply["state"] in ("idle", "active", "error")
    assert reply["counters"] == {"seen": 0, "routed": 0, "dropped": 0}


def test_rust_notification_status(rust_daemon_ctx):
    client = rust_daemon_ctx
    reply = client.send_command("notification_status")
    assert reply["success"] is True
    assert reply["state"] in ("idle", "active", "error")
    assert reply["counters"] == {"seen": 0, "routed": 0, "dropped": 0}


def test_rust_start_stop_notifications(rust_daemon_ctx):
    client = rust_daemon_ctx
    # start_notifications
    reply = client.send_command("start_notifications")
    
    # On non-macOS, start_notifications returns success=false or unsupported=true.
    # On macOS, it should start or report access/TCC errors.
    # Let's assert the schema properties.
    assert "success" in reply
    assert "state" in reply
    assert "counters" in reply
    
    # stop_notifications
    reply2 = client.send_command("stop_notifications")
    assert reply2["success"] is True
    assert reply2["state"] == "idle"
    assert "counters" in reply2


def test_rust_set_routing(rust_daemon_ctx):
    client = rust_daemon_ctx
    rules = [
        ("whatsapp", 6),
        ("mail", 7),
        ("slack", 13)
    ]
    reply = client.set_routing(rules)
    assert reply["success"] is True


def test_rust_tcp_token_auth():
    # Locate the compiled Rust binary
    repo_root = Path(__file__).parent.parent
    bin_path = repo_root / "native-port" / "divoomd" / "target" / "debug" / "divoomd"
    if not bin_path.exists():
        bin_path = repo_root / "native-port" / "divoomd" / "target" / "release" / "divoomd"
    if not bin_path.exists():
        pytest.skip(f"Rust binary not found at {bin_path}. Run cargo build first.")

    sp = f"/tmp/divoomd_parity_tcp_{os.getpid()}.sock"
    if os.path.exists(sp):
        os.remove(sp)

    host = "127.0.0.1"
    port = 9099
    token = "my_secret_token"

    # Spawn divoomd with TCP listener enabled and token auth required
    proc = subprocess.Popen(
        [str(bin_path), "--socket", sp, "--host", host, "--port", str(port), "--token", token],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # Wait for the Unix socket (and TCP port) to be bound
    bound = False
    for _ in range(50):
        if os.path.exists(sp):
            bound = True
            break
        time.sleep(0.05)

    if not bound:
        proc.kill()
        stdout, stderr = proc.communicate(timeout=1.0)
        pytest.fail(f"Rust daemon failed to bind. stdout: {stdout}, stderr: {stderr}")

    try:
        # Test 1: Successful auth with correct token
        client_ok = DaemonClient(host=host, port=port, token=token)
        reply = client_ok.send_command("ping")
        assert reply["success"] is True
        assert reply.get("pong") is True

        # Test 2: Unauthorized with wrong token
        client_wrong = DaemonClient(host=host, port=port, token="wrong_token")
        reply = client_wrong.send_command("ping")
        assert reply["success"] is False
        assert "unauthorized" in reply.get("error", "").lower()

        # Test 3: Unauthorized with no token
        client_none = DaemonClient(host=host, port=port, token=None)
        reply = client_none.send_command("ping")
        assert reply["success"] is False
        assert "unauthorized" in reply.get("error", "").lower()

    finally:
        # Shutdown cleanly via Unix socket (unauthenticated)
        try:
            DaemonClient(sp).send_command("shutdown")
        except Exception:
            pass
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()
        if os.path.exists(sp):
            os.remove(sp)


def test_rust_default_mac():
    # Locate the compiled Rust binary
    repo_root = Path(__file__).parent.parent
    bin_path = repo_root / "native-port" / "divoomd" / "target" / "debug" / "divoomd"
    if not bin_path.exists():
        bin_path = repo_root / "native-port" / "divoomd" / "target" / "release" / "divoomd"
    if not bin_path.exists():
        pytest.skip(f"Rust binary not found at {bin_path}. Run cargo build first.")

    sp = f"/tmp/divoomd_parity_mac_{os.getpid()}.sock"
    if os.path.exists(sp):
        os.remove(sp)

    default_mac = "AA:BB:CC:DD:EE:FF"

    # Spawn divoomd with a default MAC address configured
    proc = subprocess.Popen(
        [str(bin_path), "--socket", sp, "--mac", default_mac],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # Wait for the Unix socket to be bound
    bound = False
    for _ in range(50):
        if os.path.exists(sp):
            bound = True
            break
        time.sleep(0.05)

    if not bound:
        proc.kill()
        stdout, stderr = proc.communicate(timeout=1.0)
        pytest.fail(f"Rust daemon failed to bind. stdout: {stdout}, stderr: {stderr}")

    try:
        client = DaemonClient(sp)
        reply = client.send_command("device_status")
        assert reply["success"] is True
        assert reply.get("mac") == default_mac
        assert reply.get("connected") is False
        assert reply.get("connection_state") == "disconnected"

    finally:
        try:
            DaemonClient(sp).send_command("shutdown")
        except Exception:
            pass
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()
        if os.path.exists(sp):
            os.remove(sp)


def test_rust_spp_connect_failure_integration(rust_daemon_ctx):
    client = rust_daemon_ctx
    # Attempting to connect to a dummy MAC with use_ios_le_protocol=False
    # should trigger the SppTransport path, spawning spp_bridge.py.
    # It will fail (due to no such device) and return an SPP-specific connection error.
    reply = client.connect_device(
        mac="11:22:33:44:55:66",
        use_ios_le_protocol=False
    )
    assert reply["success"] is False
    # The error message should indicate SPP connection failure
    assert "spp" in reply.get("error", "").lower()


def test_rust_hardware_parity(request, rust_daemon_ctx):
    if not request.config.getoption("--run-hardware"):
        pytest.skip("Requires --run-hardware flag")

    client = rust_daemon_ctx

    # 1. Scan for Divoom devices via the Rust daemon
    reply = client.scan(timeout=8.0)
    assert reply["success"] is True
    devices = reply.get("devices", [])
    if not devices:
        pytest.skip("No physical Divoom devices found nearby")

    dev = devices[0]
    mac = dev["address"]
    name = dev["name"]
    print(f"\n[Hardware Test] Discovered device: {name} ({mac})")

    # 2. Connect to the device via Rust daemon
    reply = client.connect_device(mac=mac)
    assert reply["success"] is True
    assert reply["connected"] is True

    # 3. Query status / read-back brightness
    reply = client.send_command("device_status")
    assert reply["success"] is True
    assert reply["connected"] is True
    assert reply["mac"] == mac

    # Read current brightness
    reply = client.send_command("device_call", {
        "method": "display.get_brightness"
    })
    assert reply["success"] is True
    orig_brightness = reply["result"]
    assert isinstance(orig_brightness, int)

    # 4. Modify state (Set brightness to 40)
    reply = client.send_command("device_call", {
        "method": "display.set_brightness",
        "args": [40]
    })
    assert reply["success"] is True

    # Verify new brightness
    reply = client.send_command("device_call", {
        "method": "display.get_brightness"
    })
    assert reply["success"] is True
    assert reply["result"] == 40

    # Restore original brightness
    reply = client.send_command("device_call", {
        "method": "display.set_brightness",
        "args": [orig_brightness]
    })
    assert reply["success"] is True

    # 5. Disconnect
    reply = client.disconnect_device()
    assert reply["success"] is True


def test_rust_cloud_auth_endpoints(rust_daemon_ctx):
    client = rust_daemon_ctx
    
    # 1. Query cached credentials (should succeed)
    reply = client.send_command("get_cached_credentials")
    assert reply["success"] is True
    assert "credentials" in reply

    # 2. Query credentials (which performs guest login fallback if cache is empty/invalid)
    reply = client.send_command("get_credentials", {"force_refresh": False})
    assert reply["success"] is True
    assert "token" in reply
    assert "user_id" in reply
    assert "utc" in reply



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

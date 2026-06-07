"""R20 — the daemon runs on Linux: notification monitoring is macOS-only, so on
other platforms it degrades to a clean 'unsupported/idle' state instead of an
error, while device control + the network server keep working."""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from divoom_daemon import daemon as daemon_mod
from divoom_daemon.daemon import DivoomDaemon, STATE_IDLE, STATE_ERROR


def test_start_notifications_unsupported_on_linux(monkeypatch):
    monkeypatch.setattr(daemon_mod.sys, "platform", "linux")
    d = DivoomDaemon(socket_path="/tmp/divoom_plat_test.sock")  # monitor=None
    reply = d._cmd_start()
    assert reply["success"] is True
    assert reply.get("unsupported") is True
    assert reply["state"] == STATE_IDLE
    assert d._error is None  # not an error state


def test_start_notifications_errors_only_with_a_real_mac_monitor(monkeypatch):
    """A non-darwin platform must never even build the macOS monitor when none is
    injected (so no AppKit / DB access is attempted)."""
    monkeypatch.setattr(daemon_mod.sys, "platform", "linux")
    d = DivoomDaemon(socket_path="/tmp/divoom_plat_test2.sock")
    d._cmd_start()
    assert d._monitor is None  # never lazily constructed on Linux
    assert d._state() == STATE_IDLE
    assert d._state() != STATE_ERROR

"""
Tests for divoom_gui.mcp_control — the GUI's MCP server subprocess controller.

Coverage target: lifecycle (start/stop/is_running), the already-running guard,
spawn-failure envelopes (FileNotFoundError / OSError), SIGTERM->SIGKILL
escalation in stop(), log-tail reading in status() (including its OSError
envelope and the stale-log gate), and the process-level singleton.

All ``subprocess.Popen`` calls are mocked — this file must never spawn a real
subprocess. The MCP server is a long-lived stdio process (see
tests/test_mcp_server.py for the no-pipe-stdio guard it needs); accidentally
spawning a real one here would hang the test suite.
"""
from __future__ import annotations

import signal
import subprocess
import sys
from unittest.mock import MagicMock, patch

from divoom_gui.mcp_control import MCPController


def _fake_popen(pid: int = 4242, poll_return=None) -> MagicMock:
    """Build a MagicMock standing in for a subprocess.Popen instance."""
    proc = MagicMock(spec=subprocess.Popen)
    proc.pid = pid
    proc.poll.return_value = poll_return
    proc.wait.return_value = 0
    return proc


# ── is_running() ──────────────────────────────────────────────────────


def test_is_running_false_when_never_started(tmp_path) -> None:
    ctl = MCPController(log_path=tmp_path / "x.log")
    assert ctl.is_running() is False


def test_is_running_true_while_process_alive(tmp_path) -> None:
    ctl = MCPController(log_path=tmp_path / "x.log")
    ctl._proc = _fake_popen(poll_return=None)
    assert ctl.is_running() is True


def test_is_running_false_and_clears_state_after_exit(tmp_path) -> None:
    ctl = MCPController(log_path=tmp_path / "x.log")
    ctl._proc = _fake_popen(poll_return=1)  # exited with code 1
    ctl._started_at = 123.0
    ctl._mac = "AA:BB:CC:DD:EE:FF"
    assert ctl.is_running() is False
    assert ctl._proc is None
    assert ctl._started_at is None
    assert ctl._mac is None


# ── start() ────────────────────────────────────────────────────────────


def test_start_already_running_is_noop(tmp_path) -> None:
    ctl = MCPController(log_path=tmp_path / "x.log")
    ctl._proc = _fake_popen(poll_return=None)
    with patch("divoom_gui.mcp_control.subprocess.Popen") as popen:
        status = ctl.start(mac="11:22:33:44:55:66")
    popen.assert_not_called()
    assert status.running is True


def test_start_spawns_with_mac_and_tracks_state(tmp_path) -> None:
    log_path = tmp_path / "sub" / "mcp-server.log"
    ctl = MCPController(log_path=log_path)
    fake_proc = _fake_popen(pid=999)
    with patch("divoom_gui.mcp_control.subprocess.Popen", return_value=fake_proc) as popen:
        status = ctl.start(mac="11:22:33:44:55:66", python="/usr/bin/python3")

    assert status.running is True
    assert status.pid == 999
    assert status.mac == "11:22:33:44:55:66"
    assert ctl._started_this_session is True

    args, kwargs = popen.call_args
    cmd = args[0]
    assert cmd == ["/usr/bin/python3", "-m", "divoom_lib.cli", "mcp-server",
                   "--mac", "11:22:33:44:55:66"]
    assert kwargs["stdin"] == subprocess.DEVNULL
    assert kwargs["start_new_session"] is True
    assert kwargs["env"]["PYTHONUNBUFFERED"] == "1"
    # stdout and stderr point at the same log file handle.
    assert kwargs["stdout"] is kwargs["stderr"]
    assert log_path.parent.is_dir()


def test_start_without_mac_omits_mac_flag(tmp_path) -> None:
    ctl = MCPController(log_path=tmp_path / "x.log")
    fake_proc = _fake_popen()
    with patch("divoom_gui.mcp_control.subprocess.Popen", return_value=fake_proc) as popen:
        status = ctl.start()
    cmd = popen.call_args[0][0]
    assert "--mac" not in cmd
    assert cmd[1:] == ["-m", "divoom_lib.cli", "mcp-server"]
    assert status.mac is None


def test_start_uses_sys_executable_by_default(tmp_path) -> None:
    ctl = MCPController(log_path=tmp_path / "x.log")
    fake_proc = _fake_popen()
    with patch("divoom_gui.mcp_control.subprocess.Popen", return_value=fake_proc) as popen:
        ctl.start()
    assert popen.call_args[0][0][0] == sys.executable


def test_start_truncates_existing_log(tmp_path) -> None:
    """Each start() gets a self-contained log — old content must not survive,
    or the GUI card would mix a fresh run with a stale crash trace."""
    log_path = tmp_path / "mcp-server.log"
    log_path.write_text("stale crash from a previous session\n")
    ctl = MCPController(log_path=log_path)
    fake_proc = _fake_popen()
    with patch("divoom_gui.mcp_control.subprocess.Popen", return_value=fake_proc):
        ctl.start()
    assert log_path.read_bytes() == b""


def test_start_file_not_found_returns_error_status(tmp_path) -> None:
    ctl = MCPController(log_path=tmp_path / "x.log")
    with patch("divoom_gui.mcp_control.subprocess.Popen",
               side_effect=FileNotFoundError("nope")):
        status = ctl.start()
    assert status.running is False
    assert status.error is not None
    assert "python executable not found" in status.error
    assert ctl._proc is None


def test_start_oserror_returns_error_status(tmp_path) -> None:
    ctl = MCPController(log_path=tmp_path / "x.log")
    with patch("divoom_gui.mcp_control.subprocess.Popen", side_effect=OSError("boom")):
        status = ctl.start()
    assert status.running is False
    assert status.error is not None
    assert "failed to spawn MCP server" in status.error


# ── stop() ─────────────────────────────────────────────────────────────


def test_stop_when_not_running_is_noop(tmp_path) -> None:
    ctl = MCPController(log_path=tmp_path / "x.log")
    status = ctl.stop()
    assert status.running is False


def test_stop_sends_sigterm_and_clears_state(tmp_path) -> None:
    ctl = MCPController(log_path=tmp_path / "x.log")
    fake_proc = _fake_popen(pid=555, poll_return=None)
    ctl._proc = fake_proc
    ctl._started_at = 1.0
    ctl._mac = "AA"
    ctl._started_this_session = True
    with patch("divoom_gui.mcp_control.os.killpg") as killpg, \
         patch("divoom_gui.mcp_control.os.getpgid", return_value=555):
        status = ctl.stop()
    killpg.assert_called_once_with(555, signal.SIGTERM)
    fake_proc.wait.assert_called_once()
    assert ctl._proc is None
    assert ctl._started_at is None
    assert ctl._mac is None
    assert ctl._started_this_session is False
    assert status.running is False


def test_stop_escalates_to_sigkill_on_timeout(tmp_path) -> None:
    ctl = MCPController(log_path=tmp_path / "x.log")
    fake_proc = _fake_popen(pid=777, poll_return=None)
    fake_proc.wait.side_effect = [subprocess.TimeoutExpired(cmd="x", timeout=3.0), None]
    ctl._proc = fake_proc
    with patch("divoom_gui.mcp_control.os.killpg") as killpg, \
         patch("divoom_gui.mcp_control.os.getpgid", return_value=777):
        ctl.stop()
    assert killpg.call_count == 2
    killpg.assert_any_call(777, signal.SIGTERM)
    killpg.assert_any_call(777, signal.SIGKILL)


def test_stop_second_wait_also_times_out_is_swallowed(tmp_path) -> None:
    """Even if the process refuses to die after SIGKILL, stop() must not raise."""
    ctl = MCPController(log_path=tmp_path / "x.log")
    fake_proc = _fake_popen(pid=778, poll_return=None)
    fake_proc.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="x", timeout=3.0),
        subprocess.TimeoutExpired(cmd="x", timeout=1.0),
    ]
    ctl._proc = fake_proc
    with patch("divoom_gui.mcp_control.os.killpg"), \
         patch("divoom_gui.mcp_control.os.getpgid", return_value=778):
        status = ctl.stop()
    assert status.running is False


def test_stop_process_already_gone_swallows_lookup_error(tmp_path) -> None:
    """getpgid()/killpg() raising ProcessLookupError (process already reaped
    by the OS) must be swallowed, not propagated."""
    ctl = MCPController(log_path=tmp_path / "x.log")
    fake_proc = _fake_popen(pid=888, poll_return=None)
    ctl._proc = fake_proc
    with patch("divoom_gui.mcp_control.os.getpgid", side_effect=ProcessLookupError()):
        status = ctl.stop()
    assert status.running is False


# ── status() log tail ───────────────────────────────────────────────────


def test_status_hides_log_when_not_started_this_session(tmp_path) -> None:
    log_path = tmp_path / "mcp-server.log"
    log_path.write_text("line1\nline2\n")
    ctl = MCPController(log_path=log_path)
    status = ctl.status()
    assert status.last_log_lines == []


def test_status_tails_log_when_started_this_session(tmp_path) -> None:
    log_path = tmp_path / "mcp-server.log"
    lines = [f"line {i}" for i in range(30)]
    log_path.write_text("\n".join(lines) + "\n")
    ctl = MCPController(log_path=log_path)
    ctl._started_this_session = True
    status = ctl.status()
    assert status.last_log_lines == lines[-MCPController.LOG_TAIL_LINES:]


def test_status_missing_log_file_returns_empty_lines(tmp_path) -> None:
    ctl = MCPController(log_path=tmp_path / "does-not-exist.log")
    ctl._started_this_session = True
    status = ctl.status()
    assert status.last_log_lines == []


def test_status_oserror_reading_log_returns_error_status(tmp_path) -> None:
    log_path = tmp_path / "mcp-server.log"
    log_path.write_text("hello\n")
    ctl = MCPController(log_path=log_path)
    ctl._started_this_session = True
    ctl._proc = _fake_popen(pid=42, poll_return=None)
    ctl._started_at = 5.0
    ctl._mac = "AA"
    with patch("builtins.open", side_effect=OSError("disk gone")):
        status = ctl.status()
    assert status.error is not None
    assert "failed to read log" in status.error
    assert status.pid == 42
    assert status.mac == "AA"
    assert status.log_path == str(log_path)


# ── singleton ────────────────────────────────────────────────────────────


def test_instance_returns_singleton() -> None:
    MCPController._instance = None
    try:
        a = MCPController.instance()
        b = MCPController.instance()
        assert a is b
        assert isinstance(a, MCPController)
    finally:
        MCPController._instance = None

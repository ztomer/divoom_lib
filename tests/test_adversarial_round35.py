"""R53 round 35 — persona pass (Carmack CLEAN; Bob/Linus/Hashimoto each 1 bug).

- ensure_connected caught BaseException, swallowing asyncio.CancelledError → it
  treated a cancellation (teardown) as a connect failure and kept retrying,
  defeating cooperative cancellation. Now it re-raises CancelledError.
- The iOS-LE notification parser cleared _expected_response_command on the generic
  0x33 ACK (the FIRST of a two-frame reply), so the real data frame was dropped and
  read-backs timed out. Now the ACK is queued WITHOUT clearing the scalar.
- The daemon had no single-instance guard → a double-spawn (GUI + MCP server)
  clobbered the socket and orphaned the BLE owner. Now a flock loser exits cleanly.
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import divoom_lib.divoom  # noqa: F401  - resolve import cycle


# ── Linus: ensure_connected re-raises cancellation ──────────────────────────

def test_ensure_connected_reraises_cancellation():
    from divoom_lib.ble_connection import ensure_connected

    class _Dev:
        is_connected = False

        async def connect(self):
            raise asyncio.CancelledError()

        async def disconnect(self):
            pass

    async def run():
        try:
            await ensure_connected(_Dev(), attempts=3, attempt_timeout=1.0)
        except asyncio.CancelledError:
            return "cancelled"
        return "swallowed"

    assert asyncio.run(run()) == "cancelled", "CancelledError must propagate, not be retried"


# ── Uncle Bob: iOS-LE generic ACK must not clear the response scalar ─────────

def test_ios_le_generic_ack_keeps_scalar_then_data_frame_clears_it():
    from divoom_lib.ble_notify import BleNotifyMixin
    from divoom_lib import framing, models

    expected = next(iter(models.GENERIC_ACK_COMMANDS))  # a command that two-frames

    o = object.__new__(BleNotifyMixin)
    o._expected_response_command = expected
    o.notification_queue = asyncio.Queue()
    o._listen_commands = ()
    o.use_ios_le_protocol = True
    o.logger = logging.getLogger("t_ios_le")

    ack = framing.encode_ios_le_payload([models.GENERIC_ACK_COMMAND_ID, 0x00])
    o._handle_ios_le_notification(bytes(ack))
    assert o._expected_response_command == expected, "the 0x33 ACK must NOT clear the scalar"

    data = framing.encode_ios_le_payload([expected, 0xAB, 0xCD])
    o._handle_ios_le_notification(bytes(data))
    assert o._expected_response_command is None, "the real data frame clears the scalar"
    assert o.notification_queue.qsize() == 2, "both the ack and the data frame are queued"


# ── Hashimoto: daemon single-instance flock guard ───────────────────────────

def test_daemon_instance_lock_rejects_second(tmp_path):
    from divoom_daemon.daemon import DivoomDaemon

    sp = str(tmp_path / "divoom.sock")
    d1 = object.__new__(DivoomDaemon)
    d1.socket_path = sp
    d2 = object.__new__(DivoomDaemon)
    d2.socket_path = sp

    assert d1._acquire_instance_lock() is True, "first daemon acquires the lock"
    assert d2._acquire_instance_lock() is False, "second daemon must lose the race, not clobber"

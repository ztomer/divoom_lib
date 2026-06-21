"""R53.28: _drain_cmd_queue routes a barrier through the command queue so an
in-flight push item (submitted by a just-cancelled poller) settles before the
device is released — closing the queue-item resurrection window.
"""
import asyncio
import sys
import threading
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from divoom_daemon.command_queue import CommandQueue
from divoom_daemon.owner_live import OwnerLiveMixin


def _real_loop():
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    return loop


def test_drain_is_noop_without_a_queue():
    o = OwnerLiveMixin.__new__(OwnerLiveMixin)
    # no _cmd_queue attribute → must not raise
    loop = _real_loop()
    asyncio.run_coroutine_threadsafe(o._drain_cmd_queue(), loop).result(timeout=2)


def test_drain_waits_for_an_inflight_item():
    """An item submitted just before the drain must have FINISHED when the drain
    returns (the barrier is FIFO-after it) — this is what lets _release pop the
    device only after a racing push's `_live_devices[mac] = dev` has landed."""
    loop = _real_loop()
    q = CommandQueue(loop)
    q.start()
    o = OwnerLiveMixin.__new__(OwnerLiveMixin)
    o._cmd_queue = q
    o._live_devices = {}

    async def _slow_push():
        await asyncio.sleep(0.15)
        o._live_devices["AA"] = "dev"          # the racing orphan write

    async def _enqueue_then_drain():
        task = asyncio.ensure_future(q.submit_async(_slow_push()))
        await asyncio.sleep(0)                  # let it enqueue ahead of the barrier
        await o._drain_cmd_queue()
        await task

    try:
        asyncio.run_coroutine_threadsafe(_enqueue_then_drain(), loop).result(timeout=3)
        assert o._live_devices.get("AA") == "dev", "drain returned before the in-flight push finished"
    finally:
        q.stop()

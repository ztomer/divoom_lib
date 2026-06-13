"""Device-loop plumbing for the daemon owner.

A dedicated asyncio loop (one background thread) keeps the BLE connection alive
across RPC calls. Most device access goes through the command queue
(`_run_device`) for FIFO + exclusive-mode serialization; operations that touch
the central manager rather than the connected peripheral (a BLE scan) use
`_run_on_loop` to run directly on the loop WITHOUT serializing behind device I/O.

Split out of `device_owner.py` to keep that file under the 500-LOC cap.
"""
from __future__ import annotations

import asyncio
import threading


class OwnerLoopMixin:
    def _device_loop(self):
        """A dedicated asyncio loop so the BLE connection persists across calls."""
        with self._device_lock:
            if self._loop is not None:
                return self._loop
            from divoom_daemon.command_queue import CommandQueue
            loop = asyncio.new_event_loop()
            ready = threading.Event()

            def _run():
                asyncio.set_event_loop(loop)
                ready.set()
                loop.run_forever()

            self._loop_thread = threading.Thread(target=_run, daemon=True, name="device-loop")
            self._loop_thread.start()
            ready.wait(2.0)
            self._loop = loop
            # G3: auto-release a dead client's exclusive session (30s idle) so one
            # crashed push can't wedge the device forever.
            self._cmd_queue = CommandQueue(loop, exclusive_timeout=30.0)
            self._cmd_queue.start()
            return self._loop

    def _run_device(self, coro, *, token=None):
        """Run a coroutine through the command queue, blocking for the result.
        All device access goes through the queue (FIFO + exclusive-mode); it's
        the only path that touches the device loop. submit() is thread-safe and
        returns a concurrent.futures.Future — we block on .result()."""
        if self._cmd_queue is None:
            self._device_loop()
        return self._cmd_queue.submit(coro, token=token).result()

    def _run_on_loop(self, coro):
        """Run a coroutine directly on the device loop, BYPASSING the command
        queue. For ops that don't touch the connected peripheral (a BLE scan uses
        the central manager) so a long scan doesn't block — and freeze — device
        I/O and live-widget pushes queued behind it (G2)."""
        if self._loop is None:
            self._device_loop()
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

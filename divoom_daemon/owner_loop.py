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
import concurrent.futures
import logging
import threading

logger = logging.getLogger("divoom_daemon")

# R53: backstops so a wedged BLE op can never block a daemon RPC thread (and thus
# a socket handler) forever. These are generous — the slowest legitimate blocking
# device op (custom-art push: ~12 CDN downloads + multi-slot write) stays well
# under them, while the underlying bleak connect/notify/write calls are themselves
# bounded in ble_transport. hot_update is fire-and-forget (submit() with no
# .result()), so it is unaffected by the per-call backstop.
_DEVICE_ITEM_TIMEOUT = 240.0   # queue rejects an op left waiting behind a stuck op
_DEVICE_RESULT_TIMEOUT = 270.0  # caller-side backstop for a wedged RUNNING op
_SCAN_RESULT_TIMEOUT = 90.0     # BLE scan (discover ~10–60s)


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
                try:
                    loop.run_forever()
                finally:
                    # Close the loop once its thread exits (stop() signals
                    # loop.stop). Without this the loop's selector/fds leaked on
                    # every stop→restart cycle in a long-lived (keep-alive) daemon.
                    # Runs in the dying loop thread AFTER run_forever returns, so
                    # it can't race stop()'s sync teardown.
                    try:
                        loop.close()
                    except Exception:
                        pass

            self._loop_thread = threading.Thread(target=_run, daemon=True, name="device-loop")
            self._loop_thread.start()
            ready.wait(2.0)
            self._loop = loop
            # G3: auto-release a dead client's exclusive session (30s idle) so one
            # crashed push can't wedge the device forever. R53: item_timeout
            # rejects an op left waiting behind a stuck op instead of letting the
            # caller block forever.
            self._cmd_queue = CommandQueue(
                loop, item_timeout=_DEVICE_ITEM_TIMEOUT, exclusive_timeout=30.0)
            self._cmd_queue.start()
            return self._loop

    def _run_device(self, coro, *, token=None):
        """Run a coroutine through the command queue, blocking for the result.
        All device access goes through the queue (FIFO + exclusive-mode); it's
        the only path that touches the device loop. submit() is thread-safe and
        returns a concurrent.futures.Future — we block on .result()."""
        if self._cmd_queue is None:
            self._device_loop()
        try:
            return self._cmd_queue.submit(coro, token=token).result(
                timeout=_DEVICE_RESULT_TIMEOUT)
        except concurrent.futures.TimeoutError:
            # The worker is wedged on a RUNNING op (item_timeout only rejects
            # WAITING items). Don't hang the RPC thread — surface a clean error.
            logger.error("device op exceeded %.0fs backstop; surfacing timeout",
                         _DEVICE_RESULT_TIMEOUT)
            raise TimeoutError(
                f"device operation timed out after {_DEVICE_RESULT_TIMEOUT:.0f}s")

    def _run_on_loop(self, coro):
        """Run a coroutine directly on the device loop, BYPASSING the command
        queue. For ops that don't touch the connected peripheral (a BLE scan uses
        the central manager) so a long scan doesn't block — and freeze — device
        I/O and live-widget pushes queued behind it (G2)."""
        if self._loop is None:
            self._device_loop()
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=_SCAN_RESULT_TIMEOUT)
        except concurrent.futures.TimeoutError:
            logger.error("on-loop op (scan) exceeded %.0fs backstop", _SCAN_RESULT_TIMEOUT)
            future.cancel()
            raise TimeoutError(
                f"scan/on-loop operation timed out after {_SCAN_RESULT_TIMEOUT:.0f}s")

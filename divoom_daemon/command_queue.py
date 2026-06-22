"""FIFO command queue for serializing device access.

The daemon's single-threaded asyncio event loop already serialises
coroutines, but external callers submit from multiple threads via
``asyncio.run_coroutine_threadsafe`` — the queue provides an explicit
ordering layer with exclusive-mode support for multi-phase operations.
"""

from __future__ import annotations

import asyncio
import collections
import concurrent.futures
import logging
import time
from typing import Any

logger = logging.getLogger("divoom_daemon.command_queue")

_UNSET = object()  # sentinel for "use the queue-wide default"


class QueueFull(Exception):
    """Raised when ``submit()`` is called on a queue at capacity."""
    pass


class QueueStopped(Exception):
    """Raised when ``submit()`` is called on a stopped queue."""
    pass


class _QueueItem:
    __slots__ = ("coro", "future", "token", "enqueued_at", "timeout")

    def __init__(self, coro, future: concurrent.futures.Future,
                 token: Any, enqueued_at: float,
                 timeout: float | None) -> None:
        self.coro = coro
        self.future = future
        self.token = token
        self.enqueued_at = enqueued_at
        self.timeout = timeout


class _Ring:
    """Pre-allocated ring buffer with O(1) append/popleft.

    When *maxsize* is 0 the ring is backed by a list (dynamic growth);
    otherwise the backing array is pre-allocated and never grows.
    """

    def __init__(self, maxsize: int = 0) -> None:
        capacity = maxsize if maxsize > 0 else 0
        self._fixed = maxsize > 0
        self._data: list = [None] * capacity if capacity else []
        self._head = 0
        self._tail = 0
        self._size = 0
        self._maxsize = maxsize

    # ── public API ──────────────────────────────────────────────────────

    def append(self, item: _QueueItem) -> None:
        if self._fixed and self._size >= self._maxsize:
            raise QueueFull(f"queue at capacity ({self._maxsize})")
        if self._fixed:
            if self._size == len(self._data):
                # Redundant safety — should never happen with size < maxsize
                raise QueueFull(f"queue at capacity ({self._maxsize})")
            self._data[self._tail] = item
            self._tail = (self._tail + 1) % len(self._data)
        else:
            self._data.append(item)
        self._size += 1

    def popleft(self) -> _QueueItem | None:
        if self._size == 0:
            return None
        item: _QueueItem
        if self._fixed:
            item = self._data[self._head]
            self._data[self._head] = None
            self._head = (self._head + 1) % len(self._data)
        else:
            item = self._data.pop(0)
        self._size -= 1
        return item

    def pop(self, idx: int) -> _QueueItem:
        """Pop arbitrary item by logical index.  O(n) — used by exclusive mode."""
        if idx < 0 or idx >= self._size:
            raise IndexError(idx)
        if self._fixed:
            return self._pop_fixed(idx)
        item = self._data.pop(idx)
        self._size -= 1
        return item

    def _pop_fixed(self, idx: int) -> _QueueItem:
        phys = (self._head + idx) % len(self._data)
        item = self._data[phys]
        # Close the gap by shifting elements from head to phys-1 forward.
        # This is O(n) in the worst case but only used by exclusive mode.
        while phys != self._head:
            prev = (phys - 1) % len(self._data)
            self._data[phys] = self._data[prev]
            phys = prev
        self._data[self._head] = None
        self._head = (self._head + 1) % len(self._data)
        self._size -= 1
        return item

    def __len__(self) -> int:
        return self._size

    def __getitem__(self, idx: int) -> _QueueItem:
        if idx < 0 or idx >= self._size:
            raise IndexError(idx)
        if self._fixed:
            return self._data[(self._head + idx) % len(self._data)]
        return self._data[idx]

    def __iter__(self):
        if self._fixed:
            for i in range(self._size):
                yield self._data[(self._head + i) % len(self._data)]
        else:
            yield from self._data

    def clear(self) -> None:
        if self._fixed:
            n = len(self._data)
            self._data = [None] * n
            self._head = 0
            self._tail = 0
        else:
            self._data.clear()
        self._size = 0

    def as_list(self) -> list:
        if self._fixed:
            return [self[i] for i in range(self._size)]
        return list(self._data)


class CommandQueue:
    """Thread-safe FIFO command queue with optional exclusive-mode locking.

    Uses a pre-allocated ring buffer (when ``maxsize > 0``) so the queue
    never allocates or frees memory during normal FIFO operation.

    Parameters
    ----------
    loop
        The event loop the worker runs on (typically a dedicated background
        thread's loop).
    maxsize
        Maximum number of pending items (0 = unbounded via dynamic list).
        When the queue is full ``submit()`` raises ``QueueFull``.  The
        currently-executing item does NOT count toward this limit.
    item_timeout
        Maximum seconds an item may wait in the queue before being
        automatically rejected with ``TimeoutError``.  ``None`` = no limit.
        Items are expired at dequeue time (not via background timers), so
        a blocked worker delays expiry until it finishes the current item.

    Usage::

        q = CommandQueue(loop, maxsize=64, item_timeout=30.0)
        q.start()
        q.submit(some())
        await q.submit_async(some())
        async with q.exclusive(token):
            await q.submit_async(step1(), token=token)
        q.stop()
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, *,
                 maxsize: int = 0, item_timeout: float | None = None,
                 exclusive_timeout: float | None = None) -> None:
        self._loop = loop
        self._maxsize = maxsize
        self._item_timeout = item_timeout
        # G3: max seconds an exclusive session may go WITHOUT dequeuing one of its
        # own items before it's force-released. A client that dies between
        # exclusive_start and exclusive_end would otherwise leave the owner token
        # set forever — and _dequeue then only ever dispatches that token, so
        # every other caller (and every future command) hangs/times out until the
        # daemon restarts. None = no auto-release (legacy behaviour).
        self._exclusive_timeout = exclusive_timeout
        self._exclusive_deadline: float | None = None
        self._pending = _Ring(maxsize)
        self._cond = asyncio.Condition()
        self._worker: asyncio.Task[None] | None = None
        self._exclusive_owner: Any = None
        self._stopped = False

    # ── lifecycle (thread-safe: calls routed through self._loop) ─────────

    def start(self) -> None:
        """Start the worker task on the queue's loop.  Thread-safe, blocks
        until the worker yields its first wait."""
        if self._worker is not None:
            return
        self._stopped = False
        fut = asyncio.run_coroutine_threadsafe(
            self._start_worker(), self._loop
        )
        fut.result(timeout=10)

    async def _start_worker(self) -> None:
        async def _run() -> None:
            while not self._stopped:
                item = await self._dequeue()
                if item is None:
                    break
                if item.future.cancelled():
                    item.coro.close()
                    continue
                try:
                    result = await item.coro
                    if not item.future.cancelled():
                        item.future.set_result(result)
                except BaseException as exc:
                    if not item.future.cancelled():
                        item.future.set_exception(exc)
                    if isinstance(exc, asyncio.CancelledError):
                        raise
                # Re-arm the exclusive deadline on COMPLETION, not just at dequeue
                # (_dequeue arms when it hands out an owner item). A single
                # long-running exclusive item — or a gap before the owner submits
                # its NEXT item — would otherwise let the deadline lapse during the
                # session's own work, so the next _dequeue force-releases a session
                # that's actively progressing. (CancelledError re-raised above, so
                # we don't touch the lock while the worker is being torn down.)
                if self._exclusive_owner is not None:
                    async with self._cond:
                        self._arm_exclusive_deadline()

        self._worker = asyncio.create_task(_run())
        await asyncio.sleep(0)

    def stop(self) -> None:
        """Stop the worker and resolve pending futures.  Thread-safe."""
        if self._worker is not None:
            asyncio.run_coroutine_threadsafe(
                self._cancel_worker(), self._loop
            ).result(timeout=10)
            self._worker = None

    async def _cancel_worker(self) -> None:
        """Drain pending callbacks, mark stopped, resolve remaining items,
        then cancel and join the worker."""
        await asyncio.sleep(0)
        async with self._cond:
            self._stopped = True
            remaining = self._pending.as_list()
            self._pending.clear()
            self._cond.notify_all()
        for item in remaining:
            if not item.future.cancelled():
                item.coro.close()  # prevent RuntimeWarning
                item.future.set_exception(RuntimeError("queue stopped"))
        if self._worker is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._worker), timeout=2)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                if self._worker is not None and not self._worker.done():
                    self._worker.cancel()
                    try:
                        await self._worker
                    except asyncio.CancelledError:
                        pass

    # ── submission (thread-safe) ─────────────────────────────────────────

    def submit(self, coro, token: Any = None,
               timeout: float | None | object = _UNSET) -> concurrent.futures.Future:
        """Submit a coroutine.  Thread-safe — call from any thread.

        Parameters
        ----------
        timeout
            If provided (seconds), the future raises ``TimeoutError`` if
            the item isn't dequeued within this window.  ``None`` disables
            the timeout for this item.  Omit to use the queue-wide
            ``item_timeout``.
        """
        if self._stopped:
            coro.close()  # prevent RuntimeWarning: coroutine was never awaited
            raise QueueStopped("queue is stopped")
        fut: concurrent.futures.Future = concurrent.futures.Future()
        done = asyncio.run_coroutine_threadsafe(
            self._add(coro, fut, token, timeout), self._loop
        )
        # Wait for _add to complete so sync callers see
        # QueueFull/QueueStopped raised from submit(), not on the future.
        try:
            done.result(timeout=10)
        except Exception:
            pass
        if fut.done():
            exc = fut.exception()
            if isinstance(exc, (QueueFull, QueueStopped)):
                raise exc
        return fut

    async def submit_async(self, coro, token: Any = None,
                           timeout: float | None | object = _UNSET) -> Any:
        """Submit and await from async code on any loop.

        When the caller is ALREADY running on the queue's own loop (e.g. a live
        job created on the device loop), we must NOT route through the sync
        ``submit()`` — it blocks the loop on ``run_coroutine_threadsafe(_add,
        self._loop).result()`` while ``_add`` can only run on that same, now
        blocked, loop → deadlock (the live-widget push hung forever, silently).
        On the device loop we enqueue with a direct ``await self._add(...)``."""
        try:
            on_queue_loop = asyncio.get_running_loop() is self._loop
        except RuntimeError:
            on_queue_loop = False

        if not on_queue_loop:
            return await asyncio.wrap_future(
                self.submit(coro, token=token, timeout=timeout))

        if self._stopped:
            coro.close()
            raise QueueStopped("queue is stopped")
        fut: concurrent.futures.Future = concurrent.futures.Future()
        await self._add(coro, fut, token, timeout)
        if fut.done():
            exc = fut.exception()
            if isinstance(exc, (QueueFull, QueueStopped)):
                raise exc
        return await asyncio.wrap_future(fut)

    async def _add(self, coro, fut: concurrent.futures.Future,
                   token: Any, per_item_timeout: float | None | object) -> None:
        async with self._cond:
            if self._stopped:
                coro.close()  # prevent RuntimeWarning
                fut.set_exception(QueueStopped("queue is stopped"))
                return
            try:
                effective = self._item_timeout if per_item_timeout is _UNSET else per_item_timeout
                self._pending.append(
                    _QueueItem(coro, fut, token,
                               enqueued_at=time.monotonic(),
                               timeout=effective)
                )
            except QueueFull:
                coro.close()  # prevent RuntimeWarning
                fut.set_exception(QueueFull(
                    f"queue at capacity ({self._maxsize})"
                ))
                return
            self._cond.notify()

    # ── exclusive mode ───────────────────────────────────────────────────

    async def acquire(self, token: Any) -> None:
        async with self._cond:
            # Reject a STEAL: if a different session already holds the exclusive
            # slot, don't silently overwrite it — that stranded the first owner's
            # queued items (they only dispatch while it's the owner) until the 30s
            # idle release, and let the thief run concurrently with the holder's
            # in-flight op (clobber). The same token re-acquiring is idempotent
            # (re-arms the deadline). G3's idle deadline still frees a dead holder
            # so this can't wedge forever.
            if self._exclusive_owner is not None and self._exclusive_owner != token:
                raise RuntimeError("device is exclusively held by another session")
            self._exclusive_owner = token
            self._arm_exclusive_deadline()
            self._cond.notify_all()

    async def release(self, token: Any) -> None:
        async with self._cond:
            if self._exclusive_owner == token:
                self._exclusive_owner = None
                self._exclusive_deadline = None
                self._cond.notify_all()

    def _arm_exclusive_deadline(self) -> None:
        """(Re)set the auto-release deadline for the current exclusive session.
        Called on acquire and whenever the owner makes progress (dequeues one of
        its items), so an actively-working session is never force-released."""
        if self._exclusive_timeout is not None and self._exclusive_owner is not None:
            self._exclusive_deadline = time.monotonic() + self._exclusive_timeout
        else:
            self._exclusive_deadline = None

    def exclusive(self, token: Any):
        return _ExclusiveCtx(self, token)

    # ── internal ─────────────────────────────────────────────────────────

    async def _dequeue(self) -> _QueueItem | None:
        """Return the next item, or ``None`` if the queue is stopped.

        Expired items (those whose *timeout* has elapsed) are rejected
        transparently — ``_dequeue`` skips them and moves to the next.
        """
        async with self._cond:
            while True:
                if self._stopped:
                    return None
                if not self._pending:
                    await self._cond.wait()
                    continue

                # Expire stale items from the front
                now = time.monotonic()
                while self._pending:
                    item = self._pending[0]
                    if item.timeout is not None and (now - item.enqueued_at) >= item.timeout:
                        self._pending.popleft()
                        if not item.future.cancelled():
                            item.coro.close()  # prevent RuntimeWarning
                            item.future.set_exception(TimeoutError(
                                f"item timed out after {item.timeout:.1f}s"
                            ))
                        continue
                    break

                if not self._pending:
                    await self._cond.wait()
                    continue

                if self._exclusive_owner is not None:
                    idx = self._find(self._exclusive_owner)
                    if idx is not None:
                        self._arm_exclusive_deadline()   # owner made progress
                        return self._pending.pop(idx)
                    # G3: no item for the owner. If the session has gone idle past
                    # its deadline, assume the client died and force-release so the
                    # rest of the queue can drain instead of hanging forever.
                    if self._exclusive_deadline is not None:
                        remaining = self._exclusive_deadline - time.monotonic()
                        if remaining <= 0:
                            logger.warning(
                                "exclusive session %r timed out (>%.0fs idle); "
                                "force-releasing", self._exclusive_owner,
                                self._exclusive_timeout)
                            self._exclusive_owner = None
                            self._exclusive_deadline = None
                            self._cond.notify_all()
                            continue
                        try:
                            await asyncio.wait_for(self._cond.wait(), timeout=remaining)
                        except asyncio.TimeoutError:
                            pass
                        continue
                    await self._cond.wait()
                    continue
                return self._pending.popleft()

    def _find(self, token: Any) -> int | None:
        for i in range(len(self._pending)):
            if self._pending[i].token == token:
                return i
        return None


class _ExclusiveCtx:
    def __init__(self, queue: CommandQueue, token: Any) -> None:
        self._queue = queue
        self._token = token

    async def __aenter__(self) -> CommandQueue:
        await self._queue.acquire(self._token)
        return self._queue

    async def __aexit__(self, *exc_info) -> None:
        await self._queue.release(self._token)

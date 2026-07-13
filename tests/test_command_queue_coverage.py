"""R61 coverage push: divoom_daemon.command_queue branches not exercised by
tests/test_command_queue.py (the black-box FIFO/exclusive-mode/timeout suite).

Two layers of gaps, closed with the seam-and-cover approach (pure-logic first,
then the concurrent boundary):

  * ``_Ring`` (the pre-allocated ring buffer) is a pure data structure — its
    edge cases (empty popleft, out-of-range pop/__getitem__, popping from the
    MIDDLE of a fixed ring so ``_pop_fixed`` actually shifts elements, direct
    iteration over a fixed ring, and the "should never happen" redundant
    capacity guard in ``append``) are tested directly, white-box, with no
    asyncio/threading involved at all.
  * ``CommandQueue``'s harder-to-reach races (a future cancelled between
    enqueue and dequeue, a future cancelled WHILE its coroutine is executing,
    submitting/adding directly on the queue's own loop while stopped or full,
    the exclusive-session idle-wait with no configured deadline, an item that
    expires after its future was already cancelled, and the worker/stop
    lifecycle no-ops) are driven against the real dedicated-loop-in-a-thread
    CommandQueue — matching the existing suite's fixtures — with a few
    additional white-box pokes at ``_pending``/``_cond`` where the only way to
    force a genuine race deterministically is to set up the invariant by hand.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import threading
import time

import pytest

from divoom_daemon.command_queue import (
    CommandQueue,
    QueueFull,
    QueueStopped,
    _QueueItem,
    _Ring,
)


# ── _Ring: pure data-structure edge cases ─────────────────────────────────


def test_ring_popleft_on_empty_returns_none():
    r = _Ring(maxsize=4)
    assert r.popleft() is None
    r2 = _Ring(maxsize=0)  # dynamic (list-backed) variant too
    assert r2.popleft() is None


def test_ring_pop_out_of_range_raises_index_error():
    r = _Ring(maxsize=4)
    r.append(_item("a"))
    with pytest.raises(IndexError):
        r.pop(-1)
    with pytest.raises(IndexError):
        r.pop(1)


def test_ring_getitem_out_of_range_raises_index_error():
    r = _Ring(maxsize=4)
    r.append(_item("a"))
    with pytest.raises(IndexError):
        r[-1]
    with pytest.raises(IndexError):
        r[1]


def test_ring_pop_from_middle_of_fixed_ring_shifts_elements():
    """Popping a non-head index on a FIXED ring drives ``_pop_fixed``, which
    closes the gap by shifting head..idx-1 forward (used by exclusive mode to
    pull an owner's item out from behind other pending items)."""
    r = _Ring(maxsize=4)
    for tag in ("a", "b", "c"):
        r.append(_item(tag))
    popped = r.pop(1)  # "b" — not the head
    assert popped.token == "b"
    assert [it.token for it in r.as_list()] == ["a", "c"]
    assert len(r) == 2
    # the ring must still be usable afterwards (head/tail bookkeeping intact)
    r.append(_item("d"))
    assert [it.token for it in r.as_list()] == ["a", "c", "d"]


def test_ring_pop_from_middle_with_wraparound():
    """Same as above but after the ring has wrapped (head != 0), so
    ``_pop_fixed``'s modular shift is genuinely exercised."""
    r = _Ring(maxsize=3)
    for tag in ("a", "b", "c"):
        r.append(_item(tag))
    r.popleft()  # drop "a" -> head advances to 1
    r.append(_item("d"))  # wraps into slot 0 -> tail wraps
    # ring logically holds b, c, d (physical layout wraps around)
    assert [it.token for it in r.as_list()] == ["b", "c", "d"]
    popped = r.pop(1)  # "c" — middle, with physical wraparound in play
    assert popped.token == "c"
    assert [it.token for it in r.as_list()] == ["b", "d"]


def test_ring_iter_over_fixed_ring():
    """Direct iteration (not via as_list/__getitem__) over a FIXED ring."""
    r = _Ring(maxsize=3)
    for tag in ("a", "b", "c"):
        r.append(_item(tag))
    r.popleft()
    r.append(_item("d"))  # force wraparound so __iter__'s modular indexing runs
    assert [it.token for it in r] == ["b", "c", "d"]


def test_ring_iter_over_dynamic_ring():
    """Direct iteration over the dynamic (list-backed, maxsize=0) variant —
    the ``else: yield from self._data`` branch of __iter__."""
    r = _Ring(maxsize=0)
    for tag in ("a", "b"):
        r.append(_item(tag))
    assert [it.token for it in r] == ["a", "b"]


def test_ring_append_redundant_capacity_guard():
    """Defensive/"should never happen" branch: append() has a redundant
    ``size == len(data)`` check even though the size>=maxsize check above it
    should always fire first. Force the invariant violation directly (white
    box) to prove the redundant guard still raises QueueFull rather than
    corrupting the ring, instead of leaving genuinely dead code untested."""
    r = _Ring(maxsize=3)
    r._data = r._data[:2]        # shrink the backing array below maxsize
    r._size = 2                  # ... but claim it's already "full" at that size
    with pytest.raises(QueueFull):
        r.append(_item("x"))


def _item(token):
    return _QueueItem(_noop_coro(), concurrent.futures.Future(), token,
                       enqueued_at=time.monotonic(), timeout=None)


async def _noop():
    return None


def _noop_coro():
    c = _noop()
    c.close()  # never awaited by these white-box _Ring tests — close to avoid warnings
    return c


# ── CommandQueue: harder-to-reach concurrent branches ─────────────────────


@pytest.fixture
def loop():
    l = asyncio.new_event_loop()
    t = threading.Thread(target=l.run_forever, daemon=True, name="cq-cov-loop")
    t.start()
    yield l
    l.call_soon_threadsafe(l.stop)
    t.join(timeout=3)
    l.close()


async def coro_for(value):
    return value


async def _record(history, value):
    history.append(value)


def test_worker_loop_exits_immediately_if_already_stopped(loop):
    """``_start_worker``'s inner ``while not self._stopped`` can be False on
    the very first check (a stop() racing in before the worker's first tick).
    Drive ``_start_worker`` directly with ``_stopped`` pre-set — ``start()``
    itself always resets ``_stopped`` to False, so this state is otherwise
    unreachable through the public API."""
    q = CommandQueue(loop)
    q._stopped = True
    fut = asyncio.run_coroutine_threadsafe(q._start_worker(), loop)
    fut.result(timeout=5)
    time.sleep(0.05)
    assert q._worker.done(), "the worker task must finish immediately, no iterations"
    q._stopped = False
    q.stop()


def test_stop_when_never_started_is_a_noop(loop):
    q = CommandQueue(loop)
    q.stop()  # no worker was ever created — must not raise


def test_cancel_worker_noop_when_no_worker_was_ever_started(loop):
    """``_cancel_worker``'s own ``if self._worker is not None`` guard (distinct
    from ``stop()``'s guard above) — reached when ``_cancel_worker`` runs
    without a worker task ever having been created."""
    q = CommandQueue(loop)
    done = asyncio.run_coroutine_threadsafe(q._cancel_worker(), loop)
    done.result(timeout=5)
    assert q._stopped is True


def test_worker_skips_item_whose_future_was_cancelled_before_dequeue(loop):
    """A future cancelled while still pending must be skipped (coro closed,
    never awaited) rather than executed or raising."""
    q = CommandQueue(loop)
    q.start()
    try:
        ran = []

        async def work():
            ran.append("x")

        busy = q.submit(asyncio.sleep(0.2))  # occupies the worker
        fut = q.submit(work())
        fut.cancel()
        busy.result(timeout=5)
        time.sleep(0.05)  # let the worker dequeue + skip the cancelled item
        assert ran == []
        assert fut.cancelled()
    finally:
        q.stop()


def test_result_not_set_when_future_cancelled_during_execution(loop):
    """A future cancelled WHILE its coroutine is already running must not
    raise InvalidStateError from set_result — the worker checks
    ``.cancelled()`` right before setting the result."""
    q = CommandQueue(loop)
    q.start()
    try:
        async def work():
            await asyncio.sleep(0.1)
            return "done"

        fut = q.submit(work())
        time.sleep(0.02)  # let the worker actually start running it
        fut.cancel()
        time.sleep(0.2)   # let it finish; must not raise anywhere
        assert fut.cancelled()
        # the queue must still be healthy afterwards
        assert q.submit(coro_for("ok")).result(timeout=5) == "ok"
    finally:
        q.stop()


def test_exception_not_set_when_future_cancelled_during_execution(loop):
    """Same race as above, but the coroutine raises instead of returning."""
    q = CommandQueue(loop)
    q.start()
    try:
        async def work():
            await asyncio.sleep(0.1)
            raise ValueError("boom")

        fut = q.submit(work())
        time.sleep(0.02)
        fut.cancel()
        time.sleep(0.2)
        assert fut.cancelled()
        assert q.submit(coro_for("still-fine")).result(timeout=5) == "still-fine"
    finally:
        q.stop()


def test_submit_swallows_add_scheduling_error(loop, monkeypatch):
    """If dispatching ``_add`` onto the loop errors, ``submit()`` swallows the
    wait failure (it only cares whether the FUTURE itself carries a
    QueueFull/QueueStopped) and still returns a future to the caller."""
    q = CommandQueue(loop)
    q.start()
    try:
        async def _boom(*_a, **_k):
            raise RuntimeError("scheduling boom")

        monkeypatch.setattr(q, "_add", _boom)
        coro = coro_for("x")
        fut = q.submit(coro)
        coro.close()  # _add never touched it (patched out) — avoid a GC warning
        assert isinstance(fut, concurrent.futures.Future)
        assert not fut.done()
    finally:
        q.stop()


def test_submit_async_on_queue_loop_raises_when_stopped(loop):
    """submit_async's ON-the-queue's-own-loop path (used by live jobs) must
    raise QueueStopped directly when the queue is already stopped, instead of
    routing through the (deadlocking) sync submit()."""
    q = CommandQueue(loop)
    q.start()
    q.stop()

    async def caller():
        return await q.submit_async(coro_for("x"))

    fut = asyncio.run_coroutine_threadsafe(caller(), loop)
    with pytest.raises(QueueStopped):
        fut.result(timeout=5)


def test_submit_async_on_queue_loop_returns_result_when_add_resolves_early(loop, monkeypatch):
    """Exercises submit_async's on-loop post-``_add`` branch where the future
    is ALREADY done (``fut.done()`` True) with a plain RESULT rather than a
    QueueFull/QueueStopped exception — ``fut.exception()`` is None, so the
    isinstance check must be False and the result returned via
    ``wrap_future``, not misinterpreted as an error."""
    q = CommandQueue(loop)
    q.start()
    try:
        async def fake_add(coro, fut, token, timeout):
            coro.close()
            fut.set_result("already-done")

        monkeypatch.setattr(q, "_add", fake_add)

        async def caller():
            return await q.submit_async(coro_for("x"))

        fut = asyncio.run_coroutine_threadsafe(caller(), loop)
        assert fut.result(timeout=5) == "already-done"
    finally:
        q.stop()


def test_submit_async_on_queue_loop_raises_when_full(loop):
    """submit_async's on-loop path must also surface QueueFull from the
    future (not swallow it) when the ring is already at capacity."""
    q = CommandQueue(loop, maxsize=1)
    q.start()

    async def caller():
        # White-box pre-fill: put one dummy item directly in the ring so the
        # next _add() call hits capacity deterministically (no timing races).
        async with q._cond:
            dummy = coro_for("dummy")
            q._pending.append(_QueueItem(dummy, concurrent.futures.Future(), None,
                                          enqueued_at=time.monotonic(), timeout=None))
        with pytest.raises(QueueFull):
            await q.submit_async(coro_for("overflow"))

    fut = asyncio.run_coroutine_threadsafe(caller(), loop)
    fut.result(timeout=5)
    q.stop()  # closes the leftover dummy coro via the stop-drain path


def test_add_stopped_race_between_caller_check_and_lock(loop):
    """``_add``'s OWN ``if self._stopped`` check (distinct from submit()'s and
    submit_async()'s pre-checks) guards the race where the queue stops in the
    window between a caller's check and ``_add`` actually acquiring the
    condition lock. Call ``_add`` directly to force that race deterministically."""
    q = CommandQueue(loop)
    q.start()
    try:
        q._stopped = True
        fut = concurrent.futures.Future()
        coro = coro_for("x")

        async def call_add():
            await q._add(coro, fut, None, None)

        done = asyncio.run_coroutine_threadsafe(call_add(), loop)
        done.result(timeout=5)
        assert isinstance(fut.exception(), QueueStopped)
    finally:
        q._stopped = False
        q.stop()


def test_stop_skips_already_cancelled_pending_item(loop):
    """``_cancel_worker``'s drain loop over ``remaining`` must skip an item
    whose future was already cancelled by its caller (no double-resolve),
    rather than only handling that race in the live ``_dequeue`` expiry path."""
    q = CommandQueue(loop)
    q.start()
    busy = q.submit(asyncio.sleep(0.3))  # keeps the worker occupied so the next item stays pending
    fut = q.submit(coro_for("x"))
    fut.cancel()
    q.stop()
    assert fut.cancelled()


def test_release_with_wrong_token_is_a_noop(loop):
    q = CommandQueue(loop)
    q.start()
    try:
        asyncio.run_coroutine_threadsafe(q.acquire("A"), loop).result(timeout=5)
        asyncio.run_coroutine_threadsafe(q.release("B"), loop).result(timeout=5)
        assert q._exclusive_owner == "A", "a foreign-token release must not clear the owner"
        asyncio.run_coroutine_threadsafe(q.release("A"), loop).result(timeout=5)
        assert q._exclusive_owner is None
    finally:
        q.stop()


@pytest.mark.asyncio
async def test_exclusive_idle_wait_without_deadline_then_resumes(loop):
    """No ``exclusive_timeout`` configured (the legacy/default behavior): while
    the owner has nothing queued but another (non-owner) item IS pending,
    ``_dequeue`` must idle on the condvar rather than force-release or crash —
    it only wakes/resumes once the owner itself submits something."""
    q = CommandQueue(loop)  # exclusive_timeout defaults to None
    q.start()
    try:
        await asyncio.wrap_future(
            asyncio.run_coroutine_threadsafe(q.acquire("X"), loop))
        history = []
        free_fut = asyncio.ensure_future(
            asyncio.wrap_future(asyncio.run_coroutine_threadsafe(
                q.submit_async(_record(history, "free")), loop)))
        await asyncio.sleep(0.15)
        assert history == [], "free item must stay deferred while X holds exclusive"

        await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(
            q.submit_async(_record(history, "x1"), token="X"), loop))
        assert history == ["x1"]

        await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(q.release("X"), loop))
        await free_fut
        assert history == ["x1", "free"]
    finally:
        q.stop()


def test_expired_item_already_cancelled_is_dropped_without_double_resolve(loop):
    """An item that both times out AND was already cancelled by its caller
    must not attempt to set an exception on an already-cancelled future
    (``_dequeue``'s expiry sweep checks ``.cancelled()`` first, in the SAME
    ``_dequeue`` call that finds it stale — not via ``stop()``'s separate
    drain path, which is why ``busy`` must finish BEFORE ``fut``'s timeout
    elapses: the worker only re-enters ``_dequeue`` once it's free)."""
    q = CommandQueue(loop, item_timeout=0.05)
    q.start()
    try:
        busy = q.submit(asyncio.sleep(0.1))   # frees up well before fut's 0.05s deadline elapses...
        fut = q.submit(coro_for("late"), timeout=0.05)
        fut.cancel()
        busy.result(timeout=5)                # worker is now free to re-enter _dequeue
        time.sleep(0.1)                       # ...by which point fut is well past its deadline
        assert fut.cancelled()
        # the queue must still be healthy afterwards (expiry sweep didn't wedge it)
        assert q.submit(coro_for("ok")).result(timeout=5) == "ok"
    finally:
        q.stop()

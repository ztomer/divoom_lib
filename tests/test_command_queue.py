"""Tests for divoom_daemon.command_queue.CommandQueue."""
from __future__ import annotations

import asyncio
import threading

import pytest

from divoom_daemon.command_queue import CommandQueue, QueueFull, QueueStopped


@pytest.fixture
def loop():
    """A dedicated event loop running in a daemon thread (matches production)."""
    l = asyncio.new_event_loop()
    t = threading.Thread(target=l.run_forever, daemon=True, name="queue-test-loop")
    t.start()
    yield l
    l.call_soon_threadsafe(l.stop)
    t.join(timeout=3)
    l.close()


@pytest.fixture
def queue(loop):
    """A started CommandQueue bound to *loop* (which is running in a thread)."""
    q = CommandQueue(loop)
    q.start()
    yield q
    q.stop()


# ── FIFO ordering ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fifo_ordering(loop, queue):
    """Submissions execute in FIFO order."""
    history = []

    async def make_step(n):
        history.append(n)

    await asyncio.gather(
        queue.submit_async(make_step(1)),
        queue.submit_async(make_step(2)),
        queue.submit_async(make_step(3)),
    )
    assert history == [1, 2, 3], f"Expected FIFO, got {history}"


@pytest.mark.asyncio
async def test_fifo_single_submit(loop, queue):
    """A single submit returns the coroutine's result."""
    result = await queue.submit_async(coro_for(42))
    assert result == 42


# ── deadlock regression: submit_async FROM the queue's own loop ────────────


def test_submit_async_from_queue_own_loop_does_not_deadlock(loop, queue):
    """A live job runs ON the device loop and awaits submit_async. The old
    submit_async routed through the blocking submit() — run_coroutine_threadsafe
    + .result() targeting the SAME loop it was blocking → deadlock, so the
    live-widget push hung forever (no frame, no error). HW-found. Now an on-loop
    caller enqueues with a direct await."""
    ran = []

    async def work():
        ran.append("x")
        return 42

    async def caller():        # runs ON the queue's loop, like a live job
        return await queue.submit_async(work())

    fut = asyncio.run_coroutine_threadsafe(caller(), loop)
    assert fut.result(timeout=5) == 42      # TimeoutError here == regressed
    assert ran == ["x"]


# ── result / exception propagation ────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_returns_result(loop, queue):
    assert await queue.submit_async(coro_for("ok")) == "ok"


@pytest.mark.asyncio
async def test_submit_raises_exception(loop, queue):
    with pytest.raises(ValueError, match="boom"):
        await queue.submit_async(_raise(ValueError("boom")))


# ── exclusive mode ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exclusive_serialises_matching_token(loop, queue):
    """Items with the exclusive token run; others queue behind."""
    history = []

    async with queue.exclusive(token="A"):
        await queue.submit_async(_record(history, "a1"), token="A")
        await queue.submit_async(_record(history, "a2"), token="A")
        await queue.submit_async(_record(history, "a3"), token="A")

    assert history == ["a1", "a2", "a3"], f"Expected only A items, got {history}"


@pytest.mark.asyncio
async def test_non_exclusive_items_deferred_during_exclusive(loop, queue):
    """Items without matching token queue up during exclusive mode."""
    history = []

    async with queue.exclusive(token="X"):
        await queue.submit_async(_record(history, "x1"), token="X")
        free_fut = queue.submit_async(_record(history, "free"))
        await queue.submit_async(_record(history, "x2"), token="X")

    await free_fut
    assert history == ["x1", "x2", "free"], (
        f"Expected x1, x2, then free, got {history}"
    )


@pytest.mark.asyncio
async def test_exclusive_survives_concurrent_wrong_token(loop, queue):
    """Wrong-token items don't starve — they run after release."""
    history = []

    async with queue.exclusive(token="owner"):
        await queue.submit_async(_record(history, "o1"), token="owner")
        await queue.submit_async(_record(history, "o2"), token="owner")

    await queue.submit_async(_record(history, "free"))
    assert history == ["o1", "o2", "free"], f"Got {history}"


@pytest.mark.asyncio
async def test_exclusive_multiple_tokens(loop, queue):
    """Two different exclusive tokens serialise independently."""
    history = []

    async with queue.exclusive(token="A"):
        await queue.submit_async(_record(history, "a1"), token="A")
        await queue.submit_async(_record(history, "a2"), token="A")

    async with queue.exclusive(token="B"):
        await queue.submit_async(_record(history, "b1"), token="B")

    assert history == ["a1", "a2", "b1"], f"Got {history}"


@pytest.mark.asyncio
async def test_exclusive_token_none_with_exclusive_active(loop, queue):
    """Items with token=None queue behind exclusive-mode items."""
    history = []

    async with queue.exclusive(token="X"):
        await queue.submit_async(_record(history, "x1"), token="X")
        none_fut = queue.submit_async(_record(history, "none"))
        await queue.submit_async(_record(history, "x2"), token="X")

    await none_fut
    assert history == ["x1", "x2", "none"], f"Got {history}"


def test_acquire_now_rejects_steal_immediately(loop, queue):
    """A foreign-token acquire must be REJECTED immediately, not block on the
    idle deadline and then silently steal.

    Teeth: the pre-fix daemon routed acquire through ``submit()`` with the
    foreign token, so ``_dequeue`` gated it out (it only dispatches the owner's
    items) — ``acquire``'s "held by another session" raise was unreachable and
    the steal was "handled" only by the 30 s G3 force-release (which then let the
    thief WIN). ``acquire_now`` runs ``acquire`` straight on the loop, so the
    RuntimeError fires now and the owner is NOT stolen. If ``acquire_now`` were
    reverted to the ``submit()`` path this raises ``TimeoutError`` after the full
    result timeout (or steals) — either way the assertions below fail."""
    import time

    queue.acquire_now("A")
    assert queue._exclusive_owner == "A"

    t0 = time.monotonic()
    with pytest.raises(RuntimeError, match="held by another session"):
        queue.acquire_now("B")
    elapsed = time.monotonic() - t0
    assert elapsed < 2.0, f"steal-reject must be immediate, took {elapsed:.1f}s"
    assert queue._exclusive_owner == "A", "the slot must NOT be stolen by B"

    # same-token re-acquire stays idempotent (re-arms the deadline, no raise)
    queue.acquire_now("A")
    assert queue._exclusive_owner == "A"


# ── G3: exclusive auto-release (orphaned owner) ─────────────────────────────


@pytest.mark.asyncio
async def test_orphaned_exclusive_session_auto_releases(loop):
    """A client that acquires exclusive then dies (never releases) must not wedge
    the queue forever — the idle owner is force-released after exclusive_timeout."""
    q = CommandQueue(loop, exclusive_timeout=0.3)
    q.start()
    try:
        history = []
        # Simulate the dead client: acquire the token, never release it.
        asyncio.run_coroutine_threadsafe(q.acquire("dead"), loop).result(timeout=2)
        # Without auto-release this free item hangs forever.
        fut = q.submit(_record(history, "free"))
        await asyncio.wait_for(asyncio.wrap_future(fut), timeout=2.0)
        assert history == ["free"]
    finally:
        q.stop()


@pytest.mark.asyncio
async def test_exclusive_with_timeout_still_defers_free_items(loop):
    """With a timeout configured, a normal (fast) exclusive block still serialises
    its token's items ahead of free ones — no spurious early release."""
    q = CommandQueue(loop, exclusive_timeout=5.0)
    q.start()
    try:
        history = []
        async with q.exclusive(token="X"):
            await q.submit_async(_record(history, "x1"), token="X")
            free_fut = q.submit_async(_record(history, "free"))
            await q.submit_async(_record(history, "x2"), token="X")
        await free_fut
        assert history == ["x1", "x2", "free"], f"Got {history}"
    finally:
        q.stop()


@pytest.mark.asyncio
async def test_exclusive_not_released_during_long_item(loop):
    """R53.15: a single exclusive item that runs LONGER than exclusive_timeout must
    not cause the active session to be force-released — the deadline re-arms on
    completion. A free item genuinely PENDING behind it stays deferred until the
    real release. (submit_async only enqueues when awaited, so ensure_future both
    to get the free item actually queued while the slow item runs.)"""
    q = CommandQueue(loop, exclusive_timeout=0.2)
    q.start()
    try:
        history = []

        async def _slow(tag):
            await asyncio.sleep(0.4)            # > exclusive_timeout
            history.append(tag)

        await q.acquire("X")
        slow_task = asyncio.ensure_future(q.submit_async(_slow("x-slow"), token="X"))
        free_task = asyncio.ensure_future(q.submit_async(_record(history, "free")))
        await asyncio.sleep(0.05)              # let both actually enqueue
        await slow_task                        # ~0.4s, well past the 0.2 deadline
        await asyncio.sleep(0.15)              # past where a lapsed deadline would fire
        assert "free" not in history, f"session force-released mid-flight: {history}"
        await q.release("X")
        await free_task
        assert history == ["x-slow", "free"], history
    finally:
        q.stop()


# ── concurrent submissions from multiple tasks ────────────────────────────


@pytest.mark.asyncio
async def test_concurrent_submissions_are_fifo(loop, queue):
    """Multiple concurrent submitters are serialised FIFO."""
    history = []

    async def submitter(n):
        await queue.submit_async(_record(history, n))

    await asyncio.gather(*[submitter(i) for i in range(10)])

    assert history == list(range(10)), f"Expected 0..9, got {history}"


@pytest.mark.asyncio
async def test_many_concurrent_submissions(loop, queue):
    """50 concurrent items all complete."""
    history = set()

    async def submitter(n):
        result = await queue.submit_async(coro_for(n))
        history.add(result)

    await asyncio.gather(*[submitter(i) for i in range(50)])

    assert history == set(range(50)), f"Got {len(history)}/{50} results"


# ── queue lifecycle ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stop_resolves_pending_futures(loop):
    """Pending (not yet started) items get RuntimeError on stop."""
    q = CommandQueue(loop)
    q.start()

    long = asyncio.ensure_future(q.submit_async(asyncio.sleep(10)))
    await asyncio.sleep(0)

    pending = asyncio.ensure_future(q.submit_async(coro_for("ok")))
    await asyncio.sleep(0)

    q.stop()

    with pytest.raises(asyncio.CancelledError):
        await long

    with pytest.raises(RuntimeError, match="queue stopped"):
        await pending


@pytest.mark.asyncio
async def test_double_start_is_idempotent(loop):
    q = CommandQueue(loop)
    q.start()
    q.start()  # no error
    q.stop()


@pytest.mark.asyncio
async def test_submit_after_stop_raises(loop):
    """submit() on a stopped queue raises QueueStopped."""
    q = CommandQueue(loop)
    q.start()
    q.stop()

    with pytest.raises(QueueStopped, match="queue is stopped"):
        q.submit(coro_for("x"))


@pytest.mark.asyncio
async def test_start_stop_cycle(loop):
    """Start, stop, start, stop — clean restart."""
    q = CommandQueue(loop)
    q.start()
    assert await q.submit_async(coro_for("first")) == "first"
    q.stop()

    q.start()
    assert await q.submit_async(coro_for("second")) == "second"
    q.stop()


# ── sync submit — thread-safe ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sync_submit_from_other_thread(loop, queue):
    """submit() works from a different thread."""
    import threading

    results = []

    def _run():
        fut = queue.submit(coro_for("from-thread"))
        results.append(fut.result())

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=3)
    assert results == ["from-thread"], f"Got {results}"


@pytest.mark.asyncio
async def test_sync_submit_blocking_result(loop, queue):
    """submit().result() blocks until the coroutine completes."""
    fut = queue.submit(coro_for("sync-ok"))
    assert fut.result(timeout=5) == "sync-ok"


# ── bounded queue (maxsize) ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_maxsize_rejects_when_full(loop):
    """submit() raises QueueFull when the queue is at capacity."""
    q = CommandQueue(loop, maxsize=2)
    q.start()

    long = asyncio.ensure_future(q.submit_async(asyncio.sleep(10)))
    await asyncio.sleep(0)

    q.submit(coro_for("ok"))
    q.submit(coro_for("ok"))

    with pytest.raises(QueueFull):
        q.submit(coro_for("too-many"))

    q.stop()
    await _drain_futures([long], [])


@pytest.mark.asyncio
async def test_maxsize_accepts_at_limit(loop):
    """Queue at exactly maxsize can still process items."""
    q = CommandQueue(loop, maxsize=3)
    q.start()
    result = await q.submit_async(coro_for("should-work"))
    assert result == "should-work"
    q.stop()


@pytest.mark.asyncio
async def test_maxsize_does_not_count_active_item(loop):
    """The currently-executing item does not count toward maxsize."""
    q = CommandQueue(loop, maxsize=1)
    q.start()

    long = asyncio.ensure_future(q.submit_async(asyncio.sleep(10)))
    await asyncio.sleep(0)

    q.submit(coro_for("pending"))

    with pytest.raises(QueueFull):
        q.submit(coro_for("overflow"))

    q.stop()
    await _drain_futures([long], [])


# ── item timeout ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_item_timeout_expires_stale_items(loop):
    """Items sitting too long in the queue get TimeoutError."""
    q = CommandQueue(loop, item_timeout=0.05)
    q.start()

    # Occupy worker briefly, then submit an item that times out before
    # the worker becomes free.
    long_fut = q.submit(asyncio.sleep(0.1))
    pending = q.submit(coro_for("ok"))

    # Wait for worker to finish sleep(0.1), then _dequeue expired pending,
    # then be idle again.
    long_fut.result(timeout=5)
    import time
    time.sleep(0.2)  # give worker time to process + idle on _cond.wait()

    q.stop()
    assert isinstance(pending.exception(), TimeoutError), (
        f"Expected TimeoutError, got {pending.exception()}"
    )


@pytest.mark.asyncio
async def test_per_submit_timeout_override(loop):
    """Per-submit timeout overrides the queue-wide item_timeout."""
    q = CommandQueue(loop, item_timeout=10.0)
    q.start()

    long_fut = q.submit(asyncio.sleep(0.1))
    pending = q.submit(coro_for("ok"), timeout=0.05)

    long_fut.result(timeout=5)
    import time
    time.sleep(0.2)

    q.stop()
    assert isinstance(pending.exception(), TimeoutError), (
        f"Expected TimeoutError, got {pending.exception()}"
    )


@pytest.mark.asyncio
async def test_item_without_timeout_survives(loop):
    """Item with timeout=None does not expire — it completes normally."""
    q = CommandQueue(loop, item_timeout=0.05)
    q.start()

    long_fut = q.submit(asyncio.sleep(0.1))
    pending = q.submit(coro_for("survived"), timeout=None)

    long_fut.result(timeout=5)
    import time
    time.sleep(0.2)

    q.stop()
    assert pending.result(timeout=5) == "survived"


# ── stress tests ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rapid_burst_then_drain(loop):
    """Submit many items quickly, verify all complete."""
    q = CommandQueue(loop)
    q.start()

    N = 100
    futures = [q.submit(coro_for(i)) for i in range(N)]

    for i, fut in enumerate(futures):
        assert fut.result(timeout=10) == i, f"Mismatch at {i}"

    q.stop()


@pytest.mark.asyncio
async def test_exclusive_with_deferred_stress(loop):
    """Exclusive mode with many deferred items behind it."""
    q = CommandQueue(loop)
    q.start()

    history = []

    async with q.exclusive(token="X"):
        for i in range(20):
            await q.submit_async(_record(history, f"x{i}"), token="X")

    # These should all run after exclusive release
    for i in range(20):
        await q.submit_async(_record(history, f"free{i}"))

    assert len(history) == 40
    assert history[:20] == [f"x{i}" for i in range(20)]
    q.stop()


@pytest.mark.asyncio
async def test_concurrent_submit_from_multiple_threads(loop):
    """Sync submit() from 10 threads, all resolve."""
    q = CommandQueue(loop)
    q.start()

    results = []
    errors = []

    def _submit(n):
        try:
            r = q.submit(coro_for(n)).result(timeout=10)
            results.append(r)
        except Exception as e:
            errors.append((n, e))

    threads = [threading.Thread(target=_submit, args=(i,), daemon=True)
               for i in range(30)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(errors) == 0, f"Errors: {errors}"
    assert sorted(results) == list(range(30))
    q.stop()


# ── edge cases ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.filterwarnings("ignore:coroutine '.*slow' was never awaited:RuntimeWarning")
async def test_cancel_does_not_block_queue(loop, queue):
    """Cancelling a submit future doesn't stall the queue."""
    history = []

    async def slow():
        await asyncio.sleep(0.5)
        history.append("slow")

    t1 = asyncio.ensure_future(queue.submit_async(slow()))
    t2 = asyncio.ensure_future(queue.submit_async(_record(history, "fast")))

    t1.cancel()
    await t2

    assert history == ["fast"]


@pytest.mark.asyncio
async def test_empty_queue_does_not_deadlock(loop):
    """Worker survives idle periods."""
    q = CommandQueue(loop)
    q.start()
    await asyncio.sleep(0.05)
    result = await q.submit_async(coro_for("still works"))
    assert result == "still works"
    q.stop()


@pytest.mark.asyncio
async def test_exception_types_propagate_correctly(loop, queue):
    """Various exception types all propagate through the queue."""
    for exc in (ValueError("v"), RuntimeError("r"), TypeError("t"), KeyError("k")):
        with pytest.raises(type(exc), match=exc.args[0]):
            await queue.submit_async(_raise(exc))


@pytest.mark.asyncio
async def test_submit_none_coro_still_runs(loop, queue):
    """A coroutine returning None is fine."""
    async def none_coro():
        return None
    assert await queue.submit_async(none_coro()) is None


# ── helpers ────────────────────────────────────────────────────────────────


async def coro_for(value):
    return value


async def _raise(exc):
    raise exc


async def _record(history, value):
    history.append(value)


async def _drain_futures(long_futs, other_futs):
    """Clean up futures from a test.  CancelledError is expected for running items."""
    for f in long_futs:
        try:
            await f
        except (asyncio.CancelledError, RuntimeError):
            pass
    for f in other_futs:
        try:
            await asyncio.wrap_future(f)
        except (asyncio.CancelledError, RuntimeError, TimeoutError):
            pass

"""R53.43: the device event loop must be CLOSED once its thread exits. _run()
called loop.run_forever() with no loop.close() afterward, so every stop→restart
cycle in a long-lived (keep-alive) daemon leaked the loop's selector/fds. The
close now lives in _run()'s finally (runs in the dying loop thread).

Teeth: drop the finally: loop.close() and the loop stays open after teardown.
"""
import sys
import threading
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from divoom_daemon.owner_loop import OwnerLoopMixin


def test_device_loop_is_closed_after_thread_exits():
    owner = object.__new__(type("_Owner", (OwnerLoopMixin,), {}))
    owner._device_lock = threading.Lock()
    owner._loop = None
    owner._cmd_queue = None
    owner._loop_thread = None

    loop = owner._device_loop()
    thread = owner._loop_thread
    assert loop is not None and thread.is_alive()
    assert not loop.is_closed()

    # Tear down the way device_owner.stop() does: stop the queue, then the loop.
    owner._cmd_queue.stop()
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=3)

    assert not thread.is_alive(), "loop thread should have exited"
    assert loop.is_closed(), "loop must be closed after its thread exits (no fd leak)"

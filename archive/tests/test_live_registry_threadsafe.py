"""R53.32: the live-device/activity registry dicts are mutated on the device
LOOP thread (get_live_device inserts, stop_all clears, _start/_stop touch
_live_tasks) while the menubar polls get_device_activity on an RPC handler
thread. A bare `for ... in self._live_devices.items()` / set-comprehension over
`self._live_tasks` raises "RuntimeError: dictionary changed size during
iteration" when the size changes mid-loop. The methods must iterate a
point-in-time snapshot instead.

Teeth: revert any of the list()/dict() snapshots in owner_live.py and this test
raises within the contention window.
"""
import sys
import threading
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from archive.divoom_daemon.owner_live import OwnerLiveMixin


class _Dev:
    is_connected = True
    is_alive = True


def _make_owner():
    class _Owner(OwnerLiveMixin):
        def __init__(self):
            super().__init__()
            self.mac = None
            self._lan_ip = None
            self._device = None

    return _Owner()


def test_get_device_activity_is_thread_safe_under_registry_mutation():
    o = _make_owner()
    # Seed a steady-state set so every reader pass iterates non-empty dicts.
    for i in range(60):
        m = f"AA:{i:02d}"
        o._device_activity[m] = {"name": m, "kind": "clock", "at": time.time()}
        o._live_devices[m] = _Dev()
        o._live_tasks[(m, "clock")] = object()
        o._live_params[(m, "clock")] = {}

    errors: list[BaseException] = []
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            try:
                o.get_device_activity({})
            except BaseException as e:  # noqa: BLE001 - capture the race
                errors.append(e)
                return

    def mutator():
        # Churn keys on the dicts the reader iterates: each add+pop changes the
        # dict size mid-iteration for the reader's Python-level loops.
        i = 0
        while not stop.is_set():
            m = f"BB:{i % 256:02x}"
            o._device_activity[m] = {"name": m, "kind": "eq", "at": time.time()}
            o._live_devices[m] = _Dev()
            o._live_tasks[(m, "eq")] = object()
            o._device_activity.pop(m, None)
            o._live_devices.pop(m, None)
            o._live_tasks.pop((m, "eq"), None)
            i += 1

    threads = [threading.Thread(target=reader), threading.Thread(target=reader),
               threading.Thread(target=mutator), threading.Thread(target=mutator)]
    for t in threads:
        t.start()
    time.sleep(0.6)
    stop.set()
    for t in threads:
        t.join(timeout=2)

    assert not errors, (
        "get_device_activity raised under concurrent registry mutation "
        f"(expected snapshots): {errors[:3]}"
    )

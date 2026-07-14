"""R53 round 33 — persona pass (Linus + Carmack CLEAN; Bob + Hashimoto each 1 bug).

- LightingApi._device_size() probed _state["_active_device_size"], but that's a
  METHOD on the orchestrator (not in __dict__), so it always returned the 16px
  fallback → push_text rendered wrong-sized text on non-16px devices. The
  orchestrator now exposes the bound resolver through the shared state dict.
- hot_update wedged the whole feature forever if _cmd_queue.submit() RAISED
  (QueueStopped/QueueFull) before returning a future: the just-claimed "starting"
  phase was never cleared (add_done_callback never attached). Now submit is
  guarded and the claim is released on failure.
"""
import sys
import threading
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "divoom_gui"))


# ── Uncle Bob: push_text device-size resolution ─────────────────────────────

def test_orchestrator_exposes_active_device_size_to_lighting():
    from divoom_gui.gui_api import DivoomGuiAPI

    o = object.__new__(DivoomGuiAPI)
    o.loop_thread = None
    o._daemon_client = None
    o.wall_slots = {"AA": {"size": 64}}   # _active_device_size → min slot size
    o.current_divoom = None

    o._wire_collaborators()

    assert callable(o.__dict__.get("_active_device_size")), "resolver must be in the state dict"
    assert o.lighting._device_size() == 64, "push_text must see the real device size, not 16"


def test_lighting_device_size_falls_back_without_resolver():
    from divoom_gui.api.lighting import LightingApi
    api = object.__new__(LightingApi)
    api._state_getter = lambda: {}   # nothing wired
    assert api._device_size() == 16


# ── Hashimoto: hot_update submit() failure must not wedge the feature ────────

def test_hot_update_submit_failure_clears_starting():
    from archive.divoom_daemon.owner_art import OwnerArtMixin

    o = object.__new__(OwnerArtMixin)
    o._hot_progress = {}
    o._hot_progress_lock = threading.Lock()

    class _Q:
        def submit(self, coro):
            coro.close()                  # avoid "coroutine was never awaited"
            raise RuntimeError("QueueStopped")

    o._cmd_queue = _Q()

    res = o.hot_update({"device_size": 16})
    assert res.get("success") is False, "submit failure must surface, not raise"
    # crucially: the claimed "starting" must be cleared so the feature isn't wedged
    assert o._get_hot_progress().get("phase") != "starting"
    assert o._try_begin_hot_update() is True, "a new hot_update must be allowed after a submit failure"

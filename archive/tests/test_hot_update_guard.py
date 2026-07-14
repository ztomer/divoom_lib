"""R53.x: hot_update's in-progress guard was a non-atomic check-then-set that
also omitted the "starting" phase, so two socket-handler threads could both
launch a hot update and clobber each other's progress. _try_begin_hot_update now
claims the slot atomically (with "starting" in the active set); a never-started
item is reset by _clear_stuck_starting so "starting" can't wedge future updates.

Teeth: drop "starting" from _HOT_ACTIVE_PHASES and the
test_hot_update_rejected_while_starting case lets a second start through.
"""
import sys
import threading
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from archive.divoom_daemon.owner_art import OwnerArtMixin


def _owner():
    o = object.__new__(OwnerArtMixin)
    o._hot_progress = {}
    o._hot_progress_lock = threading.Lock()
    return o


def test_try_begin_claims_when_idle_and_rejects_when_active():
    o = _owner()
    assert o._try_begin_hot_update() is True
    assert o._get_hot_progress()["phase"] == "starting"
    # already "starting" → must reject (the window the old guard left open)
    assert o._try_begin_hot_update() is False
    for ph in ("fetching_manifest", "downloading", "uploading"):
        o._set_hot_progress({"phase": ph})
        assert o._try_begin_hot_update() is False, f"{ph} must block a new start"


def test_idle_or_terminal_phase_allows_new_start():
    o = _owner()
    for ph in ("done", "error", "idle"):
        o._set_hot_progress({"phase": ph})
        assert o._try_begin_hot_update() is True, f"{ph} must allow a new start"


def test_hot_update_rejected_while_starting():
    o = _owner()
    o._set_hot_progress({"phase": "starting"})
    res = o.hot_update({"device_size": 16})
    assert res.get("success") is False
    assert "in progress" in res.get("error", "")


def test_clear_stuck_starting_resets_only_starting():
    o = _owner()
    o._set_hot_progress({"phase": "starting"})
    o._clear_stuck_starting()
    assert o._get_hot_progress()["phase"] == "error"

    # a real in-flight phase must NOT be clobbered by the stuck-reset
    o._set_hot_progress({"phase": "downloading"})
    o._clear_stuck_starting()
    assert o._get_hot_progress()["phase"] == "downloading"

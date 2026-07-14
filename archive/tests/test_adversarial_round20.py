"""R53.35 / R53.36 — round-20 adversarial fixes.

R53.35: DivoomWall.set_light/show_clock/show_effects/show_visualization used a
bare asyncio.gather — one slot's BLE failure raised out of the method (instead
of an honest degraded False) and abandoned the sibling pushes. They must use
return_exceptions=True like set_volume/switch_channel/set_brightness.

R53.36: DeviceOwner.device_call materialized base64 blobs to /tmp via mkstemp
but never unlinked them → one leaked file per blob-based call, forever. The
files must be cleaned up after the call (success or failure).
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import divoom_lib.divoom  # noqa: F401  - resolve the import cycle first
from divoom_lib.wall import DivoomWall
from archive.divoom_daemon.device_owner import DeviceOwner


# ── R53.35: wall partial-failure honesty ────────────────────────────────────

def _make_wall(slot_behaviors):
    """slot_behaviors: list of values/Exceptions each slot's display method yields."""
    wall = object.__new__(DivoomWall)
    wall.logger = logging.getLogger("test_wall_gather")

    class _Display:
        def __init__(self, beh):
            self._beh = beh

        async def _act(self, *a, **k):
            if isinstance(self._beh, BaseException):
                raise self._beh
            return self._beh

        show_light = _act
        show_clock = _act
        show_effects = _act
        show_visualization = _act

    class _Dev:
        def __init__(self, beh):
            self.display = _Display(beh)

    class _Slot:
        def __init__(self, beh):
            self.device = _Dev(beh)

    wall.devices = [_Slot(b) for b in slot_behaviors]
    return wall


def test_wall_set_light_one_failing_slot_returns_false_not_raises():
    # slot 0 raises (dropped GATT), slot 1 ok → honest False, no exception.
    wall = _make_wall([RuntimeError("gatt drop"), True])
    assert asyncio.run(wall.set_light("#FF0000")) is False


def test_wall_clock_effects_visualization_degrade_honestly():
    for method, call in (
        ("show_clock", lambda w: w.show_clock(0)),
        ("show_effects", lambda w: w.show_effects(0)),
        ("show_visualization", lambda w: w.show_visualization(0)),
    ):
        wall = _make_wall([True, ConnectionError("boom")])
        assert asyncio.run(call(wall)) is False, f"{method} should degrade to False"


def test_wall_all_slots_ok_returns_true():
    wall = _make_wall([True, True, True])
    assert asyncio.run(wall.set_light("#00FF00")) is True


# ── R53.36: device_call blob temp-file cleanup ──────────────────────────────

def test_device_call_unlinks_blob_temp_file():
    import base64

    owner = object.__new__(DeviceOwner)
    captured = {}

    class _Display:
        async def show_image(self, path, **kw):
            captured["path"] = path
            captured["existed_during_call"] = os.path.exists(path)
            return True

    class _Dev:
        display = _Display()

    async def _ensure_device_async(_mac):
        return _Dev()

    def _run_device(coro, token=None):
        return asyncio.run(coro)

    owner._ensure_device_async = _ensure_device_async
    owner._run_device = _run_device
    owner._wall = None

    blob = base64.b64encode(b"\x89PNG fake").decode()
    res = owner.device_call({
        "method": "display.show_image",
        "args": ["frame.png"],
        "blobs": {"0": blob},
        "mac": "AA:BB",
    })

    assert res["success"] is True
    # the device saw a real file during the call...
    assert captured["existed_during_call"] is True
    # ...and it's gone afterward (no /tmp leak).
    assert not os.path.exists(captured["path"]), "blob temp file leaked"

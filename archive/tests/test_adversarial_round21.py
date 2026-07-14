"""R53.37 / R53.38 — round-21 adversarial fixes.

R53.37: OwnerConnectMixin._owned_devices() iterated self._live_devices with a
bare for-loop while the device-loop thread inserts/pops it (the one _live_devices
read R53.32 missed). During a scan (which runs off the queue, concurrent with
live-job pollers) it raised "dict changed size during iteration", swallowed by
scan()'s except → a false empty "no devices found".

R53.38: GUI get_ticker_preview only renders a LOCAL preview (no device push) yet
read dev.lan / dev.is_connected and called dev.connect() — each a blocking
device RPC on the pywebview JS thread — for no benefit (same anti-pattern as
R53.30's media_sync._push_frame). The dev pre-check is removed.
"""
import json
import sys
import threading
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "divoom_gui"))

from archive.divoom_daemon.owner_connect import OwnerConnectMixin
from divoom_gui import media_sync as media_sync_mod
from divoom_gui.media_sync import MediaSyncMixin


# ── R53.37: _owned_devices snapshot ─────────────────────────────────────────

class _Dev:
    device_name = None


def test_owned_devices_thread_safe_under_live_device_mutation():
    owner = object.__new__(OwnerConnectMixin)
    owner._device = None
    owner.mac = None
    owner._lan_ip = None
    owner._scan_name_cache = {}
    owner._live_devices = {f"AA:{i:03d}": _Dev() for i in range(200)}

    errors: list[BaseException] = []
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            try:
                owner._owned_devices()
            except BaseException as e:  # noqa: BLE001
                errors.append(e)
                return

    def mutator():
        # add a burst then remove it, so the dict size genuinely changes WHILE a
        # reader is mid-iteration (a single add+pop barely widens the window).
        i = 0
        while not stop.is_set():
            burst = [f"BB:{i % 500:03x}:{j}" for j in range(20)]
            for m in burst:
                owner._live_devices[m] = _Dev()
            for m in burst:
                owner._live_devices.pop(m, None)
            i += 1

    # Force frequent GIL hand-offs so the reader's per-item loop reliably
    # interleaves with the mutator (otherwise a short loop runs within one slice).
    old_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        threads = [threading.Thread(target=reader), threading.Thread(target=reader),
                   threading.Thread(target=mutator), threading.Thread(target=mutator)]
        for t in threads:
            t.start()
        time.sleep(0.6)
        stop.set()
        for t in threads:
            t.join(timeout=2)
    finally:
        sys.setswitchinterval(old_interval)

    assert not errors, f"_owned_devices raised under concurrent mutation: {errors[:3]}"


# ── R53.38: get_ticker_preview must not touch the connection ─────────────────

def test_get_ticker_preview_does_not_read_blocking_dev_attrs(monkeypatch):
    monkeypatch.setattr(media_sync_mod.media_source, "fetch_stock_ticker",
                        lambda _symbol: None)

    accessed: list[str] = []

    class _BlockingDev:
        @property
        def lan(self):
            accessed.append("lan")
            return None

        @property
        def is_connected(self):
            accessed.append("is_connected")
            return False

    o = MediaSyncMixin.__new__(MediaSyncMixin)
    o.current_divoom = _BlockingDev()

    res = o.get_ticker_preview("AAPL")
    # no data → honest ok:False, but crucially the connection was never probed
    assert json.loads(res)["ok"] is False
    assert accessed == [], f"get_ticker_preview probed the connection: {accessed}"

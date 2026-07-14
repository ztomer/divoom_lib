"""R53.21: live-job pollers back off on consecutive failures instead of hammering
ensure_connected (~16s/attempt) every tick when a device is permanently dead.
"""
import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from archive.divoom_daemon import live_jobs


def _sleep_duration(monkeypatch, interval, fails):
    captured = {}

    async def _fake_sleep(d):
        captured["d"] = d

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(live_jobs._backoff_sleep(interval, fails))
    finally:
        loop.close()
    return captured["d"]


def test_no_backoff_on_success(monkeypatch):
    assert _sleep_duration(monkeypatch, 5.0, 0) == 5.0


def test_backoff_grows_with_consecutive_failures(monkeypatch):
    assert _sleep_duration(monkeypatch, 5.0, 1) == 10.0
    assert _sleep_duration(monkeypatch, 5.0, 2) == 20.0
    assert _sleep_duration(monkeypatch, 5.0, 3) == 40.0


def test_backoff_capped_at_max(monkeypatch):
    assert _sleep_duration(monkeypatch, 5.0, 6) == live_jobs._MAX_BACKOFF
    assert _sleep_duration(monkeypatch, 5.0, 99) == live_jobs._MAX_BACKOFF


def test_long_interval_never_sped_up_by_cap(monkeypatch):
    """Weather polls every 15min (> _MAX_BACKOFF). A failure must NOT shorten it to
    the 60s cap — backoff never sleeps less than the normal interval."""
    interval = 15.0 * 60
    assert _sleep_duration(monkeypatch, interval, 1) == interval
    assert _sleep_duration(monkeypatch, interval, 5) == interval

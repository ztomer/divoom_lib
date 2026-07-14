"""R61 coverage push: divoom_daemon.live_jobs gaps not exercised by
test_ble_phase2.py (``_ensure_live_device`` + the sysmon error/skip path) or
test_music_sync.py (``run_music``'s first-tick push/no-push branches).

Everything below is driven against hand-written fakes / patched
``divoom_lib.utils.media_source`` + ``divoom_lib.weather_provider`` calls and a
patched ``asyncio.sleep`` that raises to break the infinite polling loops after
one (or two) ticks — nothing here touches a real device, BLE link, or network.

Gaps closed:
  * ``push_image_to_device`` / ``push_weather_to_device`` — the actual device
    calls (``dev.display.show_image`` / the light-mode + ``Weather.set`` pair),
    never exercised directly (only via the loops, which mock them out).
  * ``run_stocks`` and ``run_weather`` — entirely untested: the no-symbol early
    return, the success/push/fails-reset path, the ``CancelledError``
    re-raise, and the generic-exception backoff path.
  * ``run_sysmon``'s success path (``fails = 0``) and ``CancelledError``
    re-raise (only the unrecoverable-drop error path was covered before).
  * ``run_music``'s branches: unchanged-track skip (second tick, same
    track/artist), artwork_url already present (skips the fetch), a fetch that
    resolves to no art (skips the render), a render that returns a missing
    path (skips the push), and the ``CancelledError``/generic-exception
    handlers.
"""
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from archive.divoom_daemon import live_jobs


class _Stop(Exception):
    """Raised in place of asyncio.sleep to break a run_* loop deterministically."""


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── push_image_to_device / push_weather_to_device (the actual device calls) ──


class _PassthroughQueue:
    async def submit_async(self, coro):
        return await coro


class _FakeOwner:
    """Just enough of DeviceOwner for _ensure_live_device + the cmd queue."""

    def __init__(self, dev):
        self._dev = dev
        self._cmd_queue = _PassthroughQueue()

    async def get_live_device(self, mac, params):
        return self._dev


def test_push_image_to_device_shows_image(tmp_path):
    dev = MagicMock()
    dev.is_alive = True
    dev.display.show_image = AsyncMock()
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"x")

    _run(live_jobs.push_image_to_device(_FakeOwner(dev), "AA:BB", {}, frame))

    dev.display.show_image.assert_awaited_once_with(str(frame))


def test_push_weather_to_device_sets_light_mode_then_weather():
    from divoom_lib.models import COMMANDS

    dev = MagicMock()
    dev.is_alive = True
    dev.send_command = AsyncMock(return_value=True)

    _run(live_jobs.push_weather_to_device(_FakeOwner(dev), "AA:BB", {}, 21, 1))

    assert dev.send_command.await_count == 2
    first, second = dev.send_command.await_args_list
    assert first.args[0] == COMMANDS["set light mode"]
    assert second.args[0] == COMMANDS["set temp"]


# ── run_sysmon: success path + cancellation (error/skip path already covered
#    by test_ble_phase2.py::test_run_sysmon_skips_tick_on_unrecoverable_drop) ─


def test_run_sysmon_pushes_and_resets_fails():
    with patch.object(live_jobs.media_source, "get_system_stats",
                       return_value={"cpu": 1.0}), \
         patch.object(live_jobs.media_source, "render_system_stats_frame",
                       return_value=Path("/tmp/sysmon.png")), \
         patch.object(live_jobs, "push_image_to_device", new=AsyncMock()) as push, \
         patch.object(live_jobs.asyncio, "sleep", side_effect=_Stop()):
        with pytest.raises(_Stop):
            _run(live_jobs.run_sysmon(MagicMock(), "AA:BB", {"size": 16}))
    push.assert_awaited_once()


def test_run_sysmon_cancelled_error_reraises():
    with patch.object(live_jobs.media_source, "get_system_stats",
                       side_effect=asyncio.CancelledError()):
        with pytest.raises(asyncio.CancelledError):
            _run(live_jobs.run_sysmon(MagicMock(), "AA:BB", {}))


# ── run_stocks: entirely uncovered before this ────────────────────────────


def test_run_stocks_no_symbol_returns_immediately():
    result = _run(live_jobs.run_stocks(MagicMock(), "AA:BB", {}))
    assert result is None


def test_run_stocks_pushes_on_data_and_resets_fails():
    with patch.object(live_jobs.media_source, "fetch_stock_ticker",
                       return_value={"price": 100}), \
         patch.object(live_jobs.media_source, "render_stock_ticker_frame",
                       return_value=Path("/tmp/stock.png")), \
         patch.object(live_jobs, "push_image_to_device", new=AsyncMock()) as push, \
         patch.object(live_jobs.asyncio, "sleep", side_effect=_Stop()):
        with pytest.raises(_Stop):
            _run(live_jobs.run_stocks(MagicMock(), "AA:BB", {"symbol": "aapl"}))
    push.assert_awaited_once()


def test_run_stocks_no_data_skips_push():
    with patch.object(live_jobs.media_source, "fetch_stock_ticker", return_value=None), \
         patch.object(live_jobs, "push_image_to_device", new=AsyncMock()) as push, \
         patch.object(live_jobs.asyncio, "sleep", side_effect=_Stop()):
        with pytest.raises(_Stop):
            _run(live_jobs.run_stocks(MagicMock(), "AA:BB", {"symbol": "AAPL"}))
    push.assert_not_awaited()


def test_run_stocks_cancelled_error_reraises():
    with patch.object(live_jobs.media_source, "fetch_stock_ticker",
                       side_effect=asyncio.CancelledError()):
        with pytest.raises(asyncio.CancelledError):
            _run(live_jobs.run_stocks(MagicMock(), "AA:BB", {"symbol": "AAPL"}))


def test_run_stocks_exception_backs_off_without_crashing():
    with patch.object(live_jobs.media_source, "fetch_stock_ticker",
                       side_effect=RuntimeError("network down")), \
         patch.object(live_jobs.asyncio, "sleep", side_effect=_Stop()):
        with pytest.raises(_Stop):
            _run(live_jobs.run_stocks(MagicMock(), "AA:BB", {"symbol": "AAPL"}))


# ── run_weather: entirely uncovered before this ───────────────────────────


def test_run_weather_pushes_and_resets_fails():
    info = SimpleNamespace(temperature_c=20, weather_type=1)
    with patch("divoom_lib.weather_provider.get_weather",
               new=AsyncMock(return_value=info)), \
         patch.object(live_jobs, "push_weather_to_device", new=AsyncMock()) as push, \
         patch.object(live_jobs.asyncio, "sleep", side_effect=_Stop()):
        with pytest.raises(_Stop):
            _run(live_jobs.run_weather(MagicMock(), "AA:BB", {}))
    push.assert_awaited_once()
    args = push.call_args.args
    assert args[3] == 20 and args[4] == 1


def test_run_weather_cancelled_error_reraises():
    with patch("divoom_lib.weather_provider.get_weather",
               new=AsyncMock(side_effect=asyncio.CancelledError())):
        with pytest.raises(asyncio.CancelledError):
            _run(live_jobs.run_weather(MagicMock(), "AA:BB", {}))


def test_run_weather_exception_backs_off_without_crashing():
    with patch("divoom_lib.weather_provider.get_weather",
               new=AsyncMock(side_effect=RuntimeError("provider down"))), \
         patch.object(live_jobs.asyncio, "sleep", side_effect=_Stop()):
        with pytest.raises(_Stop):
            _run(live_jobs.run_weather(MagicMock(), "AA:BB", {}))


# ── run_music: branch coverage beyond test_music_sync.py's first-tick cases ─


def test_run_music_unchanged_track_skips_second_push():
    """Same track/artist on tick 2 must skip the whole art-fetch/push block
    (the ``track != last_track or artist != last_artist`` branch going False)."""
    track = {"track": "A", "artist": "X", "artwork_url": "http://art"}
    p = Path("/tmp/divoom_fake_art_unchanged.png")
    p.write_bytes(b"x")
    calls = {"sleep": 0}

    async def fake_sleep(_d):
        calls["sleep"] += 1
        if calls["sleep"] >= 2:
            raise _Stop()

    with patch.object(live_jobs.media_source, "get_current_playing_track",
                       side_effect=[track, track]), \
         patch.object(live_jobs.media_source, "render_and_downsample_artwork",
                       return_value=p), \
         patch.object(live_jobs, "push_image_to_device", new=AsyncMock()) as push, \
         patch.object(live_jobs.asyncio, "sleep", side_effect=fake_sleep):
        with pytest.raises(_Stop):
            _run(live_jobs.run_music(MagicMock(), "AA:BB", {"size": 16}))

    push.assert_awaited_once(), "second (unchanged) tick must not push again"
    assert calls["sleep"] == 2


def test_run_music_no_art_url_skips_render_and_push():
    """artwork_url absent AND fetch_album_art_url returns falsy -> render is
    never called (the ``if art_url:`` branch going False)."""
    track = {"track": "B", "artist": "Y"}
    with patch.object(live_jobs.media_source, "get_current_playing_track",
                       side_effect=[track]), \
         patch.object(live_jobs.media_source, "fetch_album_art_url", return_value=None), \
         patch.object(live_jobs, "push_image_to_device", new=AsyncMock()) as push, \
         patch.object(live_jobs.asyncio, "sleep", side_effect=_Stop()):
        with pytest.raises(_Stop):
            _run(live_jobs.run_music(MagicMock(), "AA:BB", {"size": 16}))
    push.assert_not_awaited()


def test_run_music_render_returns_missing_path_skips_push():
    """render_and_downsample_artwork returning a path that doesn't exist must
    skip the push (the ``if out_path and out_path.exists():`` branch False)."""
    track = {"track": "C", "artist": "Z", "artwork_url": "http://art"}
    missing = Path("/tmp/divoom_definitely_missing_art_xyz.png")
    if missing.exists():
        missing.unlink()
    with patch.object(live_jobs.media_source, "get_current_playing_track",
                       side_effect=[track]), \
         patch.object(live_jobs.media_source, "render_and_downsample_artwork",
                       return_value=missing), \
         patch.object(live_jobs, "push_image_to_device", new=AsyncMock()) as push, \
         patch.object(live_jobs.asyncio, "sleep", side_effect=_Stop()):
        with pytest.raises(_Stop):
            _run(live_jobs.run_music(MagicMock(), "AA:BB", {"size": 16}))
    push.assert_not_awaited()


def test_run_music_cancelled_error_reraises():
    with patch.object(live_jobs.media_source, "get_current_playing_track",
                       side_effect=asyncio.CancelledError()):
        with pytest.raises(asyncio.CancelledError):
            _run(live_jobs.run_music(MagicMock(), "AA:BB", {"size": 16}))


def test_run_music_generic_exception_backs_off_without_crashing():
    calls = {"sleep": 0}

    async def fake_sleep(_d):
        calls["sleep"] += 1
        raise _Stop()

    with patch.object(live_jobs.media_source, "get_current_playing_track",
                       side_effect=RuntimeError("osascript boom")), \
         patch.object(live_jobs.asyncio, "sleep", side_effect=fake_sleep):
        with pytest.raises(_Stop):
            _run(live_jobs.run_music(MagicMock(), "AA:BB", {"size": 16}))
    assert calls["sleep"] == 1

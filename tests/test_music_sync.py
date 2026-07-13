"""R44 §6: music cover-art live sync now runs as a DAEMON live job
(`divoom_daemon.live_jobs.run_music`), not a GUI-side method — so a widget
keeps updating its device even after the GUI switches target.

These tests cover:
  - the daemon `run_music` change-detection (push on first/changed track) by
    driving exactly one loop iteration;
  - the GUI `toggle_music_sync` wiring → `live_job_start/stop`.
"""
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "divoom_gui"))

from divoom_daemon import live_jobs
from divoom_gui.media_sync import MediaSyncMixin


class _OneShotSleep(Exception):
    """Raised in place of asyncio.sleep to break run_music after one iteration."""


def _run_one_iteration(track_seq, owner):
    """Drive run_music for a single loop pass by making the first sleep raise."""
    async def _go():
        p = Path("/tmp/divoom_fake_art.png")
        p.write_bytes(b"x")
        with patch.object(live_jobs.media_source, "get_current_playing_track",
                          side_effect=track_seq), \
             patch.object(live_jobs.media_source, "fetch_album_art_url",
                          return_value="http://art"), \
             patch.object(live_jobs.media_source, "render_and_downsample_artwork",
                          return_value=p), \
             patch.object(live_jobs, "push_image_to_device", new=AsyncMock()) as push, \
             patch.object(live_jobs.asyncio, "sleep", side_effect=_OneShotSleep()):
            try:
                await live_jobs.run_music(owner, "AA:BB", {"size": 16})
            except _OneShotSleep:
                pass
            return push
    return asyncio.new_event_loop().run_until_complete(_go())


def test_pushes_on_first_track():
    push = _run_one_iteration([{"track": "A", "artist": "X"}], MagicMock())
    push.assert_awaited_once()


def test_pushes_on_track_change():
    push = _run_one_iteration([{"track": "B", "artist": "Y"}], MagicMock())
    push.assert_awaited_once()


def test_no_track_skips_push():
    push = _run_one_iteration([None], MagicMock())
    push.assert_not_awaited()


def test_run_music_has_unchanged_guard():
    """The push-skip-when-unchanged logic lives in run_music's loop body."""
    src = Path(live_jobs.__file__).read_text()
    assert "track != last_track or artist != last_artist" in src


# ── GUI toggle wiring → daemon live job ───────────────────────────────────

def _gui():
    from media_sync import MediaSyncMixin
    o = MediaSyncMixin.__new__(MediaSyncMixin)
    o.wall_slots = {}
    dev = MagicMock()
    dev.lan = None
    dev._conn = MagicMock(mac="AA:BB:CC")
    o.current_divoom = dev
    o._active_device_size = MagicMock(return_value=16)
    client = MagicMock()
    o._client = MagicMock(return_value=client)
    return o, client


def test_toggle_music_sync_starts_daemon_job():
    o, client = _gui()
    assert o.toggle_music_sync(True) is True
    client.live_job_start.assert_called_once()
    args = client.live_job_start.call_args.args
    assert args[0] == "AA:BB:CC" and args[1] == "music"


def test_toggle_music_sync_stops_daemon_job():
    o, client = _gui()
    assert o.toggle_music_sync(False) is True
    client.live_job_stop.assert_called_once_with("AA:BB:CC", "music")


# ── R61 coverage push: the rest of MediaSyncMixin ──────────────────────────
#
# media_sync.py bundles several unrelated GUI-facing widgets (system stats,
# stock tickers, cover-art push, notifications, sysmon/stocks/weather/music
# live-sync toggles, audio visualizer). Every external touchpoint (media
# source calls, BLE/device pushes, subprocess, disk I/O) is mocked below;
# nothing here touches real hardware.

import divoom_gui.media_sync as media_sync_mod


def _bare():
    """A fresh, unconfigured MediaSyncMixin instance for direct method tests."""
    return MediaSyncMixin.__new__(MediaSyncMixin)


# -- _get_device_size ---------------------------------------------------

def test_get_device_size_matches_64_in_name():
    o = _bare()
    o.discovered_list = [{"address": "AA", "name": "Pixoo64 Wall"}]
    assert o._get_device_size("AA") == 64


def test_get_device_size_matches_without_64_defaults_16():
    o = _bare()
    o.discovered_list = [{"address": "AA", "name": "Timoo"}]
    assert o._get_device_size("AA") == 16


def test_get_device_size_no_match_defaults_16():
    o = _bare()
    o.discovered_list = [{"address": "BB", "name": "Pixoo64"}]
    assert o._get_device_size("AA") == 16


# -- get_system_stats_preview -------------------------------------------

def test_get_system_stats_preview_success():
    o = _bare()
    o._active_device_size = MagicMock(return_value=16)
    o._frame_to_data_url = MagicMock(return_value="data:preview")
    stats = {"cpu": 12.0}
    with patch.object(media_sync_mod.media_source, "get_system_stats", return_value=stats), \
         patch.object(media_sync_mod.media_source, "render_system_stats_frame", return_value=Path("/tmp/s.png")):
        result = json.loads(o.get_system_stats_preview())
    assert result == {"ok": True, "size": 16, "stats": stats, "preview": "data:preview"}


def test_get_system_stats_preview_uses_explicit_size():
    o = _bare()
    o._active_device_size = MagicMock(side_effect=AssertionError("should not be called"))
    o._frame_to_data_url = MagicMock(return_value="")
    with patch.object(media_sync_mod.media_source, "get_system_stats", return_value={}), \
         patch.object(media_sync_mod.media_source, "render_system_stats_frame", return_value=Path("/tmp/s.png")):
        result = json.loads(o.get_system_stats_preview(size=32))
    assert result["ok"] is True and result["size"] == 32


def test_get_system_stats_preview_exception():
    o = _bare()
    with patch.object(media_sync_mod.media_source, "get_system_stats", side_effect=RuntimeError("boom")):
        result = json.loads(o.get_system_stats_preview())
    assert result == {"ok": False, "error": "boom"}


# -- apply_system_stats ---------------------------------------------------

def test_apply_system_stats_no_push_target():
    o = _bare()
    o.wall_slots = {}
    o.current_divoom = None
    with patch.object(media_sync_mod.media_source, "get_system_stats", return_value={"cpu": 1}):
        result = json.loads(o.apply_system_stats())
    assert result == {"success": False, "error": "No device connected", "stats": {"cpu": 1}}


def test_apply_system_stats_success():
    o = _bare()
    o.wall_slots = {}
    o.current_divoom = MagicMock()
    o._active_device_size = MagicMock(return_value=16)
    o._push_frame = MagicMock(return_value=True)
    o._frame_to_data_url = MagicMock(return_value="data:preview")
    with patch.object(media_sync_mod.media_source, "get_system_stats", return_value={"cpu": 1}), \
         patch.object(media_sync_mod.media_source, "render_system_stats_frame", return_value=Path("/tmp/s.png")):
        result = json.loads(o.apply_system_stats())
    assert result == {"success": True, "stats": {"cpu": 1}, "preview": "data:preview"}


def test_apply_system_stats_exception():
    o = _bare()
    with patch.object(media_sync_mod.media_source, "get_system_stats", side_effect=RuntimeError("boom")):
        result = json.loads(o.apply_system_stats())
    assert result == {"success": False, "error": "boom"}


# -- get_current_track_info ------------------------------------------------

def test_get_current_track_info_no_track():
    o = _bare()
    with patch.object(media_sync_mod.media_source, "get_current_playing_track", return_value=None):
        assert json.loads(o.get_current_track_info()) == {}


def test_get_current_track_info_with_artwork(tmp_path):
    o = _bare()
    art_path = tmp_path / "art.png"
    art_path.write_bytes(b"x")
    o._active_device_size = MagicMock(return_value=16)
    o._frame_to_data_url = MagicMock(return_value="data:art")
    track_info = {"track": "Song", "artist": "Artist", "source": "Music", "artwork_url": "http://art"}
    with patch.object(media_sync_mod.media_source, "get_current_playing_track", return_value=track_info), \
         patch.object(media_sync_mod.media_source, "render_and_downsample_artwork", return_value=art_path):
        result = json.loads(o.get_current_track_info())
    assert result == {
        "track": "Song", "artist": "Artist", "source": "Music",
        "artwork_url": "http://art", "preview": "data:art",
    }


def test_get_current_track_info_no_artwork_url_found():
    o = _bare()
    track_info = {"track": "Song", "artist": "Artist", "source": "Music"}
    with patch.object(media_sync_mod.media_source, "get_current_playing_track", return_value=track_info), \
         patch.object(media_sync_mod.media_source, "fetch_album_art_url", return_value=None):
        result = json.loads(o.get_current_track_info())
    assert result["artwork_url"] is None and result["preview"] == ""


def test_get_current_track_info_render_path_missing():
    o = _bare()
    o._active_device_size = MagicMock(return_value=16)
    track_info = {"track": "Song", "artist": "Artist", "source": "Music", "artwork_url": "http://art"}
    with patch.object(media_sync_mod.media_source, "get_current_playing_track", return_value=track_info), \
         patch.object(media_sync_mod.media_source, "render_and_downsample_artwork", return_value=None):
        result = json.loads(o.get_current_track_info())
    assert result["preview"] == ""


def test_get_current_track_info_exception():
    o = _bare()
    with patch.object(media_sync_mod.media_source, "get_current_playing_track", side_effect=RuntimeError("boom")):
        assert json.loads(o.get_current_track_info()) == {}


# -- push_music_cover_now --------------------------------------------------

def test_push_music_cover_now_no_track_cached():
    o = _bare()
    o.current_track_cache = None
    result = json.loads(o.push_music_cover_now())
    assert result == {"success": False, "error": "No track playing"}


def test_push_music_cover_now_cache_missing_track_key():
    o = _bare()
    o.current_track_cache = {"artist": "Artist"}
    result = json.loads(o.push_music_cover_now())
    assert result == {"success": False, "error": "No track playing"}


def test_push_music_cover_now_no_push_target():
    o = _bare()
    o.current_track_cache = {"track": "Song", "artist": "Artist"}
    o.wall_slots = {}
    o.current_divoom = None
    result = json.loads(o.push_music_cover_now())
    assert result == {"success": False, "error": "No device connected"}


def test_push_music_cover_now_no_art_url():
    o = _bare()
    o.current_track_cache = {"track": "Song", "artist": "Artist"}
    o.wall_slots = {}
    o.current_divoom = MagicMock()
    with patch.object(media_sync_mod.media_source, "fetch_album_art_url", return_value=None):
        result = json.loads(o.push_music_cover_now())
    assert result == {"success": False, "error": "Could not fetch album art"}


def test_push_music_cover_now_render_fails():
    o = _bare()
    o.current_track_cache = {"track": "Song", "artist": "Artist"}
    o.wall_slots = {}
    o.current_divoom = MagicMock()
    o._active_device_size = MagicMock(return_value=16)
    with patch.object(media_sync_mod.media_source, "fetch_album_art_url", return_value="http://art"), \
         patch.object(media_sync_mod.media_source, "render_and_downsample_artwork", return_value=None):
        result = json.loads(o.push_music_cover_now())
    assert result == {"success": False, "error": "Failed to render artwork"}


def test_push_music_cover_now_push_fails_still_updates_cache(tmp_path):
    o = _bare()
    cache = {"track": "Song", "artist": "Artist"}
    o.current_track_cache = cache
    o.wall_slots = {}
    o.current_divoom = MagicMock()
    o._active_device_size = MagicMock(return_value=16)
    o._push_frame = MagicMock(return_value=False)
    art_path = tmp_path / "art.png"
    art_path.write_bytes(b"x")
    with patch.object(media_sync_mod.media_source, "fetch_album_art_url", return_value="http://art"), \
         patch.object(media_sync_mod.media_source, "render_and_downsample_artwork", return_value=art_path):
        result = json.loads(o.push_music_cover_now())
    assert result == {"success": False, "preview": ""}
    assert cache["artwork_url"] == "http://art"
    assert cache["preview"] == ""


def test_push_music_cover_now_success(tmp_path):
    o = _bare()
    cache = {"track": "Song", "artist": "Artist"}
    o.current_track_cache = cache
    o.wall_slots = {}
    o.current_divoom = MagicMock()
    o._active_device_size = MagicMock(return_value=16)
    o._push_frame = MagicMock(return_value=True)
    o._frame_to_data_url = MagicMock(return_value="data:art")
    art_path = tmp_path / "art.png"
    art_path.write_bytes(b"x")
    with patch.object(media_sync_mod.media_source, "fetch_album_art_url", return_value="http://art"), \
         patch.object(media_sync_mod.media_source, "render_and_downsample_artwork", return_value=art_path):
        result = json.loads(o.push_music_cover_now())
    assert result == {"success": True, "preview": "data:art"}
    assert cache["preview"] == "data:art"


def test_push_music_cover_now_exception():
    o = _bare()
    o.current_track_cache = {"track": "Song", "artist": "Artist"}
    o.wall_slots = {}
    o.current_divoom = MagicMock()
    o._active_device_size = MagicMock(side_effect=RuntimeError("boom"))
    with patch.object(media_sync_mod.media_source, "fetch_album_art_url", return_value="http://art"):
        result = json.loads(o.push_music_cover_now())
    assert result == {"success": False, "error": "boom"}


# -- _active_device_size ---------------------------------------------------

def test_active_device_size_wall_slots_min():
    o = _bare()
    o.wall_slots = {"a": {"size": 32}, "b": {"size": 16}}
    assert o._active_device_size() == 16


def test_active_device_size_wall_slots_no_dict_sizes_falls_back_default():
    o = _bare()
    o.wall_slots = {"a": "not-a-dict"}
    assert o._active_device_size(default=16) == 16


def test_active_device_size_from_conn_mac():
    o = _bare()
    o.wall_slots = {}
    o.discovered_list = [{"address": "AA:BB", "name": "Pixoo64"}]
    dev = MagicMock()
    dev._conn = MagicMock(mac="AA:BB")
    dev.mac = None
    o.current_divoom = dev
    assert o._active_device_size() == 64


def test_active_device_size_exception_returns_default():
    o = _bare()  # no wall_slots attribute set at all -> AttributeError -> except -> default
    assert o._active_device_size(default=16) == 16


def test_active_device_size_no_mac_returns_default():
    o = _bare()
    o.wall_slots = {}
    o.current_divoom = None  # no mac available at all -> falls through to `return default`
    assert o._active_device_size(default=16) == 16


# -- _push_frame (wall_slots branch) ----------------------------------------

def test_push_frame_wall_slots_rebuild_fails():
    o = _bare()
    o.wall_slots = {"a": {"size": 16}}
    o._rebuild_wall_instance = MagicMock(return_value=False)
    assert o._push_frame("/tmp/f.png", 16) is False


def test_push_frame_wall_slots_pushes_via_wall_instance():
    o = _bare()
    o.wall_slots = {"a": {"size": 16}}
    o._rebuild_wall_instance = MagicMock(return_value=True)
    wall = MagicMock()
    wall.connect = AsyncMock()
    wall.show_image = AsyncMock(return_value=True)
    o.wall_instance = wall
    o._run_async = lambda coro: asyncio.new_event_loop().run_until_complete(coro)
    assert o._push_frame("/tmp/f.png", 16) is True
    wall.connect.assert_awaited_once()
    wall.show_image.assert_awaited_once_with("/tmp/f.png")


# -- _frame_to_data_url ------------------------------------------------------

def test_frame_to_data_url_missing_file_returns_empty():
    assert MediaSyncMixin._frame_to_data_url("/nonexistent/path/frame.png") == ""


def test_frame_to_data_url_success(tmp_path):
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"hello")
    import base64 as _b64
    expected = "data:image/png;base64," + _b64.b64encode(b"hello").decode("ascii")
    assert MediaSyncMixin._frame_to_data_url(frame) == expected


# -- get_ticker_preview -------------------------------------------------

def test_get_ticker_preview_success():
    o = _bare()
    o._active_device_size = MagicMock(return_value=16)
    data = {"price": 100.0, "change": 1.0, "pct_change": 1.0}
    with patch.object(media_sync_mod.media_source, "fetch_stock_ticker", return_value=data), \
         patch.object(media_sync_mod.media_source, "render_stock_ticker_frame", return_value=Path("/tmp/t.png")), \
         patch.object(media_sync_mod.MediaSyncMixin, "_frame_to_data_url", return_value="data:t"):
        result = json.loads(o.get_ticker_preview("AAPL"))
    assert result["ok"] is True and result["price"] == 100.0 and result["preview"] == "data:t"


def test_get_ticker_preview_no_data():
    o = _bare()
    with patch.object(media_sync_mod.media_source, "fetch_stock_ticker", return_value=None):
        result = json.loads(o.get_ticker_preview("AAPL"))
    assert result == {"ok": False, "error": "no data"}


def test_get_ticker_preview_exception():
    o = _bare()
    with patch.object(media_sync_mod.media_source, "fetch_stock_ticker", side_effect=RuntimeError("boom")):
        result = json.loads(o.get_ticker_preview("AAPL"))
    assert result == {"ok": False, "error": "boom"}


# -- apply_stock_ticker ------------------------------------------------

def test_apply_stock_ticker_no_data():
    o = _bare()
    with patch.object(media_sync_mod.media_source, "fetch_stock_ticker", return_value=None):
        result = json.loads(o.apply_stock_ticker("AAPL"))
    assert result == {"success": False, "error": "Could not fetch ticker data"}


def test_apply_stock_ticker_no_push_target():
    o = _bare()
    o.wall_slots = {}
    o.current_divoom = None
    with patch.object(media_sync_mod.media_source, "fetch_stock_ticker", return_value={"price": 1, "change": 0, "pct_change": 0}):
        result = json.loads(o.apply_stock_ticker("AAPL"))
    assert result == {"success": False, "error": "No device connected"}


def test_apply_stock_ticker_success():
    o = _bare()
    o.wall_slots = {}
    o.current_divoom = MagicMock()
    o._active_device_size = MagicMock(return_value=16)
    o._push_frame = MagicMock(return_value=True)
    o._frame_to_data_url = MagicMock(return_value="data:t")
    data = {"price": 100.0, "change": 1.0, "pct_change": 1.0}
    with patch.object(media_sync_mod.media_source, "fetch_stock_ticker", return_value=data), \
         patch.object(media_sync_mod.media_source, "render_stock_ticker_frame", return_value=Path("/tmp/t.png")):
        result = json.loads(o.apply_stock_ticker("AAPL"))
    assert result == {"success": True, "preview": "data:t", "price": 100.0, "change": 1.0, "pct_change": 1.0}


def test_apply_stock_ticker_exception():
    o = _bare()
    with patch.object(media_sync_mod.media_source, "fetch_stock_ticker", side_effect=RuntimeError("boom")):
        result = json.loads(o.apply_stock_ticker("AAPL"))
    assert result == {"success": False, "error": "boom"}


def test_tickers_path_under_config_dir():
    o = _bare()
    path = o._tickers_path()
    assert path == Path.home() / ".config" / "divoom-control" / "tickers.json"


# -- tickers.json read/write/seed -------------------------------------------

def test_get_tickers_missing_file_seeds(tmp_path, monkeypatch):
    o = _bare()
    fake_path = tmp_path / "tickers.json"
    o._tickers_path = MagicMock(return_value=fake_path)
    with patch.object(media_sync_mod.MediaSyncMixin, "_seed_tickers_from_macos", return_value=["AAPL"]):
        result = json.loads(o.get_tickers())
    assert result == ["AAPL"]
    assert json.loads(fake_path.read_text()) == ["AAPL"]


def test_get_tickers_existing_valid_file(tmp_path):
    o = _bare()
    fake_path = tmp_path / "tickers.json"
    fake_path.write_text(json.dumps(["MSFT", "TSLA"]))
    o._tickers_path = MagicMock(return_value=fake_path)
    result = json.loads(o.get_tickers())
    assert result == ["MSFT", "TSLA"]


def test_get_tickers_corrupt_file_falls_back_to_seed(tmp_path):
    o = _bare()
    fake_path = tmp_path / "tickers.json"
    fake_path.write_text("{not json")
    o._tickers_path = MagicMock(return_value=fake_path)
    with patch.object(media_sync_mod.MediaSyncMixin, "_seed_tickers_from_macos", return_value=["ETH-USD"]):
        result = json.loads(o.get_tickers())
    assert result == ["ETH-USD"]


def test_set_tickers_writes_deduped_upper_list(tmp_path):
    o = _bare()
    fake_path = tmp_path / "sub" / "tickers.json"
    o._tickers_path = MagicMock(return_value=fake_path)
    assert o.set_tickers(["aapl", " AAPL ", "msft"]) is True
    assert json.loads(fake_path.read_text()) == ["AAPL", "MSFT"]


def test_set_tickers_exception_returns_false():
    o = _bare()
    o._tickers_path = MagicMock(return_value=Path("/tmp/tickers.json"))
    with patch.object(media_sync_mod, "atomic_write_text", side_effect=RuntimeError("disk full")):
        assert o.set_tickers(["AAPL"]) is False


# -- _seed_tickers_from_macos ------------------------------------------------

def test_seed_tickers_from_macos_parses_symbols():
    fake_proc = MagicMock(stdout='"symbol" = "AAPL"; "symbol" = "GOOGL";')
    with patch("subprocess.run", return_value=fake_proc):
        result = MediaSyncMixin._seed_tickers_from_macos()
    assert result == ["AAPL", "GOOGL"]


def test_seed_tickers_from_macos_dedupes_repeated_symbol():
    # A repeated symbol exercises the "already in cleaned, skip" branch of the loop.
    fake_proc = MagicMock(stdout='"symbol" = "AAPL"; "symbol" = "AAPL"; "symbol" = "MSFT";')
    with patch("subprocess.run", return_value=fake_proc):
        result = MediaSyncMixin._seed_tickers_from_macos()
    assert result == ["AAPL", "MSFT"]


def test_seed_tickers_from_macos_no_matches_returns_default():
    fake_proc = MagicMock(stdout="nothing useful here")
    with patch("subprocess.run", return_value=fake_proc):
        result = MediaSyncMixin._seed_tickers_from_macos()
    assert result == ["AAPL", "GOOGL", "MSFT", "TSLA", "BTC-USD", "ETH-USD"]


def test_seed_tickers_from_macos_subprocess_raises_returns_default():
    with patch("subprocess.run", side_effect=OSError("no defaults binary")):
        result = MediaSyncMixin._seed_tickers_from_macos()
    assert result == ["AAPL", "GOOGL", "MSFT", "TSLA", "BTC-USD", "ETH-USD"]


# -- trigger_notification -----------------------------------------------

def test_trigger_notification_no_push_target():
    o = _bare()
    o.wall_slots = {}
    o.current_divoom = None
    result = json.loads(o.trigger_notification("mail"))
    assert result == {"success": False, "error": "No device connected"}


def _run_coro_now(coro, loop):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_trigger_notification_ble_sends_hw_alert_and_pushes():
    o = _bare()
    o.wall_slots = {}
    dev = MagicMock()
    dev.lan = None
    dev.device = MagicMock()
    dev.device.send_command = AsyncMock()
    o.current_divoom = dev
    o.loop_thread = MagicMock()
    o._active_device_size = MagicMock(return_value=16)
    o._push_frame = MagicMock(return_value=True)
    o._frame_to_data_url = MagicMock(return_value="data:n")
    with patch.object(media_sync_mod.media_source, "render_notification_frame", return_value=Path("/tmp/n.png")), \
         patch("asyncio.run_coroutine_threadsafe", side_effect=_run_coro_now):
        result = json.loads(o.trigger_notification("whatsapp"))
    assert result == {"success": True, "preview": "data:n"}
    dev.device.send_command.assert_awaited_once_with(0x60, [6, 34, 197, 94])


def test_trigger_notification_hw_alert_exception_is_swallowed():
    o = _bare()
    o.wall_slots = {}
    dev = MagicMock()
    dev.lan = None
    dev.device = MagicMock()
    dev.device.send_command = AsyncMock(side_effect=RuntimeError("ble down"))
    o.current_divoom = dev
    o.loop_thread = MagicMock()
    o._active_device_size = MagicMock(return_value=16)
    o._push_frame = MagicMock(return_value=True)
    o._frame_to_data_url = MagicMock(return_value="data:n")
    with patch.object(media_sync_mod.media_source, "render_notification_frame", return_value=Path("/tmp/n.png")), \
         patch("asyncio.run_coroutine_threadsafe", side_effect=_run_coro_now):
        result = json.loads(o.trigger_notification("mail"))
    assert result["success"] is True


def _raise_and_close(coro, loop):
    coro.close()  # avoid an unawaited-coroutine warning while still failing to schedule
    raise RuntimeError("no running loop")


def test_trigger_notification_hw_alert_outer_exception_swallowed():
    """A failure scheduling the BLE hw-alert must not abort the notification
    push — it's swallowed by the outer try/except around that block."""
    o = _bare()
    o.wall_slots = {}
    dev = MagicMock()
    dev.lan = None
    dev.device = MagicMock()
    o.current_divoom = dev
    o.loop_thread = MagicMock()
    o._active_device_size = MagicMock(return_value=16)
    o._push_frame = MagicMock(return_value=True)
    o._frame_to_data_url = MagicMock(return_value="data:n")
    with patch.object(media_sync_mod.media_source, "render_notification_frame", return_value=Path("/tmp/n.png")), \
         patch("asyncio.run_coroutine_threadsafe", side_effect=_raise_and_close):
        result = json.loads(o.trigger_notification("mail"))
    assert result["success"] is True


def test_trigger_notification_lan_device_skips_hw_alert():
    o = _bare()
    o.wall_slots = {}
    dev = MagicMock()
    dev.lan = MagicMock()  # truthy -> LAN device, no BLE hw alert
    o.current_divoom = dev
    o._active_device_size = MagicMock(return_value=16)
    o._push_frame = MagicMock(return_value=True)
    o._frame_to_data_url = MagicMock(return_value="data:n")
    with patch.object(media_sync_mod.media_source, "render_notification_frame", return_value=Path("/tmp/n.png")), \
         patch("asyncio.run_coroutine_threadsafe") as run_coro:
        result = json.loads(o.trigger_notification("mail"))
    run_coro.assert_not_called()
    assert result["success"] is True


def test_trigger_notification_no_device_object_skips_hw_alert():
    o = _bare()
    o.wall_slots = {}
    dev = MagicMock()
    dev.lan = None
    dev.device = None
    o.current_divoom = dev
    o._active_device_size = MagicMock(return_value=16)
    o._push_frame = MagicMock(return_value=True)
    o._frame_to_data_url = MagicMock(return_value="data:n")
    with patch.object(media_sync_mod.media_source, "render_notification_frame", return_value=Path("/tmp/n.png")), \
         patch("asyncio.run_coroutine_threadsafe") as run_coro:
        result = json.loads(o.trigger_notification("mail"))
    run_coro.assert_not_called()
    assert result["success"] is True


def test_trigger_notification_wall_slots_with_no_current_divoom():
    o = _bare()
    o.wall_slots = {"a": {"size": 16}}
    o.current_divoom = None
    o._active_device_size = MagicMock(return_value=16)
    o._push_frame = MagicMock(return_value=True)
    o._frame_to_data_url = MagicMock(return_value="data:n")
    with patch.object(media_sync_mod.media_source, "render_notification_frame", return_value=Path("/tmp/n.png")):
        result = json.loads(o.trigger_notification("mail"))
    assert result["success"] is True


def test_trigger_notification_exception_path():
    o = _bare()
    o.wall_slots = {}
    o.current_divoom = MagicMock()
    o._active_device_size = MagicMock(side_effect=RuntimeError("boom"))
    result = json.loads(o.trigger_notification("mail"))
    assert result == {"success": False, "error": "boom"}


# -- _active_device_mac / _get_live_params -----------------------------

def test_active_device_mac_wall_slots():
    o = _bare()
    o.wall_slots = {"a": {"size": 16}}
    assert o._active_device_mac() == "MatrixWall"


def test_active_device_mac_no_device():
    o = _bare()
    o.wall_slots = {}
    o.current_divoom = None
    assert o._active_device_mac() is None


def test_active_device_mac_lan():
    o = _bare()
    o.wall_slots = {}
    dev = MagicMock()
    dev.lan = MagicMock(device_ip="192.168.1.5")
    o.current_divoom = dev
    assert o._active_device_mac() == "LAN:192.168.1.5"


def test_active_device_mac_ble():
    o = _bare()
    o.wall_slots = {}
    dev = MagicMock()
    dev.lan = None
    dev._conn = MagicMock(mac="AA:BB")
    o.current_divoom = dev
    assert o._active_device_mac() == "AA:BB"


def test_get_live_params_wall_slots():
    o = _bare()
    o._active_device_size = MagicMock(return_value=16)
    o.wall_slots = {"a": {"size": 16}}
    o.current_divoom = None
    params = o._get_live_params()
    assert params["wall_slots"] == o.wall_slots
    assert "lan_token" not in params


def test_get_live_params_lan_token():
    o = _bare()
    o._active_device_size = MagicMock(return_value=16)
    o.wall_slots = {}
    dev = MagicMock()
    dev.lan = MagicMock(local_token=42)
    o.current_divoom = dev
    params = o._get_live_params()
    assert params["lan_token"] == 42


# -- toggle_sysmon_sync / toggle_stocks_sync / toggle_weather_sync -----

def _toggle_gui(mac="AA:BB:CC"):
    o = _bare()
    o.wall_slots = {}
    dev = MagicMock()
    dev.lan = None
    dev._conn = MagicMock(mac=mac)
    o.current_divoom = dev
    o._active_device_size = MagicMock(return_value=16)
    client = MagicMock()
    o._client = MagicMock(return_value=client)
    return o, client


def test_toggle_sysmon_sync_no_client():
    o, _ = _toggle_gui()
    o._client = MagicMock(return_value=None)
    assert o.toggle_sysmon_sync(True) is False


def test_toggle_sysmon_sync_no_mac():
    o, client = _toggle_gui()
    o.current_divoom = None
    o.wall_slots = {}
    assert o.toggle_sysmon_sync(True) is False
    client.live_job_start.assert_not_called()


def test_toggle_sysmon_sync_start_stop():
    o, client = _toggle_gui()
    assert o.toggle_sysmon_sync(True) is True
    client.live_job_start.assert_called_once_with("AA:BB:CC", "sysmon", o._get_live_params())
    assert o.toggle_sysmon_sync(False) is True
    client.live_job_stop.assert_called_once_with("AA:BB:CC", "sysmon")


def test_toggle_stocks_sync_no_client():
    o, _ = _toggle_gui()
    o._client = MagicMock(return_value=None)
    assert o.toggle_stocks_sync(True, "AAPL") is False


def test_toggle_stocks_sync_no_mac():
    o, client = _toggle_gui()
    o.current_divoom = None
    o.wall_slots = {}
    assert o.toggle_stocks_sync(True, "AAPL") is False


def test_toggle_stocks_sync_start_with_symbol():
    o, client = _toggle_gui()
    assert o.toggle_stocks_sync(True, "AAPL") is True
    args = client.live_job_start.call_args.args
    assert args[0] == "AA:BB:CC" and args[1] == "stocks"
    assert args[2]["symbol"] == "AAPL"
    assert o.stocks_symbol == "AAPL"


def test_toggle_stocks_sync_start_uses_saved_symbol_when_none_given():
    o, client = _toggle_gui()
    o.stocks_symbol = "TSLA"
    assert o.toggle_stocks_sync(True) is True
    args = client.live_job_start.call_args.args
    assert args[2]["symbol"] == "TSLA"


def test_toggle_stocks_sync_stop():
    o, client = _toggle_gui()
    assert o.toggle_stocks_sync(False) is True
    client.live_job_stop.assert_called_once_with("AA:BB:CC", "stocks")


def test_toggle_music_sync_no_client():
    o, _ = _toggle_gui()
    o._client = MagicMock(return_value=None)
    assert o.toggle_music_sync(True) is False


def test_toggle_music_sync_no_mac():
    o, client = _toggle_gui()
    o.current_divoom = None
    o.wall_slots = {}
    assert o.toggle_music_sync(True) is False
    client.live_job_start.assert_not_called()


def test_toggle_weather_sync_no_client():
    o, _ = _toggle_gui()
    o._client = MagicMock(return_value=None)
    assert o.toggle_weather_sync(True) is False


def test_toggle_weather_sync_no_mac():
    o, client = _toggle_gui()
    o.current_divoom = None
    o.wall_slots = {}
    assert o.toggle_weather_sync(True) is False


def test_toggle_weather_sync_start_stop():
    o, client = _toggle_gui()
    assert o.toggle_weather_sync(True) is True
    client.live_job_start.assert_called_once_with("AA:BB:CC", "weather", o._get_live_params())
    assert o.toggle_weather_sync(False) is True
    client.live_job_stop.assert_called_once_with("AA:BB:CC", "weather")


# -- audio visualizer bindings --------------------------------------------

def test_toggle_audio_visualizer_enable_creates_worker():
    o = _bare()
    fake_worker = MagicMock()
    with patch.object(media_sync_mod, "AudioVisualizerWorker", return_value=fake_worker) as cls:
        assert o.toggle_audio_visualizer(True) is True
    cls.assert_called_once()
    fake_worker.start.assert_called_once()
    assert o._audio_worker is fake_worker


def test_toggle_audio_visualizer_enable_when_already_running_noop():
    o = _bare()
    existing = MagicMock()
    o._audio_worker = existing
    with patch.object(media_sync_mod, "AudioVisualizerWorker") as cls:
        assert o.toggle_audio_visualizer(True) is True
    cls.assert_not_called()
    existing.start.assert_not_called()


def test_toggle_audio_visualizer_disable_stops_worker():
    o = _bare()
    existing = MagicMock()
    o._audio_worker = existing
    assert o.toggle_audio_visualizer(False) is True
    existing.stop.assert_called_once()
    assert o._audio_worker is None


def test_toggle_audio_visualizer_disable_noop_when_no_worker():
    o = _bare()
    o._audio_worker = None
    assert o.toggle_audio_visualizer(False) is True


def test_get_audio_levels_with_worker():
    o = _bare()
    worker = MagicMock()
    worker.levels = [1.0] * 10
    worker.loopback_active = True
    worker.device_name = "BlackHole"
    o._audio_worker = worker
    result = json.loads(o.get_audio_levels())
    assert result == {"levels": [1.0] * 10, "loopback_active": True, "device_name": "BlackHole"}


def test_get_audio_levels_no_worker():
    o = _bare()
    result = json.loads(o.get_audio_levels())
    assert result == {"levels": [0.0] * 10, "loopback_active": False, "device_name": "None"}

import json
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from divoom_lib.utils import media_source
from divoom_lib.utils import media_source_feishin as feishin_mod


def test_get_current_playing_track_spotify():
    empty_mock = MagicMock()
    empty_mock.stdout = ""
    spotify_mock = MagicMock()
    spotify_mock.stdout = "Song Title -|- Artist Name"
    with patch("subprocess.run", side_effect=[empty_mock, spotify_mock]) as mock_run:
        with patch.object(feishin_mod, "_feishin_is_running", return_value=False):
            res = media_source.get_current_playing_track()
        assert res == {
            "track": "Song Title",
            "artist": "Artist Name",
            "source": "Spotify",
            "artwork_url": None,
        }
        # Kaset (empty) + Spotify (hit) — Music.app not reached
        assert mock_run.call_count == 2


def test_get_current_playing_track_kaset():
    kaset_json = json.dumps({
        "currentTrack": {
            "name": "Test Song",
            "artist": "Test Artist",
            "artworkURL": "https://i.ytimg.com/vi/test/hqdefault.jpg",
        },
        "isPlaying": True,
    })
    mock_proc = MagicMock()
    mock_proc.stdout = kaset_json
    with patch("subprocess.run", return_value=mock_proc) as mock_run:
        with patch.object(feishin_mod, "_feishin_is_running", return_value=False):
            res = media_source.get_current_playing_track()
        assert res == {
            "track": "Test Song",
            "artist": "Test Artist",
            "source": "Kaset",
            "artwork_url": "https://i.ytimg.com/vi/test/hqdefault.jpg",
        }
        mock_run.assert_called_once()


def test_get_feishin_playing_track():
    """Feishin returns a track via Navidrome Subsonic API."""
    api_response = {
        "subsonic-response": {
            "status": "ok",
            "nowPlaying": {
                "entry": [{
                    "title": "Feishin Song",
                    "artist": "Feishin Artist",
                    "coverArt": "ar-42",
                }]
            }
        }
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(api_response).encode("utf-8")
    with patch.object(feishin_mod, "_feishin_is_running", return_value=True), \
         patch.object(feishin_mod, "_feishin_creds",
                      return_value=("http://server:4533", "u=admin&s=abc&t=def")), \
         patch("urllib.request.urlopen", return_value=MagicMock(__enter__=lambda self: mock_resp)):
        res = feishin_mod.get_feishin_playing_track()
    assert res == {
        "track": "Feishin Song",
        "artist": "Feishin Artist",
        "source": "Feishin",
        "artwork_url": "http://server:4533/rest/getCoverArt.view?f=json&c=divoom&v=1.16.0&u=admin&s=abc&t=def&id=ar-42&size=500",
    }


def test_get_feishin_nothing_playing():
    """Feishin running but no track playing."""
    api_response = {
        "subsonic-response": {
            "status": "ok",
            "nowPlaying": {}
        }
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(api_response).encode("utf-8")
    with patch.object(feishin_mod, "_feishin_is_running", return_value=True), \
         patch.object(feishin_mod, "_feishin_creds",
                      return_value=("http://server:4533", "u=admin&s=abc&t=def")), \
         patch("urllib.request.urlopen", return_value=MagicMock(__enter__=lambda self: mock_resp)):
        res = feishin_mod.get_feishin_playing_track()
    assert res is None


def test_get_feishin_not_running():
    """Feishin not running → no track."""
    with patch.object(feishin_mod, "_feishin_is_running", return_value=False):
        res = feishin_mod.get_feishin_playing_track()
    assert res is None


def test_get_feishin_no_creds():
    """Feishin running but no credentials found."""
    with patch.object(feishin_mod, "_feishin_is_running", return_value=True), \
         patch.object(feishin_mod, "_feishin_creds", return_value=None):
        res = feishin_mod.get_feishin_playing_track()
    assert res is None


def test_fetch_album_art_url():
    mock_response_data = {
        "results": [{"artworkUrl100": "https://example.com/cover/100x100bb.jpg"}]
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_response_data).encode("utf-8")
    
    with patch("urllib.request.urlopen", return_value=MagicMock(__enter__=lambda self: mock_resp)):
        url = media_source.fetch_album_art_url("Track", "Artist")
        assert url == "https://example.com/cover/500x500bb.jpg"


def test_render_and_downsample_artwork(tmp_path):
    # Create a dummy high-resolution image
    high_res = Image.new("RGB", (500, 500), (255, 0, 0))
    img_byte_arr = BytesIO()
    high_res.save(img_byte_arr, format="JPEG")
    img_bytes = img_byte_arr.getvalue()

    mock_resp = MagicMock()
    mock_resp.read.return_value = img_bytes

    with patch("urllib.request.urlopen", return_value=MagicMock(__enter__=lambda self: mock_resp)):
        # Override scratch_dir in media_source to use tmp_path
        with patch("divoom_lib.utils.media_source.Path") as mock_path:
            mock_path.return_value.parent.parent.parent = tmp_path
            # Set up mock behavior for Path object operations
            mock_path_inst = MagicMock()
            mock_path_inst.parent.parent.parent = tmp_path
            mock_path.return_value = mock_path_inst
            
            # Run the downsample
            out_path = media_source.render_and_downsample_artwork("https://example.com/art.jpg", size=16)
            
            assert out_path is not None
            # Verify the file was written and is indeed 16x16
            written_img = Image.open(out_path)
            assert written_img.size == (16, 16)
            assert written_img.mode == "RGB"


def test_fetch_stock_ticker():
    mock_data = {
        "chart": {
            "result": [
                {
                    "meta": {
                        "regularMarketPrice": 150.0,
                        "chartPreviousClose": 145.0,
                    }
                }
            ]
        }
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_data).encode("utf-8")

    with patch("urllib.request.urlopen", return_value=MagicMock(__enter__=lambda self: mock_resp)):
        res = media_source.fetch_stock_ticker("AAPL")
        assert res == {
            "price": 150.0,
            "change": 5.0,
            "pct_change": 3.45,
        }


def test_render_stock_ticker_frame(tmp_path):
    data = {"price": 150.0, "change": 5.0, "pct_change": 3.45}
    with patch("divoom_lib.utils.media_source.Path") as mock_path:
        mock_path.return_value.parent.parent.parent = tmp_path
        out_path = media_source.render_stock_ticker_frame("AAPL", data, size=16)
        assert out_path.exists()
        img = Image.open(out_path)
        assert img.size == (16, 16)


def test_get_system_stats():
    with patch("psutil.cpu_percent", return_value=12.5), \
         patch("psutil.virtual_memory") as mock_mem, \
         patch("psutil.sensors_battery", return_value=MagicMock(percent=85)):
        mock_mem.return_value.percent = 45.2
        stats = media_source.get_system_stats()
        assert stats == {"cpu": 12, "mem": 45, "battery": 85}


def test_render_system_stats_frame(tmp_path):
    stats = {"cpu": 12, "mem": 45, "battery": 85}
    with patch("divoom_lib.utils.media_source.Path") as mock_path:
        mock_path.return_value.parent.parent.parent = tmp_path
        out_path = media_source.render_system_stats_frame(stats, size=16)
        assert out_path.exists()
        img = Image.open(out_path)
        assert img.size == (16, 16)


# ── R61 coverage push: get_current_playing_track branches ──────────────────


def test_get_current_playing_track_non_darwin_returns_none():
    with patch.object(media_source.sys, "platform", "linux"), \
         patch("subprocess.run") as mock_run:
        assert media_source.get_current_playing_track() is None
    mock_run.assert_not_called()


def test_get_current_playing_track_feishin_hit_skips_applescript():
    track = {"track": "T", "artist": "A", "source": "Feishin", "artwork_url": None}
    with patch.object(media_source, "get_feishin_playing_track", return_value=track), \
         patch("subprocess.run") as mock_run:
        res = media_source.get_current_playing_track()
    assert res == track
    mock_run.assert_not_called()


def test_get_current_playing_track_kaset_not_playing_falls_through():
    """isPlaying False -> the 64->75 branch skips the Kaset return."""
    kaset_json = json.dumps({"currentTrack": {"name": "X", "artist": "Y"}, "isPlaying": False})
    kaset_mock = MagicMock(stdout=kaset_json)
    empty_mock = MagicMock(stdout="")
    with patch("subprocess.run", side_effect=[kaset_mock, empty_mock, empty_mock]) as mock_run, \
         patch.object(feishin_mod, "_feishin_is_running", return_value=False):
        res = media_source.get_current_playing_track()
    assert res is None
    assert mock_run.call_count == 3


def test_get_current_playing_track_kaset_empty_name_falls_through():
    """currentTrack.name empty -> the 69->75 branch skips the Kaset return."""
    kaset_json = json.dumps({"currentTrack": {"name": "", "artist": "Y"}, "isPlaying": True})
    kaset_mock = MagicMock(stdout=kaset_json)
    empty_mock = MagicMock(stdout="")
    with patch("subprocess.run", side_effect=[kaset_mock, empty_mock, empty_mock]), \
         patch.object(feishin_mod, "_feishin_is_running", return_value=False):
        res = media_source.get_current_playing_track()
    assert res is None


def test_get_current_playing_track_kaset_exception_falls_through():
    empty_mock = MagicMock(stdout="")
    with patch("subprocess.run", side_effect=[OSError("boom"), empty_mock, empty_mock]), \
         patch.object(feishin_mod, "_feishin_is_running", return_value=False):
        res = media_source.get_current_playing_track()
    assert res is None


def test_get_current_playing_track_spotify_exception_falls_through():
    empty_mock = MagicMock(stdout="")
    music_mock = MagicMock(stdout="Tune -|- Band")
    with patch("subprocess.run", side_effect=[empty_mock, OSError("boom"), music_mock]), \
         patch.object(feishin_mod, "_feishin_is_running", return_value=False):
        res = media_source.get_current_playing_track()
    assert res == {"track": "Tune", "artist": "Band", "source": "Apple Music", "artwork_url": None}


def test_get_current_playing_track_apple_music_hit():
    empty_mock = MagicMock(stdout="")
    music_mock = MagicMock(stdout="Tune -|- Band")
    with patch("subprocess.run", side_effect=[empty_mock, empty_mock, music_mock]) as mock_run, \
         patch.object(feishin_mod, "_feishin_is_running", return_value=False):
        res = media_source.get_current_playing_track()
    assert res == {"track": "Tune", "artist": "Band", "source": "Apple Music", "artwork_url": None}
    assert mock_run.call_count == 3


def test_get_current_playing_track_music_exception_returns_none():
    empty_mock = MagicMock(stdout="")
    with patch("subprocess.run", side_effect=[empty_mock, empty_mock, OSError("boom")]), \
         patch.object(feishin_mod, "_feishin_is_running", return_value=False):
        res = media_source.get_current_playing_track()
    assert res is None


def test_get_current_playing_track_nothing_playing_returns_none():
    empty_mock = MagicMock(stdout="")
    with patch("subprocess.run", return_value=empty_mock), \
         patch.object(feishin_mod, "_feishin_is_running", return_value=False):
        res = media_source.get_current_playing_track()
    assert res is None


# ── R61 coverage push: fetch_album_art_url error/malformed paths ───────────


def test_fetch_album_art_url_no_results_returns_none():
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"results": []}).encode("utf-8")
    with patch("urllib.request.urlopen", return_value=MagicMock(__enter__=lambda self: mock_resp)):
        assert media_source.fetch_album_art_url("Track", "Artist") is None


def test_fetch_album_art_url_network_error_returns_none():
    with patch("urllib.request.urlopen", side_effect=OSError("network down")):
        assert media_source.fetch_album_art_url("Track", "Artist") is None


# ── R61 coverage push: render_and_downsample_artwork error/fallback paths ──


class _HidingImageProxy:
    """Proxies to the real PIL.Image module but raises AttributeError for
    the given attribute names, to exercise the resample-filter fallback
    chain (Image.Resampling.LANCZOS -> Image.LANCZOS -> Image.ANTIALIAS)."""

    def __init__(self, hidden):
        self._hidden = hidden

    def __getattr__(self, name):
        if name in self._hidden:
            raise AttributeError(name)
        return getattr(Image, name)


def _jpeg_bytes():
    high_res = Image.new("RGB", (100, 100), (10, 20, 30))
    buf = BytesIO()
    high_res.save(buf, format="JPEG")
    return buf.getvalue()


def test_render_and_downsample_artwork_network_error_returns_none():
    with patch("urllib.request.urlopen", side_effect=OSError("network down")):
        assert media_source.render_and_downsample_artwork("https://example.com/a.jpg", size=16) is None


def test_render_and_downsample_artwork_lanczos_fallback(tmp_path):
    """Image.Resampling is missing (older Pillow) -> falls back to Image.LANCZOS."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = _jpeg_bytes()
    proxy = _HidingImageProxy({"Resampling"})
    with patch("urllib.request.urlopen", return_value=MagicMock(__enter__=lambda self: mock_resp)), \
         patch.object(media_source, "Image", proxy), \
         patch("divoom_lib.utils.media_source.Path") as mock_path:
        mock_path_inst = MagicMock()
        mock_path_inst.parent.parent.parent = tmp_path
        mock_path.return_value = mock_path_inst
        out_path = media_source.render_and_downsample_artwork("https://example.com/a.jpg", size=16)
    assert out_path is not None
    written_img = Image.open(out_path)
    assert written_img.size == (16, 16)


def test_render_and_downsample_artwork_antialias_fallback_missing_hits_exception(tmp_path):
    """Both Image.Resampling and Image.LANCZOS missing -> falls through to
    Image.ANTIALIAS, which modern Pillow (10+) no longer has, so that final
    AttributeError propagates to the function's outer except -> None."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = _jpeg_bytes()
    proxy = _HidingImageProxy({"Resampling", "LANCZOS"})
    with patch("urllib.request.urlopen", return_value=MagicMock(__enter__=lambda self: mock_resp)), \
         patch.object(media_source, "Image", proxy), \
         patch("divoom_lib.utils.media_source.Path") as mock_path:
        mock_path_inst = MagicMock()
        mock_path_inst.parent.parent.parent = tmp_path
        mock_path.return_value = mock_path_inst
        out_path = media_source.render_and_downsample_artwork("https://example.com/a.jpg", size=16)
    assert out_path is None


# ── R61 coverage push: fetch_stock_ticker error/malformed paths ────────────


def test_fetch_stock_ticker_empty_result_returns_none():
    mock_data = {"chart": {"result": []}}
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_data).encode("utf-8")
    with patch("urllib.request.urlopen", return_value=MagicMock(__enter__=lambda self: mock_resp)):
        assert media_source.fetch_stock_ticker("AAPL") is None


def test_fetch_stock_ticker_network_error_returns_none():
    with patch("urllib.request.urlopen", side_effect=OSError("network down")):
        assert media_source.fetch_stock_ticker("AAPL") is None


# ── R61 coverage push: render_stock_ticker_frame branches ──────────────────


def test_render_stock_ticker_frame_down_16(tmp_path):
    data = {"price": 100.0, "change": -2.0, "pct_change": -2.0}
    with patch("divoom_lib.utils.media_source.Path") as mock_path:
        mock_path.return_value.parent.parent.parent = tmp_path
        out_path = media_source.render_stock_ticker_frame("AAPL", data, size=16)
    assert out_path.exists()


def test_render_stock_ticker_frame_size_32_up(tmp_path):
    data = {"price": 150.0, "change": 5.0, "pct_change": 3.3}
    with patch("divoom_lib.utils.media_source.Path") as mock_path:
        mock_path.return_value.parent.parent.parent = tmp_path
        out_path = media_source.render_stock_ticker_frame("AAPL", data, size=32)
    assert out_path.exists()
    img = Image.open(out_path)
    assert img.size == (32, 32)


def test_render_stock_ticker_frame_size_32_down(tmp_path):
    data = {"price": 90.0, "change": -3.0, "pct_change": -3.2}
    with patch("divoom_lib.utils.media_source.Path") as mock_path:
        mock_path.return_value.parent.parent.parent = tmp_path
        out_path = media_source.render_stock_ticker_frame("AAPL", data, size=32)
    assert out_path.exists()


# ── R61 coverage push: get_system_stats error paths ────────────────────────


def test_get_system_stats_battery_sensor_exception_returns_none_battery():
    with patch("psutil.cpu_percent", return_value=10.0), \
         patch("psutil.virtual_memory") as mock_mem, \
         patch("psutil.sensors_battery", side_effect=RuntimeError("no battery")):
        mock_mem.return_value.percent = 20.0
        stats = media_source.get_system_stats()
    assert stats == {"cpu": 10, "mem": 20, "battery": None}


def test_get_system_stats_outer_exception_returns_defaults():
    with patch("psutil.cpu_percent", side_effect=RuntimeError("boom")):
        stats = media_source.get_system_stats()
    assert stats == {"cpu": 0, "mem": 0, "battery": None}


# ── R61 coverage push: render_system_stats_frame branches ──────────────────


def test_render_system_stats_frame_battery_none_defaults_to_100(tmp_path):
    stats = {"cpu": 50, "mem": 60, "battery": None}
    with patch("divoom_lib.utils.media_source.Path") as mock_path:
        mock_path.return_value.parent.parent.parent = tmp_path
        out_path = media_source.render_system_stats_frame(stats, size=16)
    assert out_path.exists()


def test_render_system_stats_frame_size_32(tmp_path):
    stats = {"cpu": 12, "mem": 45, "battery": 85}
    with patch("divoom_lib.utils.media_source.Path") as mock_path:
        mock_path.return_value.parent.parent.parent = tmp_path
        out_path = media_source.render_system_stats_frame(stats, size=32)
    assert out_path.exists()
    img = Image.open(out_path)
    assert img.size == (32, 32)


def test_render_system_stats_frame_size_20_small_bars_min_clamped(tmp_path):
    """size=20 -> scale ~0.625 -> computed bar_h < 3, exercising the min-clamp branch."""
    stats = {"cpu": 30, "mem": 40, "battery": 50}
    with patch("divoom_lib.utils.media_source.Path") as mock_path:
        mock_path.return_value.parent.parent.parent = tmp_path
        out_path = media_source.render_system_stats_frame(stats, size=20)
    assert out_path.exists()


# ── R61 coverage push: render_notification_frame (previously untested) ────


def test_render_notification_frame_mail(tmp_path):
    with patch("divoom_lib.utils.media_source.Path") as mock_path:
        mock_path.return_value.parent.parent.parent = tmp_path
        out_path = media_source.render_notification_frame("mail", size=16)
    assert out_path.exists()
    img = Image.open(out_path)
    assert img.size == (16, 16)


def test_render_notification_frame_whatsapp_scaled(tmp_path):
    with patch("divoom_lib.utils.media_source.Path") as mock_path:
        mock_path.return_value.parent.parent.parent = tmp_path
        out_path = media_source.render_notification_frame("WhatsApp", size=32)
    assert out_path.exists()
    img = Image.open(out_path)
    assert img.size == (32, 32)


def test_render_notification_frame_telegram(tmp_path):
    with patch("divoom_lib.utils.media_source.Path") as mock_path:
        mock_path.return_value.parent.parent.parent = tmp_path
        out_path = media_source.render_notification_frame("Telegram", size=16)
    assert out_path.exists()


def test_render_notification_frame_unknown_app_generic_bell(tmp_path):
    with patch("divoom_lib.utils.media_source.Path") as mock_path:
        mock_path.return_value.parent.parent.parent = tmp_path
        out_path = media_source.render_notification_frame("SomeOtherApp", size=16)
    assert out_path.exists()

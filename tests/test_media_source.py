import json
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from divoom_lib.utils import media_source


def test_get_current_playing_track_spotify():
    empty_mock = MagicMock()
    empty_mock.stdout = ""
    spotify_mock = MagicMock()
    spotify_mock.stdout = "Song Title -|- Artist Name"
    with patch("subprocess.run", side_effect=[empty_mock, spotify_mock]) as mock_run:
        with patch.object(media_source, "_feishin_is_running", return_value=False):
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
        with patch.object(media_source, "_feishin_is_running", return_value=False):
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
    with patch.object(media_source, "_feishin_is_running", return_value=True), \
         patch.object(media_source, "_feishin_creds",
                      return_value=("http://server:4533", "u=admin&s=abc&t=def")), \
         patch("urllib.request.urlopen", return_value=MagicMock(__enter__=lambda self: mock_resp)):
        res = media_source.get_feishin_playing_track()
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
    with patch.object(media_source, "_feishin_is_running", return_value=True), \
         patch.object(media_source, "_feishin_creds",
                      return_value=("http://server:4533", "u=admin&s=abc&t=def")), \
         patch("urllib.request.urlopen", return_value=MagicMock(__enter__=lambda self: mock_resp)):
        res = media_source.get_feishin_playing_track()
    assert res is None


def test_get_feishin_not_running():
    """Feishin not running → no track."""
    with patch.object(media_source, "_feishin_is_running", return_value=False):
        res = media_source.get_feishin_playing_track()
    assert res is None


def test_get_feishin_no_creds():
    """Feishin running but no credentials found."""
    with patch.object(media_source, "_feishin_is_running", return_value=True), \
         patch.object(media_source, "_feishin_creds", return_value=None):
        res = media_source.get_feishin_playing_track()
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

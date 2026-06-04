import json
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from divoom_lib.utils import media_source


def test_get_current_playing_track_spotify():
    mock_proc = MagicMock()
    mock_proc.stdout = "Song Title -|- Artist Name"
    with patch("subprocess.run", return_value=mock_proc) as mock_run:
        res = media_source.get_current_playing_track()
        assert res == {
            "track": "Song Title",
            "artist": "Artist Name",
            "source": "Spotify",
        }
        mock_run.assert_called_once()


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

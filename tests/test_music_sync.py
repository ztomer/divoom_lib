"""R11: music cover-art auto-push (listen for album change + push immediately).

Tests the change-detection / force-push logic of MediaSyncMixin._sync_now_playing
without any real device, AppleScript, or network.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "divoom_gui"))

from media_sync import MediaSyncMixin


def _obj():
    """A bare MediaSyncMixin instance with just the attrs _sync_now_playing uses."""
    o = MediaSyncMixin.__new__(MediaSyncMixin)
    o.current_divoom = None  # falsy → _ensure_device_ready returns True
    o.current_track_cache = None
    o._last_synced_track = None
    o._last_synced_artist = None
    o._push_cover_for_track = MagicMock(return_value=True)
    return o


def test_pushes_on_first_track():
    o = _obj()
    with patch("media_sync.media_source.get_current_playing_track",
               return_value={"track": "A", "artist": "X", "source": "Spotify"}):
        o._sync_now_playing()
    o._push_cover_for_track.assert_called_once_with("A", "X", "Spotify")


def test_no_push_when_track_unchanged():
    o = _obj()
    o._last_synced_track, o._last_synced_artist = "A", "X"
    with patch("media_sync.media_source.get_current_playing_track",
               return_value={"track": "A", "artist": "X", "source": "Spotify"}):
        o._sync_now_playing()
    o._push_cover_for_track.assert_not_called()


def test_pushes_on_track_change():
    o = _obj()
    o._last_synced_track, o._last_synced_artist = "A", "X"
    with patch("media_sync.media_source.get_current_playing_track",
               return_value={"track": "B", "artist": "Y", "source": "Apple Music"}):
        o._sync_now_playing()
    o._push_cover_for_track.assert_called_once_with("B", "Y", "Apple Music")


def test_force_pushes_even_when_unchanged():
    """Immediate push on enable: force=True pushes the current track even if it
    matches the last-synced one."""
    o = _obj()
    o._last_synced_track, o._last_synced_artist = "A", "X"
    with patch("media_sync.media_source.get_current_playing_track",
               return_value={"track": "A", "artist": "X", "source": "Spotify"}):
        o._sync_now_playing(force=True)
    o._push_cover_for_track.assert_called_once_with("A", "X", "Spotify")


def test_no_track_clears_cache_and_state():
    o = _obj()
    o._last_synced_track, o._last_synced_artist = "A", "X"
    o.current_track_cache = {"track": "A"}
    with patch("media_sync.media_source.get_current_playing_track",
               return_value=None):
        o._sync_now_playing()
    assert o.current_track_cache is None
    assert o._last_synced_track is None
    o._push_cover_for_track.assert_not_called()


def test_reconnect_failure_skips_push():
    o = _obj()
    dev = MagicMock()
    dev.lan = None
    dev.is_connected = False
    o.current_divoom = dev
    o._run_async = MagicMock(side_effect=RuntimeError("no BLE"))
    with patch("media_sync.media_source.get_current_playing_track",
               return_value={"track": "A", "artist": "X", "source": "Spotify"}):
        o._sync_now_playing(force=True)
    o._push_cover_for_track.assert_not_called()

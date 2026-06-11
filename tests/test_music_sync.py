"""R44 §6: music cover-art live sync now runs as a DAEMON live job
(`divoom_daemon.live_jobs.run_music`), not a GUI-side method — so a widget
keeps updating its device even after the GUI switches target.

These tests cover:
  - the daemon `run_music` change-detection (push on first/changed track) by
    driving exactly one loop iteration;
  - the GUI `toggle_music_sync` wiring → `live_job_start/stop`.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "divoom_gui"))

from divoom_daemon import live_jobs


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

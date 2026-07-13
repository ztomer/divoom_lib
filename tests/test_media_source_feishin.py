"""First tests for divoom_lib/utils/media_source_feishin.py — the Feishin
(Navidrome/Subsonic) "now playing" media source. No real Feishin install,
LevelDB, or Subsonic server is touched: pgrep, the LevelDB directory scan, and
the HTTP call are all mocked.

Module-level cache globals (_FEISHIN_CREDS_CACHE / _FEISHIN_CREDS_AT) are reset
around every test so results don't leak between tests.
"""
import json
import sys
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.append(str(Path(__file__).parent.parent))

import divoom_lib.utils.media_source_feishin as feishin


@pytest.fixture(autouse=True)
def _reset_creds_cache():
    feishin._FEISHIN_CREDS_CACHE = None
    feishin._FEISHIN_CREDS_AT = 0.0
    yield
    feishin._FEISHIN_CREDS_CACHE = None
    feishin._FEISHIN_CREDS_AT = 0.0


# ── _feishin_is_running ───────────────────────────────────────────────────────

def test_is_running_true_when_pgrep_finds_it():
    with patch("divoom_lib.utils.media_source_feishin.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0)
        assert feishin._feishin_is_running() is True


def test_is_running_false_when_pgrep_finds_nothing():
    with patch("divoom_lib.utils.media_source_feishin.subprocess.run") as run:
        run.return_value = MagicMock(returncode=1)
        assert feishin._feishin_is_running() is False


def test_is_running_false_when_pgrep_raises():
    with patch("divoom_lib.utils.media_source_feishin.subprocess.run", side_effect=OSError("no pgrep")):
        assert feishin._feishin_is_running() is False


# ── _feishin_creds ────────────────────────────────────────────────────────────

def test_creds_none_when_leveldb_dir_missing(tmp_path):
    with patch.object(Path, "home", lambda: tmp_path):
        assert feishin._feishin_creds() is None


def test_creds_extracted_from_leveldb_files(tmp_path):
    leveldb = tmp_path / "Library/Application Support/Feishin/Local Storage/leveldb"
    leveldb.mkdir(parents=True)
    (leveldb / "000003.log").write_bytes(
        b'garbage...{"credential":"u=alice&p=enc:abc&v=1.16.0&c=divoom"}...'
        b'{"url":"https://navidrome.example.com"}...'
    )
    with patch.object(Path, "home", lambda: tmp_path):
        creds = feishin._feishin_creds()
    assert creds == ("https://navidrome.example.com", "u=alice&p=enc:abc&v=1.16.0&c=divoom")


def test_creds_strips_trailing_slash_from_url(tmp_path):
    leveldb = tmp_path / "Library/Application Support/Feishin/Local Storage/leveldb"
    leveldb.mkdir(parents=True)
    (leveldb / "000003.log").write_bytes(
        b'{"credential":"u=bob&p=x"}{"url":"https://nav.example.com/"}'
    )
    with patch.object(Path, "home", lambda: tmp_path):
        creds = feishin._feishin_creds()
    assert creds[0] == "https://nav.example.com"


def test_creds_none_when_only_credential_present(tmp_path):
    leveldb = tmp_path / "Library/Application Support/Feishin/Local Storage/leveldb"
    leveldb.mkdir(parents=True)
    (leveldb / "000003.log").write_bytes(b'{"credential":"u=alice&p=x"}')
    with patch.object(Path, "home", lambda: tmp_path):
        assert feishin._feishin_creds() is None


def test_creds_skips_unreadable_file_and_ignores_non_ldb_log(tmp_path):
    leveldb = tmp_path / "Library/Application Support/Feishin/Local Storage/leveldb"
    leveldb.mkdir(parents=True)
    (leveldb / "MANIFEST-000001").write_bytes(b'{"credential":"u=ignored&p=x"}{"url":"https://ignored.example.com"}')
    good = leveldb / "000004.ldb"
    good.write_bytes(b'{"credential":"u=carol&p=y"}{"url":"https://good.example.com"}')

    orig_read_bytes = Path.read_bytes

    def _flaky_read(self):
        if self.name == "000004.ldb" and not getattr(_flaky_read, "_called", False):
            _flaky_read._called = True
            raise OSError("locked by another process")
        return orig_read_bytes(self)

    with patch.object(Path, "home", lambda: tmp_path), \
         patch.object(Path, "read_bytes", _flaky_read):
        # First call: 000004.ldb read raises (caught, continue) -> no creds found
        # in this pass since it's the only file with the pattern.
        assert feishin._feishin_creds() is None


def test_creds_skips_recheck_once_auth_already_found(tmp_path):
    """Once auth_qs is found in an earlier file, later files must skip
    re-searching for it (the `if not auth_qs` guard) and go straight to the
    url search."""
    leveldb = tmp_path / "Library/Application Support/Feishin/Local Storage/leveldb"
    leveldb.mkdir(parents=True)
    (leveldb / "000001.log").write_bytes(b'{"credential":"u=dave&p=z"}')
    (leveldb / "000002.log").write_bytes(b'{"url":"https://later.example.com"}')
    with patch.object(Path, "home", lambda: tmp_path):
        creds = feishin._feishin_creds()
    assert creds == ("https://later.example.com", "u=dave&p=z")


def test_creds_skips_recheck_once_url_already_found(tmp_path):
    """Once server_url is found in an earlier file (with no credential text
    yet), later files must skip re-searching for it (the `if not server_url`
    guard) once auth_qs also lands."""
    leveldb = tmp_path / "Library/Application Support/Feishin/Local Storage/leveldb"
    leveldb.mkdir(parents=True)
    (leveldb / "000001.log").write_bytes(b'{"url":"https://early.example.com"}')
    (leveldb / "000002.log").write_bytes(b'{"credential":"u=erin&p=z"}')
    with patch.object(Path, "home", lambda: tmp_path):
        creds = feishin._feishin_creds()
    assert creds == ("https://early.example.com", "u=erin&p=z")


def test_creds_cache_reused_within_ttl(tmp_path):
    leveldb = tmp_path / "Library/Application Support/Feishin/Local Storage/leveldb"
    leveldb.mkdir(parents=True)
    (leveldb / "000003.log").write_bytes(
        b'{"credential":"u=alice&p=x"}{"url":"https://nav.example.com"}'
    )
    with patch.object(Path, "home", lambda: tmp_path):
        first = feishin._feishin_creds()
        # Remove the directory entirely; a fresh scan would now return None.
        # The cached value must still be returned since we're well within TTL.
        for f in leveldb.iterdir():
            f.unlink()
        second = feishin._feishin_creds()
    assert first == second == ("https://nav.example.com", "u=alice&p=x")


# ── get_feishin_playing_track ─────────────────────────────────────────────────

def test_returns_none_on_non_darwin():
    with patch.object(feishin.sys, "platform", "linux"):
        assert feishin.get_feishin_playing_track() is None


def test_returns_none_when_feishin_not_running():
    with patch.object(feishin, "_feishin_is_running", return_value=False):
        assert feishin.get_feishin_playing_track() is None


def test_returns_none_when_no_creds():
    with patch.object(feishin, "_feishin_is_running", return_value=True), \
         patch.object(feishin, "_feishin_creds", return_value=None):
        assert feishin.get_feishin_playing_track() is None


def _mock_response(body: dict):
    payload = json.dumps(body).encode("utf-8")
    resp = MagicMock()
    resp.read.return_value = payload
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


def test_returns_track_with_artwork_url_when_playing():
    body = {
        "subsonic-response": {
            "status": "ok",
            "nowPlaying": {"entry": [{"title": "Song A", "artist": "Artist A", "coverArt": "cov1"}]},
        }
    }
    with patch.object(feishin, "_feishin_is_running", return_value=True), \
         patch.object(feishin, "_feishin_creds", return_value=("https://nav.example.com", "u=a&p=b")), \
         patch.object(urllib.request, "urlopen", return_value=_mock_response(body)):
        track = feishin.get_feishin_playing_track()
    assert track["track"] == "Song A"
    assert track["artist"] == "Artist A"
    assert track["source"] == "Feishin"
    assert track["artwork_url"].startswith("https://nav.example.com/rest/getCoverArt.view")
    assert "id=cov1" in track["artwork_url"]


def test_entry_as_dict_not_list_is_supported():
    """nowPlaying.entry can be a bare dict (single track) rather than a list."""
    body = {
        "subsonic-response": {
            "status": "ok",
            "nowPlaying": {"entry": {"title": "Solo Track", "artist": "Solo Artist"}},
        }
    }
    with patch.object(feishin, "_feishin_is_running", return_value=True), \
         patch.object(feishin, "_feishin_creds", return_value=("https://nav.example.com", "u=a&p=b")), \
         patch.object(urllib.request, "urlopen", return_value=_mock_response(body)):
        track = feishin.get_feishin_playing_track()
    assert track["track"] == "Solo Track"
    assert track["artwork_url"] is None   # no coverArt -> art_url stays None


def test_returns_none_when_status_not_ok():
    body = {"subsonic-response": {"status": "failed"}}
    with patch.object(feishin, "_feishin_is_running", return_value=True), \
         patch.object(feishin, "_feishin_creds", return_value=("https://nav.example.com", "u=a&p=b")), \
         patch.object(urllib.request, "urlopen", return_value=_mock_response(body)):
        assert feishin.get_feishin_playing_track() is None


def test_returns_none_when_nothing_playing():
    body = {"subsonic-response": {"status": "ok", "nowPlaying": {}}}
    with patch.object(feishin, "_feishin_is_running", return_value=True), \
         patch.object(feishin, "_feishin_creds", return_value=("https://nav.example.com", "u=a&p=b")), \
         patch.object(urllib.request, "urlopen", return_value=_mock_response(body)):
        assert feishin.get_feishin_playing_track() is None


def test_returns_none_when_entry_missing_title():
    body = {
        "subsonic-response": {
            "status": "ok",
            "nowPlaying": {"entry": [{"artist": "No Title Artist"}]},
        }
    }
    with patch.object(feishin, "_feishin_is_running", return_value=True), \
         patch.object(feishin, "_feishin_creds", return_value=("https://nav.example.com", "u=a&p=b")), \
         patch.object(urllib.request, "urlopen", return_value=_mock_response(body)):
        assert feishin.get_feishin_playing_track() is None


def test_returns_none_on_network_exception():
    with patch.object(feishin, "_feishin_is_running", return_value=True), \
         patch.object(feishin, "_feishin_creds", return_value=("https://nav.example.com", "u=a&p=b")), \
         patch.object(urllib.request, "urlopen", side_effect=OSError("connection refused")):
        assert feishin.get_feishin_playing_track() is None

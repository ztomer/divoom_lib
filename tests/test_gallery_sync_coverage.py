"""
Coverage-raising unit tests for divoom_gui/gallery_sync.py.

Targets the previously-uncovered branches: load_cached_gallery /
get_cached_gallery_files error paths, the fetch_gallery background worker
(auth retries, HTTP error codes, parallel download/decode, progressive
streaming, cache persistence, error propagation), batch_sync_artwork /
_sync_artwork_detailed (wall vs single-device vs no-device routing), the
Monthly Best sync-target/config plumbing, and the per-device gallery
style/filter persistence helpers.

Network and BLE are always mocked — this environment cannot make real BLE
calls (TCC), and these are unit tests, not integration tests against the
real Divoom cloud.
"""
import json
import logging
import sys
import threading
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Stub the C dylib the same way test_gallery_cache_rebuild.py does, so the
# top-level `from divoom_lib import media_decoder` import in gallery_sync.py
# is safe even in environments where the native lib isn't built.
if "divoom_lib.media_decoder" not in sys.modules:
    import divoom_lib
    _shim = types.ModuleType("divoom_lib.media_decoder")
    _shim.extract_image_from_magic_43 = lambda b: None
    _shim.extract_gif_from_magic_43 = lambda b: None
    _shim.decode_and_save_preview = lambda *a, **k: None
    sys.modules["divoom_lib.media_decoder"] = _shim
    divoom_lib.media_decoder = _shim

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from divoom_gui.gallery_sync import GallerySyncMixin  # noqa: E402


class _Host(GallerySyncMixin):
    """Minimal host exposing the attributes gallery_sync.py methods expect,
    without pulling in the full DivoomGuiAPI (webview/daemon bootstrap)."""

    def __init__(self):
        self.window = None
        self.cached_creds = None
        self.device_id = 123
        self.device_pw = 0
        self.current_target_mode = "single"
        self.current_divoom = None
        self.wall_slots = {}
        self._daemon_client = None

    def _client(self):
        return self._daemon_client


def _wait_for_fetch_thread():
    for t in threading.enumerate():
        if t.name == "DivoomGalleryFetch":
            t.join(timeout=5.0)


# ─────────────────────────── load_cached_gallery ───────────────────────────

def test_load_cached_gallery_malformed_json_returns_empty(tmp_path, monkeypatch):
    """Corrupt JSON on disk must not raise — caught, warned, empty list."""
    monkeypatch.setenv("HOME", str(tmp_path))
    m = _Host()

    cfg_dir = tmp_path / ".config" / "divoom-control"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "gallery_cache.json").write_text("{not valid json[")

    out = m.load_cached_gallery()
    assert out == "[]"


# ───────────────────────── get_cached_gallery_files ─────────────────────────

def test_get_cached_gallery_files_no_dir_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    m = _Host()
    assert m.get_cached_gallery_files() == "[]"


def test_get_cached_gallery_files_malformed_name_map_warns_and_continues(tmp_path, monkeypatch):
    """gallery_cache.json exists but isn't valid JSON -> name-map build fails,
    but the directory scan still proceeds using filenames as display names."""
    monkeypatch.setenv("HOME", str(tmp_path))
    m = _Host()

    cfg_dir = tmp_path / ".config" / "divoom-control"
    cache_dir = cfg_dir / "cache_gallery"
    cache_dir.mkdir(parents=True)
    (cache_dir / "art1.png").write_bytes(b"\x00" * 4)
    (cfg_dir / "gallery_cache.json").write_text("not json at all {{{")

    out = json.loads(m.get_cached_gallery_files())
    assert len(out) == 1
    assert out[0]["name"] == "art1.png"


def test_get_cached_gallery_files_skips_zero_size_and_missing_fid_entries(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    m = _Host()

    cfg_dir = tmp_path / ".config" / "divoom-control"
    cache_dir = cfg_dir / "cache_gallery"
    cache_dir.mkdir(parents=True)
    (cache_dir / "empty.png").write_bytes(b"")  # zero-size -> skipped
    (cache_dir / "real.png").write_bytes(b"\x01\x02")

    # First entry has no file_id (falsy) -> exercises the name_map loop's
    # "if fid" false arm without raising.
    cache_items = [
        {"name": "NoId"},
        {"file_id": "real", "name": "RealName"},
    ]
    (cfg_dir / "gallery_cache.json").write_text(json.dumps(cache_items))

    out = json.loads(m.get_cached_gallery_files())
    names = {item["name"] for item in out}
    assert names == {"RealName"}


def test_get_cached_gallery_files_prioritizes_gif_over_other_ext_both_orders(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    m = _Host()
    cache_dir = tmp_path / ".config" / "divoom-control" / "cache_gallery"
    cache_dir.mkdir(parents=True)

    (cache_dir / "a.png").write_bytes(b"\x01")
    (cache_dir / "a.gif").write_bytes(b"\x02")
    (cache_dir / "b.gif").write_bytes(b"\x03")
    (cache_dir / "b.png").write_bytes(b"\x04")

    out = json.loads(m.get_cached_gallery_files())
    paths = [item["path"] for item in out]
    assert any(p.endswith("a.gif") for p in paths)
    assert not any(p.endswith("a.png") for p in paths)
    assert any(p.endswith("b.gif") for p in paths)
    assert not any(p.endswith("b.png") for p in paths)


def test_get_cached_gallery_files_encode_failure_is_warned_not_raised(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    m = _Host()
    cache_dir = tmp_path / ".config" / "divoom-control" / "cache_gallery"
    cache_dir.mkdir(parents=True)
    (cache_dir / "bad.png").write_bytes(b"\x01\x02")

    with patch.object(Path, "read_bytes", side_effect=OSError("disk gone")):
        out = json.loads(m.get_cached_gallery_files())
    assert out == []  # the one file failed to encode -> excluded, no crash


# ────────────────────────────── fetch_gallery ───────────────────────────────

def _fake_urlopen_factory(*, rc=0, return_message="", file_list=None, dl_bytes_map=None,
                           dl_raises_for=None, list_raises_first_n=0, captured_bodies=None):
    """Build a urlopen side_effect answering both the auth/list POST to
    appin.divoom-gz.com and the per-item GET to fin.divoom-gz.com.

    `list_raises_first_n` lets a test simulate N transient failures on the
    list endpoint before it starts succeeding (retry-path coverage).
    """
    file_list = file_list if file_list is not None else []
    dl_bytes_map = dl_bytes_map or {}
    dl_raises_for = dl_raises_for or set()
    state = {"list_calls": 0}

    def _urlopen(req, timeout=10):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        cm = MagicMock()
        if "GetCategoryFileListV2" in url:
            if captured_bodies is not None:
                captured_bodies.append(json.loads(req.data.decode("utf-8")))
            state["list_calls"] += 1
            if state["list_calls"] <= list_raises_first_n:
                raise RuntimeError("transient network blip")
            body = json.dumps({
                "ReturnCode": rc,
                "ReturnMessage": return_message,
                "FileList": file_list,
            }).encode("utf-8")
            cm.__enter__.return_value.read.return_value = body
        else:
            file_id = url.rsplit("/", 1)[-1]
            if file_id in dl_raises_for:
                raise RuntimeError(f"download failed for {file_id}")
            cm.__enter__.return_value.read.return_value = dl_bytes_map.get(file_id, b"\x00\x00")
        return cm

    return _urlopen


def test_fetch_gallery_success_full_pipeline(tmp_path, monkeypatch):
    """Happy path: cached creds present, one item needs full download+decode
    (magic-43 extraction), one already has a cached preview (skips download
    and decode), one has no FileId at all. Window is present so progressive
    streaming + the final broadcast both fire, and the JSON cache persists."""
    monkeypatch.setenv("HOME", str(tmp_path))
    m = _Host()
    m.window = MagicMock()
    m.cached_creds = MagicMock(token="tok", user_id=42)
    m.device_pw = "secretpw"  # exercise the DevicePassword-in-body branch

    cache_dir = tmp_path / ".config" / "divoom-control" / "cache_gallery"
    cache_dir.mkdir(parents=True)
    (cache_dir / "already_cached.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    file_list = [
        {"FileId": "needs_download", "FileName": "New", "LikeCnt": 3, "FileType": 5},
        {"FileId": "already_cached", "FileName": "Old", "LikeCnt": 1, "FileType": 5},
        {"FileName": "NoFileId"},  # no FileId -> download_item early-returns
    ]
    captured_bodies = []
    urlopen_fn = _fake_urlopen_factory(
        rc=0, file_list=file_list,
        dl_bytes_map={"needs_download": b"rawbytes"},
        captured_bodies=captured_bodies,
    )

    with patch("urllib.request.urlopen", side_effect=urlopen_fn), \
         patch("divoom_gui.gallery_sync.media_decoder.extract_image_from_magic_43",
               return_value=(b"decodedpng", ".png")):
        out = m.fetch_gallery(classify=18, target_size=16)
        assert out == "[]"  # no pre-existing gallery_cache.json -> cached_data empty
        _wait_for_fetch_thread()

    assert (cache_dir / "needs_download.png").read_bytes() == b"decodedpng"
    assert captured_bodies[0]["DevicePassword"] == "secretpw"

    cache_file = tmp_path / ".config" / "divoom-control" / "gallery_cache.json"
    saved = json.loads(cache_file.read_text())
    assert len(saved) == 3
    assert {item["name"] for item in saved} == {"New", "Old", "NoFileId"}

    assert m.window.evaluate_js.call_count >= 4  # 3 progressive + 1 final broadcast


def test_fetch_gallery_file_size_bitmask_explicit_vs_lookup(tmp_path, monkeypatch):
    """file_size>0 is used directly; file_size=0 falls back to
    FILE_SIZE_BITMASK.get(target_size, 1), defaulting to 1 for an unknown
    target_size — both arms of that branch."""
    monkeypatch.setenv("HOME", str(tmp_path))
    m = _Host()
    m.cached_creds = MagicMock(token="tok", user_id=1)

    bodies_explicit, bodies_lookup = [], []
    with patch("urllib.request.urlopen",
               side_effect=_fake_urlopen_factory(file_list=[], captured_bodies=bodies_explicit)):
        m.fetch_gallery(classify=1, target_size=16, file_size=64)
        _wait_for_fetch_thread()
    assert bodies_explicit[0]["FileSize"] == 64

    with patch("urllib.request.urlopen",
               side_effect=_fake_urlopen_factory(file_list=[], captured_bodies=bodies_lookup)):
        m.fetch_gallery(classify=1, target_size=99999, file_size=0)  # unknown size
        _wait_for_fetch_thread()
    assert bodies_lookup[0]["FileSize"] == 1  # FILE_SIZE_BITMASK.get(99999, 1)


def test_fetch_gallery_retries_and_refreshes_credentials_on_transient_failure(tmp_path, monkeypatch):
    """First attempt fails -> credentials reset -> second attempt refetches
    creds with force_refresh=True and succeeds. Covers both `force_refresh`
    arms (retries<1 false then true) and the config.ini credential path."""
    monkeypatch.setenv("HOME", str(tmp_path))
    m = _Host()  # cached_creds starts None -> forces the config.ini path

    cfg_dir = tmp_path / ".config" / "divoom-control"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.ini").write_text("[divoom]\nemail = a@b.com\npassword = pw\n")

    fake_creds = MagicMock(token="tok", user_id=7)
    with patch("urllib.request.urlopen",
               side_effect=_fake_urlopen_factory(file_list=[], list_raises_first_n=1)), \
         patch("divoom_gui.gallery_sync.divoom_auth.get_credentials",
               return_value=fake_creds) as mock_get_creds:
        m.fetch_gallery(classify=1)
        _wait_for_fetch_thread()

    assert mock_get_creds.call_count == 2
    assert mock_get_creds.call_args_list[0].kwargs["force_refresh"] is False
    assert mock_get_creds.call_args_list[1].kwargs["force_refresh"] is True


def test_fetch_gallery_credentials_not_configured_reports_error(tmp_path, monkeypatch, caplog):
    """No cached creds and no config.ini -> permanent failure; the error is
    classified as an auth issue (is_expired) and broadcast if a window
    exists, or silently skipped (no crash) if it doesn't."""
    monkeypatch.setenv("HOME", str(tmp_path))

    with caplog.at_level(logging.WARNING, logger="divoom_gui"):
        # No window: covers the `if self.window` false arm in the error handler.
        m_no_window = _Host()
        with patch("urllib.request.urlopen", side_effect=AssertionError("must not be called")):
            m_no_window.fetch_gallery(classify=1)
            _wait_for_fetch_thread()
        assert not (tmp_path / ".config" / "divoom-control" / "gallery_cache.json").exists()

        # With window: the error broadcast fires and reports is_expired=true.
        m_window = _Host()
        m_window.window = MagicMock()
        with patch("urllib.request.urlopen", side_effect=AssertionError("must not be called")):
            m_window.fetch_gallery(classify=1)
            _wait_for_fetch_thread()

    m_window.window.evaluate_js.assert_called_once()
    js_code = m_window.window.evaluate_js.call_args[0][0]
    assert "onGalleryFetchError" in js_code
    assert ", true," in js_code  # is_expired_val
    assert "Background gallery fetch failed permanently" in caplog.text


def test_fetch_gallery_token_expired_return_code_marks_expired(tmp_path, monkeypatch):
    """ReturnCode in [9, 10, 11] means the cloud rejected the token. Both
    retry attempts must be able to re-fetch credentials (config.ini present
    + get_credentials mocked) so the final error is really the ReturnCode
    failure, not an unrelated "credentials not configured"."""
    monkeypatch.setenv("HOME", str(tmp_path))
    m = _Host()
    m.window = MagicMock()
    m.cached_creds = MagicMock(token="tok", user_id=1)

    cfg_dir = tmp_path / ".config" / "divoom-control"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.ini").write_text("[divoom]\nemail = a@b.com\npassword = pw\n")

    with patch("urllib.request.urlopen", side_effect=_fake_urlopen_factory(rc=10)), \
         patch("divoom_gui.gallery_sync.divoom_auth.get_credentials",
               return_value=MagicMock(token="tok2", user_id=1)):
        m.fetch_gallery(classify=1)
        _wait_for_fetch_thread()

    js_code = m.window.evaluate_js.call_args[0][0]
    assert "onGalleryFetchError" in js_code
    assert ", true," in js_code
    assert "Token expired" in js_code


def test_fetch_gallery_api_error_return_code_not_expired(tmp_path, monkeypatch):
    """A non-auth ReturnCode error is reported but NOT flagged as expired."""
    monkeypatch.setenv("HOME", str(tmp_path))
    m = _Host()
    m.window = MagicMock()
    m.cached_creds = MagicMock(token="tok", user_id=1)

    cfg_dir = tmp_path / ".config" / "divoom-control"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.ini").write_text("[divoom]\nemail = a@b.com\npassword = pw\n")

    with patch("urllib.request.urlopen",
               side_effect=_fake_urlopen_factory(rc=5, return_message="server exploded")), \
         patch("divoom_gui.gallery_sync.divoom_auth.get_credentials",
               return_value=MagicMock(token="tok2", user_id=1)):
        m.fetch_gallery(classify=1)
        _wait_for_fetch_thread()

    js_code = m.window.evaluate_js.call_args[0][0]
    assert "onGalleryFetchError" in js_code
    assert ", false," in js_code
    assert "server exploded" in js_code


def test_fetch_gallery_download_failure_continues_pipeline(tmp_path, monkeypatch, caplog):
    """A per-item download failure is warned but does not abort the whole
    fetch — the item still appears in results with an empty preview_url."""
    monkeypatch.setenv("HOME", str(tmp_path))
    m = _Host()
    m.cached_creds = MagicMock(token="tok", user_id=1)

    file_list = [{"FileId": "flaky", "FileName": "Flaky", "LikeCnt": 0, "FileType": 5}]
    with caplog.at_level(logging.WARNING, logger="divoom_gui"):
        with patch("urllib.request.urlopen",
                   side_effect=_fake_urlopen_factory(file_list=file_list, dl_raises_for={"flaky"})):
            m.fetch_gallery(classify=1)
            _wait_for_fetch_thread()

    assert "Parallel download failed for flaky" in caplog.text
    cache_dir = tmp_path / ".config" / "divoom-control" / "cache_gallery"
    assert not (cache_dir / "flaky.bin").exists()

    cache_file = tmp_path / ".config" / "divoom-control" / "gallery_cache.json"
    saved = json.loads(cache_file.read_text())
    assert saved[0]["preview_url"] == ""


def test_fetch_gallery_decode_signature_branches(tmp_path, monkeypatch):
    """With magic-43 extraction returning nothing, raw bytes are classified
    by file signature (GIF/PNG/JPEG), falling back to decode_and_save_preview
    for anything unrecognized."""
    monkeypatch.setenv("HOME", str(tmp_path))
    m = _Host()
    m.cached_creds = MagicMock(token="tok", user_id=1)

    file_list = [
        {"FileId": "is_gif", "FileName": "G", "FileType": 5},
        {"FileId": "is_png", "FileName": "P", "FileType": 5},
        {"FileId": "is_jpg", "FileName": "J", "FileType": 5},
        {"FileId": "is_other", "FileName": "O", "FileType": 5},
    ]
    dl_bytes_map = {
        "is_gif": b"GIF89a" + b"\x00" * 10,
        "is_png": b"\x89PNG\r\n\x1a\n" + b"\x00" * 10,
        "is_jpg": b"\xff\xd8" + b"\x00" * 10,
        "is_other": b"unrecognized bytes",
    }

    fallback_calls = []

    def fake_decode_and_save_preview(raw_bytes, out_path):
        fallback_calls.append((raw_bytes, out_path))
        out_path.write_bytes(b"fallback-png")
        return True

    with patch("urllib.request.urlopen",
               side_effect=_fake_urlopen_factory(file_list=file_list, dl_bytes_map=dl_bytes_map)), \
         patch("divoom_gui.gallery_sync.media_decoder.extract_image_from_magic_43", return_value=None), \
         patch("divoom_gui.gallery_sync.media_decoder.decode_and_save_preview",
               side_effect=fake_decode_and_save_preview):
        m.fetch_gallery(classify=1)
        _wait_for_fetch_thread()

    cache_dir = tmp_path / ".config" / "divoom-control" / "cache_gallery"
    assert (cache_dir / "is_gif.gif").exists()
    assert (cache_dir / "is_png.png").exists()
    assert (cache_dir / "is_jpg.jpg").exists()
    assert len(fallback_calls) == 1
    assert (cache_dir / "is_other.png").read_bytes() == b"fallback-png"


def test_fetch_gallery_progressive_and_error_broadcast_exceptions_are_caught(tmp_path, monkeypatch, caplog):
    """If window.evaluate_js itself always raises, the per-item progressive
    send is warned and skipped, the (un-guarded) final broadcast raising
    propagates into the outer handler, and THAT handler's own attempt to
    report the error also fails safely and is warned."""
    monkeypatch.setenv("HOME", str(tmp_path))
    m = _Host()
    m.cached_creds = MagicMock(token="tok", user_id=1)
    m.window = MagicMock()
    m.window.evaluate_js.side_effect = RuntimeError("js boom")

    file_list = [{"FileId": "x", "FileName": "X", "FileType": 5}]
    with caplog.at_level(logging.WARNING, logger="divoom_gui"):
        with patch("urllib.request.urlopen", side_effect=_fake_urlopen_factory(file_list=file_list)):
            m.fetch_gallery(classify=1)
            _wait_for_fetch_thread()

    assert "Failed to send progressive gallery item" in caplog.text
    assert "Background gallery fetch failed permanently" in caplog.text
    assert "Failed to send gallery fetch error" in caplog.text
    # The cache write happens before the final broadcast attempt, so it must
    # still have succeeded despite every evaluate_js call blowing up.
    cache_file = tmp_path / ".config" / "divoom-control" / "gallery_cache.json"
    assert json.loads(cache_file.read_text())[0]["name"] == "X"


def test_fetch_gallery_cache_save_failure_is_warned(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("HOME", str(tmp_path))
    m = _Host()
    m.cached_creds = MagicMock(token="tok", user_id=1)

    with caplog.at_level(logging.WARNING, logger="divoom_gui"):
        with patch("urllib.request.urlopen", side_effect=_fake_urlopen_factory(file_list=[])), \
             patch("divoom_gui.gallery_sync.atomic_write_text", side_effect=OSError("disk full")):
            m.fetch_gallery(classify=1)
            _wait_for_fetch_thread()

    assert "Failed to save gallery cache" in caplog.text


# ───────────────────── batch_sync_artwork / _sync_artwork_detailed ─────────────────────

def test_sync_artwork_no_daemon_available():
    m = _Host()
    m._daemon_client = None
    ok, err = m._sync_artwork_detailed(json.dumps({"file_id": "abc"}))
    assert ok is False
    assert err == "no daemon available"
    assert m.batch_sync_artwork(json.dumps({"file_id": "abc"})) is False


def test_sync_artwork_wall_mode_rebuild_fails():
    m = _Host()
    m.current_target_mode = "wall"
    m._daemon_client = MagicMock()
    m._rebuild_wall_instance = MagicMock(return_value=False)
    ok, err = m._sync_artwork_detailed(json.dumps({"file_id": "abc"}))
    assert ok is False
    assert err == "wall not configured"


def test_sync_artwork_wall_mode_success_via_explicit_mode():
    m = _Host()
    m.current_target_mode = "wall"
    fake_client = MagicMock()
    fake_client.sync_artwork.return_value = {"success": True}
    m._daemon_client = fake_client
    m._rebuild_wall_instance = MagicMock(return_value=True)
    ok, err = m._sync_artwork_detailed(json.dumps({"file_id": "abc"}))
    assert ok is True
    assert err is None
    fake_client.sync_artwork.assert_called_once_with("abc", target="wall")


def test_sync_artwork_wall_mode_inferred_from_no_device_and_wall_slots():
    """current_target_mode="single" but no current_divoom + wall_slots set
    still routes to wall (the `or` arm of the is_wall condition)."""
    m = _Host()
    m.current_divoom = None
    m.wall_slots = {"AA:BB": {"x": 0}}
    fake_client = MagicMock()
    fake_client.sync_artwork.return_value = {"success": True}
    m._daemon_client = fake_client
    m._rebuild_wall_instance = MagicMock(return_value=True)
    ok, _ = m._sync_artwork_detailed(json.dumps({"file_id": "abc"}))
    assert ok is True
    fake_client.sync_artwork.assert_called_once_with("abc", target="wall")


def test_sync_artwork_single_device_connected_uses_active_device_size():
    m = _Host()
    m.current_divoom = MagicMock(is_connected=True, lan=None)
    m._active_device_size = lambda: 32
    fake_client = MagicMock()
    fake_client.sync_artwork.return_value = {"success": True}
    m._daemon_client = fake_client
    ok, err = m._sync_artwork_detailed(json.dumps({"file_id": "xyz"}))
    assert ok is True
    fake_client.sync_artwork.assert_called_once_with("xyz", default_size=32, target="device")


def test_sync_artwork_single_device_falls_back_to_16_without_size_helper():
    m = _Host()
    m.current_divoom = MagicMock(is_connected=True, lan=None)
    assert not hasattr(m, "_active_device_size")
    fake_client = MagicMock()
    fake_client.sync_artwork.return_value = {"success": True}
    m._daemon_client = fake_client
    m._sync_artwork_detailed(json.dumps({"file_id": "xyz"}))
    fake_client.sync_artwork.assert_called_once_with("xyz", default_size=16, target="device")


def test_sync_artwork_single_device_via_lan_not_ble_connected():
    """is_connected False but a `lan` attribute is truthy -> still routes to
    the single-device path (covers the `or getattr(..., "lan", None)` arm)."""
    m = _Host()
    m.current_divoom = MagicMock(is_connected=False, lan="192.168.1.20")
    fake_client = MagicMock()
    fake_client.sync_artwork.return_value = {"success": True}
    m._daemon_client = fake_client
    ok, _ = m._sync_artwork_detailed(json.dumps({"file_id": "xyz"}))
    assert ok is True
    fake_client.sync_artwork.assert_called_once_with("xyz", default_size=16, target="device")


def test_sync_artwork_no_connected_device():
    m = _Host()
    m.current_divoom = None
    m.wall_slots = {}
    m._daemon_client = MagicMock()
    ok, err = m._sync_artwork_detailed(json.dumps({"file_id": "abc"}))
    assert ok is False
    assert err == "no connected device"


def test_sync_artwork_reply_failure_with_and_without_error_message():
    m = _Host()
    m.current_divoom = MagicMock(is_connected=True, lan=None)
    m._active_device_size = lambda: 16

    fake_client = MagicMock()
    fake_client.sync_artwork.return_value = {"success": False, "error": "device busy"}
    m._daemon_client = fake_client
    ok, err = m._sync_artwork_detailed(json.dumps({"file_id": "a"}))
    assert ok is False
    assert err == "device busy"

    fake_client.sync_artwork.return_value = {"success": False}
    ok, err = m._sync_artwork_detailed(json.dumps({"file_id": "a"}))
    assert ok is False
    assert err == "unknown daemon error"


def test_sync_artwork_malformed_json_and_missing_file_id_are_caught():
    m = _Host()
    m._daemon_client = MagicMock()

    ok, err = m._sync_artwork_detailed("{not json")
    assert ok is False
    assert err  # exception message from json.loads

    ok, err = m._sync_artwork_detailed(json.dumps({"no_file_id": True}))
    assert ok is False
    assert "file_id" in err  # KeyError message


# ─────────────────────────── get_sync_candidates ───────────────────────────

def test_get_sync_candidates_merges_and_dedupes_sources(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("DIVOOM_HOTCHANNEL_CONFIG", str(tmp_path / "hotchannel.json"))
    m = _Host()

    cfg_dir = tmp_path / ".config" / "divoom-control"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "discovered_devices.json").write_text(json.dumps([
        {"address": "AA:BB", "name": "Discovered1"},
        {"address": "", "name": "NoAddress"},  # falsy address -> skipped
    ]))
    m.wall_slots = {"AA:BB": {"name": "WallDup"}, "CC:DD": {"name": "WallOnly"}}

    from divoom_lib import hotchannel_config
    hotchannel_config.set_targets(["CC:DD", "EE:FF"])  # EE:FF only via "selected"

    out = json.loads(m.get_sync_candidates())
    addrs = [c["address"] for c in out]
    assert addrs.count("AA:BB") == 1  # deduped across discovered+wall
    assert "CC:DD" in addrs
    assert "EE:FF" in addrs
    by_addr = {c["address"]: c for c in out}
    assert by_addr["AA:BB"]["name"] == "Discovered1"  # first-seen (discovered) wins
    assert by_addr["CC:DD"]["selected"] is True
    assert by_addr["EE:FF"]["name"] == "Divoom Screen"  # no name -> default


def test_get_sync_candidates_handles_malformed_discovered_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("DIVOOM_HOTCHANNEL_CONFIG", str(tmp_path / "hotchannel.json"))
    m = _Host()

    cfg_dir = tmp_path / ".config" / "divoom-control"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "discovered_devices.json").write_text("not json{{{")

    out = json.loads(m.get_sync_candidates())
    assert out == []  # malformed file -> caught, no crash, nothing discovered


# ─────────────────────────── set_sync_targets ───────────────────────────

def test_set_sync_targets_valid_list_and_galleries(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVOOM_HOTCHANNEL_CONFIG", str(tmp_path / "hotchannel.json"))
    m = _Host()
    from divoom_lib import hotchannel_config

    ok = m.set_sync_targets(
        targets_json=json.dumps(["AA:BB", "CC:DD"]),
        galleries_json=json.dumps({"AA:BB": 9}),
    )
    assert ok is True
    assert hotchannel_config.get_targets() == ["AA:BB", "CC:DD"]
    assert hotchannel_config.load_config()["device_galleries"] == {"AA:BB": 9}


def test_set_sync_targets_non_list_and_non_dict_payloads_are_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVOOM_HOTCHANNEL_CONFIG", str(tmp_path / "hotchannel.json"))
    m = _Host()
    from divoom_lib import hotchannel_config

    ok = m.set_sync_targets(targets_json=json.dumps({"not": "a list"}),
                             galleries_json=json.dumps([1, 2, 3]))
    assert ok is True  # set_targets([]) still succeeds
    assert hotchannel_config.get_targets() == []
    assert hotchannel_config.load_config()["device_galleries"] == {}


def test_set_sync_targets_none_payloads(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVOOM_HOTCHANNEL_CONFIG", str(tmp_path / "hotchannel.json"))
    m = _Host()
    ok = m.set_sync_targets(targets_json=None, galleries_json=None)
    assert ok is True


def test_set_sync_targets_malformed_json_returns_false(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVOOM_HOTCHANNEL_CONFIG", str(tmp_path / "hotchannel.json"))
    m = _Host()
    ok = m.set_sync_targets(targets_json="{not valid json[")
    assert ok is False


# ───────────────────── hot channel config get/save ─────────────────────

def test_get_hot_channel_config_returns_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVOOM_HOTCHANNEL_CONFIG", str(tmp_path / "hotchannel.json"))
    m = _Host()
    cfg = json.loads(m.get_hot_channel_config())
    assert cfg["classify"] == 18
    assert cfg["targets"] == []


def test_save_hot_channel_config_positional_json_string(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVOOM_HOTCHANNEL_CONFIG", str(tmp_path / "hotchannel.json"))
    m = _Host()
    ok = m.save_hot_channel_config(json.dumps({"enabled": True, "interval": 120}))
    assert ok is True
    cfg = json.loads(m.get_hot_channel_config())
    assert cfg["enabled"] is True
    assert cfg["interval"] == 120


def test_save_hot_channel_config_kwargs_style(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVOOM_HOTCHANNEL_CONFIG", str(tmp_path / "hotchannel.json"))
    m = _Host()
    ok = m.save_hot_channel_config(enabled=True, classify=9)
    assert ok is True
    cfg = json.loads(m.get_hot_channel_config())
    assert cfg["classify"] == 9


def test_save_hot_channel_config_swallows_exception(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVOOM_HOTCHANNEL_CONFIG", str(tmp_path / "hotchannel.json"))
    m = _Host()
    with patch("divoom_lib.hotchannel_config.save_config", side_effect=RuntimeError("boom")):
        ok = m.save_hot_channel_config(enabled=True)
    assert ok is False


# ───────────────────────── gallery style persistence ─────────────────────────

def test_get_gallery_style_defaults_when_no_config(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    m = _Host()
    assert m.get_gallery_style("AABB") == 18


def test_set_and_get_gallery_style_roundtrip(tmp_path, monkeypatch):
    # NOTE: configparser's default delimiters include ":", so device
    # addresses used as ini keys here must not contain a colon (a real
    # MAC-address key would need sanitizing — out of scope for this test).
    monkeypatch.setenv("HOME", str(tmp_path))
    m = _Host()
    assert m.set_gallery_style("AABB", 7) is True
    assert m.get_gallery_style("AABB") == 7
    # A different, never-configured device with no "default" key falls back to 18.
    assert m.get_gallery_style("ZZZZ") == 18


def test_get_gallery_style_falls_back_to_default_key(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    m = _Host()
    assert m.set_gallery_style("", 3) is True  # "" -> key "default"
    assert m.get_gallery_style("never-seen-device") == 3


def test_get_gallery_style_exception_path_returns_default(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    m = _Host()
    cfg_dir = tmp_path / ".config" / "divoom-control"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.ini").write_text("[gallery]\nAABB = not-an-int\n")
    assert m.get_gallery_style("AABB") == 18


def test_set_gallery_style_preserves_existing_keys_and_handles_exception(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    m = _Host()
    assert m.set_gallery_style("AABB", 1) is True
    assert m.set_gallery_style("CCDD", 2) is True  # merges into existing [gallery] section
    assert m.get_gallery_style("AABB") == 1
    assert m.get_gallery_style("CCDD") == 2

    with patch("divoom_gui.gallery_sync.atomic_write_config", side_effect=OSError("disk full")):
        assert m.set_gallery_style("EEFF", 5) is False


# ───────────────────────── gallery filter persistence ─────────────────────────

def test_get_gallery_filter_defaults_when_no_config(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    m = _Host()
    assert json.loads(m.get_gallery_filter()) == {"sort": 1, "file_size": 0}


def test_set_and_get_gallery_filter_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    m = _Host()
    assert m.set_gallery_filter(sort=2, file_size=64) is True
    assert json.loads(m.get_gallery_filter()) == {"sort": 2, "file_size": 64}


def test_get_gallery_filter_exception_path_returns_default(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    m = _Host()
    cfg_dir = tmp_path / ".config" / "divoom-control"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.ini").write_text("[gallery]\ngallery_sort = not-an-int\n")
    assert json.loads(m.get_gallery_filter()) == {"sort": 1, "file_size": 0}


def test_set_gallery_filter_exception_path_returns_false(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    m = _Host()
    with patch("divoom_gui.gallery_sync.atomic_write_config", side_effect=OSError("disk full")):
        assert m.set_gallery_filter(sort=3, file_size=16) is False

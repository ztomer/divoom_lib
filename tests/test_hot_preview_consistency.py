"""R52: the hot-channel PREVIEW must show what the UPDATE actually sends.

Both paths derive the file set from `fetch_hot_manifest(device_type)`, where
`device_type = DEVICE_TYPE_BY_SIZE[active_device_size]`:

  - send:    HotUpdate.update(device_size=...) (divoom_lib/tools/hot_update.py)
  - preview: GalleryHotApiMixin.hot_update_preview()  (this module)

The danger is the preview silently fetching a DIFFERENT manifest than the send —
e.g. always the 16px manifest while a 64px Pixoo gets the 64px one (the same
ghost-default bug we fixed for the community gallery). These tests pin the
invariant: the preview fetches at the active device size, and identical sizes
yield identical file sets.
"""
from __future__ import annotations

import base64
import json

import divoom_lib.tools.hot_update as hot
from divoom_lib.tools.hot_update import HotFile, DEVICE_TYPE_BY_SIZE
from divoom_gui import gallery_hot_api
from divoom_gui.gallery_hot_api import GalleryHotApiMixin


class _Api(GalleryHotApiMixin):
    """Minimal host for the mixin with a controllable active device size."""
    def __init__(self, size):
        self._size = size

    def _active_device_size(self, default: int = 16) -> int:
        return self._size


def _patch_manifest(monkeypatch, tmp_path):
    """Record the device_type the preview fetches the manifest for, and keep the
    gallery-cache lookup out of the real home dir."""
    seen = {}

    def fake_fetch(device_type):
        seen["device_type"] = device_type
        return [HotFile(vendor_id=1, file_id="g/abc", version=3, sha1="x")]

    monkeypatch.setattr(hot, "fetch_hot_manifest", fake_fetch)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)  # no gallery cache
    return seen


def test_preview_fetches_manifest_at_active_device_size(monkeypatch, tmp_path):
    seen = _patch_manifest(monkeypatch, tmp_path)
    out = json.loads(_Api(64).hot_update_preview())
    assert out["success"] is True
    # 64px Pixoo → device_type 2, NOT the 16px default (1).
    assert seen["device_type"] == DEVICE_TYPE_BY_SIZE[64] == 2
    assert [i["file_id"] for i in out["items"]] == ["g/abc"]


def test_preview_device_type_tracks_size(monkeypatch, tmp_path):
    seen = _patch_manifest(monkeypatch, tmp_path)
    for size in (16, 32, 64, 128, 256):
        _Api(size).hot_update_preview()
        assert seen["device_type"] == DEVICE_TYPE_BY_SIZE[size], (
            f"preview at size {size} fetched the wrong manifest")


def test_preview_uses_gallery_cache_names_and_marks_has_cache(monkeypatch, tmp_path):
    """Cache-hit items get their friendly name/likes/preview_url from the
    local gallery cache (lines 87-98) instead of falling back to the raw
    file_id tail."""
    seen = _patch_manifest(monkeypatch, tmp_path)

    cache_dir = tmp_path / ".config" / "divoom-control"
    cache_dir.mkdir(parents=True)
    cache_file = cache_dir / "gallery_cache.json"
    cache_file.write_text(json.dumps([
        {"file_id": "g/abc", "name": "Cool Art", "likes": 42, "preview_url": "http://x/y.gif"},
    ]), encoding="utf-8")

    out = json.loads(_Api(16).hot_update_preview())
    assert out["success"] is True
    item = out["items"][0]
    assert item["name"] == "Cool Art"
    assert item["likes"] == 42
    assert item["preview_url"] == "http://x/y.gif"
    assert item["has_cache"] is True


def test_preview_falls_back_to_file_id_tail_when_uncached(monkeypatch, tmp_path):
    """No gallery cache on disk → name falls back to the file_id tail and
    has_cache is False."""
    _patch_manifest(monkeypatch, tmp_path)
    out = json.loads(_Api(16).hot_update_preview())
    item = out["items"][0]
    assert item["name"] == "abc"  # "g/abc".rsplit("/", 1)[-1]
    assert item["has_cache"] is False


def test_preview_survives_corrupt_gallery_cache(monkeypatch, tmp_path):
    """A malformed gallery_cache.json must not blow up the preview — the
    inner try/except swallows the parse error and falls back to file_id."""
    _patch_manifest(monkeypatch, tmp_path)
    cache_dir = tmp_path / ".config" / "divoom-control"
    cache_dir.mkdir(parents=True)
    (cache_dir / "gallery_cache.json").write_text("{not valid json", encoding="utf-8")

    out = json.loads(_Api(16).hot_update_preview())
    assert out["success"] is True
    assert out["items"][0]["name"] == "abc"
    assert out["items"][0]["has_cache"] is False


def test_preview_reports_manifest_fetch_failure(monkeypatch, tmp_path):
    """If fetch_hot_manifest raises (network/daemon trouble), the preview
    reports a structured failure instead of propagating the exception."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    def boom(device_type):
        raise RuntimeError("cloud unreachable")

    monkeypatch.setattr(hot, "fetch_hot_manifest", boom)
    out = json.loads(_Api(16).hot_update_preview())
    assert out == {"success": False, "error": "cloud unreachable"}


def test_preview_and_send_share_one_manifest_source():
    """Guard: both the preview and the send resolve device_type through the same
    DEVICE_TYPE_BY_SIZE map + fetch_hot_manifest — if someone forks one path,
    this is the seam that breaks. (Static reference, not a runtime call.) The
    send now funnels the fetch through _load_hot_files (device_type-keyed cache),
    so pin that indirection too rather than weakening the invariant."""
    import inspect
    preview_src = inspect.getsource(GalleryHotApiMixin.hot_update_preview)
    update_src = inspect.getsource(hot.HotUpdate.update)
    loader_src = inspect.getsource(hot._load_hot_files)
    # Both paths key off pixel size via the same map.
    assert "DEVICE_TYPE_BY_SIZE" in preview_src
    assert "DEVICE_TYPE_BY_SIZE" in update_src
    # Preview fetches the manifest directly; the send funnels through
    # _load_hot_files, the one place that calls fetch_hot_manifest.
    assert "fetch_hot_manifest" in preview_src
    assert "_load_hot_files" in update_src
    assert "fetch_hot_manifest" in loader_src


# ── get_animated_preview: download/decode fan-out ───────────────────────────
# Covers divoom_gui/gallery_hot_api.py lines 131-212. No real network: the
# CDN fetch is mocked at urllib.request.urlopen (the boundary), and the
# gallery cache dir is redirected via Path.home() like the tests above.

class _FakeResp:
    """Minimal context-manager stand-in for urllib's HTTPResponse."""
    def __init__(self, data: bytes):
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._data


def _mock_download(monkeypatch, raw_bytes: bytes | None = None, *, raises: Exception | None = None):
    def fake_urlopen(req, timeout=8):
        if raises is not None:
            raise raises
        return _FakeResp(raw_bytes)
    monkeypatch.setattr(gallery_hot_api.urllib.request, "urlopen", fake_urlopen)


class TestGetAnimatedPreview:
    def test_returns_precached_gif_without_downloading(self, monkeypatch, tmp_path):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        cache_dir = tmp_path / ".config" / "divoom-control" / "cache_gallery"
        cache_dir.mkdir(parents=True)
        (cache_dir / "g_abc.gif").write_bytes(b"already-cached-gif-bytes")
        # No urlopen mock installed — a real network call here would fail the
        # test outright, proving the cache short-circuits it.
        out = _Api(16).get_animated_preview("g/abc")
        assert out.startswith("data:image/gif;base64,")
        assert base64.b64decode(out.split(",", 1)[1]) == b"already-cached-gif-bytes"

    def test_magic43_decode_success(self, monkeypatch, tmp_path):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        _mock_download(monkeypatch, b"raw-magic43-container")
        monkeypatch.setattr(gallery_hot_api.media_decoder, "extract_image_from_magic_43",
                             lambda data: (b"pngbytes", ".png"), raising=False)
        out = _Api(16).get_animated_preview("g/xyz")
        assert out.startswith("data:image/png;base64,")
        assert base64.b64decode(out.split(",", 1)[1]) == b"pngbytes"
        # Decoded output was cached to disk for next time.
        cache_dir = tmp_path / ".config" / "divoom-control" / "cache_gallery"
        assert (cache_dir / "g_xyz.png").read_bytes() == b"pngbytes"

    def test_hot_channel_format_decode_success(self, monkeypatch, tmp_path):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        _mock_download(monkeypatch, b"\xaa-hot-channel-raw-frames")
        monkeypatch.setattr(gallery_hot_api.media_decoder, "extract_image_from_magic_43", lambda data: None, raising=False)

        def fake_decode_hot(raw, out_path, max_frames=60):
            out_path.write_bytes(b"GIF89a-decoded-hot")
            return True
        monkeypatch.setattr(gallery_hot_api.media_decoder, "decode_hot_file_to_gif", fake_decode_hot, raising=False)

        out = _Api(16).get_animated_preview("hot/1")
        assert out.startswith("data:image/gif;base64,")
        assert base64.b64decode(out.split(",", 1)[1]) == b"GIF89a-decoded-hot"

    def test_raw_gif_passthrough(self, monkeypatch, tmp_path):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        raw = b"GIF89a" + b"\x00" * 20
        _mock_download(monkeypatch, raw)
        monkeypatch.setattr(gallery_hot_api.media_decoder, "extract_image_from_magic_43", lambda data: None, raising=False)
        monkeypatch.setattr(gallery_hot_api.media_decoder, "decode_hot_file_to_gif", lambda *a, **k: False, raising=False)
        out = _Api(16).get_animated_preview("g/raw-gif")
        assert out.startswith("data:image/gif;base64,")
        assert base64.b64decode(out.split(",", 1)[1]) == raw

    def test_raw_png_passthrough(self, monkeypatch, tmp_path):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        raw = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
        _mock_download(monkeypatch, raw)
        monkeypatch.setattr(gallery_hot_api.media_decoder, "extract_image_from_magic_43", lambda data: None, raising=False)
        monkeypatch.setattr(gallery_hot_api.media_decoder, "decode_hot_file_to_gif", lambda *a, **k: False, raising=False)
        out = _Api(16).get_animated_preview("g/raw-png")
        assert out.startswith("data:image/png;base64,")
        assert base64.b64decode(out.split(",", 1)[1]) == raw

    def test_raw_jpeg_passthrough(self, monkeypatch, tmp_path):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        raw = b"\xff\xd8" + b"\x00" * 20
        _mock_download(monkeypatch, raw)
        monkeypatch.setattr(gallery_hot_api.media_decoder, "extract_image_from_magic_43", lambda data: None, raising=False)
        monkeypatch.setattr(gallery_hot_api.media_decoder, "decode_hot_file_to_gif", lambda *a, **k: False, raising=False)
        out = _Api(16).get_animated_preview("g/raw-jpg")
        assert out.startswith("data:image/jpeg;base64,")
        assert base64.b64decode(out.split(",", 1)[1]) == raw

    def test_cloud_frames_multi_frame_becomes_gif(self, monkeypatch, tmp_path):
        from PIL import Image
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        # Not GIF/PNG/JPEG magic — forces the cloud-frames fallback branch.
        _mock_download(monkeypatch, b"\x09unrecognized-container")
        monkeypatch.setattr(gallery_hot_api.media_decoder, "extract_image_from_magic_43", lambda data: None, raising=False)
        monkeypatch.setattr(gallery_hot_api.media_decoder, "decode_hot_file_to_gif", lambda *a, **k: False, raising=False)
        frames = [Image.new("RGB", (16, 16), c) for c in [(255, 0, 0), (0, 255, 0)]]
        monkeypatch.setattr(gallery_hot_api.media_decoder, "decode_cloud_frames", lambda raw: (frames, 100), raising=False)

        out = _Api(16).get_animated_preview("cloud/multi")
        assert out.startswith("data:image/gif;base64,")

    def test_cloud_frames_single_frame_becomes_png(self, monkeypatch, tmp_path):
        from PIL import Image
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        _mock_download(monkeypatch, b"\x09unrecognized-container")
        monkeypatch.setattr(gallery_hot_api.media_decoder, "extract_image_from_magic_43", lambda data: None, raising=False)
        monkeypatch.setattr(gallery_hot_api.media_decoder, "decode_hot_file_to_gif", lambda *a, **k: False, raising=False)
        frames = [Image.new("RGB", (16, 16), (10, 20, 30))]
        monkeypatch.setattr(gallery_hot_api.media_decoder, "decode_cloud_frames", lambda raw: (frames, 0), raising=False)

        out = _Api(16).get_animated_preview("cloud/single")
        assert out.startswith("data:image/png;base64,")

    def test_pil_catch_all_fallback_success(self, monkeypatch, tmp_path):
        """A format with no dedicated decoder (e.g. BMP) still renders via the
        PIL catch-all — real PIL-encoded bytes, not a mock of PIL itself."""
        from PIL import Image
        import io as _io
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        buf = _io.BytesIO()
        Image.new("RGB", (4, 4), (1, 2, 3)).save(buf, format="BMP")
        bmp_bytes = buf.getvalue()
        assert bmp_bytes[:2] == b"BM"  # doesn't match the gif/png/jpeg magic checks
        _mock_download(monkeypatch, bmp_bytes)
        monkeypatch.setattr(gallery_hot_api.media_decoder, "extract_image_from_magic_43", lambda data: None, raising=False)
        monkeypatch.setattr(gallery_hot_api.media_decoder, "decode_hot_file_to_gif", lambda *a, **k: False, raising=False)
        monkeypatch.setattr(gallery_hot_api.media_decoder, "decode_cloud_frames", lambda raw: (None, 0), raising=False)

        out = _Api(16).get_animated_preview("misc/bmp")
        assert out.startswith("data:image/png;base64,")

    def test_no_decoder_handles_returns_empty_string(self, monkeypatch, tmp_path):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        _mock_download(monkeypatch, b"totally-unrecognizable-junk")
        monkeypatch.setattr(gallery_hot_api.media_decoder, "extract_image_from_magic_43", lambda data: None, raising=False)
        monkeypatch.setattr(gallery_hot_api.media_decoder, "decode_hot_file_to_gif", lambda *a, **k: False, raising=False)
        monkeypatch.setattr(gallery_hot_api.media_decoder, "decode_cloud_frames", lambda raw: (None, 0), raising=False)

        out = _Api(16).get_animated_preview("misc/junk")
        assert out == ""

    def test_download_failure_returns_empty_string(self, monkeypatch, tmp_path):
        """Network trouble (timeout, DNS, 404 raised as URLError) must degrade
        to an empty string, not propagate — the GUI just shows no preview."""
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        _mock_download(monkeypatch, raises=OSError("connection refused"))
        out = _Api(16).get_animated_preview("g/unreachable")
        assert out == ""


# ── _coerce_list / _coerce_dict: pywebview varargs normalization ────────────
# Called as `self._coerce_list(*args_tuple, kwargs, key)` from callers like
# MediaSyncMixin.set_tickers — pywebview may hand these either a single JSON
# string, a single Python list, multiple positional args, or kwargs.

class TestCoerceList:
    def test_single_json_list_string(self):
        assert GalleryHotApiMixin._coerce_list(('["a", "b"]',), {}, "tickers") == ["a", "b"]

    def test_single_json_object_string_wraps_in_list(self):
        assert GalleryHotApiMixin._coerce_list(('{"a": 1}',), {}, "tickers") == [{"a": 1}]

    def test_single_non_json_string_falls_back_to_one_item_list(self):
        assert GalleryHotApiMixin._coerce_list(("AAPL",), {}, "tickers") == ["AAPL"]

    def test_single_list_arg_passthrough(self):
        assert GalleryHotApiMixin._coerce_list((["x", "y"],), {}, "tickers") == ["x", "y"]

    def test_single_tuple_arg_becomes_list(self):
        assert GalleryHotApiMixin._coerce_list((("x", "y"),), {}, "tickers") == ["x", "y"]

    def test_single_non_iterable_arg_wraps_in_list(self):
        assert GalleryHotApiMixin._coerce_list((5,), {}, "tickers") == [5]

    def test_multiple_positional_args(self):
        assert GalleryHotApiMixin._coerce_list(("a", "b", "c"), {}, "tickers") == ["a", "b", "c"]

    def test_kwargs_list_fallback(self):
        assert GalleryHotApiMixin._coerce_list((), {"tickers": ["z"]}, "tickers") == ["z"]

    def test_kwargs_non_list_value_ignored(self):
        assert GalleryHotApiMixin._coerce_list((), {"tickers": "not-a-list"}, "tickers") == []

    def test_no_args_no_kwargs_returns_empty(self):
        assert GalleryHotApiMixin._coerce_list((), {}, "tickers") == []


class TestCoerceDict:
    def test_single_json_dict_string(self):
        assert GalleryHotApiMixin._coerce_dict(('{"enabled": true}',), {}) == {"enabled": True}

    def test_single_non_json_string_returns_empty(self):
        assert GalleryHotApiMixin._coerce_dict(("not json",), {}) == {}

    def test_single_json_list_string_returns_empty(self):
        assert GalleryHotApiMixin._coerce_dict(('["a"]',), {}) == {}

    def test_single_dict_arg_passthrough(self):
        assert GalleryHotApiMixin._coerce_dict(({"enabled": True},), {}) == {"enabled": True}

    def test_single_non_dict_arg_returns_empty(self):
        assert GalleryHotApiMixin._coerce_dict((5,), {}) == {}

    def test_kwargs_allowed_keys_filtered(self):
        out = GalleryHotApiMixin._coerce_dict(
            (), {"enabled": True, "interval": 5, "bogus": "x"})
        assert out == {"enabled": True, "interval": 5}

    def test_no_args_no_kwargs_returns_empty(self):
        assert GalleryHotApiMixin._coerce_dict((), {}) == {}

    def test_multiple_positional_args_uses_kwargs_branch(self):
        out = GalleryHotApiMixin._coerce_dict(("a", "b"), {"classify": True})
        assert out == {"classify": True}

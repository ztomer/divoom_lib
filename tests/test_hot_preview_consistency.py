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

import json

import divoom_lib.tools.hot_update as hot
from divoom_lib.tools.hot_update import HotFile, DEVICE_TYPE_BY_SIZE
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

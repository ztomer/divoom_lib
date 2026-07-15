# gui/gallery_download.py — single-asset download + decode for the cloud gallery.

# Split out of gallery_sync.py to stay under the 500-LOC module gate; the
# decode/recovery contract lives here, GallerySyncMixin.fetch_gallery just
# calls fetch_gallery_asset() per item.

import logging
import urllib.request
from pathlib import Path

from divoom_lib import media_decoder

logger = logging.getLogger("divoom_gui")


def fetch_gallery_asset(cache_dir: Path, file_id: str) -> bool:
    """Download + decode one cloud gallery asset into ``cache_dir``.

    Returns True if a decoded preview (``.gif``/``.png``/``.jpg``) now exists.
    A cached ``.bin`` may be corrupt/truncated (confirmed live via CBC-padding
    errors on this project's own cache) — if it fails to decode it is dropped
    and re-downloaded in the SAME call, so a single ``fetch_gallery`` pass
    recovers the preview instead of leaving an empty (black) gallery tile
    until the gallery is opened again."""
    safe_filename = file_id.replace("/", "_")
    cache_file_item = cache_dir / safe_filename
    cache_file_bin = cache_file_item.with_suffix(".bin")

    def existing_preview():
        for ext in (".gif", ".png", ".jpg", ".jpeg"):
            p = cache_file_item.with_suffix(ext)
            if p.exists():
                return p
        return None

    def preview_valid():
        """A preview counts only if it opens AND is not blank.

        A stale/corrupt preview (all-black / unreadable — e.g. written by a
        pre-fix build) is dropped, along with its ``.bin``, so the asset is
        re-downloaded and re-decoded in the same pass instead of rendering a
        permanent black tile (R64)."""
        p = existing_preview()
        if p is None:
            return False
        if media_decoder.is_black_image(p):
            logger.warning(f"Gallery: dropping blank/corrupt preview {p.name}")
            p.unlink(missing_ok=True)
            cache_file_bin.unlink(missing_ok=True)
            return False
        return True

    def has_preview():
        return existing_preview() is not None

    def decode_bin():
        try:
            raw_bytes = cache_file_bin.read_bytes()
        except Exception:
            return False
        decoded = False
        try:
            extracted = media_decoder.extract_image_from_magic_43(raw_bytes)
            if extracted:
                img_bytes, ext = extracted
                cache_file_item.with_suffix(ext).write_bytes(img_bytes)
                decoded = True
            elif raw_bytes.startswith(b"GIF89a") or raw_bytes.startswith(b"GIF87a"):
                cache_file_item.with_suffix(".gif").write_bytes(raw_bytes)
                decoded = True
            elif raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                cache_file_item.with_suffix(".png").write_bytes(raw_bytes)
                decoded = True
            elif raw_bytes.startswith(b"\xff\xd8"):
                cache_file_item.with_suffix(".jpg").write_bytes(raw_bytes)
                decoded = True
            else:
                decoded = bool(media_decoder.decode_and_save_preview(
                    raw_bytes, cache_file_item.with_suffix(".png")))
        except Exception as dec_err:
            logger.warning(f"Gallery decode failed for {file_id}: {dec_err}")
        if not decoded:
            # Drop the bad .bin (truncated/corrupt download) so the next decode
            # attempt re-downloads fresh bytes instead of retrying the same
            # corrupt cache entry forever.
            cache_file_bin.unlink(missing_ok=True)
        return decoded

    def download_bin():
        try:
            dl_url = f"https://fin.divoom-gz.com/{file_id}"
            req_dl = urllib.request.Request(dl_url, headers={"User-Agent": "okhttp/4.12.0"})
            with urllib.request.urlopen(req_dl, timeout=5) as dl_resp:
                cache_file_bin.write_bytes(dl_resp.read())
            return True
        except Exception as dl_err:
            logger.warning(f"Gallery download failed for {file_id}: {dl_err}")
            return False

    if preview_valid():
        return True
    if cache_file_bin.exists():
        if decode_bin():
            return True
        cache_file_bin.unlink(missing_ok=True)
    return bool(download_bin() and existing_preview() is None and decode_bin())

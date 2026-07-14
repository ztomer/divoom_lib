# gui/gallery_hot_api.py — hot-channel + custom-art RPC wrappers and the
# animated-preview download/decode path. Split from gallery_sync.py
# (500-LOC rule); mixed into GallerySyncMixin.

import json
import logging
import base64
import threading
import time
import urllib.request
from pathlib import Path

from divoom_lib import media_decoder

logger = logging.getLogger("divoom_gui")


class GalleryHotApiMixin:
    def custom_art_push(self, payload_json: str, page: int,
                        slot: int | None = None) -> str:
        """Push cloud files to a custom art page on the device. JSON summary.

        ``payload_json`` is either a {slot: file_id} mapping (preferred — the
        page is sent once, unmapped slots cleared) or a legacy file-id list."""
        logger.info(f"GUI Action: Custom art push page={page} slot={slot} payload={payload_json}")
        client = self._client()
        if client is None:
            return json.dumps({"success": False, "error": "no daemon available"})
        try:
            payload = json.loads(payload_json)
        except (TypeError, ValueError):
            return json.dumps({"success": False, "error": "invalid payload"})
        if isinstance(payload, dict):
            return json.dumps(client.custom_art_push([], int(page), slots=payload))
        return json.dumps(client.custom_art_push(payload, int(page), slot))

    def custom_art_query_page(self, page: int = 0) -> str:
        """Query device for filled slot IDs on a custom art page. JSON summary."""
        logger.info(f"GUI Action: Custom art query page={page}")
        client = self._client()
        if client is None:
            return json.dumps({"success": False, "error": "no daemon available"})
        return json.dumps(client.custom_art_query_page(page))

    def hot_channel_update(self) -> str:
        """Start HOT channel update in background on daemon. Returns immediately."""
        logger.info("GUI Action: Hot channel update (start)...")
        client = self._client()
        if client is None:
            return json.dumps({"success": False, "error": "no daemon available"})
        size = self._active_device_size() if hasattr(self, "_active_device_size") else 16
        # R53: pass the active device address so the DAEMON stamps the
        # last-checked state under the same key the GUI reads by (hot_get_check).
        addr = self._active_device_mac() if hasattr(self, "_active_device_mac") else None
        r = client.hot_update(device_size=int(size), show=True, address=addr or "")
        return json.dumps(r)

    def sync_now(self) -> str:
        """Manually run Auto-Sync immediately, instead of waiting for the
        scheduled interval. Pushes hot-channel content to every toggled sync
        target (`hotchannel_config.get_targets()` — the same list the
        Routines > Auto-Sync device toggles edit) one at a time — the daemon
        owns a single active device, so this connects, runs the same
        `hot_update` the "Update Hot Channel" button uses, waits for it to
        finish, disconnects (implicitly, on the next `connect_single_device`),
        and moves on. A device that can't connect or fails to sync is
        reported and skipped, not fatal to the run (mirrors
        `monthly_best_daemon.py::_push_items_to_target`'s per-address
        try/except). Runs in a background thread; returns immediately."""
        logger.info("GUI Action: Sync Now (start)...")
        from divoom_lib import hotchannel_config

        def notify(address, phase, **extra):
            if not self.window:
                return
            try:
                payload = {"address": address, "phase": phase, **extra}
                js = f"if (window.onSyncNowProgress) {{ window.onSyncNowProgress({json.dumps(payload)}); }}"
                self.window.evaluate_js(js)
            except Exception as e:
                logger.warning(f"Failed to send sync-now progress: {e}")

        def worker():
            targets = hotchannel_config.get_targets()
            summary = {"total": len(targets), "ok": 0, "failed": 0}
            for address in targets:
                notify(address, "connecting")
                try:
                    if not self.connect_single_device(address):
                        summary["failed"] += 1
                        notify(address, "error", error="Could not connect")
                        continue
                except Exception as e:
                    summary["failed"] += 1
                    notify(address, "error", error=str(e))
                    continue

                try:
                    client = self._client()
                    if client is None:
                        raise RuntimeError("no daemon available")
                    size = self._active_device_size() if hasattr(self, "_active_device_size") else 16
                    start = client.hot_update(device_size=int(size), show=True, address=address)
                    if not start.get("success"):
                        raise RuntimeError(start.get("error") or "could not start hot update")
                    notify(address, "syncing")

                    status = {"phase": "starting"}
                    deadline = time.monotonic() + 120
                    while time.monotonic() < deadline:
                        status = client.hot_update_progress()
                        if status.get("phase") in ("done", "error"):
                            break
                        time.sleep(0.6)

                    if status.get("phase") == "done":
                        summary["ok"] += 1
                        served = len((status.get("result") or {}).get("served", []))
                        notify(address, "done", served=served)
                    else:
                        summary["failed"] += 1
                        notify(address, "error", error=status.get("error") or "timed out")
                except Exception as e:
                    summary["failed"] += 1
                    notify(address, "error", error=str(e))

            if self.window:
                try:
                    js = f"if (window.onSyncNowComplete) {{ window.onSyncNowComplete({json.dumps(summary)}); }}"
                    self.window.evaluate_js(js)
                except Exception as e:
                    logger.warning(f"Failed to send sync-now completion: {e}")

        threading.Thread(target=worker, name="DivoomSyncNow", daemon=True).start()
        return json.dumps({"success": True})

    def hot_update_status(self) -> str:
        """Query daemon for current hot update progress."""
        logger.debug("GUI Action: Hot update status poll...")
        client = self._client()
        if client is None:
            return json.dumps({"phase": "error", "error": "no daemon"})
        return json.dumps(client.hot_update_progress())

    def hot_get_check(self, address: str = "") -> str:
        """R53: the daemon-recorded last hot-channel check for a device (or
        ``{}``). Reads the shared ``hot_update_state.json`` the daemon writes.
        With no ``address`` it resolves the active device — the same key
        ``hot_channel_update`` passes for the write, so read and write always
        agree."""
        from divoom_lib import hot_update_state
        addr = address or (self._active_device_mac()
                           if hasattr(self, "_active_device_mac") else "")
        return json.dumps(hot_update_state.get_check(addr or ""))

    def hot_update_preview(self) -> str:
        """Fetch the hot channel manifest from Divoom's cloud and cross-reference
        with the cached gallery to show what would be pushed."""
        from divoom_lib.tools.hot_update import fetch_hot_manifest, DEVICE_TYPE_BY_SIZE
        try:
            size = self._active_device_size() if hasattr(self, "_active_device_size") else 16
            device_type = DEVICE_TYPE_BY_SIZE.get(int(size), 1)
            files = fetch_hot_manifest(device_type)

            cache_file = Path.home() / ".config" / "divoom-control" / "gallery_cache.json"
            name_map = {}
            if cache_file.exists():
                try:
                    cached = json.loads(cache_file.read_text(encoding="utf-8"))
                    for item in cached:
                        fid = item.get("file_id")
                        if fid:
                            name_map[fid] = {
                                "name": item.get("name", "unnamed"),
                                "likes": item.get("likes", 0),
                                "preview_url": item.get("preview_url", ""),
                            }
                except Exception:
                    pass

            items = []
            for f in files:
                meta = name_map.get(f.file_id, {})
                # Don't send raw CDN URL as preview — it's a binary container the
                # browser can't render. Animated previews are loaded lazily via
                # get_animated_preview() which handles download+decode.
                items.append({
                    "file_id": f.file_id,
                    "version": f.version,
                    "vendor_id": f.vendor_id,
                    "name": meta.get("name") or f.file_id.rsplit("/", 1)[-1],
                    "likes": meta.get("likes", 0),
                    "preview_url": meta.get("preview_url", ""),
                    "has_cache": f.file_id in name_map,
                })

            # Show newest-first deterministically. The hot API's list order is
            # not a stable contract (it can reorder its "featured" set between
            # requests), which made the newest file land at an arbitrary tile —
            # so the just-added art wasn't where the user looked for it. Sorting by
            # version here pins the newest to tile 0 regardless of API order.
            items.sort(key=lambda it: it.get("version", 0), reverse=True)

            return json.dumps({"success": True, "items": items, "count": len(items)})
        except Exception as e:
            logger.warning(f"hot_update_preview failed: {e}")
            return json.dumps({"success": False, "error": str(e)})

    def get_animated_preview(self, file_id: str) -> str:
        """Return base64-encoded animated preview, downloading + decoding from
        CDN if not already cached. Works for both gallery and hot channel items."""
        logger.info(f"GUI Action: Fetching animated preview for {file_id}")
        try:
            safe_filename = file_id.replace("/", "_")
            cache_dir = Path.home() / ".config" / "divoom-control" / "cache_gallery"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file_gif = cache_dir / f"{safe_filename}.gif"
            cache_file_png = cache_dir / f"{safe_filename}.png"
            cache_file_jpg = cache_dir / f"{safe_filename}.jpg"

            # Check for any existing decoded preview
            for ext, mime in [(".gif", "image/gif"), (".png", "image/png"), (".jpg", "image/jpeg")]:
                cached = cache_dir / f"{safe_filename}{ext}"
                if cached.exists():
                    img_data = cached.read_bytes()
                    b64_str = base64.b64encode(img_data).decode("utf-8")
                    return f"data:{mime};base64,{b64_str}"

            # Not cached — download raw file from CDN
            from divoom_lib.tools.hot_update import HOT_FILE_BASE
            dl_url = HOT_FILE_BASE + file_id
            req = urllib.request.Request(dl_url, headers={"User-Agent": "okhttp/4.12.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                raw_bytes = resp.read()

            # Try magic-43 decode first
            extracted = media_decoder.extract_image_from_magic_43(raw_bytes)
            if extracted:
                img_bytes, ext = extracted
                out_path = cache_dir / f"{safe_filename}{ext}"
                out_path.write_bytes(img_bytes)
                b64_str = base64.b64encode(img_bytes).decode("utf-8")
                mime = "image/gif" if ext == ".gif" else ("image/jpeg" if ext in (".jpg", ".jpeg") else "image/png")
                return f"data:{mime};base64,{b64_str}"

            # Hot channel format (magic 0xAA): raw sequential 16×16 RGB frames
            if media_decoder.decode_hot_file_to_gif(raw_bytes, cache_file_gif):
                b64_str = base64.b64encode(cache_file_gif.read_bytes()).decode("utf-8")
                return f"data:image/gif;base64,{b64_str}"

            # Raw GIF/PNG/JPEG
            if raw_bytes.startswith(b"GIF89a") or raw_bytes.startswith(b"GIF87a"):
                cache_file_gif.write_bytes(raw_bytes)
                b64_str = base64.b64encode(raw_bytes).decode("utf-8")
                return f"data:image/gif;base64,{b64_str}"
            if raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                cache_file_png.write_bytes(raw_bytes)
                b64_str = base64.b64encode(raw_bytes).decode("utf-8")
                return f"data:image/png;base64,{b64_str}"
            if raw_bytes.startswith(b"\xff\xd8"):
                cache_file_jpg.write_bytes(raw_bytes)
                b64_str = base64.b64encode(raw_bytes).decode("utf-8")
                return f"data:image/jpeg;base64,{b64_str}"

            # Fallback 1: cloud container decoder (magic 9/18/26) → animated GIF
            frames, duration = media_decoder.decode_cloud_frames(raw_bytes)
            if frames:
                from PIL import Image
                previews = [f.resize((128, 128), Image.Resampling.NEAREST) for f in frames]
                if len(previews) > 1:
                    previews[0].save(cache_file_gif, save_all=True,
                                     append_images=previews[1:], duration=duration, loop=0)
                    b64_str = base64.b64encode(cache_file_gif.read_bytes()).decode("utf-8")
                    return f"data:image/gif;base64,{b64_str}"
                else:
                    previews[0].save(cache_file_png)
                    b64_str = base64.b64encode(cache_file_png.read_bytes()).decode("utf-8")
                    return f"data:image/png;base64,{b64_str}"

            # Fallback 2: PIL catch-all (handles any format PIL can open)
            try:
                from PIL import Image
                import io
                pil_img = Image.open(io.BytesIO(raw_bytes))
                pil_img.save(cache_file_png)
                b64_str = base64.b64encode(cache_file_png.read_bytes()).decode("utf-8")
                return f"data:image/png;base64,{b64_str}"
            except Exception:
                logger.warning(f"No decoder could handle {file_id} (magic={raw_bytes[0] if raw_bytes else 0}, {len(raw_bytes)}B)")

        except Exception as e:
            logger.warning(f"get_animated_preview failed for {file_id}: {e}")
        return ""

    @staticmethod
    def _coerce_list(args, kwargs, key) -> list:
        if len(args) == 1:
            v = args[0]
            if isinstance(v, str):
                try:
                    parsed = json.loads(v)
                    return parsed if isinstance(parsed, list) else [parsed]
                except ValueError:
                    return [v]
            return list(v) if isinstance(v, (list, tuple)) else [v]
        if len(args) > 1:
            return list(args)
        if key in kwargs and isinstance(kwargs[key], (list, tuple)):
            return list(kwargs[key])
        return []

    @staticmethod
    def _coerce_dict(args, kwargs) -> dict:
        if len(args) == 1:
            v = args[0]
            if isinstance(v, str):
                try:
                    parsed = json.loads(v)
                    return parsed if isinstance(parsed, dict) else {}
                except ValueError:
                    return {}
            return dict(v) if isinstance(v, dict) else {}
        allowed = ("enabled", "interval", "classify", "targets")
        return {k: kwargs[k] for k in allowed if k in kwargs}

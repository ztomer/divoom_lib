# gui/gallery_sync.py

import json
import logging
import base64
import urllib.request
import threading
from pathlib import Path
from divoom_lib import divoom_auth
from divoom_lib import media_decoder
from divoom_lib.utils.atomic_io import atomic_write_config, atomic_write_text

logger = logging.getLogger("divoom_gui")

from divoom_gui.gallery_hot_api import GalleryHotApiMixin


class GallerySyncMixin(GalleryHotApiMixin):
    """Mixin for cloud-voted gallery fetching and hot-channel schedule orchestration."""
    def load_cached_gallery(self) -> str:
        cache_file = Path.home() / ".config" / "divoom-control" / "gallery_cache.json"
        if cache_file.exists():
            try:
                raw = cache_file.read_text(encoding="utf-8")
                parsed = json.loads(raw)
                # Rebuild from the on-disk cache directory if the JSON cache
                # is empty, or only contains a manual/test entry (file_id="9999"
                # is the convention from the NeonSkull test fixture — a real
                # Divoom FileId is a CDN path like "group1_M00_..."). This
                # prevents the gallery from rendering a single bogus item
                # when the on-disk items are otherwise present.
                cache_dir = Path.home() / ".config" / "divoom-control" / "cache_gallery"
                if (not parsed
                    or all(str(a.get("file_id", "")) == "9999" for a in parsed)):
                    if cache_dir.exists() and any(cache_dir.iterdir()):
                        logger.info(
                            "Gallery JSON cache is empty/stale; rebuilding from "
                            "on-disk cache_gallery directory."
                        )
                        return self.get_cached_gallery_files()
                return raw
            except Exception as ce:
                logger.warning(f"Failed to read gallery cache: {ce}")
        return "[]"

    def get_cached_gallery_files(self) -> str:
        cache_dir = Path.home() / ".config" / "divoom-control" / "cache_gallery"
        if not cache_dir.exists():
            return "[]"
        
        name_map = {}
        cache_file = Path.home() / ".config" / "divoom-control" / "gallery_cache.json"
        if cache_file.exists():
            try:
                cached_items = json.loads(cache_file.read_text(encoding="utf-8"))
                for item in cached_items:
                    fid = item.get("file_id")
                    if fid:
                        safe_name = fid.replace("/", "_")
                        name_map[safe_name] = item.get("name", "unnamed")
            except Exception as e:
                logger.warning(f"Failed to parse gallery cache map: {e}")

        results = {}
        for path in cache_dir.iterdir():
            if path.is_file() and path.suffix.lower() in [".gif", ".png", ".jpg", ".jpeg"]:
                if path.stat().st_size == 0:
                    continue
                safe_name = path.stem
                ext = path.suffix.lower()
                
                # Deduplicate by stem, prioritizing .gif animations
                if safe_name in results and results[safe_name]["ext"] == ".gif" and ext != ".gif":
                    continue
                    
                display_name = name_map.get(safe_name, path.name)
                mime_type = "image/gif" if ext == ".gif" else ("image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png")
                try:
                    img_data = path.read_bytes()
                    b64_str = base64.b64encode(img_data).decode("utf-8")
                    preview_url = f"data:{mime_type};base64,{b64_str}"
                    results[safe_name] = {
                        "name": display_name,
                        "path": str(path.absolute()),
                        "preview_url": preview_url,
                        "ext": ext
                    }
                except Exception as e:
                    logger.warning(f"Failed to encode cache file {path}: {e}")
        
        final_list = []
        for item in results.values():
            final_list.append({
                "name": item["name"],
                "path": item["path"],
                "preview_url": item["preview_url"]
            })
        return json.dumps(final_list)

    FILE_SIZE_BITMASK: dict[int, int] = {16: 1, 32: 2, 64: 4, 128: 16, 256: 32}

    @staticmethod
    def _fetch_gallery_asset(cache_dir: Path, file_id: str) -> bool:
        """Download + decode one cloud gallery asset (see gallery_download.py).

        A cached ``.bin`` that fails to decode is dropped and re-downloaded in
        the SAME call, so a single ``fetch_gallery`` pass recovers the preview
        instead of leaving an empty (black) gallery tile until reopened."""
        from divoom_gui.gallery_download import fetch_gallery_asset
        return fetch_gallery_asset(cache_dir, file_id)

    def fetch_gallery(self, classify: int, target_size: int = 16,
                      file_sort: int = 1, file_size: int = 0) -> str:
        """Fetch gallery items. file_size=0 means auto-detect from target_size."""
        logger.info(
            f"GUI Action: Fetching gallery classify={classify} "
            f"target_size={target_size} file_sort={file_sort} file_size={file_size}..."
        )
        
        cached_data = self.load_cached_gallery()

        def background_fetch_worker():
            try:
                retries = 1
                file_list = []
                while retries >= 0:
                    try:
                        if not self.cached_creds:
                            import configparser
                            config_file = Path.home() / ".config" / "divoom-control" / "config.ini"
                            email, password = "", ""
                            if config_file.exists():
                                cfg = configparser.ConfigParser()
                                cfg.read(config_file)
                                email = cfg.get("divoom", "email", fallback="")
                                password = cfg.get("divoom", "password", fallback="")
                            
                            if not email or not password:
                                logger.warning("Background fetch: credentials not configured.")
                                raise RuntimeError("Credentials not configured in config.ini")

                            force_refresh = (retries < 1)
                            self.cached_creds = divoom_auth.get_credentials(force_refresh=force_refresh)
                            
                        if file_size > 0:
                            file_size_bitmask = file_size
                        else:
                            file_size_bitmask = self.FILE_SIZE_BITMASK.get(target_size, 1)
                            
                        body = {
                            "Command": "GetCategoryFileListV2",
                            "Token": self.cached_creds.token,
                            "UserId": self.cached_creds.user_id,
                            "DeviceId": self.device_id,
                            "Classify": classify,
                            "FileSort": file_sort,
                            "FileType": 5,
                            "FileSize": file_size_bitmask,
                            "Version": 19,
                            "StartNum": 1,
                            "EndNum": 30,
                            "RefreshIndex": 0
                        }
                        if self.device_pw:
                            body["DevicePassword"] = self.device_pw

                        url = "https://appin.divoom-gz.com/GetCategoryFileListV2"
                        payload = json.dumps(body).encode("utf-8")
                        req = urllib.request.Request(
                            url,
                            data=payload,
                            headers={
                                "Content-Type": "application/json; charset=utf-8",
                                "User-Agent": "okhttp/4.12.0",
                            },
                            method="POST"
                        )
                        
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            data = json.loads(resp.read().decode("utf-8"))
                            rc = data.get("ReturnCode", -1)
                            if rc in [9, 10, 11]:
                                raise RuntimeError(f"Token expired or mismatch (ReturnCode={rc})")
                            elif rc != 0:
                                raise RuntimeError(f"API Error (ReturnCode={rc}): {data.get('ReturnMessage')}")
                            
                            file_list = data.get("FileList", [])
                            break # success, break out of retry loop
                    except Exception as e:
                        logger.warning(f"Fetch attempt failed (retries left={retries}): {e}")
                        self.cached_creds = None
                        retries -= 1
                        if retries < 0:
                            raise # propagate to outer try-except

                cache_dir = Path.home() / ".config" / "divoom-control" / "cache_gallery"
                cache_dir.mkdir(parents=True, exist_ok=True)
                
                # ── Parallel download and decode of missing .bin assets ──
                from concurrent.futures import ThreadPoolExecutor

                def download_item(item):
                    # Delegate to the module-level helper so a corrupt/stale
                    # .bin is re-downloaded and decoded in a single pass
                    # (see _fetch_gallery_asset for the recovery contract).
                    file_id = item.get("FileId")
                    if file_id:
                        GallerySyncMixin._fetch_gallery_asset(cache_dir, file_id)

                with ThreadPoolExecutor(max_workers=10) as executor:
                    list(executor.map(download_item, file_list))
                
                # ── Sequential base64 encoding and progressive streaming ──
                results = []
                for idx, item in enumerate(file_list):
                    file_id = item.get("FileId")
                    preview_url = ""
                    
                    if file_id:
                        safe_filename = file_id.replace("/", "_")
                        cache_file_item = cache_dir / safe_filename
                        
                        for ext in [".gif", ".png", ".jpg", ".jpeg"]:
                            possible_file = cache_file_item.with_suffix(ext)
                            if possible_file.exists():
                                try:
                                    mime_type = "image/gif" if ext == ".gif" else ("image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png")
                                    img_data = possible_file.read_bytes()
                                    b64_str = base64.b64encode(img_data).decode("utf-8")
                                    preview_url = f"data:{mime_type};base64,{b64_str}"
                                except Exception as b64_err:
                                    logger.warning(f"Failed to base64 encode {possible_file.name}: {b64_err}")
                                break
                    
                    art_item = {
                        "name": item.get("FileName", "unnamed"),
                        "file_id": file_id,
                        "likes": item.get("LikeCnt", 0),
                        "magic": item.get("FileType", 3),
                        "preview_url": preview_url
                    }
                    results.append(art_item)
                    
                    if self.window:
                        try:
                            item_json = json.dumps(art_item)
                            b64_item_data = base64.b64encode(item_json.encode("utf-8")).decode("utf-8")
                            js_code = f"if (window.onGalleryItemLoaded) {{ window.onGalleryItemLoaded({classify}, {target_size}, {idx}, {len(file_list)}, '{b64_item_data}', {file_sort}, {file_size}); }}"
                            self.window.evaluate_js(js_code)
                        except Exception as js_err:
                            logger.warning(f"Failed to send progressive gallery item: {js_err}")
                
                cache_file = Path.home() / ".config" / "divoom-control" / "gallery_cache.json"
                try:
                    # Atomic (temp+fsync+rename): a crash/disk-full mid-write must
                    # not truncate the offline cache — a partial file makes every
                    # json.loads consumer fall back to an empty gallery (A1).
                    atomic_write_text(cache_file, json.dumps(results, indent=2))
                    logger.info(f"Gallery Cache: Successfully saved {len(results)} gallery items offline.")
                except Exception as cache_err:
                    logger.warning(f"Failed to save gallery cache: {cache_err}")
                    
                if self.window:
                    js_data = json.dumps(results)
                    b64_js_data = base64.b64encode(js_data.encode("utf-8")).decode("utf-8")
                    js_code = f"if (window.onGalleryBackgroundFetched) {{ window.onGalleryBackgroundFetched({classify}, {target_size}, '{b64_js_data}', {file_sort}, {file_size}); }}"
                    self.window.evaluate_js(js_code)
            except Exception as e:
                err_msg = str(e)
                is_expired = "expired" in err_msg.lower() or "token" in err_msg.lower() or "credentials not configured" in err_msg.lower()
                logger.error(f"Background gallery fetch failed permanently: {e}")
                if self.window:
                    try:
                        is_expired_val = "true" if is_expired else "false"
                        js_code = f"if (window.onGalleryFetchError) {{ window.onGalleryFetchError({classify}, {target_size}, {is_expired_val}, {json.dumps(err_msg)}); }}"
                        self.window.evaluate_js(js_code)
                    except Exception as js_err:
                        logger.warning(f"Failed to send gallery fetch error: {js_err}")

        threading.Thread(target=background_fetch_worker, name="DivoomGalleryFetch", daemon=True).start()
        return cached_data

    def batch_sync_artwork(self, artwork_json: str) -> bool:
        """R17 P5 full cutover: the daemon owns the device, so it downloads +
        decodes + resizes + streams the asset against its real device/wall
        (binary never crosses the socket). The GUI just resolves the target
        (single vs. wall) and the single-device size."""
        ok, _err = self._sync_artwork_detailed(artwork_json)
        return ok

    def _sync_artwork_detailed(self, artwork_json: str) -> tuple[bool, str | None]:
        """Core of batch_sync_artwork that keeps the failure REASON, so callers
        like sync_hot_channel can report per-file errors instead of a bare bool."""
        logger.info(f"GUI Action: Batch syncing artwork details: {artwork_json}")
        try:
            art = json.loads(artwork_json)
            file_id = art["file_id"]
            client = self._client()
            if client is None:
                logger.error("Batch sync failed: no daemon available")
                return False, "no daemon available"

            is_wall = (getattr(self, "current_target_mode", "single") == "wall"
                       or (not self.current_divoom and self.wall_slots))
            if is_wall:
                if not self._rebuild_wall_instance():
                    return False, "wall not configured"
                reply = client.sync_artwork(file_id, target="wall")
            elif self.current_divoom and (self.current_divoom.is_connected
                                          or getattr(self.current_divoom, "lan", None)):
                size = self._active_device_size() if hasattr(self, "_active_device_size") else 16
                reply = client.sync_artwork(file_id, default_size=int(size), target="device")
            else:
                return False, "no connected device"
            if reply.get("success"):
                return True, None
            return False, str(reply.get("error", "unknown daemon error"))
        except Exception as e:
            logger.error(f"Batch sync failed: {e}")
            return False, str(e)


    def get_sync_candidates(self) -> str:
        from divoom_lib import hotchannel_config
        selected = set(hotchannel_config.get_targets())
        cfg = hotchannel_config.load_config()
        seen, candidates = set(), []

        def add(address, name):
            if not address or address in seen:
                return
            seen.add(address)
            candidates.append({
                "address": address,
                "name": name or "Divoom Screen",
                "selected": address in selected,
                "gallery_style": hotchannel_config.get_device_classify(cfg, address),
                "device_name": name or "Divoom Screen",
            })

        try:
            cache = Path.home() / ".config" / "divoom-control" / "discovered_devices.json"
            if cache.exists():
                for d in json.loads(cache.read_text(encoding="utf-8")):
                    add(d.get("address"), d.get("name"))
        except Exception:
            pass
        for mac, slot in (getattr(self, "wall_slots", {}) or {}).items():
            add(mac, (slot or {}).get("name"))
        for addr in selected:
            add(addr, None)
        return json.dumps(candidates)

    def set_sync_targets(self, targets_json=None, galleries_json=None) -> bool:
        """Accept JSON-string targets list and optional JSON-string galleries dict."""
        from divoom_lib import hotchannel_config
        try:
            addrs = []
            if targets_json and isinstance(targets_json, str):
                parsed = json.loads(targets_json)
                if isinstance(parsed, list):
                    addrs = [str(a) for a in parsed]
            ok = hotchannel_config.set_targets(addrs)
            if galleries_json and isinstance(galleries_json, str):
                parsed = json.loads(galleries_json)
                if isinstance(parsed, dict):
                    hotchannel_config.set_device_galleries(parsed)
            return ok
        except Exception as e:
            logger.error(f"set_sync_targets failed: {e}")
            return False

    def get_hot_channel_config(self) -> str:
        from divoom_lib import hotchannel_config
        return json.dumps(hotchannel_config.load_config())

    def save_hot_channel_config(self, *config, **kwargs) -> bool:
        from divoom_lib import hotchannel_config
        try:
            cfg = self._coerce_dict(config, kwargs)
            return hotchannel_config.save_config(cfg)
        except Exception as e:
            logger.error(f"save_hot_channel_config failed: {e}")
            return False

    # ── R32 §A2: per-device preferred gallery style ───────────────────────
    # Stored in config.ini under a [gallery] section, keyed by device address
    # (or "default" when no device is given). The Monthly Best gallery loads
    # the active device's preferred style on startup, and the Routines card
    # lets the user set a style per device.
    @staticmethod
    def _gallery_config_path() -> Path:
        return Path.home() / ".config" / "divoom-control" / "config.ini"

    @staticmethod
    def _gallery_style_key(address: str) -> str:
        return (str(address or "").strip() or "default")

    def get_gallery_style(self, address: str = "") -> int:
        import configparser
        key = self._gallery_style_key(address)
        try:
            path = self._gallery_config_path()
            if path.exists():
                cfg = configparser.ConfigParser()
                cfg.read(path)
                if cfg.has_option("gallery", key):
                    return int(cfg.get("gallery", key))
                # Fall back to the global default style if the device has none.
                if key != "default" and cfg.has_option("gallery", "default"):
                    return int(cfg.get("gallery", "default"))
        except Exception as e:
            logger.warning(f"get_gallery_style failed: {e}")
        return 18  # "Recommend"

    def set_gallery_style(self, address: str = "", classify: int = 18) -> bool:
        import configparser
        key = self._gallery_style_key(address)
        try:
            path = self._gallery_config_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            cfg = configparser.ConfigParser()
            if path.exists():
                cfg.read(path)
            if "gallery" not in cfg:
                cfg["gallery"] = {}
            cfg["gallery"][key] = str(int(classify))
            atomic_write_config(path, cfg, mode=0o600)  # config.ini holds creds
            return True
        except Exception as e:
            logger.warning(f"set_gallery_style failed: {e}")
            return False

    def get_gallery_filter(self) -> str:
        """Return current sort + file_size preferences as JSON."""
        import configparser
        try:
            path = self._gallery_config_path()
            if path.exists():
                cfg = configparser.ConfigParser()
                cfg.read(path)
                sort = int(cfg.get("gallery", "gallery_sort", fallback="1"))
                file_size = int(cfg.get("gallery", "gallery_file_size", fallback="0"))
                return json.dumps({"sort": sort, "file_size": file_size})
        except Exception as e:
            logger.warning(f"get_gallery_filter failed: {e}")
        return json.dumps({"sort": 1, "file_size": 0})

    def set_gallery_filter(self, sort: int = 1, file_size: int = 0) -> bool:
        import configparser
        try:
            path = self._gallery_config_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            cfg = configparser.ConfigParser()
            if path.exists():
                cfg.read(path)
            if "gallery" not in cfg:
                cfg["gallery"] = {}
            cfg["gallery"]["gallery_sort"] = str(int(sort))
            cfg["gallery"]["gallery_file_size"] = str(int(file_size))
            atomic_write_config(path, cfg, mode=0o600)  # config.ini holds creds
            return True
        except Exception as e:
            logger.warning(f"set_gallery_filter failed: {e}")
            return False


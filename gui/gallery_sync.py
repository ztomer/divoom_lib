# gui/gallery_sync.py

import json
import logging
import base64
import urllib.request
import threading
from pathlib import Path
from divoom_lib import divoom_auth
import media_decoder

logger = logging.getLogger("divoom_gui")

class GallerySyncMixin:
    """Mixin for cloud-voted gallery fetching and hot-channel schedule orchestration."""
    def fetch_gallery(self, classify: int, target_size: int = 16) -> str:
        logger.info(f"GUI Action: Fetching gallery classify={classify} target_size={target_size}...")
        
        cached_data = "[]"
        cache_file = Path.home() / ".config" / "divoom-control" / "gallery_cache.json"
        if cache_file.exists():
            try:
                cached_data = cache_file.read_text(encoding="utf-8")
                logger.info(f"Gallery: Loaded {len(json.loads(cached_data))} items immediately from cache.")
            except Exception as ce:
                logger.warning(f"Failed to read gallery cache: {ce}")

        def background_fetch_worker():
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
                        return

                    self.cached_creds = divoom_auth.get_credentials()
                    
                file_size_bitmask = 1
                if target_size == 32:
                    file_size_bitmask = 2
                elif target_size == 64:
                    file_size_bitmask = 4
                    
                body = {
                    "Command": "GetCategoryFileListV2",
                    "Token": self.cached_creds.token,
                    "UserId": self.cached_creds.user_id,
                    "DeviceId": self.device_id,
                    "Classify": classify,
                    "FileSort": 1,
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
                    file_list = data.get("FileList", [])
                    
                    cache_dir = Path.home() / ".config" / "divoom-control" / "cache_gallery"
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    
                    results = []
                    for item in file_list:
                        file_id = item.get("FileId")
                        preview_url = ""
                        
                        if file_id:
                            safe_filename = file_id.replace("/", "_")
                            cache_file_item = cache_dir / safe_filename
                            
                            has_preview = any(cache_file_item.with_suffix(ext).exists() for ext in [".gif", ".png", ".jpg", ".jpeg"])
                            cache_file_bin = cache_file_item.with_suffix(".bin")
                            
                            if not has_preview:
                                try:
                                    raw_bytes = None
                                    if cache_file_bin.exists():
                                        raw_bytes = cache_file_bin.read_bytes()
                                    else:
                                        dl_url = f"https://fin.divoom-gz.com/{file_id}"
                                        req_dl = urllib.request.Request(dl_url, headers={"User-Agent": "okhttp/4.12.0"})
                                        with urllib.request.urlopen(req_dl, timeout=5) as dl_resp:
                                            raw_bytes = dl_resp.read()
                                    
                                    if raw_bytes:
                                        extracted = media_decoder.extract_image_from_magic_43(raw_bytes)
                                        if extracted:
                                            img_bytes, ext = extracted
                                            cache_file_item.with_suffix(ext).write_bytes(img_bytes)
                                        elif raw_bytes.startswith(b"GIF89a") or raw_bytes.startswith(b"GIF87a"):
                                            cache_file_item.with_suffix(".gif").write_bytes(raw_bytes)
                                        elif raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                                            cache_file_item.with_suffix(".png").write_bytes(raw_bytes)
                                        elif raw_bytes.startswith(b"\xff\xd8"):
                                            cache_file_item.with_suffix(".jpg").write_bytes(raw_bytes)
                                        else:
                                            if not cache_file_bin.exists():
                                                cache_file_bin.write_bytes(raw_bytes)
                                            media_decoder.decode_and_save_preview(raw_bytes, cache_file_item.with_suffix(".png"))
                                except Exception as dl_err:
                                    logger.warning(f"Failed to cache preview for {file_id}: {dl_err}")
                            
                            for ext in [".gif", ".png", ".jpg"]:
                                possible_file = cache_file_item.with_suffix(ext)
                                if possible_file.exists():
                                    try:
                                        mime_type = "image/gif" if ext == ".gif" else ("image/jpeg" if ext == ".jpg" else "image/png")
                                        img_data = possible_file.read_bytes()
                                        b64_str = base64.b64encode(img_data).decode("utf-8")
                                        preview_url = f"data:{mime_type};base64,{b64_str}"
                                    except Exception as b64_err:
                                        logger.warning(f"Failed to base64 encode {possible_file.name}: {b64_err}")
                                    break
                        
                        results.append({
                            "name": item.get("FileName", "unnamed"),
                            "file_id": file_id,
                            "likes": item.get("LikeCnt", 0),
                            "magic": item.get("FileType", 3),
                            "preview_url": preview_url
                        })
                    
                    try:
                        cache_file.parent.mkdir(parents=True, exist_ok=True)
                        cache_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
                        logger.info(f"Gallery Cache: Successfully saved {len(results)} gallery items offline.")
                    except Exception as cache_err:
                        logger.warning(f"Failed to save gallery cache: {cache_err}")
                        
                    if self.window:
                        js_data = json.dumps(results)
                        b64_js_data = base64.b64encode(js_data.encode("utf-8")).decode("utf-8")
                        js_code = f"if (window.onGalleryBackgroundFetched) {{ window.onGalleryBackgroundFetched({classify}, {target_size}, '{b64_js_data}'); }}"
                        self.window.evaluate_js(js_code)
            except Exception as e:
                logger.error(f"Background gallery fetch failed: {e}")

        threading.Thread(target=background_fetch_worker, name="DivoomGalleryFetch", daemon=True).start()
        return cached_data

    def batch_sync_artwork(self, artwork_json: str) -> bool:
        logger.info(f"GUI Action: Batch syncing artwork details: {artwork_json}")
        try:
            art = json.loads(artwork_json)
            file_id = art["file_id"]
            
            logger.info(f"Downloading gallery asset from CDN: {file_id}...")
            dl_url = f"https://fin.divoom-gz.com/{file_id}"
            d_req = urllib.request.Request(dl_url, headers={"User-Agent": "okhttp/4.12.0"})
            
            with urllib.request.urlopen(d_req, timeout=10) as d_resp:
                file_bytes = d_resp.read()
                if len(file_bytes) < 4:
                    return False
                
                targets = []
                if getattr(self, "current_target_mode", "single") == "wall" or (not self.current_divoom and self.wall_slots):
                    if not self._rebuild_wall_instance():
                        return False
                    targets = [d for d, _, _, _, _, _ in self.wall_instance.devices]
                elif self.current_divoom and (self.current_divoom.is_connected or getattr(self.current_divoom, "lan", None) is not None):
                    targets = [self.current_divoom]
                else:
                    return False
                    
                extracted_gif = media_decoder.extract_gif_from_magic_43(file_bytes)
                is_gif = False
                gif_data = None
                
                if extracted_gif:
                    is_gif = True
                    gif_data = extracted_gif
                elif file_bytes.startswith(b"GIF89a") or file_bytes.startswith(b"GIF87a"):
                    is_gif = True
                    gif_data = file_bytes
                
                async def run_sync():
                    import asyncio
                    sync_tasks = []
                    for divoom in targets:
                        if is_gif:
                            target_size = self._get_device_size(divoom._conn.mac)
                            temp_dir = Path(__file__).parent.parent / "scratch"
                            temp_dir.mkdir(parents=True, exist_ok=True)
                            
                            temp_input = temp_dir / f"sync_in_{divoom._conn.mac}.gif"
                            temp_input.write_bytes(gif_data)
                            
                            temp_output = temp_dir / f"sync_out_{divoom._conn.mac}.gif"
                            
                            try:
                                from PIL import Image
                                with Image.open(temp_input) as img:
                                    frames = []
                                    durations = []
                                    for frame_idx in range(img.n_frames):
                                        img.seek(frame_idx)
                                        resized_frame = img.resize((target_size, target_size), Image.Resampling.NEAREST)
                                        frames.append(resized_frame.convert("RGB"))
                                        durations.append(img.info.get("duration", 100))
                                    
                                    frames[0].save(
                                        temp_output,
                                        save_all=True,
                                        append_images=frames[1:],
                                        duration=durations,
                                        loop=0
                                    )
                                logger.info(f"Sync: Resized GIF to {target_size}x{target_size} for {divoom._conn.mac}")
                                sync_tasks.append(divoom.display.show_image(str(temp_output)))
                            except Exception as resize_err:
                                logger.error(f"Failed to resize GIF: {resize_err}")
                                sync_tasks.append(divoom.display.show_image(str(temp_input)))
                        else:
                            from divoom_lib.monthly_best_daemon import stream_raw_bin_payload
                            sync_tasks.append(stream_raw_bin_payload(divoom, file_bytes))
                            
                    results = await asyncio.gather(*sync_tasks, return_exceptions=True)
                    return all(res is True for res in results)
                    
                return self._run_async(run_sync())
        except Exception as e:
            logger.error(f"Batch sync failed: {e}")
            return False

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

    def get_sync_candidates(self) -> str:
        from divoom_lib import hotchannel_config
        selected = set(hotchannel_config.get_targets())
        seen, candidates = set(), []

        def add(address, name):
            if not address or address in seen:
                return
            seen.add(address)
            candidates.append({"address": address, "name": name or "Divoom Screen",
                               "selected": address in selected})

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

    def set_sync_targets(self, *addresses, **kwargs) -> bool:
        from divoom_lib import hotchannel_config
        try:
            addrs = self._coerce_list(addresses, kwargs, "targets")
            return hotchannel_config.set_targets([str(a) for a in addrs])
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

    def sync_hot_channel(self, *file_ids_arg, **kwargs) -> str:
        file_ids = self._coerce_list(file_ids_arg, kwargs, "file_ids")
        synced, failed = [], []
        for fid in file_ids:
            ok = False
            try:
                ok = self.batch_sync_artwork(json.dumps({"file_id": fid}))
            except Exception as e:
                logger.error(f"hot-channel sync of {fid} failed: {e}")
            (synced if ok else failed).append(fid)
        return json.dumps({"ok": len(failed) == 0, "synced": synced, "failed": failed})

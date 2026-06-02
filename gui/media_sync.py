import json
import asyncio
import base64
import logging
import urllib.request
import struct
import subprocess
import threading
import time
from pathlib import Path
from divoom_lib import divoom_auth
from divoom_lib.utils import media_source

logger = logging.getLogger("divoom_gui")

class MediaSyncMixin:
    def _get_device_size(self, address: str) -> int:
        for d in self.discovered_list:
            if d.get("address") == address:
                name = d.get("name", "").lower()
                if "64" in name:
                    return 64
                return 16
        return 16

    def _extract_image_from_magic_43(self, file_data: bytes) -> tuple[bytes, str] | None:
        if len(file_data) < 10 or file_data[0] != 43:
            return None
        try:
            text_len = struct.unpack("<I", file_data[6:10])[0]
            text_start = 10
            text_end = text_start + text_len
            
            img_len_offset = text_end
            if len(file_data) < img_len_offset + 4:
                return None
                
            img_len = struct.unpack("<I", file_data[img_len_offset:img_len_offset+4])[0]
            img_start = img_len_offset + 4
            img_end = img_start + img_len
            
            if img_end > len(file_data):
                img_end = len(file_data)
                
            img_data = file_data[img_start:img_end]
            if img_data.startswith(b"GIF89a") or img_data.startswith(b"GIF87a"):
                return img_data, ".gif"
            elif img_data.startswith(b"\x89PNG\r\n\x1a\n"):
                return img_data, ".png"
            elif img_data.startswith(b"\xff\xd8"):
                return img_data, ".jpg"
        except Exception as e:
            logger.warning(f"Failed to extract image from Magic 43: {e}")
        return None

    def _extract_gif_from_magic_43(self, file_data: bytes) -> bytes | None:
        res = self._extract_image_from_magic_43(file_data)
        if res and res[1] == ".gif":
            return res[0]
        return None

    def fetch_gallery(self, classify: int, target_size: int = 16) -> str:
        """
        Fetches popular community gallery artworks and caches previews locally.
        Filters by active connected device grid size to prevent hardware scaling mismatch.
        """
        logger.info(f"GUI Action: Fetching gallery classify={classify} target_size={target_size}...")
        try:
            if not self.cached_creds:
                # Check config.ini first to ensure credentials are stored
                import configparser
                config_file = Path.home() / ".config" / "divoom-control" / "config.ini"
                email, password = "", ""
                if config_file.exists():
                    cfg = configparser.ConfigParser()
                    cfg.read(config_file)
                    email = cfg.get("divoom", "email", fallback="")
                    password = cfg.get("divoom", "password", fallback="")
                
                if not email or not password:
                    return json.dumps({"error": "Divoom account credentials are not configured. Please enter your email and password in the Divoom tab inside Settings."})

                self.cached_creds = divoom_auth.get_credentials()
                
            # FileSize bitmask: 1=16px, 2=32px, 4=64px
            file_size_bitmask = 127
            if target_size == 16:
                file_size_bitmask = 1
            elif target_size == 32:
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
                
                cache_dir = Path(__file__).parent / "web_ui" / "assets" / "cache_gallery"
                cache_dir.mkdir(parents=True, exist_ok=True)
                
                results = []
                for item in file_list:
                    file_id = item.get("FileId")
                    pixel_amb_id = item.get("PixelAmbId")
                    preview_url = ""
                    
                    if file_id:
                        safe_filename = file_id.replace("/", "_")
                        cache_file = cache_dir / safe_filename
                        
                        has_preview = any(cache_file.with_suffix(ext).exists() for ext in [".gif", ".png", ".jpg", ".jpeg"])
                        cache_file_bin = cache_file.with_suffix(".bin")
                        
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
                                    extracted = self._extract_image_from_magic_43(raw_bytes)
                                    if extracted:
                                        img_bytes, ext = extracted
                                        cache_file.with_suffix(ext).write_bytes(img_bytes)
                                        logger.info(f"Gallery Cache: Extracted Magic 43 {ext[1:].upper()} to {cache_file.name}")
                                    elif raw_bytes.startswith(b"GIF89a") or raw_bytes.startswith(b"GIF87a"):
                                        cache_file.with_suffix(".gif").write_bytes(raw_bytes)
                                        logger.info(f"Gallery Cache: Saved standard GIF to {cache_file.name}")
                                    elif raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                                        cache_file.with_suffix(".png").write_bytes(raw_bytes)
                                        logger.info(f"Gallery Cache: Saved standard PNG to {cache_file.name}")
                                    elif raw_bytes.startswith(b"\xff\xd8"):
                                        cache_file.with_suffix(".jpg").write_bytes(raw_bytes)
                                        logger.info(f"Gallery Cache: Saved standard JPEG to {cache_file.name}")
                                    else:
                                        if not cache_file_bin.exists():
                                            cache_file_bin.write_bytes(raw_bytes)
                                        self._decode_and_save_preview(raw_bytes, cache_file.with_suffix(".png"))
                            except Exception as dl_err:
                                logger.warning(f"Failed to cache preview for {file_id}: {dl_err}")
                        
                        for ext in [".gif", ".png", ".jpg"]:
                            possible_file = cache_file.with_suffix(ext)
                            if possible_file.exists():
                                preview_url = f"assets/cache_gallery/{possible_file.name}"
                                break
                    
                    results.append({
                        "name": item.get("FileName", "unnamed"),
                        "file_id": file_id,
                        "likes": item.get("LikeCnt", 0),
                        "magic": item.get("FileType", 3),
                        "preview_url": preview_url
                    })
                
                try:
                    gallery_cache = Path.home() / ".config" / "divoom-control" / "gallery_cache.json"
                    gallery_cache.parent.mkdir(parents=True, exist_ok=True)
                    gallery_cache.write_text(json.dumps(results, indent=2), encoding="utf-8")
                    logger.info(f"Gallery Cache: Successfully saved {len(results)} gallery items offline.")
                except Exception as cache_err:
                    logger.warning(f"Failed to save gallery cache: {cache_err}")
                    
                return json.dumps(results)
        except Exception as e:
            logger.error(f"Gallery fetch failed: {e}")
            try:
                gallery_cache = Path.home() / ".config" / "divoom-control" / "gallery_cache.json"
                if gallery_cache.exists():
                    logger.warning("Gallery: Offline fallback loaded from gallery_cache.json")
                    return gallery_cache.read_text(encoding="utf-8")
            except Exception as cache_err:
                logger.error(f"Failed to load gallery cache fallback: {cache_err}")
            return json.dumps({"error": str(e)})

    def batch_sync_artwork(self, artwork_json: str) -> bool:
        """Syncs the selected artwork to all active devices in parallel with automatic PIL resizing."""
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
                    
                extracted_gif = self._extract_gif_from_magic_43(file_bytes)
                is_gif = False
                gif_data = None
                
                if extracted_gif:
                    is_gif = True
                    gif_data = extracted_gif
                elif file_bytes.startswith(b"GIF89a") or file_bytes.startswith(b"GIF87a"):
                    is_gif = True
                    gif_data = file_bytes
                
                async def run_sync():
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

    # ── Monthly Best "hot channel" (request area 4) ────────────────────────

    @staticmethod
    def _coerce_list(args, kwargs, key) -> list:
        """Normalize varied call conventions into a list.

        Accepts: a single JSON string (pywebview bridge), a single native list
        (REST single-arg), spread positional values (REST array body), or a
        ``key=[...]`` kwarg (REST object body)."""
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
        """Normalize into a dict: single JSON string / native dict, or kwargs."""
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
        """List devices selectable as hot-channel sync targets, marking which
        are currently selected (4.c). Combines discovered + wall + connected."""
        from divoom_lib import hotchannel_config
        selected = set(hotchannel_config.get_targets())
        seen, candidates = set(), []

        def add(address, name):
            if not address or address in seen:
                return
            seen.add(address)
            candidates.append({"address": address, "name": name or "Divoom Screen",
                               "selected": address in selected})

        # Discovered devices cache
        try:
            cache = Path.home() / ".config" / "divoom-control" / "discovered_devices.json"
            if cache.exists():
                for d in json.loads(cache.read_text(encoding="utf-8")):
                    add(d.get("address"), d.get("name"))
        except Exception:
            pass
        # Wall slots
        for mac, slot in (getattr(self, "wall_slots", {}) or {}).items():
            add(mac, (slot or {}).get("name"))
        # Any selected target not otherwise listed (keep it visible/removable)
        for addr in selected:
            add(addr, None)
        return json.dumps(candidates)

    def set_sync_targets(self, *addresses, **kwargs) -> bool:
        """Persist the selected hot-channel target devices (4.c).

        Accepts a JSON-string array (pywebview), a native list, or spread
        addresses (REST)."""
        from divoom_lib import hotchannel_config
        try:
            addrs = self._coerce_list(addresses, kwargs, "targets")
            return hotchannel_config.set_targets([str(a) for a in addrs])
        except Exception as e:
            logger.error(f"set_sync_targets failed: {e}")
            return False

    def get_hot_channel_config(self) -> str:
        """Return the persisted hot-channel schedule + targets (4.d)."""
        from divoom_lib import hotchannel_config
        return json.dumps(hotchannel_config.load_config())

    def save_hot_channel_config(self, *config, **kwargs) -> bool:
        """Persist hot-channel schedule (enabled/interval/classify/targets) (4.d).

        Accepts a JSON-string object (pywebview), a native dict, or kwargs (REST)."""
        from divoom_lib import hotchannel_config
        try:
            cfg = self._coerce_dict(config, kwargs)
            return hotchannel_config.save_config(cfg)
        except Exception as e:
            logger.error(f"save_hot_channel_config failed: {e}")
            return False

    def sync_hot_channel(self, *file_ids_arg, **kwargs) -> str:
        """Sync MULTIPLE monthly-best images to all current targets at once (4.b).

        Replaces the one-image-at-a-time flow: pushes each provided artwork to
        the resolved target set (wall = every wall device). Returns a summary.
        Accepts a JSON-string array, native list, or spread file ids."""
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

    # ── System monitor widget (area 7: ported from Pixoo64 over BLE) ───────

    def get_system_stats_preview(self, size: int = 0) -> str:
        """Render a CPU/RAM monitor frame and return it as a data URL (5.d-style
        on-device preview, no device needed)."""
        try:
            stats = media_source.get_system_stats()
            sz = int(size) if size and int(size) > 0 else self._active_device_size()
            frame_path = media_source.render_system_stats_frame(stats, size=sz)
            return json.dumps({
                "ok": True, "size": sz, "stats": stats,
                "preview": self._frame_to_data_url(frame_path),
            })
        except Exception as e:
            logger.error(f"get_system_stats_preview failed: {e}")
            return json.dumps({"ok": False, "error": str(e)})

    def apply_system_stats(self) -> str:
        """Render live CPU/RAM and push it to the active screen(s)."""
        try:
            stats = media_source.get_system_stats()
            if not self._has_push_target():
                return json.dumps({"success": False, "error": "No device connected", "stats": stats})
            size = self._active_device_size()
            frame_path = media_source.render_system_stats_frame(stats, size=size)
            res = self._push_frame(frame_path, size)
            return json.dumps({
                "success": res, "stats": stats,
                "preview": self._frame_to_data_url(frame_path),
            })
        except Exception as e:
            logger.error(f"apply_system_stats failed: {e}")
            return json.dumps({"success": False, "error": str(e)})

    def _music_sync_loop(self):
        """Background thread polling macOS active playback and streaming artwork."""
        last_track = None
        last_artist = None
        while self.music_sync_active:
            try:
                track_info = media_source.get_current_playing_track()
                if track_info:
                    track = track_info.get("track")
                    artist = track_info.get("artist")
                    source = track_info.get("source")
                    
                    if track != last_track or artist != last_artist:
                        logger.info(f"Music Sync: New track: {track} by {artist} ({source})")
                        last_track = track
                        last_artist = artist
                        
                        art_url = media_source.fetch_album_art_url(track, artist)
                        if art_url:
                            size = self._active_device_size()
                            out_path = media_source.render_and_downsample_artwork(art_url, size=size)
                            preview_url = ""
                            if out_path and out_path.exists():
                                preview_url = self._frame_to_data_url(out_path)
                                logger.info(f"Music Sync: Push cover art frame ({size}px): {out_path}")
                                try:
                                    # Use the shared push (wall or single BLE/LAN) and
                                    # real device size — fixes art not showing (5.c).
                                    if not self._push_frame(out_path, size):
                                        logger.warning("Music Sync: no connected target for cover art")
                                except Exception as e:
                                    logger.error(f"Failed to stream artwork: {e}")

                            self.current_track_cache = {
                                "preview": preview_url,
                                "track": track,
                                "artist": artist,
                                "source": source,
                                "artwork_url": art_url
                            }
                        else:
                            self.current_track_cache = {
                                "track": track,
                                "artist": artist,
                                "source": source,
                                "artwork_url": ""
                            }
                else:
                    self.current_track_cache = None
            except Exception as e:
                logger.error(f"Music sync error: {e}")
            time.sleep(3.0)

    def toggle_music_sync(self, enable: bool) -> bool:
        logger.info(f"GUI Action: Toggle music sync to {enable}")
        self.music_sync_active = enable
        if enable:
            if not self.music_thread or not self.music_thread.is_alive():
                self.music_thread = threading.Thread(target=self._music_sync_loop, daemon=True)
                self.music_thread.start()
        return True

    def get_current_track_info(self) -> str:
        if self.current_track_cache:
            return json.dumps(self.current_track_cache)
        return json.dumps({})

    # ── Live widgets: device-size helpers, previews, tickers (area 5) ──────

    def _active_device_size(self, default: int = 16) -> int:
        """Pixel matrix size of the active target (5.a/5.c: stop hardcoding 16)."""
        try:
            if self.wall_slots:
                sizes = [s.get("size", default) for s in self.wall_slots.values() if isinstance(s, dict)]
                return min(sizes) if sizes else default
            dev = self.current_divoom
            mac = getattr(getattr(dev, "_conn", None), "mac", None) or getattr(dev, "mac", None)
            if mac:
                return self._get_device_size(mac)
        except Exception:
            pass
        return default

    def _has_push_target(self) -> bool:
        dev = self.current_divoom
        return bool(self.wall_slots) or bool(
            dev and (getattr(dev, "is_connected", False) or getattr(dev, "lan", None) is not None))

    def _push_frame(self, frame_path, size: int) -> bool:
        """Push a rendered frame to the wall or the single active (BLE/LAN) device."""
        if self.wall_slots:
            if self._rebuild_wall_instance(size):
                return bool(self._run_async(self.wall_instance.show_image(str(frame_path))))
            return False
        dev = self.current_divoom
        if dev and (getattr(dev, "is_connected", False) or getattr(dev, "lan", None) is not None):
            return bool(self._run_async(dev.display.show_image(str(frame_path))))
        return False

    @staticmethod
    def _frame_to_data_url(frame_path) -> str:
        """Base64 data URL for a rendered PNG so the UI can show the exact frame."""
        try:
            data = Path(frame_path).read_bytes()
            return "data:image/png;base64," + base64.b64encode(data).decode("ascii")
        except Exception:
            return ""

    def get_ticker_preview(self, symbol: str, size: int = 0) -> str:
        """Render a ticker frame and return it as a data URL (no device needed),
        so the UI can show a live on-device preview at the target matrix (5.d)."""
        try:
            data = media_source.fetch_stock_ticker(symbol)
            if not data:
                return json.dumps({"ok": False, "error": "no data"})
            sz = int(size) if size and int(size) > 0 else self._active_device_size()
            frame_path = media_source.render_stock_ticker_frame(symbol, data, size=sz)
            return json.dumps({
                "ok": True, "size": sz, "symbol": symbol,
                "preview": self._frame_to_data_url(frame_path),
                "price": data["price"], "change": data["change"], "pct_change": data["pct_change"],
            })
        except Exception as e:
            logger.error(f"get_ticker_preview failed: {e}")
            return json.dumps({"ok": False, "error": str(e)})

    def apply_stock_ticker(self, symbol: str) -> str:
        logger.info(f"GUI Action: Applying stock ticker for {symbol}...")
        try:
            data = media_source.fetch_stock_ticker(symbol)
            if not data:
                return json.dumps({"success": False, "error": "Could not fetch ticker data"})
            if not self._has_push_target():
                return json.dumps({"success": False, "error": "No device connected"})

            size = self._active_device_size()
            frame_path = media_source.render_stock_ticker_frame(symbol, data, size=size)
            res = self._push_frame(frame_path, size)

            return json.dumps({
                "success": res,
                "preview": self._frame_to_data_url(frame_path),
                "price": data["price"],
                "change": data["change"],
                "pct_change": data["pct_change"],
            })
        except Exception as e:
            logger.error(f"Failed to apply stock ticker: {e}")
            return json.dumps({"success": False, "error": str(e)})

    # ── Multiple tickers (5.e) ─────────────────────────────────────────────

    def _tickers_path(self):
        return Path.home() / ".config" / "divoom-control" / "tickers.json"

    def get_tickers(self) -> str:
        """Return the saved ticker symbols, seeding from macOS Stocks on first use."""
        path = self._tickers_path()
        if path.exists():
            try:
                return json.dumps(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                pass
        seed = self._seed_tickers_from_macos()
        self.set_tickers(json.dumps(seed))
        return json.dumps(seed)

    def set_tickers(self, *symbols_arg, **kwargs) -> bool:
        try:
            symbols = self._coerce_list(symbols_arg, kwargs, "tickers")
            # de-dupe, upper-case, drop blanks, preserve order
            seen, clean = set(), []
            for s in symbols:
                s = str(s).strip().upper()
                if s and s not in seen:
                    seen.add(s)
                    clean.append(s)
            path = self._tickers_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(clean, indent=2), encoding="utf-8")
            return True
        except Exception as e:
            logger.error(f"set_tickers failed: {e}")
            return False

    @staticmethod
    def _seed_tickers_from_macos() -> list:
        """Best-effort seed from the macOS Stocks app watchlist; falls back to a
        sensible default list when it can't be read (sandboxed / not present)."""
        default = ["AAPL", "GOOGL", "MSFT", "TSLA", "BTC-USD", "ETH-USD"]
        try:
            # Stocks stores its symbols in a preferences plist; read it via
            # `defaults` and scrape ticker-like tokens. Quietly fall back.
            out = subprocess.run(
                ["defaults", "read", "com.apple.stocks"],
                capture_output=True, text=True, timeout=4)
            import re
            syms = re.findall(r'"?symbol"?\s*=\s*"?([A-Z][A-Z0-9.\-]{0,9})"?', out.stdout)
            cleaned = []
            for s in syms:
                s = s.upper()
                if s and s not in cleaned:
                    cleaned.append(s)
            return cleaned or default
        except Exception:
            return default

    def _decode_and_save_preview(self, raw_bytes: bytes, cache_file_png: Path) -> bool:
        try:
            from Crypto.Cipher import AES
            from PIL import Image
            import struct
            
            magic = raw_bytes[0]
            key = '78hrey23y28ogs89'.encode('utf-8')
            iv = '1234567890123456'.encode('utf-8')
            
            def decrypt_aes(data):
                return AES.new(key, AES.MODE_CBC, iv).decrypt(data)

            if magic == 9:
                encrypted = raw_bytes[4:]
                decrypted = decrypt_aes(encrypted)
                total_frames = raw_bytes[1]
                speed = struct.unpack('>H', raw_bytes[2:4])[0]
                
                frames = []
                for f_idx in range(total_frames):
                    start = f_idx * 768
                    end = start + 768
                    if end > len(decrypted):
                        break
                    frame_data = bytes(decrypted[start:end])
                    img = Image.frombytes("RGB", (16, 16), frame_data)
                    img_resized = img.resize((128, 128), Image.Resampling.NEAREST)
                    frames.append(img_resized)
                
                if frames:
                    if len(frames) > 1:
                        cache_file_gif = cache_file_png.with_suffix(".gif")
                        frame_duration = speed if speed >= 10 else 100
                        frames[0].save(
                            cache_file_gif,
                            save_all=True,
                            append_images=frames[1:],
                            duration=frame_duration,
                            loop=0
                        )
                        logger.info(f"Gallery Cache: Decoded Magic 9 animation with {len(frames)} frames to {cache_file_gif.name}")
                    else:
                        frames[0].save(cache_file_png)
                        logger.info(f"Gallery Cache: Decoded Magic 9 static frame to {cache_file_png.name}")
                    return True
                    
            elif magic == 18 or magic == 26:
                import lzallright
                total_frames, speed, row_count, column_count = struct.unpack('>BHBB', raw_bytes[1:6])
                encrypted = raw_bytes[6:]
                decrypted = decrypt_aes(encrypted)
                
                lzo = lzallright.LZOCompressor()
                uncompressed_size = row_count * column_count * 768
                
                frames = []
                pos = 0
                for f_idx in range(total_frames):
                    if pos + 4 > len(decrypted):
                        break
                    frame_size = struct.unpack('>I', decrypted[pos : pos + 4])[0]
                    pos += 4
                    if pos + frame_size > len(decrypted):
                        break
                    compressed_frame = decrypted[pos : pos + frame_size]
                    pos += frame_size
                    
                    try:
                        frame_data = lzo.decompress(compressed_frame, uncompressed_size)
                        img = self._compact_tiles(frame_data, row_count, column_count)
                        img_resized = img.resize((128, 128), Image.Resampling.NEAREST)
                        frames.append(img_resized)
                    except Exception as frame_err:
                        logger.warning(f"Failed to decompress frame {f_idx} for magic {magic}: {frame_err}")
                        break
                
                if frames:
                    if len(frames) > 1:
                        cache_file_gif = cache_file_png.with_suffix(".gif")
                        frame_duration = speed if speed >= 10 else 100
                        frames[0].save(
                            cache_file_gif,
                            save_all=True,
                            append_images=frames[1:],
                            duration=frame_duration,
                            loop=0
                        )
                        logger.info(f"Gallery Cache: Decoded Magic {magic} animation with {len(frames)} frames to {cache_file_gif.name}")
                    else:
                        frames[0].save(cache_file_png)
                        logger.info(f"Gallery Cache: Decoded Magic {magic} static frame to {cache_file_png.name}")
                    return True
        except Exception as e:
            logger.warning(f"Failed to transcode preview for Magic {raw_bytes[0] if raw_bytes else 0}: {e}")
        return False

    def _compact_tiles(self, frame_data: bytes, row_count: int, column_count: int) -> "Image":
        from PIL import Image
        width, height = column_count * 16, row_count * 16
        img = Image.new("RGB", (width, height))
        pixels = img.load()
        pos = 0
        for grid_y in range(row_count):
            for grid_x in range(column_count):
                for y in range(16):
                    for x in range(16):
                        if pos + 3 <= len(frame_data):
                            pixels[grid_x * 16 + x, grid_y * 16 + y] = (frame_data[pos], frame_data[pos+1], frame_data[pos+2])
                            pos += 3
        return img

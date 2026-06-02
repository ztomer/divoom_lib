import json
import asyncio
import logging
import urllib.request
import struct
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
                        
                        has_cached = any(cache_file.with_suffix(ext).exists() for ext in [".gif", ".png", ".jpg", ".jpeg", ".bin"])
                        if not has_cached:
                            try:
                                dl_url = f"https://fin.divoom-gz.com/{file_id}"
                                req_dl = urllib.request.Request(dl_url, headers={"User-Agent": "okhttp/4.12.0"})
                                with urllib.request.urlopen(req_dl, timeout=5) as dl_resp:
                                    raw_bytes = dl_resp.read()
                                    
                                    extracted = self._extract_image_from_magic_43(raw_bytes)
                                    if extracted:
                                        img_bytes, ext = extracted
                                        cache_file = cache_file.with_suffix(ext)
                                        cache_file.write_bytes(img_bytes)
                                        logger.info(f"Gallery Cache: Extracted Magic 43 {ext[1:].upper()} to {cache_file.name}")
                                    elif raw_bytes.startswith(b"GIF89a") or raw_bytes.startswith(b"GIF87a"):
                                        cache_file = cache_file.with_suffix(".gif")
                                        cache_file.write_bytes(raw_bytes)
                                        logger.info(f"Gallery Cache: Saved standard GIF to {cache_file.name}")
                                    elif raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                                        cache_file = cache_file.with_suffix(".png")
                                        cache_file.write_bytes(raw_bytes)
                                        logger.info(f"Gallery Cache: Saved standard PNG to {cache_file.name}")
                                    elif raw_bytes.startswith(b"\xff\xd8"):
                                        cache_file = cache_file.with_suffix(".jpg")
                                        cache_file.write_bytes(raw_bytes)
                                        logger.info(f"Gallery Cache: Saved standard JPEG to {cache_file.name}")
                                    else:
                                        # Also save the raw binary file for streaming if needed
                                        cache_file_bin = cache_file.with_suffix(".bin")
                                        if not cache_file_bin.exists():
                                            cache_file_bin.write_bytes(raw_bytes)
                                        
                                        # Decode the actual first frame as PNG preview
                                        cache_file_png = cache_file.with_suffix(".png")
                                        self._decode_and_save_preview(raw_bytes, cache_file_png)
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
                            size = 16
                            out_path = media_source.render_and_downsample_artwork(art_url, size=size)
                            if out_path and out_path.exists():
                                logger.info(f"Music Sync: Push cover art frame: {out_path}")
                                try:
                                    if self.wall_slots:
                                        if self._rebuild_wall_instance(size):
                                            self._run_async(self.wall_instance.show_image(str(out_path)))
                                    elif self.current_divoom and self.current_divoom.is_connected:
                                        self._run_async(self.current_divoom.display.show_image(str(out_path)))
                                except Exception as e:
                                    logger.error(f"Failed to stream artwork: {e}")
                                    
                            self.current_track_cache = {
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

    def apply_stock_ticker(self, symbol: str) -> str:
        logger.info(f"GUI Action: Applying stock ticker for {symbol}...")
        try:
            data = media_source.fetch_stock_ticker(symbol)
            if not data:
                return json.dumps({"success": False})
                
            size = 16
            frame_path = media_source.render_stock_ticker_frame(symbol, data, size=size)
            
            res = False
            if self.wall_slots:
                if self._rebuild_wall_instance(size):
                    res = self._run_async(self.wall_instance.show_image(str(frame_path)))
            elif self.current_divoom and self.current_divoom.is_connected:
                res = self._run_async(self.current_divoom.display.show_image(str(frame_path)))
                
            return json.dumps({
                "success": res,
                "price": data["price"],
                "change": data["change"],
                "pct_change": data["pct_change"]
            })
        except Exception as e:
            logger.error(f"Failed to apply stock ticker: {e}")
            return json.dumps({"success": False, "error": str(e)})

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
                if len(decrypted) >= 768:
                    img = Image.frombytes("RGB", (16, 16), bytes(decrypted[:768]))
                    img.resize((128, 128), Image.Resampling.NEAREST).save(cache_file_png)
                    logger.info(f"Gallery Cache: Decoded Magic 9 16x16 asset to {cache_file_png.name}")
                    return True
                    
            elif magic == 18 or magic == 26:
                import lzallright
                total_frames, speed, row_count, column_count = struct.unpack('>BHBB', raw_bytes[1:6])
                encrypted = raw_bytes[6:]
                decrypted = decrypt_aes(encrypted)
                
                frame_size = struct.unpack('>I', decrypted[:4])[0]
                compressed_frame = decrypted[4 : 4 + frame_size]
                
                uncompressed_size = row_count * column_count * 768
                lzo = lzallright.LZOCompressor()
                frame_data = lzo.decompress(compressed_frame, uncompressed_size)
                
                img = self._compact_tiles(frame_data, row_count, column_count)
                img.resize((128, 128), Image.Resampling.NEAREST).save(cache_file_png)
                logger.info(f"Gallery Cache: Decoded Magic {magic} asset to {cache_file_png.name}")
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
